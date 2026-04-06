from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from admissions.models import Candidature
from branches.models import Branch
from formations.models import Cycle, Diploma, Filiere, Programme, ProgrammeRequiredDocument, RequiredDocument


class AdmissionTunnelValidationTests(TestCase):
	def setUp(self):
		self.url = reverse("admissions:admission_tunnel")

		self.branch = Branch.objects.create(
			name="Annexe Bamako",
			code="ABK",
			slug="annexe-bamako",
			city="Bamako",
			is_active=True,
			accepts_online_registration=True,
		)

		cycle = Cycle.objects.create(
			name="Licence",
			slug="licence",
			min_duration_years=3,
			max_duration_years=3,
			is_active=True,
		)
		diploma = Diploma.objects.create(name="Licence pro", level="superieur")
		filiere = Filiere.objects.create(name="Sciences infirmieres", is_active=True)
		self.programme = Programme.objects.create(
			title="Licence Infirmier",
			slug="licence-infirmier",
			filiere=filiere,
			cycle=cycle,
			diploma_awarded=diploma,
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
