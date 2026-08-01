from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from branches.models import Branch


USER_MANAGER = get_user_model().objects


class DirectorDashboardRenderTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(name="Annexe Test", slug="annexe-test")
        self.user = USER_MANAGER.create_user(
            username="director_test",
            email="director_test@example.com",
            password="pass1234",
            is_staff=True,
        )
        profile = self.user.profile
        profile.role = "executive"
        profile.position = "director_of_studies"
        profile.branch = self.branch
        profile.save(update_fields=["role", "position", "branch", "updated_at"])

    def test_director_dashboard_renders(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("accounts_portal:portal_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dashboard Direction des Études")
        self.assertContains(response, 'data-ui-core="app-shell"')
        self.assertContains(response, 'data-ui-core="app-sidebar"')
        self.assertContains(response, 'data-ui-core="app-topbar"')
