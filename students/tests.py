from io import StringIO
from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from academics.models import AcademicClass, AcademicEnrollment, AcademicYear
from admissions.models import Candidature
from branches.models import Branch
from formations.models import Cycle, Diploma, Filiere, Programme
from inscriptions.models import Inscription
from payments.models import Payment
from students.models import Student
from students.services.create_student import create_student_after_first_payment


User = get_user_model()


class StudentCreationWorkflowTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            name="Annexe Test",
            code="AT1",
            slug="annexe-test-1",
        )
        self.cycle = Cycle.objects.create(
            name="Licence Test",
            theme="accent",
            min_duration_years=1,
            max_duration_years=5,
        )
        self.diploma = Diploma.objects.create(
            name="Diplome Test",
            level="superieur",
        )
        self.filiere = Filiere.objects.create(name="Filiere Test")
        self.programme = Programme.objects.create(
            title="Programme Test",
            filiere=self.filiere,
            cycle=self.cycle,
            diploma_awarded=self.diploma,
            duration_years=3,
            short_description="Programme test",
            description="Description test",
        )
        self.candidature = Candidature.objects.create(
            programme=self.programme,
            branch=self.branch,
            academic_year="2025-2026",
            entry_year=1,
            first_name="Ali",
            last_name="Traore",
            birth_date="2000-01-01",
            birth_place="Bamako",
            gender="male",
            phone="70000000",
            email="ali.traore@example.com",
            status="accepted",
        )
        self.inscription = Inscription.objects.create(
            candidature=self.candidature,
            amount_due=100000,
            status=Inscription.STATUS_CREATED,
        )
        self.academic_year = AcademicYear.objects.create(
            name="2025-2026",
            start_date=date(2025, 10, 1),
            end_date=date(2026, 7, 31),
            is_active=True,
        )

    def _create_validated_payment(self, amount):
        with self.captureOnCommitCallbacks(execute=True):
            return Payment.objects.create(
                inscription=self.inscription,
                amount=amount,
                method=Payment.METHOD_CASH,
                status=Payment.STATUS_VALIDATED,
            )

    @patch("payments.models.send_payment_confirmation_email")
    @patch("payments.models.send_student_credentials_email")
    def test_pending_payment_does_not_create_student(self, send_credentials, send_confirmation):
        Payment.objects.create(
            inscription=self.inscription,
            amount=25000,
            method=Payment.METHOD_CASH,
            status=Payment.STATUS_PENDING,
        )

        self.assertFalse(Student.objects.filter(inscription=self.inscription).exists())
        self.assertFalse(User.objects.filter(username=f"etu_esfe{self.inscription.id}").exists())
        send_credentials.assert_not_called()
        send_confirmation.assert_not_called()

    @patch("payments.models.send_payment_confirmation_email")
    @patch("payments.models.send_student_credentials_email")
    def test_first_validated_partial_payment_creates_user_student_and_role(self, send_credentials, send_confirmation):
        self._create_validated_payment(25000)

        student = Student.objects.select_related("user__profile").get(inscription=self.inscription)
        self.inscription.refresh_from_db()
        self.assertEqual(self.inscription.status, Inscription.STATUS_PARTIAL)
        self.assertEqual(student.user.profile.role, "student")
        self.assertEqual(User.objects.filter(username=f"etu_esfe{self.inscription.id}").count(), 1)
        self.assertEqual(
            Student.objects.get(inscription=self.inscription).inscription.status,
            Inscription.STATUS_PARTIAL,
        )
        self.assertFalse(AcademicEnrollment.objects.filter(inscription=self.inscription).exists())
        send_credentials.assert_called_once()
        send_confirmation.assert_not_called()

    @patch("payments.models.send_payment_confirmation_email")
    @patch("payments.models.send_student_credentials_email")
    def test_partial_payment_creates_academic_enrollment_when_matching_class_exists(self, send_credentials, send_confirmation):
        AcademicClass.objects.create(
            programme=self.programme,
            branch=self.branch,
            academic_year=self.academic_year,
            level="L1",
            study_level="LICENCE",
            is_active=True,
        )

        self._create_validated_payment(25000)

        enrollment = AcademicEnrollment.objects.select_related("academic_class").get(inscription=self.inscription)
        self.inscription.refresh_from_db()
        self.assertEqual(self.inscription.status, Inscription.STATUS_PARTIAL)
        self.assertEqual(enrollment.academic_class.level, "L1")
        send_credentials.assert_called_once()
        send_confirmation.assert_not_called()

    @patch("payments.models.send_payment_confirmation_email")
    @patch("payments.models.send_student_credentials_email")
    def test_second_validated_payment_does_not_create_duplicates(self, send_credentials, send_confirmation):
        self._create_validated_payment(25000)
        first_student = Student.objects.get(inscription=self.inscription)

        self._create_validated_payment(25000)

        self.assertEqual(Student.objects.filter(inscription=self.inscription).count(), 1)
        self.assertEqual(Student.objects.filter(user=first_student.user).count(), 1)
        self.assertEqual(User.objects.filter(username=f"etu_esfe{self.inscription.id}").count(), 1)
        send_credentials.assert_called_once()
        self.assertEqual(send_confirmation.call_count, 1)

    @patch("payments.models.send_payment_confirmation_email")
    @patch("payments.models.send_student_credentials_email")
    def test_full_payment_creates_academic_enrollment_when_matching_class_exists(self, send_credentials, send_confirmation):
        AcademicClass.objects.create(
            programme=self.programme,
            branch=self.branch,
            academic_year=self.academic_year,
            level="L1",
            study_level="LICENCE",
            is_active=True,
        )

        self._create_validated_payment(25000)
        self._create_validated_payment(75000)

        enrollment = AcademicEnrollment.objects.select_related("academic_class").get(inscription=self.inscription)
        self.assertEqual(enrollment.student.username, f"etu_esfe{self.inscription.id}")
        self.assertEqual(enrollment.academic_class.level, "L1")
        self.assertEqual(enrollment.programme, self.programme)
        self.assertEqual(enrollment.branch, self.branch)
        send_credentials.assert_called_once()
        self.assertEqual(send_confirmation.call_count, 1)

    @patch("payments.models.send_payment_confirmation_email")
    @patch("payments.models.send_student_credentials_email")
    def test_full_payment_without_matching_class_keeps_student_without_enrollment(self, send_credentials, send_confirmation):
        self._create_validated_payment(25000)
        self._create_validated_payment(75000)

        self.assertFalse(AcademicEnrollment.objects.filter(inscription=self.inscription).exists())
        send_credentials.assert_called_once()
        self.assertEqual(send_confirmation.call_count, 1)

    @patch("payments.models.send_payment_confirmation_email")
    @patch("payments.models.send_student_credentials_email")
    def test_full_payment_does_not_recreate_existing_student(self, send_credentials, send_confirmation):
        self._create_validated_payment(25000)
        first_student = Student.objects.get(inscription=self.inscription)

        self._create_validated_payment(75000)

        self.inscription.refresh_from_db()
        self.assertEqual(self.inscription.status, Inscription.STATUS_ACTIVE)
        self.assertEqual(Student.objects.get(inscription=self.inscription).pk, first_student.pk)
        send_credentials.assert_called_once()
        self.assertEqual(send_confirmation.call_count, 1)

    def test_service_requires_validated_payment(self):
        result = create_student_after_first_payment(self.inscription)

        self.assertIsNone(result)
        self.assertFalse(Student.objects.filter(inscription=self.inscription).exists())

    def test_service_reuses_existing_student_and_ensures_role(self):
        self._create_validated_payment(25000)
        student = Student.objects.select_related("user__profile").get(inscription=self.inscription)
        student.user.profile.role = ""
        student.user.profile.save(update_fields=["role", "updated_at"])

        result = create_student_after_first_payment(self.inscription)

        student.user.refresh_from_db()
        self.assertEqual(result["student"].pk, student.pk)
        self.assertFalse(result["created"])
        self.assertEqual(student.user.profile.role, "student")
        self.assertEqual(result["academic_enrollment"]["status"], "manual_required_no_class")

    def test_manual_academic_enrollment_allowed_after_first_validated_payment(self):
        self._create_validated_payment(25000)
        student = Student.objects.get(inscription=self.inscription)
        academic_class = AcademicClass.objects.create(
            programme=self.programme,
            branch=self.branch,
            academic_year=self.academic_year,
            level="L1",
            study_level="LICENCE",
            is_active=True,
        )

        enrollment = AcademicEnrollment.objects.create(
            inscription=self.inscription,
            student=student.user,
            programme=self.programme,
            branch=self.branch,
            academic_year=self.academic_year,
            academic_class=academic_class,
        )

        self.inscription.refresh_from_db()
        self.assertEqual(self.inscription.status, Inscription.STATUS_PARTIAL)
        self.assertEqual(enrollment.academic_class, academic_class)

    def test_service_returns_already_assigned_when_enrollment_exists(self):
        academic_class = AcademicClass.objects.create(
            programme=self.programme,
            branch=self.branch,
            academic_year=self.academic_year,
            level="L1",
            study_level="LICENCE",
            is_active=True,
        )
        self._create_validated_payment(25000)

        result = create_student_after_first_payment(self.inscription)

        self.assertEqual(result["academic_enrollment"]["status"], "already_assigned")
        self.assertEqual(result["academic_enrollment"]["enrollment"].academic_class, academic_class)

    def test_service_returns_manual_required_missing_data_when_year_unresolved(self):
        self.candidature.academic_year = "2029-2030"
        self.candidature.save(update_fields=["academic_year"])
        self._create_validated_payment(25000)

        result = create_student_after_first_payment(self.inscription)

        self.assertIsNotNone(result)
        self.assertEqual(result["academic_enrollment"]["status"], "manual_required_missing_data")
        self.assertEqual(result["academic_enrollment"]["reason"], "academic_year_not_found")

    def test_backfill_creates_missing_student_and_assigns_role(self):
        self._create_validated_payment(25000)

        student = Student.objects.get(inscription=self.inscription)
        user = student.user
        student.delete()
        user.profile.role = ""
        user.profile.save(update_fields=["role", "updated_at"])

        output = StringIO()
        call_command("backfill_students_from_payments", stdout=output)

        recreated = Student.objects.select_related("user__profile").get(inscription=self.inscription)
        self.assertEqual(recreated.user_id, user.id)
        self.assertEqual(recreated.user.profile.role, "student")
