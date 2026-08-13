from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from branches.models import Branch


User = get_user_model()


@override_settings(ROOT_URLCONF="config.urls")
class CertifiedManagementDashboardIntegrationTests(TestCase):
    """Every management landing page inherits the certified DE shell."""

    @classmethod
    def setUpTestData(cls):
        cls.branch = Branch.objects.create(
            name="Annexe Shell",
            code="ASH",
            slug="annexe-shell",
        )

    def _user(self, position):
        user = User.objects.create_user(
            username=f"shell_{position}",
            email=f"shell_{position}@example.com",
            password="pass1234",
            is_staff=True,
        )
        profile = user.profile
        profile.position = position
        profile.branch = self.branch
        profile.user_type = "staff"
        profile.save(update_fields=["position", "branch", "user_type", "updated_at"])
        return user

    def _assert_certified(self, *, user, url, expected_role):
        self.client.force_login(user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "portal/staff/director_dashboard.html")
        self.assertContains(response, 'data-certified-dashboard-shell="true"')
        self.assertContains(response, 'data-ui-core="app-sidebar"', count=1)
        self.assertContains(response, 'data-ui-core="app-topbar"', count=1)
        self.assertEqual(response.context["dashboard_shell"]["role"], expected_role)
        self.assertTrue(response.context["dashboard_shell"]["navigation"])
        self.client.logout()
        return response

    def test_branch_management_dashboards_use_certified_shell(self):
        cases = (
            ("annex_manager", "accounts_portal:portal_annex_manager"),
            ("finance_manager", "accounts_portal:portal_finance"),
            ("admissions", "accounts_portal:portal_admissions"),
            ("secretary", "accounts_portal:portal_secretary"),
            ("it_support", "accounts_portal:portal_dashboard"),
        )
        for position, url_name in cases:
            with self.subTest(position=position):
                response = self._assert_certified(
                    user=self._user(position),
                    url=reverse(url_name),
                    expected_role=position,
                )
                self.assertIn(self.branch.name, response.context["dashboard_shell"]["context_label"])

    def test_global_management_dashboards_use_certified_shell(self):
        for position, url_name in (
            ("executive_director", "accounts_portal:portal_dg"),
            ("marketing_manager", "marketing:dashboard"),
        ):
            with self.subTest(position=position):
                self._assert_certified(
                    user=self._user(position),
                    url=reverse(url_name),
                    expected_role=position,
                )

        superuser = User.objects.create_superuser(
            username="shell_superadmin",
            email="shell_superadmin@example.com",
            password="pass1234",
        )
        self._assert_certified(
            user=superuser,
            url=reverse("superadmin:dashboard"),
            expected_role="super_admin",
        )
