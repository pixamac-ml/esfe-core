from django.contrib.auth import get_user_model
from django.test import TestCase

from accounts.models import Profile
from branches.models import Branch
from portal.dg.forms import DgStaffLifecycleForm
from portal.dg.rh_service import apply_staff_lifecycle_action
from portal.models import SupportAuditLog


class DgStaffLifecycleServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.centre = Branch.objects.create(name="Annexe RH Centre", code="RHC", slug="rh-centre")
        cls.nord = Branch.objects.create(name="Annexe RH Nord", code="RHN", slug="rh-nord")
        user_model = get_user_model()
        cls.dg = user_model.objects.create_user(username="dg-rh", password="password")
        cls.staff = user_model.objects.create_user(username="staff-rh", password="password")
        Profile.objects.filter(user=cls.dg).update(
            user_type="staff", position="executive_director", employment_status="active"
        )
        Profile.objects.filter(user=cls.staff).update(
            user_type="staff", position="secretary", branch=cls.centre, employment_status="active"
        )

    def _submit(self, action, **extra):
        profile = Profile.objects.get(user=self.staff)
        form = DgStaffLifecycleForm(
            {"profile_id": profile.id, "action": action, "reason": "Décision RH documentée.", **extra}
        )
        self.assertTrue(form.is_valid(), form.errors)
        return apply_staff_lifecycle_action(actor=self.dg, form=form)

    def test_suspend_reactivate_and_revoke_keep_staff_history(self):
        self._submit("suspend")
        self.staff.refresh_from_db()
        profile = Profile.objects.get(user=self.staff)
        self.assertFalse(self.staff.is_active)
        self.assertEqual(profile.employment_status, "suspended")
        self.assertTrue(
            SupportAuditLog.objects.filter(
                target_user=self.staff,
                action_type=SupportAuditLog.ACTION_ACCOUNT_SUSPENDED,
            ).exists()
        )

        self._submit("reactivate")
        self.staff.refresh_from_db()
        profile.refresh_from_db()
        self.assertTrue(self.staff.is_active)
        self.assertEqual(profile.employment_status, "active")

        result = self._submit("revoke")
        self.staff.refresh_from_db()
        profile.refresh_from_db()
        self.assertTrue(result["ok"])
        self.assertFalse(self.staff.is_active)
        self.assertEqual(profile.employment_status, "inactive")
        self.assertTrue(Profile.objects.filter(pk=profile.pk).exists())
        self.assertTrue(
            SupportAuditLog.objects.filter(
                target_user=self.staff,
                action_type=SupportAuditLog.ACTION_ACCOUNT_DEACTIVATED,
            ).exists()
        )

    def test_reassignment_changes_branch_and_records_the_decision(self):
        self._submit("reassign", branch=str(self.nord.id))
        profile = Profile.objects.get(user=self.staff)

        self.assertEqual(profile.branch, self.nord)
        self.assertTrue(
            SupportAuditLog.objects.filter(
                target_user=self.staff,
                action_type=SupportAuditLog.ACTION_STAFF_ASSIGNED,
                branch=self.nord,
            ).exists()
        )
