from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase

from accounts.services.institutional_access import (
    CANONICAL_GROUP_NAMES,
    ensure_canonical_groups,
    synchronize_user_position_groups,
)
from branches.models import Branch


User = get_user_model()


class InstitutionalPositionGroupSyncTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            name="Annexe droits institutionnels",
            code="ADI",
            slug="annexe-droits-institutionnels",
        )

    def test_every_official_position_group_is_created(self):
        ensure_canonical_groups()

        self.assertEqual(
            set(Group.objects.filter(name__in=CANONICAL_GROUP_NAMES).values_list("name", flat=True)),
            CANONICAL_GROUP_NAMES,
        )

    def test_position_change_removes_conflicting_access_group(self):
        user = User.objects.create_user(username="position-sync", password="pass1234", is_staff=True)
        admissions_group, _ = Group.objects.get_or_create(name="admissions_managers")
        support_group, _ = Group.objects.get_or_create(name="Support")
        user.groups.add(admissions_group, support_group)

        profile = user.profile
        profile.position = "academic_supervisor"
        profile.branch = self.branch
        profile.role = "admissions"
        profile.save(update_fields=["position", "branch", "role", "updated_at"])
        user.refresh_from_db()

        self.assertEqual(user.profile.role, "")
        self.assertEqual(
            set(user.groups.values_list("name", flat=True)),
            {"academic_supervisor", "Support"},
        )

    def test_explicit_sync_normalizes_legacy_branch_manager_alias(self):
        user = User.objects.create_user(username="manager-sync", password="pass1234", is_staff=True)
        legacy_group, _ = Group.objects.get_or_create(name="gestionnaire")
        user.groups.add(legacy_group)
        profile = user.profile
        profile.position = "branch_manager"
        profile.branch = self.branch
        profile.save(update_fields=["position", "branch", "updated_at"])

        synchronize_user_position_groups(user, position="branch_manager")
        self.assertIn("annex_manager", user.groups.values_list("name", flat=True))
        self.assertNotIn("gestionnaire", user.groups.values_list("name", flat=True))
