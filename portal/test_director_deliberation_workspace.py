from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from academic_cycle import constants
from academic_cycle.models import AcademicClosureReport, BranchAcademicCycle
from academics.models import AcademicClass, AcademicYear, Semester
from branches.models import Branch
from formations.models import Cycle, Diploma, Filiere, Programme


class DirectorDeliberationWorkspaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.branch = Branch.objects.create(
            name="Annexe Délibération", code="ADELIB", slug="annexe-deliberation"
        )
        cls.other_branch = Branch.objects.create(
            name="Annexe Hors Délibération", code="AHDEL", slug="annexe-hors-deliberation"
        )
        cycle = Cycle.objects.create(
            name="Licence Délibération", theme="primary",
            min_duration_years=1, max_duration_years=5,
        )
        diploma = Diploma.objects.create(name="Diplôme Délibération", level="superieur")
        filiere = Filiere.objects.create(name="Filière Délibération")
        programme = Programme.objects.create(
            title="Programme Délibération",
            filiere=filiere,
            cycle=cycle,
            diploma_awarded=diploma,
            duration_years=3,
            short_description="Préparation des délibérations",
            description="Données de test.",
        )
        cls.academic_year = AcademicYear.objects.create(
            name="2026-2027",
            start_date=date(2026, 10, 1),
            end_date=date(2027, 7, 31),
            is_active=True,
        )
        cls.academic_class = AcademicClass.objects.create(
            name="Classe prête",
            programme=programme,
            branch=cls.branch,
            academic_year=cls.academic_year,
            level="L1",
            study_level="LICENCE",
        )
        Semester.objects.create(
            academic_class=cls.academic_class,
            number=1,
            status=Semester.STATUS_FINALIZED,
        )
        Semester.objects.create(
            academic_class=cls.academic_class,
            number=2,
            status=Semester.STATUS_FINALIZED,
        )
        cls.branch_cycle = BranchAcademicCycle.objects.create(
            branch=cls.branch,
            academic_year=cls.academic_year,
            status=constants.BRANCH_CYCLE_ACTIVE,
        )
        cls.other_cycle = BranchAcademicCycle.objects.create(
            branch=cls.other_branch,
            academic_year=cls.academic_year,
            status=constants.BRANCH_CYCLE_ACTIVE,
        )
        cls.director = get_user_model().objects.create_user(
            username="director_deliberation",
            email="director-deliberation@example.test",
            password="test-password",
            is_staff=True,
        )
        profile = cls.director.profile
        profile.position = "director_of_studies"
        profile.role = "executive"
        profile.branch = cls.branch
        profile.save(update_fields=["position", "role", "branch", "updated_at"])

    def setUp(self):
        self.client.force_login(self.director)

    def test_deliberation_subsection_is_rendered_inside_director_workspace(self):
        response = self.client.get(
            reverse("accounts_portal:director_workspace"),
            {"section": "evaluations", "view": "deliberation"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Préparation de la délibération")
        self.assertContains(response, self.branch.name)
        self.assertNotContains(response, self.other_branch.name)
        self.assertContains(response, 'id="director-result-tabs-deliberation-tab"')
        self.assertNotContains(response, 'data-ui-core="app-shell"')

    def test_director_can_open_deliberation_only_after_scoped_readiness_check(self):
        response = self.client.post(
            reverse("accounts_portal:director_deliberation_action"),
            {"cycle_id": self.branch_cycle.id, "action": "start"},
            HTTP_HX_REQUEST="true",
        )

        self.branch_cycle.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.branch_cycle.status, constants.BRANCH_CYCLE_DELIBERATION)
        self.assertTrue(
            AcademicClosureReport.objects.filter(
                branch_cycle=self.branch_cycle,
                status=constants.CLOSURE_REPORT_VALID,
            ).exists()
        )
        self.assertContains(response, "La délibération est ouverte")

    def test_deliberation_stays_blocked_when_a_later_semester_is_not_finalized(self):
        """S3+ must never be ignored when deciding annual readiness."""
        Semester.objects.create(
            academic_class=self.academic_class,
            number=3,
            status=Semester.STATUS_DRAFT,
        )

        response = self.client.post(
            reverse("accounts_portal:director_deliberation_action"),
            {"cycle_id": self.branch_cycle.id, "action": "start"},
            HTTP_HX_REQUEST="true",
        )

        self.branch_cycle.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.branch_cycle.status, constants.BRANCH_CYCLE_ACTIVE)
        self.assertTrue(
            AcademicClosureReport.objects.filter(
                branch_cycle=self.branch_cycle,
                status=constants.CLOSURE_REPORT_INVALID,
            ).exists()
        )
        self.assertContains(response, "La deliberation est impossible")

    def test_director_cannot_act_on_another_branch_cycle(self):
        response = self.client.post(
            reverse("accounts_portal:director_deliberation_action"),
            {"cycle_id": self.other_cycle.id, "action": "start"},
            HTTP_HX_REQUEST="true",
        )

        self.other_cycle.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.other_cycle.status, constants.BRANCH_CYCLE_ACTIVE)
        self.assertFalse(
            AcademicClosureReport.objects.filter(branch_cycle=self.other_cycle).exists()
        )
        self.assertContains(response, "Cycle académique introuvable")

    def test_official_pv_type_can_be_preselected_from_deliberation(self):
        response = self.client.get(
            reverse("accounts_portal:director_workspace"),
            {
                "section": "correspondances",
                "view": "create",
                "doc_type": "pv_deliberation",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<option value="pv_deliberation" selected>Procès-verbal de délibération</option>',
            html=True,
        )
