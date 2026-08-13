from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.test_manager_workflows import (
    _create_branch,
    _create_candidature,
    _create_programme,
    _create_user,
)
from inscriptions.models import Inscription
from payments.models import Payment, PaymentAgent


@override_settings(
    AUTH_POLICY_V2_ENABLED=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class ManagerFinanceWorkspaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.branch = _create_branch(code="FIN", name="Annexe Finance")
        cls.other_branch = _create_branch(code="AUT", name="Autre Annexe")
        cls.programme = _create_programme()
        cls.finance_manager = _create_user(
            "finance_workspace",
            branch=cls.branch,
            position="finance_manager",
        )
        cls.payment_agent_user = _create_user(
            "payment_agent_workspace",
            branch=cls.branch,
            position="payment_agent",
        )
        PaymentAgent.objects.create(
            user=cls.finance_manager,
            branch=cls.branch,
            agent_code="FIN001",
            is_active=True,
        )
        PaymentAgent.objects.create(
            user=cls.payment_agent_user,
            branch=cls.branch,
            agent_code="AGT001",
            is_active=True,
        )

        candidature = _create_candidature(
            cls.programme,
            cls.branch,
            email="finance-student@example.com",
            status="accepted",
        )
        cls.inscription = Inscription.objects.create(
            candidature=candidature,
            amount_due=500000,
            amount_paid=0,
            status=Inscription.STATUS_AWAITING_PAYMENT,
        )
        cls.payment = Payment.objects.create(
            inscription=cls.inscription,
            amount=100000,
            method=Payment.METHOD_CASH,
        )

        other_candidature = _create_candidature(
            cls.programme,
            cls.other_branch,
            email="other-student@example.com",
            status="accepted",
        )
        other_inscription = Inscription.objects.create(
            candidature=other_candidature,
            amount_due=300000,
            amount_paid=0,
            status=Inscription.STATUS_AWAITING_PAYMENT,
        )
        cls.other_payment = Payment.objects.create(
            inscription=other_inscription,
            amount=50000,
            method=Payment.METHOD_ORANGE,
        )

    def test_finance_route_uses_shared_manager_workspace_and_branch_scope(self):
        self.client.force_login(self.finance_manager)

        response = self.client.get(reverse("accounts_portal:portal_finance"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/dashboard/manager_dashboard.html")
        self.assertTemplateNotUsed(response, "accounts/dashboard/finance.html")
        self.assertEqual(response.context["active_section"], "paiements")
        self.assertEqual(response.context["dashboard_shell"]["key"], "manager")
        self.assertEqual(response.context["dashboard_shell"]["role"], "finance_manager")
        navigation_keys = {
            item["nav_key"]
            for group in response.context["dashboard_shell"]["navigation"]
            for item in group["items"]
        }
        self.assertEqual(navigation_keys, {"paiements", "settings", "reenrollment"})
        self.assertContains(response, 'data-ui-core="filter-bar"')
        self.assertContains(response, 'data-ui-core="data-table"')
        self.assertContains(response, 'data-ui-core="modal"', count=1)
        self.assertNotContains(response, 'id="modal-container"')
        self.assertContains(response, self.payment.reference)
        self.assertNotContains(response, self.other_payment.reference)

        account_response = self.client.get(
            reverse("accounts_portal:portal_finance"),
            {"section": "settings"},
        )
        self.assertEqual(account_response.status_code, 200)
        self.assertContains(account_response, "Responsable finance")
        self.assertContains(account_response, 'data-dashboard-section="settings"')

    def test_finance_manager_can_validate_only_own_branch_payment(self):
        self.client.force_login(self.finance_manager)

        response = self.client.post(
            reverse("accounts:htmx_payment_validate", args=[self.payment.pk]),
            HTTP_HX_REQUEST="true",
        )
        foreign_response = self.client.post(
            reverse("accounts:htmx_payment_validate", args=[self.other_payment.pk]),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(foreign_response.status_code, 404)
        self.payment.refresh_from_db()
        self.other_payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.STATUS_VALIDATED)
        self.assertEqual(self.other_payment.status, Payment.STATUS_PENDING)

    def test_payment_agent_can_view_but_cannot_correct(self):
        self.payment.status = Payment.STATUS_VALIDATED
        self.payment.save(update_fields=["status"])
        self.client.force_login(self.payment_agent_user)

        detail = self.client.get(
            reverse("accounts:htmx_payment_detail", args=[self.payment.pk]),
            HTTP_HX_REQUEST="true",
        )
        correction = self.client.post(
            reverse("accounts:htmx_payment_correct", args=[self.payment.pk]),
            {"new_amount": "90000", "reason": "Test", "confirmation": "CORRIGER"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(detail.status_code, 200)
        self.assertNotContains(detail, "Correction controlee")
        self.assertEqual(correction.status_code, 403)

    def test_finance_role_cannot_call_non_finance_manager_workflow(self):
        self.client.force_login(self.finance_manager)

        response = self.client.post(reverse("accounts:htmx_manager_cash_sync"))

        self.assertEqual(response.status_code, 403)
