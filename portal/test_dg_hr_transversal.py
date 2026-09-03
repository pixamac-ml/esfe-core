from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.access import get_user_annexe, get_user_position
from accounts.models import InstitutionalProfile
from branches.models import Branch
from portal.models import SupportAuditLog


@override_settings(AUTH_POLICY_V2_ENABLED=True, AUTH_PORTAL_ROUTING_V2_ENABLED=True)
class DgHrTransversalWorkflowTests(TestCase):
    password = "StrongPassword!2042"

    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.dg = user_model.objects.create_user(
            username="dg-hr-transversal",
            password=cls.password,
            first_name="Direction",
            last_name="Générale",
        )
        dg_profile = cls.dg.profile
        dg_profile.user_type = "staff"
        dg_profile.position = "executive_director"
        dg_profile.employment_status = "active"
        dg_profile.save()
        cls.branch = Branch.objects.create(
            name="Annexe Moribabougou RH",
            code="MRH",
            slug="moribabougou-rh",
            is_active=True,
        )

    def _recruit(self, *, email, position, branch=None, teacher_hourly_rate=""):
        self.client.force_login(self.dg)
        payload = {
            "first_name": "Awa",
            "last_name": position.replace("_", " ").title(),
            "professional_email": email,
            "position": position,
            "salary_base": "125000",
            "teacher_hourly_rate": teacher_hourly_rate,
            "generate_access": "on",
            "send_access_email": "on",
        }
        if branch is not None:
            payload["branch"] = str(branch.id)
        with patch("portal.dg.rh_service.send_mail") as send_mail:
            response = self.client.post(reverse("accounts_portal:dg_recruit_staff"), payload)
        self.assertEqual(response.status_code, 200, response.content.decode())
        send_mail.assert_called_once()
        user = get_user_model().objects.get(email=email)
        user.set_password(self.password)
        user.save(update_fields=["password"])
        return user

    def _staff_action(self, user, action, **extra):
        self.client.force_login(self.dg)
        payload = {
            "profile_id": user.profile.id,
            "action": action,
            "reason": "Décision RH ciblée et documentée.",
            **extra,
        }
        response = self.client.post(reverse("accounts_portal:dg_staff_action"), payload)
        self.assertEqual(response.status_code, 200, response.content.decode())
        self.assertTrue(response.json()["ok"])
        return response

    def test_director_recruitment_without_branch_then_assignment_suspend_and_reactivate(self):
        staff = self._recruit(
            email="de.sans.annexe@example.test",
            position="director_of_studies",
        )
        staff.refresh_from_db()
        self.assertEqual(get_user_position(staff), "director_of_studies")
        self.assertIsNone(get_user_annexe(staff))
        self.assertEqual(staff.groups.get().name, "director_of_studies")
        self.assertIsNone(InstitutionalProfile.objects.get(user=staff).branch_id)

        self.client.logout()
        self.assertTrue(self.client.login(username=staff.username, password=self.password))
        home = self.client.get(reverse("accounts_portal:portal_home"))
        self.assertRedirects(
            home,
            reverse("accounts_portal:access_regularization"),
            fetch_redirect_response=False,
        )
        direct = self.client.get(reverse("accounts_portal:portal_director"))
        self.assertRedirects(
            direct,
            reverse("accounts_portal:access_regularization"),
            fetch_redirect_response=False,
        )
        regularization = self.client.get(reverse("accounts_portal:access_regularization"))
        self.assertEqual(regularization.status_code, 403)
        self.assertContains(regularization, "aucune annexe", status_code=403)
        self.assertContains(regularization, "Aucun accès aux données d’une autre annexe", status_code=403)

        self._staff_action(
            staff,
            "update_assignment",
            position="director_of_studies",
            branch=str(self.branch.id),
        )
        staff.refresh_from_db()
        self.assertEqual(get_user_annexe(staff), self.branch)
        self.assertEqual(InstitutionalProfile.objects.get(user=staff).branch, self.branch)

        self.client.logout()
        self.assertTrue(self.client.login(username=staff.username, password=self.password))
        dashboard = self.client.get(reverse("accounts_portal:portal_home"), follow=True)
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(dashboard.context["branch"], self.branch)

        self._staff_action(staff, "suspend")
        staff.refresh_from_db()
        self.assertFalse(staff.is_active)
        self.client.logout()
        self.assertFalse(self.client.login(username=staff.username, password=self.password))

        self._staff_action(staff, "reactivate")
        staff.refresh_from_db()
        self.assertTrue(staff.is_active)
        self.client.logout()
        self.assertTrue(self.client.login(username=staff.username, password=self.password))

    def test_second_existing_role_uses_same_recruitment_and_router(self):
        staff = self._recruit(
            email="it.rh@example.test",
            position="it_support",
            branch=self.branch,
        )
        self.assertEqual(get_user_position(staff), "it_support")
        self.assertEqual(get_user_annexe(staff), self.branch)
        self.assertEqual(staff.groups.get().name, "it_support")

        self.client.logout()
        self.assertTrue(self.client.login(username=staff.username, password=self.password))
        response = self.client.get(reverse("accounts_portal:portal_home"))
        self.assertRedirects(
            response,
            reverse("accounts_portal:portal_it_v2"),
            fetch_redirect_response=False,
        )

    def test_dg_can_create_edit_and_deactivate_branch_but_regular_staff_cannot(self):
        self.client.force_login(self.dg)
        create_response = self.client.post(
            reverse("accounts_portal:dg_branch_save"),
            {
                "name": "Annexe Kalaban DG",
                "code": "KDG",
                "slug": "kalaban-dg",
                "city": "Bamako",
                "is_active": "on",
                "accepts_online_registration": "on",
            },
        )
        self.assertEqual(create_response.status_code, 200, create_response.content.decode())
        branch = Branch.objects.get(code="KDG")
        self.assertTrue(branch.is_active)

        edit_response = self.client.post(
            reverse("accounts_portal:dg_branch_save"),
            {
                "branch_id": str(branch.id),
                "name": "Annexe Kalaban DG actualisée",
                "code": "KDG",
                "slug": "kalaban-dg",
                "city": "Bamako",
                "accepts_online_registration": "on",
            },
        )
        self.assertEqual(edit_response.status_code, 200, edit_response.content.decode())
        branch.refresh_from_db()
        self.assertFalse(branch.is_active)
        self.assertTrue(
            SupportAuditLog.objects.filter(
                branch=branch,
                actor=self.dg,
                action_type=SupportAuditLog.ACTION_BRANCH_SETTINGS_UPDATED,
            ).exists()
        )

        ordinary = self._recruit(
            email="secretariat.rh@example.test",
            position="secretary",
            branch=self.branch,
        )
        self.client.force_login(ordinary)
        denied = self.client.post(
            reverse("accounts_portal:dg_branch_save"),
            {"name": "Interdite", "code": "NON", "slug": "interdite", "city": "Bamako"},
        )
        self.assertEqual(denied.status_code, 403)
        self.assertFalse(Branch.objects.filter(code="NON").exists())

    def test_role_and_branch_update_stays_synchronized_and_audited(self):
        staff = self._recruit(
            email="enseignant.rh@example.test",
            position="teacher",
            branch=self.branch,
            teacher_hourly_rate="9000",
        )
        self.assertEqual(staff.profile.teacher_hourly_rate, 9000)
        self._staff_action(
            staff,
            "update_assignment",
            position="secretary",
            branch=str(self.branch.id),
        )
        staff.refresh_from_db()
        staff.profile.refresh_from_db()
        institutional = InstitutionalProfile.objects.get(user=staff)
        self.assertEqual(staff.profile.position, "secretary")
        self.assertEqual(institutional.position, "secretary")
        self.assertEqual(list(staff.groups.values_list("name", flat=True)), ["secretary"])
        self.assertTrue(
            SupportAuditLog.objects.filter(
                target_user=staff,
                action_type=SupportAuditLog.ACTION_STAFF_ASSIGNED,
            ).exists()
        )
