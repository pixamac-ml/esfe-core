import json

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from academics.models import AcademicYear
from admissions.models import Candidature
from branches.models import Branch
from notifier.models import NotificationMessage
from formations.models import (
	Cycle,
	Diploma,
	Fee,
	Filiere,
	Programme,
	ProgrammeRequiredDocument,
	ProgrammeYear,
	RequiredDocument,
)


class AdmissionTunnelValidationTests(TestCase):
	def setUp(self):
		self.url = reverse("admissions:admission_tunnel")

		current_year = timezone.now().year
		AcademicYear.objects.create(
			name=f"{current_year}-{current_year + 1}",
			start_date=f"{current_year}-10-01",
			end_date=f"{current_year + 1}-07-31",
			is_active=True,
		)

		self.branch = Branch.objects.create(
			name="Annexe Bamako",
			code="ABK",
			slug="annexe-bamako",
			city="Bamako",
			is_active=True,
			accepts_online_registration=True,
		)

		self.cycle = Cycle.objects.create(
			name="Licence",
			slug="licence",
			min_duration_years=3,
			max_duration_years=3,
			is_active=True,
		)
		self.diploma = Diploma.objects.create(name="Licence pro", level="superieur")
		self.filiere = Filiere.objects.create(name="Sciences infirmieres", is_active=True)
		self.programme = Programme.objects.create(
			title="Licence Infirmier",
			slug="licence-infirmier",
			filiere=self.filiere,
			cycle=self.cycle,
			diploma_awarded=self.diploma,
			duration_years=3,
			short_description="Formation infirmiere",
			description="Description programme",
			is_active=True,
		)

		doc_a = RequiredDocument.objects.create(name="Piece d'identite", is_mandatory=True)
		doc_b = RequiredDocument.objects.create(name="Diplome", is_mandatory=True)
		ProgrammeRequiredDocument.objects.create(programme=self.programme, document=doc_a)
		ProgrammeRequiredDocument.objects.create(programme=self.programme, document=doc_b)

	def _valid_payload(self, **overrides):
		payload = {
			"last_name": "Traore",
			"first_name": "Awa",
			"city": "Bamako",
			"email": "awa@example.com",
			"phone": "+22370000000",
			"birth_date": "2002-05-20",
			"birth_place": "Bamako",
			"gender": "female",
			"current_level": "licence",
			"formation": self.programme.title,
			"formation_slug": self.programme.slug,
			"branch_id": str(self.branch.id),
			"branch_name": self.branch.name,
			"branch_city": self.branch.city,
			"campus_image": "",
		}
		payload.update(overrides)
		return payload

	def test_submission_without_documents_is_allowed(self):
		response = self.client.post(self.url, data=self._valid_payload(), follow=False)

		self.assertEqual(response.status_code, 302)
		self.assertEqual(Candidature.objects.count(), 1)
		self.assertEqual(Candidature.objects.first().documents.count(), 0)

	def test_missing_required_field_returns_precise_message(self):
		response = self.client.post(self.url, data=self._valid_payload(email=""))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Le champ email est obligatoire")
		self.assertEqual(Candidature.objects.count(), 0)

	def test_existing_email_blocks_with_targeted_message(self):
		current_year = timezone.now().year
		Candidature.objects.create(
			programme=self.programme,
			branch=self.branch,
			academic_year=f"{current_year}-{current_year + 1}",
			entry_year=1,
			first_name="Awa",
			last_name="Traore",
			birth_date="2002-05-20",
			birth_place="Bamako",
			gender="female",
			phone="+22370000000",
			email="awa@example.com",
			city="Bamako",
			country="Mali",
		)

		response = self.client.post(self.url, data=self._valid_payload())

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Cette adresse email est deja utilisee pour cette formation cette annee")
		self.assertEqual(Candidature.objects.count(), 1)

	def test_direct_link_preselects_real_branch_and_programme(self):
		response = self.client.get(
			self.url,
			{"step": "3", "branch": self.branch.slug, "formation": self.programme.slug},
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context["initial_step"], 3)
		self.assertEqual(response.context["initial_step3_phase"], "documents")
		form_data = json.loads(response.context["initial_form_json"])
		self.assertEqual(form_data["branch_id"], str(self.branch.id))
		self.assertEqual(form_data["branch_name"], self.branch.name)
		self.assertEqual(form_data["formation_slug"], self.programme.slug)
		self.assertEqual(form_data["current_level"], "licence")

	def test_formation_fragment_uses_database_metadata_and_excludes_inactive(self):
		year = ProgrammeYear.objects.create(programme=self.programme, year_number=1)
		Fee.objects.create(programme_year=year, label="Inscription", amount=125000, due_month="Octobre")
		inactive = Programme.objects.create(
			title="Ancienne formation",
			slug="ancienne-formation",
			filiere=self.filiere,
			cycle=self.cycle,
			diploma_awarded=self.diploma,
			duration_years=3,
			short_description="Ne doit pas apparaitre",
			description="Archive",
			is_active=False,
		)

		response = self.client.get(
			reverse("admissions:admission_step3_formations"),
			{"branch_id": self.branch.id, "cycle": "licence"},
		)

		self.assertEqual(response.status_code, 200)
		cards = response.context["formation_cards"]
		self.assertEqual([card["slug"] for card in cards], [self.programme.slug])
		self.assertEqual(cards[0]["cycle"], self.cycle.name)
		self.assertEqual(cards[0]["diploma"], self.diploma.name)
		self.assertEqual(cards[0]["first_year_cost"], 125000)
		self.assertNotContains(response, inactive.title)

	def test_inactive_branch_cannot_load_formations(self):
		self.branch.is_active = False
		self.branch.save(update_fields=["is_active"])

		response = self.client.get(
			reverse("admissions:admission_step3_formations"),
			{"branch_id": self.branch.id, "cycle": "licence"},
		)

		self.assertEqual(response.status_code, 200)
		self.assertIsNone(response.context["selected_branch"])
		self.assertEqual(response.context["formation_cards"], [])

	def test_non_numeric_branch_identifier_is_rejected_without_server_error(self):
		response = self.client.post(
			self.url,
			data=self._valid_payload(branch_id="annexe-invalide"),
		)

		self.assertEqual(response.status_code, 200)
		errors = json.loads(response.context["backend_errors_json"])
		self.assertEqual(errors["branch_id"], "Le campus selectionne n'est plus disponible.")
		self.assertEqual(Candidature.objects.count(), 0)

	def test_invalid_email_and_missing_gender_are_rejected(self):
		response = self.client.post(
			self.url,
			data=self._valid_payload(email="adresse-invalide", gender=""),
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Saisissez une adresse email valide")
		self.assertContains(response, "Veuillez selectionner votre genre")
		self.assertEqual(Candidature.objects.count(), 0)

	def test_programme_cycle_must_match_selected_level(self):
		response = self.client.post(
			self.url,
			data=self._valid_payload(current_level="master"),
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "La formation choisie ne correspond pas au niveau selectionne")
		self.assertEqual(Candidature.objects.count(), 0)

	def test_entry_year_is_derived_from_real_programme_cycle(self):
		master_cycle = Cycle.objects.create(
			name="Master",
			slug="master",
			min_duration_years=2,
			max_duration_years=2,
			is_active=True,
		)
		master_programme = Programme.objects.create(
			title="Master Sante",
			slug="master-sante",
			filiere=self.filiere,
			cycle=master_cycle,
			diploma_awarded=self.diploma,
			duration_years=2,
			short_description="Specialisation",
			description="Description master",
			is_active=True,
		)

		response = self.client.post(
			self.url,
			data=self._valid_payload(
				current_level="master",
				formation=master_programme.title,
				formation_slug=master_programme.slug,
			),
			follow=False,
		)

		self.assertEqual(response.status_code, 302)
		self.assertEqual(Candidature.objects.get().entry_year, 4)

	def test_unapproved_document_extension_is_rejected(self):
		document_id = self.programme.required_documents.first().document_id
		payload = self._valid_payload()
		payload[f"document_{document_id}"] = SimpleUploadedFile(
			"piece.exe",
			b"not-an-executable",
			content_type="application/octet-stream",
		)

		response = self.client.post(self.url, data=payload)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "format non autorise")
		self.assertEqual(Candidature.objects.count(), 0)

	def test_classic_catalogue_and_detail_routes_remain_available(self):
		list_response = self.client.get(reverse("formations:list"))
		detail_response = self.client.get(self.programme.get_absolute_url())

		self.assertEqual(list_response.status_code, 200)
		self.assertContains(list_response, self.programme.title)
		self.assertEqual(detail_response.status_code, 200)
		self.assertContains(detail_response, self.programme.title)

	def test_accepted_status_uses_premium_admissions_template_metadata(self):
		candidature = Candidature.objects.create(
			programme=self.programme,
			branch=self.branch,
			academic_year="2026-2027",
			entry_year=1,
			first_name="Awa",
			last_name="Traore",
			birth_date="2002-05-20",
			birth_place="Bamako",
			gender="female",
			phone="+22370000000",
			email="awa.accepted@example.com",
			city="Bamako",
			country="Mali",
			status="submitted",
		)

		candidature.status = "accepted"
		candidature.save(update_fields=["status"])

		notification = NotificationMessage.objects.filter(
			event_type="candidature_accepted",
			channel=NotificationMessage.CHANNEL_EMAIL_TRANSACTIONAL,
		).latest("created_at")

		self.assertEqual(notification.metadata["template_key"], "candidature_accepted")
		self.assertEqual(notification.metadata["programme_name"], self.programme.title)
		self.assertEqual(notification.metadata["academic_year"], "2026-2027")
		self.assertEqual(
			notification.metadata["context"]["candidate_name"],
			candidature.full_name,
		)
