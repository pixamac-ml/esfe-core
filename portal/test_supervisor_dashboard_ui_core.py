from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from academics.models import AcademicClass, AcademicYear
from branches.models import Branch
from formations.models import Cycle, Diploma, Filiere, Programme
from portal.permissions import get_post_login_portal_url


User = get_user_model()


class SupervisorDashboardUiCoreTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            name="Annexe UI Surveillant",
            code="UIS",
            slug="annexe-ui-surveillant",
        )
        self.user = User.objects.create_user(
            username="supervisor-ui-core",
            password="test-pass",
        )
        profile = self.user.profile
        profile.position = "academic_supervisor"
        profile.branch = self.branch
        profile.save(update_fields=["position", "branch", "updated_at"])
        self.client.force_login(self.user)

    def test_canonical_dashboard_uses_ui_core_shell(self):
        response = self.client.get(reverse("accounts_portal:portal_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "portal/staff/director_dashboard.html")
        self.assertTemplateNotUsed(response, "portal/staff/supervisor_dashboard.html")
        self.assertContains(response, 'data-certified-dashboard-shell="true"')
        self.assertContains(response, 'data-dashboard-role="academic_supervisor"')
        self.assertContains(response, 'data-ui-core="app-shell"')
        self.assertContains(response, 'data-ui-core="app-sidebar"')
        self.assertContains(response, 'data-ui-core="app-topbar"')
        self.assertContains(response, 'data-ui-core="drawer"')
        self.assertContains(response, 'data-ui-core="confirm-dialog"')
        self.assertContains(response, "src/js/portal/certified_dashboard_shell.js")
        self.assertContains(response, "src/js/portal/supervisor_dashboard.js")
        self.assertContains(response, 'id="supervisor-workspace"')
        self.assertContains(response, reverse("accounts:logout"))
        self.assertNotContains(response, 'class="shell"')
        self.assertNotContains(response, 'class="rail"')

    def test_navigation_uses_canonical_urls_and_htmx_workspace(self):
        response = self.client.get(
            reverse("accounts_portal:portal_dashboard"),
            {"section": "attendance"},
        )

        canonical = f"{reverse('accounts_portal:portal_dashboard')}?section=attendance"
        fragment = f"{reverse('accounts_portal:supervisor_workflow_workspace')}?section=attendance"
        self.assertContains(response, f'href="{canonical}"')
        self.assertContains(response, f'hx-get="{fragment}"')
        self.assertContains(response, 'hx-target="#supervisor-workspace"')
        self.assertContains(response, 'data-nav-key="attendance"')
        self.assertContains(response, 'aria-current="page"')

    def test_workspace_endpoint_only_returns_fragment_for_htmx(self):
        response = self.client.get(
            reverse("accounts_portal:supervisor_workflow_workspace"),
            {"section": "home"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "portal/staff/supervisor/partials/workflow_workspace.html",
        )
        self.assertContains(response, 'data-supervisor-section="home"')
        self.assertContains(response, 'data-ui-core="page-header"')
        self.assertNotContains(response, 'hx-push-url="true"')
        self.assertNotContains(response, 'data-ui-core="app-shell"')

    def test_full_workspace_request_redirects_to_canonical_dashboard(self):
        response = self.client.get(
            reverse("accounts_portal:supervisor_workflow_workspace"),
            {"section": "students"},
        )

        self.assertRedirects(
            response,
            f"{reverse('accounts_portal:portal_dashboard')}?section=classes&view=students",
            fetch_redirect_response=False,
        )

    def test_full_cases_request_redirects_to_canonical_dashboard(self):
        response = self.client.get(
            reverse("accounts_portal:supervisor_cases_workspace"),
        )

        self.assertRedirects(
            response,
            f"{reverse('accounts_portal:portal_dashboard')}?section=signals&view=transmitted",
            fetch_redirect_response=False,
        )

    def test_role_registry_routes_directly_to_canonical_dashboard(self):
        with override_settings(AUTH_PORTAL_ROUTING_V2_ENABLED=True):
            self.assertEqual(
                get_post_login_portal_url(self.user),
                reverse("accounts_portal:portal_dashboard"),
            )

    def test_dashboard_always_builds_class_picker_with_user_branch(self):
        with patch(
            "portal.services.supervisor_workspace_service.get_supervisor_class_picker_bundle",
            return_value=([], [], AcademicClass.objects.none()),
        ) as picker:
            response = self.client.get(reverse("accounts_portal:portal_dashboard"))

        self.assertEqual(response.status_code, 200)
        picker.assert_called_once_with(branch=self.branch)

    def test_certified_shell_context_is_adapted_to_supervisor_role(self):
        response = self.client.get(reverse("accounts_portal:portal_dashboard"))

        shell = response.context["dashboard_shell"]
        self.assertEqual(shell["certified_template"], "portal/staff/director_dashboard.html")
        self.assertEqual(shell["role"], "academic_supervisor")
        self.assertEqual(shell["key"], "supervisor")
        self.assertEqual(shell["workspace_id"], "supervisor-workspace")
        self.assertEqual(
            shell["workspace_template"],
            "portal/staff/supervisor/partials/workflow_workspace.html",
        )
        self.assertEqual(response.context["branch"], self.branch)

    def test_shared_shell_does_not_grant_director_capabilities(self):
        response = self.client.get(
            reverse("accounts_portal:director_workspace"),
            {"section": "programme"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 403)

    def test_supervisor_without_branch_is_forbidden_everywhere(self):
        unscoped = User.objects.create_user(
            username="supervisor-ui-unscoped",
            password="test-pass",
        )
        profile = unscoped.profile
        profile.position = "academic_supervisor"
        profile.branch = None
        profile.save(update_fields=["position", "branch", "updated_at"])
        self.client.force_login(unscoped)

        dashboard = self.client.get(reverse("accounts_portal:portal_dashboard"))
        workspace = self.client.get(
            reverse("accounts_portal:supervisor_workflow_workspace"),
            HTTP_HX_REQUEST="true",
        )
        cases = self.client.get(
            reverse("accounts_portal:supervisor_cases_workspace"),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(dashboard.status_code, 403)
        self.assertEqual(workspace.status_code, 403)
        self.assertEqual(cases.status_code, 403)

    def test_certified_dashboard_never_exposes_another_branch_class(self):
        other_branch = Branch.objects.create(
            name="Annexe UI Hors Scope",
            code="UIH",
            slug="annexe-ui-hors-scope",
        )
        cycle = Cycle.objects.create(
            name="Cycle UI Scope",
            min_duration_years=1,
            max_duration_years=3,
        )
        diploma = Diploma.objects.create(name="Diplôme UI Scope", level="superieur")
        filiere = Filiere.objects.create(name="Filière UI Scope")
        programme = Programme.objects.create(
            title="Programme UI Scope",
            filiere=filiere,
            cycle=cycle,
            diploma_awarded=diploma,
            duration_years=3,
            short_description="Contrôle du périmètre surveillant.",
            description="Données réservées aux tests d'isolation par annexe.",
        )
        academic_year = AcademicYear.objects.create(
            name="2031-2032",
            start_date=date(2031, 10, 1),
            end_date=date(2032, 7, 31),
            is_active=True,
        )
        own_class = AcademicClass.objects.create(
            name="Classe SG Autorisée",
            programme=programme,
            branch=self.branch,
            academic_year=academic_year,
            level="SG-OWN",
            study_level="LICENCE",
            is_active=True,
        )
        hidden_class = AcademicClass.objects.create(
            name="Classe SG Interdite",
            programme=programme,
            branch=other_branch,
            academic_year=academic_year,
            level="SG-HIDDEN",
            study_level="LICENCE",
            is_active=True,
        )

        response = self.client.get(reverse("accounts_portal:portal_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, own_class.display_name)
        self.assertNotContains(response, hidden_class.display_name)
