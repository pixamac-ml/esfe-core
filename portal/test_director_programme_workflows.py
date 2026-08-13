from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from academics.models import AcademicClass, AcademicYear, EC, Semester, UE
from branches.models import Branch
from formations.models import Cycle, Diploma, Filiere, Programme


class DirectorProgrammeWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.branch = Branch.objects.create(
            name="Annexe Programme", code="APR", slug="annexe-programme"
        )
        cls.other_branch = Branch.objects.create(
            name="Annexe Hors Portee", code="AHP", slug="annexe-hors-portee"
        )
        cycle = Cycle.objects.create(
            name="Licence Programme",
            theme="primary",
            min_duration_years=1,
            max_duration_years=5,
        )
        diploma = Diploma.objects.create(name="Diplome Programme", level="superieur")
        filiere = Filiere.objects.create(name="Filiere Programme")
        cls.programme = Programme.objects.create(
            title="Gestion des organisations",
            filiere=filiere,
            cycle=cycle,
            diploma_awarded=diploma,
            duration_years=3,
            short_description="Programme de test",
            description="Structure academique de test.",
        )
        cls.other_programme = Programme.objects.create(
            title="Droit des affaires",
            filiere=filiere,
            cycle=cycle,
            diploma_awarded=diploma,
            duration_years=3,
            short_description="Autre programme de test",
            description="Autre structure academique de test.",
        )
        cls.academic_year = AcademicYear.objects.create(
            name="2026-2027",
            start_date=date(2026, 10, 1),
            end_date=date(2027, 7, 31),
            is_active=True,
        )
        cls.academic_class = AcademicClass.objects.create(
            name="L1 Gestion Annexe Programme",
            programme=cls.programme,
            branch=cls.branch,
            academic_year=cls.academic_year,
            level="L1",
            study_level="LICENCE",
        )
        cls.other_class = AcademicClass.objects.create(
            name="Classe Confidentielle Hors Annexe",
            programme=cls.other_programme,
            branch=cls.other_branch,
            academic_year=cls.academic_year,
            level="L2",
            study_level="LICENCE",
        )
        cls.semester_1 = Semester.objects.create(
            academic_class=cls.academic_class, number=1
        )
        cls.semester_2 = Semester.objects.create(
            academic_class=cls.academic_class, number=2
        )
        cls.other_semester = Semester.objects.create(
            academic_class=cls.other_class, number=1
        )
        cls.ue = UE.objects.create(
            semester=cls.semester_1, code="UE101", title="Fondamentaux"
        )
        cls.other_ue = UE.objects.create(
            semester=cls.other_semester, code="UE900", title="UE Hors Annexe"
        )
        cls.ec = EC.objects.create(
            ue=cls.ue,
            title="Comptabilite generale",
            credit_required="3.00",
            coefficient="2.00",
        )
        cls.director = get_user_model().objects.create_user(
            username="programme_director",
            email="programme-director@test.test",
            password="programme-password",
            is_staff=True,
        )
        cls.director.profile.position = "director_of_studies"
        cls.director.profile.role = "executive"
        cls.director.profile.branch = cls.branch
        cls.director.profile.save(
            update_fields=["position", "role", "branch", "updated_at"]
        )

    def setUp(self):
        self.client.force_login(self.director)

    def test_workspace_exposes_three_programme_subviews_without_cross_branch_data(self):
        response = self.client.get(
            reverse("accounts_portal:director_workspace"),
            {"section": "programme"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Programmes et classes")
        self.assertContains(response, "Vue d&#x27;ensemble")
        self.assertContains(response, "Classes")
        self.assertContains(response, "Maquettes pédagogiques")
        self.assertNotContains(response, self.other_class.name)

    def test_classes_subcontent_filters_and_pushes_dashboard_url(self):
        response = self.client.get(
            reverse("accounts_portal:director_programme_subcontent"),
            {"view": "classes", "programme_q": "Gestion"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.academic_class.name)
        self.assertNotContains(response, self.other_class.name)
        self.assertIn("section=programme", response.headers["HX-Push-Url"])
        self.assertIn("view=classes", response.headers["HX-Push-Url"])

    def test_class_modal_rejects_a_class_from_another_branch(self):
        response = self.client.get(
            reverse("accounts_portal:director_programme_class_modal"),
            {"class_id": self.other_class.pk},
        )

        self.assertEqual(response.status_code, 400)

    def test_create_class_uses_director_branch_and_prepares_two_semesters(self):
        response = self.client.post(
            reverse("accounts_portal:director_programme_action"),
            {
                "action": "save_class",
                "programme": self.other_programme.pk,
                "academic_year": self.academic_year.pk,
                "level": "l3",
                "validation_threshold": "12",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        created = AcademicClass.objects.get(
            branch=self.branch, programme=self.other_programme, level="L3"
        )
        self.assertEqual(created.validation_threshold, 12)
        self.assertEqual(
            list(created.semesters.order_by("number").values_list("number", flat=True)),
            [1, 2],
        )
        self.assertEqual(response.headers["HX-Retarget"], "#director-programme-subcontent")
        self.assertEqual(response.headers["HX-Trigger"], "director-modal-close")

    def test_duplicate_class_returns_bound_form_with_field_error(self):
        response = self.client.post(
            reverse("accounts_portal:director_programme_action"),
            {
                "action": "save_class",
                "programme": self.programme.pk,
                "academic_year": self.academic_year.pk,
                "level": "L1",
                "validation_threshold": "10",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Une classe existe déjà")
        self.assertNotIn("HX-Retarget", response.headers)
        self.assertEqual(
            AcademicClass.objects.filter(
                branch=self.branch,
                programme=self.programme,
                academic_year=self.academic_year,
                level="L1",
            ).count(),
            1,
        )

    def test_save_ue_is_scoped_and_preserves_invalid_values(self):
        invalid = self.client.post(
            reverse("accounts_portal:director_programme_action"),
            {
                "action": "save_ue",
                "class_id": self.academic_class.pk,
                "semester": self.other_semester.pk,
                "code": "UE-X",
                "title": "Tentative hors annexe",
                "_reload_drawer": "1",
            },
        )

        self.assertEqual(invalid.status_code, 200)
        self.assertContains(invalid, "Sélectionnez un choix valide")
        self.assertContains(invalid, "Tentative hors annexe")
        self.assertFalse(UE.objects.filter(code="UE-X").exists())

        valid = self.client.post(
            reverse("accounts_portal:director_programme_action"),
            {
                "action": "save_ue",
                "class_id": self.academic_class.pk,
                "semester": self.semester_2.pk,
                "code": "ue202",
                "title": "Approfondissement",
                "_reload_drawer": "1",
            },
        )
        self.assertEqual(valid.status_code, 200)
        self.assertTrue(
            UE.objects.filter(
                semester=self.semester_2, code="UE202", title="Approfondissement"
            ).exists()
        )
        self.assertEqual(valid.headers["HX-Trigger"], "directorProgrammeChanged")

    def test_semester_form_rejects_numbers_outside_the_academic_model(self):
        response = self.client.post(
            reverse("accounts_portal:director_programme_action"),
            {
                "action": "save_semester",
                "class_id": self.academic_class.pk,
                "number": "3",
                "_reload_drawer": "1",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sélectionnez un choix valide")
        self.assertFalse(
            Semester.objects.filter(
                academic_class=self.academic_class, number=3
            ).exists()
        )

    def test_save_ec_uses_scoped_form_and_validates_credit_balance(self):
        invalid = self.client.post(
            reverse("accounts_portal:director_programme_action"),
            {
                "action": "save_ec",
                "class_id": self.academic_class.pk,
                "ue": self.ue.pk,
                "title": "Audit avance",
                "coefficient": "4",
                "credit_required": "2",
                "_reload_drawer": "1",
            },
        )
        self.assertEqual(invalid.status_code, 200)
        self.assertContains(invalid, "crédits ne peuvent pas être inférieurs")
        self.assertFalse(EC.objects.filter(title="Audit avance").exists())

        valid = self.client.post(
            reverse("accounts_portal:director_programme_action"),
            {
                "action": "save_ec",
                "class_id": self.academic_class.pk,
                "ue": self.ue.pk,
                "title": "Audit avance",
                "coefficient": "1",
                "credit_required": "2",
                "_reload_drawer": "1",
            },
        )
        self.assertEqual(valid.status_code, 200)
        self.assertTrue(
            EC.objects.filter(ue=self.ue, title="Audit avance").exists()
        )

    def test_delete_ec_archives_instead_of_deleting(self):
        response = self.client.post(
            reverse("accounts_portal:director_programme_action"),
            {
                "action": "delete_ec",
                "class_id": self.academic_class.pk,
                "ec_id": self.ec.pk,
                "_reload_drawer": "1",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.ec.refresh_from_db()
        self.assertEqual(self.ec.structure_status, EC.STRUCTURE_ARCHIVED)
        self.assertIsNotNone(self.ec.archived_at)
        self.assertContains(response, "EC archivé")
        self.assertNotContains(response, "Comptabilite generale")

    def test_maquette_subcontent_only_accepts_a_scoped_selected_class(self):
        response = self.client.get(
            reverse("accounts_portal:director_programme_subcontent"),
            {"view": "maquettes", "class_id": self.other_class.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.academic_class.name)
        self.assertNotContains(response, self.other_class.name)
        self.assertNotContains(response, self.other_ue.title)
