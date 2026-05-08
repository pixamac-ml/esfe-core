from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from branches.models import Branch

from .models import RegistryEntry


User = get_user_model()


class SecretaryActionMethodTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            name="Annexe Secretariat",
            code="ASEC",
            slug="annexe-secretariat",
        )
        self.user = User.objects.create_user(
            username="secretary_action_user",
            email="secretary_action_user@example.com",
            password="pass1234",
            is_staff=True,
        )
        self.user.profile.position = "secretary"
        self.user.profile.branch = self.branch
        self.user.profile.save(update_fields=["position", "branch", "updated_at"])
        self.factory = RequestFactory()

    def test_registry_archive_requires_post(self):
        entry = RegistryEntry.objects.create(
            title="Courrier test",
            entry_type="courrier",
            created_by=self.user,
        )

        from .views import registry_archive

        request = self.factory.get(f"/secretary/registry/{entry.pk}/archive/")
        request.user = self.user
        response = registry_archive(request, entry.pk)

        entry.refresh_from_db()
        self.assertEqual(response.status_code, 405)
        self.assertFalse(entry.is_archived)
        self.assertTrue(entry.is_active)
