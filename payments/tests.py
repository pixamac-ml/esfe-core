from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Profile
from admissions.models import Candidature
from branches.models import Branch
from formations.models import Cycle, Diploma, Filiere, Programme
from inscriptions.models import Inscription
from payments.models import CashPaymentSession, Payment, PaymentAgent
from students.models import Student


User = get_user_model()


class StudentPaymentViewTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            name="Annexe Paiement",
            code="PAY",
            slug="annexe-paiement",
        )
        self.cycle = Cycle.objects.create(
            name="Licence Paiement",
            theme="accent",
            min_duration_years=1,
            max_duration_years=5,
        )
        self.diploma = Diploma.objects.create(
            name="Diplome Paiement",
            level="superieur",
        )
        self.filiere = Filiere.objects.create(name="Filiere Paiement")
        self.programme = Programme.objects.create(
            title="Programme Paiement",
            filiere=self.filiere,
            cycle=self.cycle,
            diploma_awarded=self.diploma,
            duration_years=3,
            short_description="Programme paiement",
            description="Description paiement",
        )
        self.candidature = Candidature.objects.create(
            programme=self.programme,
            branch=self.branch,
            academic_year="2025-2026",
            entry_year=1,
            first_name="Awa",
            last_name="Diallo",
            birth_date="2001-01-01",
            birth_place="Bamako",
            gender="female",
            phone="70000001",
            email="awa.diallo@example.com",
            status="accepted",
        )
        self.inscription = Inscription.objects.create(
            candidature=self.candidature,
            amount_due=100000,
            status=Inscription.STATUS_CREATED,
        )
        session = self.client.session
        session[f"inscription_access_{self.inscription.id}"] = True
        session.save()

    @patch("payments.models.send_payment_confirmation_email")
    @patch("payments.models.send_student_credentials_email")
    @patch("payments.forms.validate_cash_code")
    @patch("payments.forms.verify_agent_and_create_session")
    def test_cash_payment_is_created_pending_and_does_not_create_student(
        self,
        verify_agent,
        validate_cash_code,
        send_credentials,
        send_confirmation,
    ):
        agent_user = User.objects.create_user(username="agent_cash", password="pass1234", is_staff=True)
        agent = PaymentAgent.objects.create(user=agent_user, branch=self.branch, is_active=True)
        cash_session = CashPaymentSession.objects.create(
            inscription=self.inscription,
            agent=agent,
            verification_code="123456",
            expires_at=self.inscription.created_at,
            is_used=False,
        )
        verify_agent.return_value = (agent, None)
        validate_cash_code.return_value = (cash_session, None)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("payments:student_initiate", args=[self.inscription.public_token]),
                {
                    "method": Payment.METHOD_CASH,
                    "agent_name": "Agent Cash",
                    "verification_code": "123456",
                    "amount": "25000",
                },
                HTTP_HX_REQUEST="true",
            )

        self.assertEqual(response.status_code, 200)
        payment = Payment.objects.get(inscription=self.inscription)
        self.inscription.refresh_from_db()
        self.assertEqual(payment.status, Payment.STATUS_PENDING)
        self.assertEqual(self.inscription.status, Inscription.STATUS_AWAITING_PAYMENT)
        self.assertFalse(Student.objects.filter(inscription=self.inscription).exists())
        send_credentials.assert_not_called()
        send_confirmation.assert_not_called()

    @patch("payments.models.send_payment_confirmation_email")
    @patch("payments.models.send_student_credentials_email")
    def test_non_cash_payment_stays_pending(self, send_credentials, send_confirmation):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("payments:student_initiate", args=[self.inscription.public_token]),
                {
                    "method": Payment.METHOD_ORANGE,
                    "amount": "25000",
                },
                HTTP_HX_REQUEST="true",
            )

        self.assertEqual(response.status_code, 200)
        payment = Payment.objects.get(inscription=self.inscription)
        self.inscription.refresh_from_db()
        self.assertEqual(payment.status, Payment.STATUS_PENDING)
        self.assertEqual(self.inscription.status, Inscription.STATUS_AWAITING_PAYMENT)
        self.assertFalse(Student.objects.filter(inscription=self.inscription).exists())
        send_credentials.assert_not_called()
        send_confirmation.assert_not_called()

    @patch("payments.models.send_payment_confirmation_email")
    @patch("payments.models.send_student_credentials_email")
    def test_admin_validation_marks_payment_validated_and_creates_student(self, send_credentials, send_confirmation):
        payment = Payment.objects.create(
            inscription=self.inscription,
            amount=25000,
            method=Payment.METHOD_CASH,
            status=Payment.STATUS_PENDING,
            reference="INITIATED_BY_STUDENT",
        )
        self.inscription.status = Inscription.STATUS_AWAITING_PAYMENT
        self.inscription.save(update_fields=["status"])

        finance_user = User.objects.create_user(
            username="finance_user",
            password="pass1234",
            is_staff=True,
        )
        profile = finance_user.profile
        profile.role = "finance"
        profile.branch = self.branch
        profile.save(update_fields=["role", "branch", "updated_at"])
        self.client.force_login(finance_user)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("accounts:validate_payment_htmx", args=[payment.id]),
                HTTP_HX_REQUEST="true",
            )

        self.assertEqual(response.status_code, 200)
        payment.refresh_from_db()
        self.inscription.refresh_from_db()
        self.assertEqual(payment.status, Payment.STATUS_VALIDATED)
        self.assertEqual(self.inscription.status, Inscription.STATUS_PARTIAL)
        student = Student.objects.select_related("user__profile").get(inscription=self.inscription)
        self.assertEqual(student.user.profile.role, "student")
        send_credentials.assert_called_once()
        send_confirmation.assert_not_called()
