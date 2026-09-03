from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from academics.models import AcademicClass, AcademicYear
from branches.models import Branch
from formations.models import Cycle, Diploma, Filiere, Programme
from portal.dg.context import MODE_BRANCH, MODE_GLOBAL, SESSION_KEY
from portal.dg.selectors import get_dg_base_querysets


class DgDashboardContextTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.current_year = AcademicYear.objects.create(
            name="2032-2033",
            start_date=date(2032, 10, 1),
            end_date=date(2033, 7, 31),
            is_active=True,
        )
        cls.archived_year = AcademicYear.objects.create(
            name="2031-2032",
            start_date=date(2031, 10, 1),
            end_date=date(2032, 7, 31),
        )
        cls.branch = Branch.objects.create(name="Annexe DG Centre", code="DGC", slug="dg-centre")
        cls.other_branch = Branch.objects.create(name="Annexe DG Nord", code="DGN", slug="dg-nord")
        cycle = Cycle.objects.create(name="Cycle DG", min_duration_years=1, max_duration_years=3)
        diploma = Diploma.objects.create(name="Diplôme DG", level="superieur")
        filiere = Filiere.objects.create(name="Filière DG")
        programme = Programme.objects.create(
            title="Pilotage DG",
            filiere=filiere,
            cycle=cycle,
            diploma_awarded=diploma,
            duration_years=3,
            short_description="Programme de test DG",
            description="Programme de test DG",
        )
        cls.current_class = AcademicClass.objects.create(
            name="Classe DG actuelle",
            programme=programme,
            branch=cls.branch,
            academic_year=cls.current_year,
            level="L1",
            study_level="LICENCE",
        )
        cls.archived_class = AcademicClass.objects.create(
            name="Classe DG archivée",
            programme=programme,
            branch=cls.branch,
            academic_year=cls.archived_year,
            level="L1",
            study_level="LICENCE",
        )
        user = get_user_model().objects.create_user(username="dg-context", password="password")
        user.profile.position = "executive_director"
        user.profile.save(update_fields=["position", "updated_at"])
        cls.dg = user

    def setUp(self):
        self.client.force_login(self.dg)

    def test_context_is_saved_and_restored_across_navigation(self):
        response = self.client.get(
            reverse("accounts_portal:portal_dg"),
            {"academic_year_id": self.archived_year.id, "branch_id": self.branch.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_academic_year"], self.archived_year)
        self.assertEqual(response.context["selected_branch"], self.branch)
        self.assertEqual(response.context["dashboard_mode"], MODE_BRANCH)
        self.assertEqual(
            self.client.session[SESSION_KEY],
            {"academic_year_id": self.archived_year.id, "branch_id": self.branch.id, "mode": MODE_BRANCH},
        )

        restored = self.client.get(reverse("accounts_portal:portal_dg"))
        self.assertEqual(restored.context["selected_academic_year"], self.archived_year)
        self.assertEqual(restored.context["selected_branch"], self.branch)

    def test_empty_branch_parameter_switches_to_global_mode(self):
        self.client.get(
            reverse("accounts_portal:portal_dg"),
            {"academic_year_id": self.archived_year.id, "branch_id": self.branch.id},
        )

        response = self.client.get(reverse("accounts_portal:portal_dg"), {"branch_id": ""})

        self.assertEqual(response.context["dashboard_mode"], MODE_GLOBAL)
        self.assertIsNone(response.context["selected_branch"])
        self.assertEqual(self.client.session[SESSION_KEY]["branch_id"], None)

    def test_year_scopes_the_canonical_dg_classes_queryset(self):
        archived = get_dg_base_querysets([self.branch.id], academic_year=self.archived_year)
        current = get_dg_base_querysets([self.branch.id], academic_year=self.current_year)

        self.assertEqual(list(archived["classes"]), [self.archived_class])
        self.assertEqual(list(current["classes"]), [self.current_class])

    def test_rh_workspace_uses_server_search_and_keeps_the_dg_scope(self):
        matching_user = get_user_model().objects.create_user(
            username="dg-rh-mariam",
            first_name="Mariam",
            last_name="Traore",
            email="mariam@example.test",
            password="password",
        )
        matching_user.profile.user_type = "staff"
        matching_user.profile.position = "secretary"
        matching_user.profile.branch = self.branch
        matching_user.profile.employee_code = "ESFE-RH-101"
        matching_user.profile.save()

        other_user = get_user_model().objects.create_user(
            username="dg-rh-ibrahim",
            first_name="Ibrahim",
            last_name="Coulibaly",
            password="password",
        )
        other_user.profile.user_type = "staff"
        other_user.profile.position = "secretary"
        other_user.profile.branch = self.other_branch
        other_user.profile.save()

        response = self.client.get(
            reverse("accounts_portal:dg_section", kwargs={"section": "rh"}),
            {
                "academic_year_id": self.current_year.id,
                "scope_branch_id": self.branch.id,
                "q": "Mariam",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mariam Traore")
        self.assertNotContains(response, "Ibrahim Coulibaly")
        self.assertContains(response, 'hx-trigger="input changed delay:350ms, search"')

    def test_overview_section_composes_ui_core_components(self):
        response = self.client.get(
            reverse("accounts_portal:dg_section", kwargs={"section": "overview"}),
            {"academic_year_id": self.current_year.id, "scope_branch_id": self.branch.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-ui-core="page-header"')
        self.assertContains(response, 'data-ui-core="stat-card"')
        self.assertContains(response, 'data-ui-core="data-table"')
