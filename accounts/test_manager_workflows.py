"""Tests critiques pour le dashboard gestionnaire — workflows métier."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, cast

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from branches.models import Branch
from admissions.models import Candidature
from inscriptions.models import Inscription
from formations.models import Programme, Cycle, Diploma, Filiere
from accounts.models import (
    BranchCashMovement,
    BranchExpense,
    BranchMonthlyClosure,
    Donation,
    PayrollEntry,
    TeacherHonorariumEntry,
    Profile,
)
from payments.models import CashPaymentSession, Payment, PaymentAgent


User = get_user_model()
USER_MANAGER = cast(Any, User._default_manager)


def _create_user(username, groups=None, branch=None, position="branch_manager", **kw):
    user = USER_MANAGER.create_user(
        username=username, email=f"{username}@test.com", password="pass1234", **kw,
    )
    if groups:
        for name in groups:
            g, _ = Group.objects.get_or_create(name=name)
            user.groups.add(g)
    if branch:
        profile = user.profile
        profile.branch = branch
        profile.position = position
        profile.save(update_fields=["branch", "position", "updated_at"])
    return user


def _create_branch(code="TST", name="Test Annexe"):
    return Branch.objects.create(name=name, code=code, slug=f"annexe-{code.lower()}")


def _login(client, user):
    client.force_login(user)


def _create_programme():
    cycle = Cycle.objects.create(name="Licence", min_duration_years=3, max_duration_years=4)
    diploma = Diploma.objects.create(name="Licence Pro", level="superieur")
    filiere = Filiere.objects.create(name="Informatique")
    return Programme.objects.create(
        title="LP Informatique",
        filiere=filiere,
        cycle=cycle,
        diploma_awarded=diploma,
        duration_years=3,
        short_description="Formation en informatique",
        description="Formation en informatique de niveau licence",
    )


def _create_candidature(programme, branch, **kw):
    defaults = dict(
        first_name="Jean",
        last_name="Test",
        email="jean@test.com",
        phone="70000000",
        birth_date=date(2000, 1, 1),
        birth_place="Bamako",
        gender="male",
        academic_year="2025-2026",
    )
    defaults.update(kw)
    return Candidature.objects.create(programme=programme, branch=branch, **defaults)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}},
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class ManagerCandidatureWorkflowTests(TestCase):
    """Workflow candidature : soumettre → analyser → accepter/rejeter."""

    def setUp(self):
        self.branch = _create_branch()
        self.manager = _create_user("mgr_cand", groups=["gestionnaire"], branch=self.branch)
        self.programme = _create_programme()
        self.candidature = _create_candidature(self.programme, self.branch, status="submitted")
        _login(self.client, self.manager)

    def test_candidature_under_review(self):
        url = reverse("accounts:htmx_candidature_under_review", args=[self.candidature.id])
        response = self.client.post(url, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.candidature.refresh_from_db()
        self.assertEqual(self.candidature.status, "under_review")
        self.assertIn("HX-Trigger", response.headers)
        self.assertIn("showToast", response.headers["HX-Trigger"])

    def test_candidature_accept(self):
        self.candidature.status = "under_review"
        self.candidature.save()
        url = reverse("accounts:htmx_candidature_accept", args=[self.candidature.id])
        response = self.client.post(url, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.candidature.refresh_from_db()
        self.assertEqual(self.candidature.status, "accepted")
        self.assertIn("showToast", response.headers["HX-Trigger"])

    def test_candidature_reject_with_reason(self):
        url = reverse("accounts:htmx_candidature_reject", args=[self.candidature.id])
        response = self.client.post(url, {"reason": "Dossier incomplet"}, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.candidature.refresh_from_db()
        self.assertEqual(self.candidature.status, "rejected")
        self.assertIn("Dossier incomplet", self.candidature.rejection_reason)
        self.assertIn("showToast", response.headers["HX-Trigger"])

    def test_candidature_delete_only_when_rejected(self):
        """Ne peut supprimer qu'une candidature rejetee."""
        url = reverse("accounts:htmx_candidature_delete", args=[self.candidature.id])
        response = self.client.post(url, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 400)

    def test_candidature_delete_when_rejected(self):
        self.candidature.status = "rejected"
        self.candidature.rejection_reason = "Test"
        self.candidature.save()
        url = reverse("accounts:htmx_candidature_delete", args=[self.candidature.id])
        response = self.client.post(url, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class ManagerPaymentWorkflowTests(TestCase):
    """Workflow paiement : valider, annuler."""

    def setUp(self):
        self.branch = _create_branch()
        self.manager = _create_user("mgr_pay", groups=["gestionnaire"], branch=self.branch)
        self.programme = _create_programme()
        self.candidature = _create_candidature(self.programme, self.branch, status="accepted")
        self.inscription = Inscription.objects.create(
            candidature=self.candidature,
            amount_due=500000,
            amount_paid=0,
        )
        self.inscription.status = Inscription.STATUS_AWAITING_PAYMENT
        self.inscription.save(update_fields=["status"])
        PaymentAgent.objects.create(
            user=self.manager, branch=self.branch, agent_code="AGT001", is_active=True,
        )
        self.payment = Payment.objects.create(
            inscription=self.inscription,
            amount=100000,
            method=Payment.METHOD_CASH,
        )
        _login(self.client, self.manager)

    def test_payment_validate_credits_caisse(self):
        url = reverse("accounts:htmx_payment_validate", args=[self.payment.id])
        response = self.client.post(url, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "validated")
        self.assertIn("showToast", response.headers["HX-Trigger"])
        movements = BranchCashMovement.objects.filter(
            branch=self.branch, source=BranchCashMovement.SOURCE_STUDENT_PAYMENT,
        )
        self.assertEqual(movements.count(), 1)
        self.assertEqual(movements.first().amount, 100000)

    def test_payment_cancel(self):
        url = reverse("accounts:htmx_payment_cancel", args=[self.payment.id])
        response = self.client.post(url, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "cancelled")
        self.assertIn("showToast", response.headers["HX-Trigger"])


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class ManagerExpenseWorkflowTests(TestCase):
    """Workflow depense : creer, approuver, payer."""

    def setUp(self):
        self.branch = _create_branch()
        self.manager = _create_user("mgr_exp", groups=["gestionnaire"], branch=self.branch)
        self.expense = BranchExpense.objects.create(
            branch=self.branch,
            title="Fournitures bureau",
            category="supplies",
            amount=50000,
            created_by=self.manager,
        )
        _login(self.client, self.manager)

    def test_expense_approve_changes_status(self):
        url = reverse("accounts:htmx_manager_expense_approve", args=[self.expense.id])
        response = self.client.post(url, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertIn("HX-Redirect", response.headers)
        self.expense.refresh_from_db()
        self.assertEqual(self.expense.status, "approved")

    def test_expense_pay_creates_cash_movement(self):
        self.expense.status = BranchExpense.STATUS_APPROVED
        self.expense.save()
        url = reverse("accounts:htmx_manager_expense_pay", args=[self.expense.id])
        response = self.client.post(url, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.expense.refresh_from_db()
        self.assertEqual(self.expense.status, "paid")
        movements = BranchCashMovement.objects.filter(
            branch=self.branch, source=BranchCashMovement.SOURCE_EXPENSE,
        )
        self.assertEqual(movements.count(), 1)
        self.assertEqual(movements.first().amount, 50000)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class ManagerDonationWorkflowTests(TestCase):
    """Workflow don : creer → mouvement caisse + HX-Trigger."""

    def setUp(self):
        self.branch = _create_branch()
        self.manager = _create_user("mgr_don", groups=["gestionnaire"], branch=self.branch)
        _login(self.client, self.manager)

    def test_donation_creates_cash_movement_and_toast(self):
        url = reverse("accounts:htmx_manager_donation_create")
        response = self.client.post(url, {
            "donor_name": "Bienfaiteur X",
            "amount": 100000,
            "date": date.today().isoformat(),
            "motif": "mecenat",
            "payment_method": "cash",
        }, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Donation.objects.filter(branch=self.branch, amount=100000).exists())
        self.assertTrue(
            BranchCashMovement.objects.filter(
                branch=self.branch, source=BranchCashMovement.SOURCE_DONATION, amount=100000,
            ).exists(),
        )
        self.assertIn("showToast", response.headers["HX-Trigger"])


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class ManagerAccessControlTests(TestCase):
    """Teste les permissions et le filtrage branche."""

    def setUp(self):
        self.branch_a = _create_branch("BRA", "Branche A")
        self.branch_b = _create_branch("BRB", "Branche B")
        self.manager_a = _create_user("mgr_a", groups=["gestionnaire"], branch=self.branch_a)
        self.manager_b = _create_user("mgr_b", groups=["gestionnaire"], branch=self.branch_b)
        self.programme = _create_programme()
        self.cand_a = _create_candidature(
            self.programme, self.branch_a,
            first_name="Alice", last_name="A", email="alice@a.com", phone="70000002",
        )
        self.cand_b = _create_candidature(
            self.programme, self.branch_b,
            first_name="Bob", last_name="B", email="bob@b.com", phone="70000003",
        )

    def test_manager_a_cannot_see_branch_b_candidatures(self):
        _login(self.client, self.manager_a)
        response = self.client.get(
            reverse("accounts:manager_dashboard"),
            {"section": "candidatures"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alice")
        self.assertNotContains(response, "Bob")

    def test_unauthorized_user_gets_403(self):
        stranger = _create_user("stranger")
        _login(self.client, stranger)
        url = reverse("accounts:htmx_candidature_under_review", args=[self.cand_a.id])
        response = self.client.post(url, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 403)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class ManagerDashboardViewTests(TestCase):
    """Teste le rendu du dashboard principal."""

    def setUp(self):
        self.branch = _create_branch()
        self.manager = _create_user("mgr_view", groups=["gestionnaire"], branch=self.branch)
        _login(self.client, self.manager)

    def test_overview_renders(self):
        response = self.client.get(reverse("accounts:manager_dashboard"), {"section": "overview"})
        self.assertEqual(response.status_code, 200)

    def test_candidatures_section_renders(self):
        response = self.client.get(reverse("accounts:manager_dashboard"), {"section": "candidatures"})
        self.assertEqual(response.status_code, 200)

    def test_inscriptions_section_renders(self):
        response = self.client.get(reverse("accounts:manager_dashboard"), {"section": "inscriptions"})
        self.assertEqual(response.status_code, 200)

    def test_paiements_section_renders(self):
        response = self.client.get(reverse("accounts:manager_dashboard"), {"section": "paiements"})
        self.assertEqual(response.status_code, 200)

    def test_depenses_section_renders(self):
        response = self.client.get(reverse("accounts:manager_dashboard"), {"section": "depenses"})
        self.assertEqual(response.status_code, 200)

    def test_caisse_section_renders(self):
        response = self.client.get(reverse("accounts:manager_dashboard"), {"section": "caisse"})
        self.assertEqual(response.status_code, 200)

    def test_rapport_section_renders(self):
        response = self.client.get(reverse("accounts:manager_dashboard"), {"section": "rapport"})
        self.assertEqual(response.status_code, 200)

    def test_cloture_section_renders(self):
        response = self.client.get(reverse("accounts:manager_dashboard"), {"section": "cloture"})
        self.assertEqual(response.status_code, 200)

    def test_dons_section_renders(self):
        response = self.client.get(reverse("accounts:manager_dashboard"), {"section": "dons"})
        self.assertEqual(response.status_code, 200)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class ManagerExportReportTests(TestCase):
    """Teste l'export Excel."""

    def setUp(self):
        self.branch = _create_branch()
        self.manager = _create_user("mgr_xls", groups=["gestionnaire"], branch=self.branch)
        _login(self.client, self.manager)

    def test_export_xlsx_returns_file(self):
        url = reverse("accounts:manager_export_report_xlsx")
        response = self.client.get(f"{url}?section=rapport&report_period=month")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}},
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class ManagerSalaryWorkflowTests(TestCase):
    """Workflow salaires : preparer, payer, avance, notifier."""

    def setUp(self):
        self.branch = _create_branch()
        self.manager = _create_user("mgr_sal", groups=["gestionnaire"], branch=self.branch)
        profile = self.manager.profile
        profile.salary_base = 300000
        profile.save(update_fields=["salary_base", "updated_at"])
        self.period_month = date.today().replace(day=1)
        _login(self.client, self.manager)

    def _seed_cash(self, amount=500000):
        BranchCashMovement.objects.create(
            branch=self.branch,
            movement_type=BranchCashMovement.TYPE_IN,
            source=BranchCashMovement.SOURCE_MANUAL,
            amount=amount,
            label="Solde initial",
            created_by=self.manager,
        )

    def test_salary_prepare_all_creates_entry(self):
        url = reverse("accounts:htmx_manager_salary_prepare_all")
        response = self.client.post(
            url, {"period_month": self.period_month.isoformat()}, HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        entry = PayrollEntry.objects.get(
            branch=self.branch, employee=self.manager, period_month=self.period_month,
        )
        self.assertEqual(entry.base_salary, 300000)
        self.assertEqual(entry.status, PayrollEntry.STATUS_DRAFT)

    def test_salary_pay_creates_cash_movement(self):
        self._seed_cash(500000)
        entry = PayrollEntry.objects.get(
            branch=self.branch, employee=self.manager, period_month=self.period_month,
        )
        entry.status = PayrollEntry.STATUS_READY
        entry.save()
        url = reverse("accounts:htmx_manager_salary_pay", args=[entry.id])
        response = self.client.post(url, {"payment_amount": "100000"}, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        entry.refresh_from_db()
        self.assertEqual(entry.paid_amount, 100000)
        self.assertTrue(
            BranchCashMovement.objects.filter(
                branch=self.branch, source=BranchCashMovement.SOURCE_PAYROLL, amount=100000,
            ).exists()
        )

    def test_salary_pay_rejected_when_caisse_insufficient(self):
        entry = PayrollEntry.objects.get(
            branch=self.branch, employee=self.manager, period_month=self.period_month,
        )
        entry.status = PayrollEntry.STATUS_READY
        entry.save()
        url = reverse("accounts:htmx_manager_salary_pay", args=[entry.id])
        response = self.client.post(url, {"payment_amount": "100000"}, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 400)
        entry.refresh_from_db()
        self.assertEqual(entry.paid_amount, 0)

    def test_salary_advance_creates_draft_entry_and_cash_movement(self):
        self._seed_cash(500000)
        url = reverse("accounts:htmx_manager_salary_advance", args=[self.manager.id])
        response = self.client.post(
            url,
            {"advance_amount": "50000", "period_month": self.period_month.isoformat()},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        entry = PayrollEntry.objects.get(
            branch=self.branch, employee=self.manager, period_month=self.period_month,
        )
        self.assertEqual(entry.advances, 50000)
        self.assertEqual(entry.status, PayrollEntry.STATUS_DRAFT)
        self.assertTrue(
            BranchCashMovement.objects.filter(
                branch=self.branch, source=BranchCashMovement.SOURCE_PAYROLL, amount=50000,
            ).exists()
        )

    def test_salary_pay_ready_all_notifies_employee(self):
        entry = PayrollEntry.objects.get(
            branch=self.branch, employee=self.manager, period_month=self.period_month,
        )
        entry.status = PayrollEntry.STATUS_READY
        entry.save()
        url = reverse("accounts:htmx_manager_salary_pay_ready_all")
        response = self.client.post(
            url, {"period_month": self.period_month.isoformat()}, HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("salaires_disponibles_1", response.headers["HX-Redirect"])


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}},
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class ManagerHonorariumWorkflowTests(TestCase):
    """Workflow honoraires enseignants : preparer, payer."""

    def setUp(self):
        self.branch = _create_branch()
        self.manager = _create_user("mgr_hon", groups=["gestionnaire"], branch=self.branch)
        self.teacher = _create_user("teacher_hon", branch=self.branch, position="teacher")
        profile = self.teacher.profile
        profile.teacher_hourly_rate = 5000
        profile.save(update_fields=["teacher_hourly_rate", "updated_at"])
        self.period_month = date.today().replace(day=1)
        _login(self.client, self.manager)

    def _seed_cash(self, amount=500000):
        BranchCashMovement.objects.create(
            branch=self.branch,
            movement_type=BranchCashMovement.TYPE_IN,
            source=BranchCashMovement.SOURCE_MANUAL,
            amount=amount,
            label="Solde initial",
            created_by=self.manager,
        )

    def test_teacher_honorarium_prepare_all_creates_entry(self):
        url = reverse("accounts:htmx_manager_teacher_honorarium_prepare_all")
        response = self.client.post(
            url, {"period_month": self.period_month.isoformat()}, HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        entry = TeacherHonorariumEntry.objects.get(
            branch=self.branch, teacher=self.teacher, period_month=self.period_month,
        )
        self.assertEqual(entry.hourly_rate, 5000)
        self.assertEqual(entry.status, TeacherHonorariumEntry.STATUS_DRAFT)

    def test_teacher_honorarium_pay_creates_cash_movement(self):
        self._seed_cash(500000)
        entry = TeacherHonorariumEntry.objects.get(
            branch=self.branch, teacher=self.teacher, period_month=self.period_month,
        )
        entry.validated_hours = Decimal("40")
        entry.status = TeacherHonorariumEntry.STATUS_READY
        entry.save()
        url = reverse("accounts:htmx_manager_teacher_honorarium_pay", args=[entry.id])
        response = self.client.post(url, {"payment_amount": "100000"}, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        entry.refresh_from_db()
        self.assertEqual(entry.paid_amount, 100000)
        self.assertTrue(
            BranchCashMovement.objects.filter(
                branch=self.branch, source=BranchCashMovement.SOURCE_HONORARIUM, amount=100000,
            ).exists()
        )


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class ManagerMonthlyClosureWorkflowTests(TestCase):
    """Workflow cloture mensuelle : brouillon -> validee -> cloturee."""

    def setUp(self):
        self.branch = _create_branch()
        self.manager = _create_user("mgr_clo", groups=["gestionnaire"], branch=self.branch)
        self.period_month = date.today().replace(day=1)
        _login(self.client, self.manager)

    def _create_closure(self):
        url = reverse("accounts:htmx_manager_monthly_closure_create")
        response = self.client.post(
            url,
            {"period_month": self.period_month.isoformat(), "notes": ""},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        return BranchMonthlyClosure.objects.get(branch=self.branch, period_month=self.period_month)

    def test_closure_create_is_draft(self):
        closure = self._create_closure()
        self.assertEqual(closure.status, BranchMonthlyClosure.STATUS_DRAFT)

    def test_closure_validate_from_draft(self):
        closure = self._create_closure()
        url = reverse("accounts:htmx_manager_monthly_closure_validate", args=[closure.id])
        response = self.client.post(url, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        closure.refresh_from_db()
        self.assertEqual(closure.status, BranchMonthlyClosure.STATUS_VALIDATED)
        self.assertEqual(closure.validated_by, self.manager)
        self.assertIsNotNone(closure.validated_at)

    def test_closure_close_from_validated(self):
        closure = self._create_closure()
        closure.status = BranchMonthlyClosure.STATUS_VALIDATED
        closure.validated_by = self.manager
        closure.validated_at = timezone.now()
        closure.save(update_fields=["status", "validated_by", "validated_at", "updated_at"])
        url = reverse("accounts:htmx_manager_monthly_closure_close", args=[closure.id])
        response = self.client.post(url, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        closure.refresh_from_db()
        self.assertEqual(closure.status, BranchMonthlyClosure.STATUS_CLOSED)
        self.assertIsNotNone(closure.closed_at)

    def test_closure_validate_fails_if_not_draft(self):
        closure = self._create_closure()
        closure.status = BranchMonthlyClosure.STATUS_CLOSED
        closure.save(update_fields=["status", "updated_at"])
        url = reverse("accounts:htmx_manager_monthly_closure_validate", args=[closure.id])
        response = self.client.post(url, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertIn("cloture_non_brouillon", response.headers["HX-Redirect"])
        closure.refresh_from_db()
        self.assertEqual(closure.status, BranchMonthlyClosure.STATUS_CLOSED)

    def test_closure_close_fails_if_not_validated(self):
        closure = self._create_closure()
        url = reverse("accounts:htmx_manager_monthly_closure_close", args=[closure.id])
        response = self.client.post(url, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertIn("cloture_non_validee", response.headers["HX-Redirect"])
        closure.refresh_from_db()
        self.assertEqual(closure.status, BranchMonthlyClosure.STATUS_DRAFT)

    def test_closure_recreate_fails_if_not_draft(self):
        closure = self._create_closure()
        closure.status = BranchMonthlyClosure.STATUS_VALIDATED
        closure.save(update_fields=["status", "updated_at"])
        url = reverse("accounts:htmx_manager_monthly_closure_create")
        response = self.client.post(
            url,
            {"period_month": self.period_month.isoformat(), "notes": ""},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 400)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class ManagerCashSessionWorkflowTests(TestCase):
    """Workflow sessions caisse : creer, finaliser, annuler."""

    def setUp(self):
        self.branch = _create_branch()
        self.manager = _create_user("mgr_cash", groups=["gestionnaire"], branch=self.branch)
        self.programme = _create_programme()
        self.candidature = _create_candidature(self.programme, self.branch, status="accepted")
        self.inscription = Inscription.objects.create(
            candidature=self.candidature,
            amount_due=500000,
            amount_paid=0,
        )
        self.inscription.status = Inscription.STATUS_AWAITING_PAYMENT
        self.inscription.save(update_fields=["status"])
        self.agent = PaymentAgent.objects.create(
            user=self.manager, branch=self.branch, agent_code="AGT002", is_active=True,
        )
        _login(self.client, self.manager)

    def test_cash_session_create(self):
        url = reverse("accounts:htmx_manager_cash_session_create", args=[self.inscription.id])
        response = self.client.post(url, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            CashPaymentSession.objects.filter(inscription=self.inscription, is_used=False).exists()
        )

    def test_cash_session_complete_creates_payment_and_cash_movement(self):
        session = CashPaymentSession.objects.create(
            inscription=self.inscription,
            agent=self.agent,
            verification_code="123456",
            expires_at=timezone.now() + timedelta(minutes=15),
        )
        url = reverse("accounts:htmx_manager_cash_session_complete", args=[session.id])
        response = self.client.post(url, {"amount": "100000"}, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        session.refresh_from_db()
        self.assertTrue(session.is_used)
        self.assertTrue(
            Payment.objects.filter(
                inscription=self.inscription, status=Payment.STATUS_VALIDATED, amount=100000,
            ).exists()
        )
        self.assertTrue(
            BranchCashMovement.objects.filter(
                branch=self.branch, source=BranchCashMovement.SOURCE_STUDENT_PAYMENT, amount=100000,
            ).exists()
        )

    def test_cash_session_cancel(self):
        session = CashPaymentSession.objects.create(
            inscription=self.inscription,
            agent=self.agent,
            verification_code="654321",
            expires_at=timezone.now() + timedelta(minutes=15),
        )
        url = reverse("accounts:htmx_manager_cash_session_cancel", args=[session.id])
        response = self.client.post(url, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        session.refresh_from_db()
        self.assertTrue(session.is_used)
