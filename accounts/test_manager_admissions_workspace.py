from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.test_manager_workflows import (
    _create_branch,
    _create_academic_class,
    _create_candidature,
    _create_positioning_fee,
    _create_programme,
    _create_user,
)
from inscriptions.models import Inscription
from payments.models import Payment


@override_settings(
    AUTH_POLICY_V2_ENABLED=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class ManagerAdmissionsWorkspaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.branch = _create_branch(code="ADM", name="Annexe Admissions")
        cls.other_branch = _create_branch(code="ADX", name="Autre Annexe Admissions")
        cls.programme = _create_programme()
        cls.admissions_user = _create_user(
            "admissions_workspace",
            branch=cls.branch,
            position="admissions",
        )
        cls.candidature = _create_candidature(
            cls.programme,
            cls.branch,
            first_name="Awa",
            last_name="Admissions",
            email="awa-admissions@example.com",
            status="submitted",
        )
        cls.other_candidature = _create_candidature(
            cls.programme,
            cls.other_branch,
            first_name="Moussa",
            last_name="Externe",
            email="moussa-externe@example.com",
            status="submitted",
        )
        enrolled_candidature = _create_candidature(
            cls.programme,
            cls.branch,
            first_name="Fatou",
            last_name="Inscrite",
            email="fatou-inscrite@example.com",
            status="accepted",
        )
        cls.inscription = Inscription.objects.create(
            candidature=enrolled_candidature,
            amount_due=400000,
            amount_paid=0,
            status=Inscription.STATUS_AWAITING_PAYMENT,
        )
        cls.payment = Payment.objects.create(
            inscription=cls.inscription,
            amount=50000,
            method=Payment.METHOD_ORANGE,
        )

    def test_admissions_route_uses_shared_manager_workspace_and_branch_scope(self):
        self.client.force_login(self.admissions_user)

        response = self.client.get(reverse("accounts_portal:portal_admissions"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/dashboard/manager_dashboard.html")
        self.assertTemplateNotUsed(response, "accounts/dashboard/admissions.html")
        self.assertEqual(response.context["active_section"], "candidatures")
        self.assertEqual(response.context["dashboard_shell"]["key"], "manager")
        self.assertEqual(response.context["dashboard_shell"]["role"], "admissions")
        navigation_keys = {
            item["nav_key"]
            for group in response.context["dashboard_shell"]["navigation"]
            for item in group["items"]
        }
        self.assertEqual(navigation_keys, {"candidatures", "inscriptions", "settings"})
        self.assertContains(response, 'data-ui-core="filter-bar"')
        self.assertContains(response, 'data-ui-core="data-table"')
        self.assertContains(response, 'data-ui-core="modal"', count=1)
        self.assertNotContains(response, 'id="modal-container"')
        self.assertContains(response, self.candidature.email)
        self.assertNotContains(response, self.other_candidature.email)

    def test_admissions_can_process_only_own_branch_candidature(self):
        self.client.force_login(self.admissions_user)

        response = self.client.post(
            reverse("accounts:htmx_candidature_under_review", args=[self.candidature.pk]),
            HTTP_HX_REQUEST="true",
        )
        foreign_response = self.client.post(
            reverse("accounts:htmx_candidature_under_review", args=[self.other_candidature.pk]),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(foreign_response.status_code, 404)
        self.candidature.refresh_from_db()
        self.other_candidature.refresh_from_db()
        self.assertEqual(self.candidature.status, "under_review")
        self.assertEqual(self.other_candidature.status, "submitted")

    def test_inscription_detail_is_read_only_for_finance_actions(self):
        self.client.force_login(self.admissions_user)

        response = self.client.get(
            reverse("accounts:htmx_inscription_detail", args=[self.inscription.pk]),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Appliquer un coupon")
        self.assertNotContains(response, "Paiement en espece")
        self.assertNotContains(response, "Corriger paiement")

    def test_admissions_role_cannot_call_finance_workflow(self):
        self.client.force_login(self.admissions_user)

        response = self.client.post(
            reverse("accounts:htmx_payment_validate", args=[self.payment.pk]),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 403)

    def test_admissions_can_create_scoped_inscription(self):
        _create_positioning_fee(self.programme, level="L1", amount=125000)
        academic_class = _create_academic_class(self.programme, self.branch, level="L1")
        candidature = _create_candidature(
            self.programme,
            self.branch,
            first_name="Oumar",
            last_name="Nouveau",
            email="oumar-nouveau@example.com",
            status="accepted",
        )
        self.client.force_login(self.admissions_user)

        response = self.client.post(
            reverse("accounts:htmx_inscription_create", args=[candidature.pk]),
            {"academic_level": "L1", "academic_class": str(academic_class.pk)},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        inscription = Inscription.objects.get(candidature=candidature)
        self.assertEqual(inscription.candidature.branch, self.branch)
        self.assertEqual(inscription.amount_due, 125000)

    def test_admissions_account_context_uses_real_role(self):
        self.client.force_login(self.admissions_user)

        response = self.client.get(
            reverse("accounts_portal:portal_admissions"),
            {"section": "settings"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Responsable des admissions")
        self.assertContains(response, 'data-dashboard-section="settings"')
