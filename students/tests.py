from io import StringIO
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from django.urls import reverse

from academics.models import AcademicClass, AcademicDiplomaAward, AcademicEnrollment, AcademicScheduleEvent, AcademicYear, EC, Semester, UE
from academics.services.academic_years import get_current_academic_year_name
from admissions.models import Candidature
from branches.models import Branch
from formations.models import Cycle, Diploma, Filiere, Programme
from inscriptions.models import Inscription
from payments.models import Payment
from students.models import AttendanceAlert, Student, StudentAttendance, StudentYearDecision, TeacherAttendance
from portal.services.reenrollment_service import (
    apply_student_decision,
    build_reenrollment_candidates,
    can_user_handle_reenrollment,
    propose_student_decision,
    reject_student_decision,
    validate_student_decision_academic,
    validate_student_decision_finance,
)
from portal.models import SupportAuditLog
from students.services.attendance_service import (
    detect_repeated_absences,
    detect_repeated_lates,
    get_class_attendance_summary,
    mark_student_attendance,
    mark_teacher_attendance,
)
from students.services.create_student import create_student_after_first_payment
from portal.student.widgets.academics import get_student_academic_snapshot
from portal.student.widgets.finance import get_finance_widget
from portal.student.profile_service import update_editable_fields


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
        self.assertEqual(result["academic_enrollment"]["status"], "manual_required_missing_class")

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

    def test_service_returns_manual_required_missing_year_when_year_unresolved(self):
        self.candidature.academic_year = "2029-2030"
        self.candidature.save(update_fields=["academic_year"])
        self._create_validated_payment(25000)

        result = create_student_after_first_payment(self.inscription)

        self.assertIsNotNone(result)
        self.assertEqual(result["academic_enrollment"]["status"], "manual_required_missing_year")
        self.assertEqual(result["academic_enrollment"]["reason"], "academic_year_not_found")

    @patch("payments.models.send_payment_confirmation_email")
    @patch("payments.models.send_student_credentials_email")
    def test_service_normalizes_legacy_academic_year_string_before_assignment(self, send_credentials, send_confirmation):
        AcademicClass.objects.create(
            programme=self.programme,
            branch=self.branch,
            academic_year=self.academic_year,
            level="L1",
            study_level="LICENCE",
            is_active=True,
        )
        self.candidature.academic_year = "2025 / 2026"
        self.candidature.save(update_fields=["academic_year"])

        self._create_validated_payment(25000)

        enrollment = AcademicEnrollment.objects.select_related("academic_year").get(inscription=self.inscription)
        self.assertEqual(enrollment.academic_year, self.academic_year)
        send_credentials.assert_called_once()
        send_confirmation.assert_not_called()

    def test_active_academic_year_name_service_returns_the_unique_active_year(self):
        self.assertEqual(get_current_academic_year_name(), "2025-2026")

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


class ReenrollmentPhaseOneTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="reenrollment_student",
            email="reenrollment_student@example.com",
            password="pass1234",
            first_name="Awa",
            last_name="Traore",
        )
        self.branch = Branch.objects.create(name="Annexe Reinscription", code="RIN", slug="annexe-reinscription")
        self.cycle = Cycle.objects.create(name="Licence Reinscription", theme="accent", min_duration_years=1, max_duration_years=3)
        self.diploma = Diploma.objects.create(name="Diplome Reinscription", level="superieur")
        self.filiere = Filiere.objects.create(name="Filiere Reinscription")
        self.programme = Programme.objects.create(
            title="Programme Reinscription",
            filiere=self.filiere,
            cycle=self.cycle,
            diploma_awarded=self.diploma,
            duration_years=3,
            short_description="Reinscription",
            description="Reinscription",
        )
        self.source_year = AcademicYear.objects.create(
            name="2031-2032",
            start_date=date(2031, 10, 1),
            end_date=date(2032, 7, 31),
            is_active=True,
        )
        self.target_year = AcademicYear.objects.create(
            name="2032-2033",
            start_date=date(2032, 10, 1),
            end_date=date(2033, 7, 31),
            is_active=False,
        )
        self.source_class = AcademicClass.objects.create(
            programme=self.programme,
            branch=self.branch,
            academic_year=self.source_year,
            level="L1",
            study_level="LICENCE",
            validation_threshold=Decimal("10.00"),
            is_active=True,
        )
        self.target_l2 = AcademicClass.objects.create(
            programme=self.programme,
            branch=self.branch,
            academic_year=self.target_year,
            level="L2",
            study_level="LICENCE",
            validation_threshold=Decimal("10.00"),
            is_active=True,
        )
        self.target_l1 = AcademicClass.objects.create(
            programme=self.programme,
            branch=self.branch,
            academic_year=self.target_year,
            level="L1",
            study_level="LICENCE",
            validation_threshold=Decimal("10.00"),
            is_active=True,
        )
        self.candidature = Candidature.objects.create(
            programme=self.programme,
            branch=self.branch,
            academic_year="2031-2032",
            entry_year=1,
            first_name="Awa",
            last_name="Traore",
            birth_date="2001-01-01",
            birth_place="Bamako",
            gender="female",
            phone="70000002",
            email="awa.reinscription@example.com",
            status="accepted",
        )
        self.inscription = Inscription.objects.create(
            candidature=self.candidature,
            academic_class=self.source_class,
            amount_due=100000,
            status=Inscription.STATUS_ACTIVE,
        )
        self.student = Student.objects.create(
            user=self.user,
            inscription=self.inscription,
            matricule="MAT-RIN-001",
            is_active=True,
        )
        self.enrollment = AcademicEnrollment.objects.create(
            inscription=self.inscription,
            student=self.user,
            programme=self.programme,
            branch=self.branch,
            academic_year=self.source_year,
            academic_class=self.source_class,
        )
        self.student.current_academic_enrollment = self.enrollment
        self.student.save(update_fields=["current_academic_enrollment"])

    def test_promoted_decision_keeps_student_identity_and_history(self):
        decision = propose_student_decision(
            student=self.student,
            source_enrollment=self.enrollment,
            target_academic_year=self.target_year,
            target_class=self.target_l2,
            annual_average=Decimal("12.50"),
        )

        self.student.refresh_from_db()
        self.enrollment.refresh_from_db()
        self.assertEqual(decision.decision, StudentYearDecision.DECISION_PROMOTED)
        self.assertEqual(decision.target_class, self.target_l2)
        self.assertEqual(self.student.matricule, "MAT-RIN-001")
        self.assertEqual(self.student.user, self.user)
        self.assertEqual(self.student.current_academic_enrollment, self.enrollment)
        self.assertEqual(self.enrollment.status, AcademicEnrollment.STATUS_ACTIVE)

    def test_repeated_decision_can_resolve_same_level_target_class(self):
        decision = propose_student_decision(
            student=self.student,
            source_enrollment=self.enrollment,
            target_academic_year=self.target_year,
            annual_average=Decimal("8.25"),
        )

        self.assertEqual(decision.decision, StudentYearDecision.DECISION_REPEATED)
        self.assertEqual(decision.target_class, self.target_l1)

    def test_duplicate_active_enrollment_same_year_programme_is_rejected(self):
        candidature = Candidature.objects.create(
            programme=self.programme,
            branch=self.branch,
            academic_year="2031-2032",
            entry_year=1,
            first_name="Awa",
            last_name="Traore",
            birth_date="2001-01-01",
            birth_place="Bamako",
            gender="female",
            phone="70000003",
            email="awa.reinscription.2@example.com",
            status="accepted",
        )
        inscription = Inscription.objects.create(
            candidature=candidature,
            academic_class=self.source_class,
            amount_due=100000,
            status=Inscription.STATUS_ACTIVE,
        )
        Payment.objects.create(
            inscription=inscription,
            amount=100000,
            method=Payment.METHOD_CASH,
            status=Payment.STATUS_VALIDATED,
        )

        with self.assertRaises(ValidationError):
            AcademicEnrollment.objects.create(
                inscription=inscription,
                student=self.user,
                programme=self.programme,
                branch=self.branch,
                academic_year=self.source_year,
                academic_class=self.source_class,
            )

    def test_candidates_include_finance_and_proposed_decision(self):
        candidates = build_reenrollment_candidates(source_year=self.source_year, source_class=self.source_class)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["matricule"], "MAT-RIN-001")
        self.assertIn(candidates[0]["proposed_decision"], {
            StudentYearDecision.DECISION_PROMOTED,
            StudentYearDecision.DECISION_REPEATED,
        })
        self.assertEqual(candidates[0]["financial_status"]["status"], "debt")

    def test_automatic_non_admis_mapping_can_be_academically_validated(self):
        """The annual-rule vocabulary must be mapped before workflow validation."""
        actor = User.objects.create_user(
            username="reenrollment_academic_mapping_actor",
            password="pass1234",
            is_staff=True,
        )
        actor.profile.position = "director_of_studies"
        actor.profile.branch = self.branch
        actor.profile.save(update_fields=["position", "branch", "updated_at"])
        Payment.objects.create(
            inscription=self.inscription,
            amount=self.inscription.amount_due,
            method=Payment.METHOD_CASH,
            status=Payment.STATUS_VALIDATED,
        )
        self.inscription.update_financial_state()

        decision = propose_student_decision(
            student=self.student,
            source_enrollment=self.enrollment,
            target_academic_year=self.target_year,
            proposed_by=actor,
        )

        self.assertEqual(decision.decision, StudentYearDecision.DECISION_REPEATED)
        self.assertEqual(decision.target_class, self.target_l1)
        validate_student_decision_academic(decision=decision, actor=actor)
        decision.refresh_from_db()
        self.assertEqual(
            decision.workflow_status,
            StudentYearDecision.WORKFLOW_ACADEMIC_VALIDATED,
        )

    def test_proposal_rejects_target_class_from_another_branch(self):
        actor = User.objects.create_user(
            username="reenrollment_target_scope_actor",
            password="pass1234",
            is_staff=True,
        )
        actor.profile.position = "director_of_studies"
        actor.profile.branch = self.branch
        actor.profile.save(update_fields=["position", "branch", "updated_at"])
        other_branch = Branch.objects.create(
            name="Annexe cible interdite",
            code="RINX",
            slug="annexe-cible-interdite",
        )
        wrong_target = AcademicClass.objects.create(
            programme=self.programme,
            branch=other_branch,
            academic_year=self.target_year,
            level="L1",
            study_level="LICENCE",
            validation_threshold=Decimal("10.00"),
            is_active=True,
        )

        with self.assertRaisesMessage(ValidationError, "meme annexe"):
            propose_student_decision(
                student=self.student,
                source_enrollment=self.enrollment,
                target_academic_year=self.target_year,
                target_class=wrong_target,
                decision=StudentYearDecision.DECISION_REPEATED,
                proposed_by=actor,
            )
        self.assertFalse(StudentYearDecision.objects.filter(source_enrollment=self.enrollment).exists())

    def _create_settled_transition_decision(self, actor):
        Payment.objects.create(
            inscription=self.inscription,
            amount=100000,
            method=Payment.METHOD_CASH,
            status=Payment.STATUS_VALIDATED,
        )
        self.inscription.update_financial_state()
        decision = propose_student_decision(
            student=self.student,
            source_enrollment=self.enrollment,
            target_academic_year=self.target_year,
            target_class=self.target_l2,
            decision=StudentYearDecision.DECISION_PROMOTED,
            annual_average=Decimal("13.00"),
            proposed_by=actor,
        )

        actor.profile.position = "director_of_studies"
        actor.profile.save(update_fields=["position", "updated_at"])
        validate_student_decision_academic(decision=decision, actor=actor)
        actor.profile.position = "branch_manager"
        actor.profile.save(update_fields=["position", "updated_at"])
        validate_student_decision_finance(decision=decision, actor=actor)
        return decision

    def test_validated_transition_prepares_target_inscription_without_archiving_history(self):
        actor = User.objects.create_user(username="reenrollment_actor", password="pass1234", is_staff=True)
        actor.profile.position = "branch_manager"
        actor.profile.branch = self.branch
        actor.profile.save(update_fields=["position", "branch", "updated_at"])
        decision = self._create_settled_transition_decision(actor)
        prepared = apply_student_decision(decision=decision, actor=actor)

        self.student.refresh_from_db()
        self.enrollment.refresh_from_db()
        self.assertEqual(prepared.workflow_status, StudentYearDecision.WORKFLOW_FINANCE_VALIDATED)
        self.assertEqual(prepared.target_inscription.status, Inscription.STATUS_AWAITING_PAYMENT)
        self.assertIsNone(prepared.target_enrollment)
        self.assertEqual(self.enrollment.status, AcademicEnrollment.STATUS_ACTIVE)
        self.assertEqual(self.student.current_academic_enrollment, self.enrollment)
        self.assertEqual(self.student.matricule, "MAT-RIN-001")
        self.assertFalse(
            AcademicEnrollment.objects.filter(
                student=self.user,
                academic_year=self.target_year,
            ).exists()
        )
        self.assertTrue(
            SupportAuditLog.objects.filter(
                action_type=SupportAuditLog.ACTION_REENROLLMENT_APPLIED,
                target_user=self.user,
            ).exists()
        )

    @patch("payments.models.send_payment_confirmation_email")
    @patch("payments.models.send_student_credentials_email")
    def test_target_payment_activates_reenrollment_without_duplicate_identity(self, _send_credentials, _send_confirmation):
        actor = User.objects.create_user(username="reenrollment_activation_actor", password="pass1234", is_staff=True)
        actor.profile.position = "branch_manager"
        actor.profile.branch = self.branch
        actor.profile.save(update_fields=["position", "branch", "updated_at"])
        decision = self._create_settled_transition_decision(actor)
        prepared = apply_student_decision(decision=decision, actor=actor)

        with self.captureOnCommitCallbacks(execute=True):
            Payment.objects.create(
                inscription=prepared.target_inscription,
                amount=prepared.target_inscription.amount_due,
                method=Payment.METHOD_CASH,
                status=Payment.STATUS_VALIDATED,
            )

        decision.refresh_from_db()
        self.student.refresh_from_db()
        self.enrollment.refresh_from_db()
        self.assertEqual(decision.workflow_status, StudentYearDecision.WORKFLOW_APPLIED)
        self.assertEqual(decision.target_enrollment.student, self.user)
        self.assertEqual(decision.target_enrollment.academic_class, self.target_l2)
        self.assertEqual(self.enrollment.status, AcademicEnrollment.STATUS_ARCHIVED)
        self.assertEqual(self.student.current_academic_enrollment, decision.target_enrollment)
        self.assertEqual(Student.objects.filter(user=self.user).count(), 1)
        self.assertEqual(Student.objects.count(), 1)

        from academic_cycle.models import AcademicReEnrollment, StudentAccessPolicy, StudentFinancialPosition

        cycle_reenrollment = AcademicReEnrollment.objects.get(
            student=self.student,
            target_academic_year=self.target_year,
        )
        self.assertEqual(cycle_reenrollment.status, AcademicReEnrollment.STATUS_ACTIVATED)
        financial_position = StudentFinancialPosition.objects.get(
            student=self.student,
            academic_year=self.target_year,
        )
        self.assertEqual(financial_position.current_year_due_amount, prepared.target_inscription.amount_due)
        self.assertEqual(financial_position.current_year_paid_amount, prepared.target_inscription.amount_due)
        self.assertEqual(
            StudentAccessPolicy.objects.get(
                student=self.student,
                academic_year=self.target_year,
            ).access_level,
            "full",
        )

        source_snapshot = get_student_academic_snapshot(self.user, academic_year_id=self.source_year.id)
        target_snapshot = get_student_academic_snapshot(self.user, academic_year_id=self.target_year.id)
        self.assertEqual(source_snapshot["academic_enrollment"], self.enrollment)
        self.assertEqual(target_snapshot["academic_enrollment"], decision.target_enrollment)
        self.assertTrue(source_snapshot["is_historical_context"])
        self.assertEqual(
            get_finance_widget(self.user, academic_year_id=self.source_year.id)["total_paid"],
            Decimal("100000"),
        )
        self.assertEqual(
            get_finance_widget(self.user, academic_year_id=self.target_year.id)["total_paid"],
            prepared.target_inscription.amount_due,
        )

    @patch("payments.models.send_payment_confirmation_email")
    @patch("payments.models.send_student_credentials_email")
    def test_partial_target_payment_activates_only_the_target_year(self, _send_credentials, _send_confirmation):
        actor = User.objects.create_user(username="reenrollment_partial_actor", password="pass1234", is_staff=True)
        actor.profile.position = "branch_manager"
        actor.profile.branch = self.branch
        actor.profile.save(update_fields=["position", "branch", "updated_at"])
        decision = self._create_settled_transition_decision(actor)
        prepared = apply_student_decision(decision=decision, actor=actor)

        with self.captureOnCommitCallbacks(execute=True):
            Payment.objects.create(
                inscription=prepared.target_inscription,
                amount=25000,
                method=Payment.METHOD_CASH,
                status=Payment.STATUS_VALIDATED,
            )

        decision.refresh_from_db()
        self.enrollment.refresh_from_db()
        prepared.target_inscription.refresh_from_db()
        self.assertEqual(decision.workflow_status, StudentYearDecision.WORKFLOW_APPLIED)
        self.assertEqual(prepared.target_inscription.status, Inscription.STATUS_PARTIAL)
        self.assertEqual(decision.target_enrollment.academic_year, self.target_year)
        self.assertEqual(self.enrollment.status, AcademicEnrollment.STATUS_ARCHIVED)
        self.assertEqual(
            get_finance_widget(self.user, academic_year_id=self.source_year.id)["total_paid"],
            Decimal("100000"),
        )
        self.assertEqual(
            get_finance_widget(self.user, academic_year_id=self.target_year.id)["total_paid"],
            Decimal("25000"),
        )

    @patch("payments.models.send_payment_confirmation_email")
    @patch("payments.models.send_student_credentials_email")
    def test_student_dashboard_selected_year_changes_the_server_context(self, _send_credentials, _send_confirmation):
        actor = User.objects.create_user(username="reenrollment_dashboard_context_actor", password="pass1234", is_staff=True)
        actor.profile.position = "branch_manager"
        actor.profile.branch = self.branch
        actor.profile.save(update_fields=["position", "branch", "updated_at"])
        decision = self._create_settled_transition_decision(actor)
        prepared = apply_student_decision(decision=decision, actor=actor)
        with self.captureOnCommitCallbacks(execute=True):
            Payment.objects.create(
                inscription=prepared.target_inscription,
                amount=prepared.target_inscription.amount_due,
                method=Payment.METHOD_CASH,
                status=Payment.STATUS_VALIDATED,
            )

        decision.refresh_from_db()
        self.user.profile.role = "student"
        self.user.profile.save(update_fields=["role", "updated_at"])
        self.client.force_login(self.user)

        source_response = self.client.get(
            reverse("portal_student:dashboard"),
            {"academic_year_id": self.source_year.id},
        )
        target_response = self.client.get(
            reverse("portal_student:dashboard"),
            {"academic_year_id": self.target_year.id},
        )

        self.assertEqual(source_response.status_code, 200)
        self.assertEqual(target_response.status_code, 200)
        self.assertEqual(source_response.context["enrollment"], self.enrollment)
        self.assertEqual(target_response.context["enrollment"], decision.target_enrollment)
        self.assertEqual(source_response.context["selected_academic_year_id"], self.source_year.id)
        self.assertEqual(target_response.context["selected_academic_year_id"], self.target_year.id)
        self.assertContains(source_response, 'id="student-academic-year-mobile"')

    def test_prepared_decision_cannot_be_modified_or_rejected(self):
        actor = User.objects.create_user(username="reenrollment_locked_actor", password="pass1234", is_staff=True)
        actor.profile.position = "branch_manager"
        actor.profile.branch = self.branch
        actor.profile.save(update_fields=["position", "branch", "updated_at"])
        decision = self._create_settled_transition_decision(actor)
        prepared = apply_student_decision(decision=decision, actor=actor)

        with self.assertRaises(ValidationError):
            propose_student_decision(
                student=self.student,
                source_enrollment=self.enrollment,
                target_academic_year=self.target_year,
                target_class=self.target_l1,
                decision=StudentYearDecision.DECISION_REPEATED,
                annual_average=Decimal("8.00"),
                proposed_by=actor,
            )
        with self.assertRaises(ValidationError):
            reject_student_decision(decision=prepared, actor=actor, reason="Annulation tardive")

        decision.refresh_from_db()
        self.assertEqual(decision.workflow_status, StudentYearDecision.WORKFLOW_FINANCE_VALIDATED)
        self.assertEqual(decision.target_inscription, prepared.target_inscription)

    def test_existing_target_inscription_with_payment_is_not_hijacked(self):
        actor = User.objects.create_user(username="reenrollment_existing_target_actor", password="pass1234", is_staff=True)
        actor.profile.position = "branch_manager"
        actor.profile.branch = self.branch
        actor.profile.save(update_fields=["position", "branch", "updated_at"])
        decision = self._create_settled_transition_decision(actor)
        target_candidature = Candidature.objects.create(
            programme=self.programme,
            branch=self.branch,
            academic_year=self.target_year.name,
            entry_year=2,
            first_name=self.candidature.first_name,
            last_name=self.candidature.last_name,
            birth_date=self.candidature.birth_date,
            birth_place=self.candidature.birth_place,
            gender=self.candidature.gender,
            phone=self.candidature.phone,
            email=self.candidature.email,
            status="accepted",
        )
        target_inscription = Inscription.objects.create(
            candidature=target_candidature,
            academic_class=self.target_l2,
            amount_due=100000,
            status=Inscription.STATUS_AWAITING_PAYMENT,
        )
        Payment.objects.create(
            inscription=target_inscription,
            amount=25000,
            method=Payment.METHOD_CASH,
            status=Payment.STATUS_VALIDATED,
        )

        with self.assertRaises(ValidationError):
            apply_student_decision(decision=decision, actor=actor)

        decision.refresh_from_db()
        self.assertIsNone(decision.target_inscription)

    def test_historical_profile_context_cannot_overwrite_source_candidature(self):
        actor = User.objects.create_user(username="reenrollment_history_profile_actor", password="pass1234", is_staff=True)
        actor.profile.position = "branch_manager"
        actor.profile.branch = self.branch
        actor.profile.save(update_fields=["position", "branch", "updated_at"])
        decision = self._create_settled_transition_decision(actor)
        prepared = apply_student_decision(decision=decision, actor=actor)
        with self.captureOnCommitCallbacks(execute=True):
            Payment.objects.create(
                inscription=prepared.target_inscription,
                amount=prepared.target_inscription.amount_due,
                method=Payment.METHOD_CASH,
                status=Payment.STATUS_VALIDATED,
            )

        with self.assertRaises(ValidationError):
            update_editable_fields(
                self.user,
                {"email": "historique-modifie@example.com", "phone": "71111111"},
                academic_year_id=self.source_year.id,
            )

        self.candidature.refresh_from_db()
        self.assertEqual(self.candidature.email, "awa.reinscription@example.com")
        self.assertEqual(self.candidature.phone, "70000002")

    @override_settings(ROOT_URLCONF="config.urls")
    def test_legacy_student_reenrollment_endpoint_cannot_advance_portal_projection(self):
        actor = User.objects.create_user(username="reenrollment_projection_actor", password="pass1234", is_staff=True)
        actor.profile.position = "branch_manager"
        actor.profile.branch = self.branch
        actor.profile.save(update_fields=["position", "branch", "updated_at"])
        propose_student_decision(
            student=self.student,
            source_enrollment=self.enrollment,
            target_academic_year=self.target_year,
            target_class=self.target_l2,
            decision=StudentYearDecision.DECISION_PROMOTED,
            annual_average=Decimal("13.00"),
            proposed_by=actor,
        )
        from academic_cycle.models import AcademicReEnrollment

        tracker = AcademicReEnrollment.objects.get(
            student=self.student,
            target_academic_year=self.target_year,
        )
        self.user.profile.role = "student"
        self.user.profile.save(update_fields=["role", "updated_at"])
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("academic_cycle:student_reenrollment", args=[tracker.token]),
        )

        tracker.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(tracker.status, AcademicReEnrollment.STATUS_PREPARED)

    @patch("payments.models.send_payment_confirmation_email")
    @patch("payments.models.send_student_credentials_email")
    def test_diplomas_partial_respects_selected_academic_year(self, _send_credentials, _send_confirmation):
        actor = User.objects.create_user(username="reenrollment_diploma_actor", password="pass1234", is_staff=True)
        actor.profile.position = "branch_manager"
        actor.profile.branch = self.branch
        actor.profile.save(update_fields=["position", "branch", "updated_at"])
        decision = self._create_settled_transition_decision(actor)
        prepared = apply_student_decision(decision=decision, actor=actor)
        with self.captureOnCommitCallbacks(execute=True):
            Payment.objects.create(
                inscription=prepared.target_inscription,
                amount=prepared.target_inscription.amount_due,
                method=Payment.METHOD_CASH,
                status=Payment.STATUS_VALIDATED,
            )
        decision.refresh_from_db()
        source_award = AcademicDiplomaAward.objects.create(
            student=self.student,
            enrollment=self.enrollment,
            academic_year=self.source_year,
            academic_class=self.source_class,
            branch=self.branch,
            programme=self.programme,
            diploma=self.diploma,
            status=AcademicDiplomaAward.STATUS_READY,
        )
        target_award = AcademicDiplomaAward.objects.create(
            student=self.student,
            enrollment=decision.target_enrollment,
            academic_year=self.target_year,
            academic_class=self.target_l2,
            branch=self.branch,
            programme=self.programme,
            diploma=self.diploma,
            status=AcademicDiplomaAward.STATUS_READY,
        )
        self.user.profile.role = "student"
        self.user.profile.save(update_fields=["role", "updated_at"])
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("portal_student:diplomas_partial"),
            {"academic_year_id": self.source_year.id},
        )

        self.assertContains(response, source_award.reference)
        self.assertNotContains(response, target_award.reference)

    def test_proposal_is_rejected_outside_actor_branch_scope(self):
        other_branch = Branch.objects.create(
            name="Annexe Hors Perimetre",
            code="RIN2",
            slug="annexe-hors-perimetre",
        )
        actor = User.objects.create_user(username="reenrollment_other_branch", password="pass1234", is_staff=True)
        actor.profile.position = "branch_manager"
        actor.profile.branch = other_branch
        actor.profile.save(update_fields=["position", "branch", "updated_at"])

        with self.assertRaises(ValidationError):
            propose_student_decision(
                student=self.student,
                source_enrollment=self.enrollment,
                target_academic_year=self.target_year,
                target_class=self.target_l2,
                decision=StudentYearDecision.DECISION_PROMOTED,
                annual_average=Decimal("13.00"),
                proposed_by=actor,
            )

    def test_finance_validation_requires_academic_validation(self):
        actor = User.objects.create_user(username="reenrollment_finance_guard", password="pass1234", is_staff=True)
        actor.profile.position = "branch_manager"
        actor.profile.branch = self.branch
        actor.profile.save(update_fields=["position", "branch", "updated_at"])
        decision = propose_student_decision(
            student=self.student,
            source_enrollment=self.enrollment,
            target_academic_year=self.target_year,
            target_class=self.target_l2,
            decision=StudentYearDecision.DECISION_PROMOTED,
            annual_average=Decimal("13.00"),
            proposed_by=actor,
        )

        with self.assertRaises(ValidationError):
            validate_student_decision_finance(decision=decision, actor=actor)

    def test_rejected_decision_cannot_be_applied(self):
        actor = User.objects.create_user(username="reenrollment_reject_actor", password="pass1234", is_staff=True)
        actor.profile.position = "director_of_studies"
        actor.profile.branch = self.branch
        actor.profile.save(update_fields=["position", "branch", "updated_at"])
        decision = propose_student_decision(
            student=self.student,
            source_enrollment=self.enrollment,
            target_academic_year=self.target_year,
            target_class=self.target_l2,
            decision=StudentYearDecision.DECISION_PROMOTED,
            annual_average=Decimal("13.00"),
            proposed_by=actor,
        )

        rejected = reject_student_decision(decision=decision, actor=actor, reason="Cible a verifier")

        self.assertEqual(rejected.workflow_status, StudentYearDecision.WORKFLOW_REJECTED)
        self.assertEqual(rejected.rejection_reason, "Cible a verifier")
        with self.assertRaises(ValidationError):
            apply_student_decision(decision=rejected, actor=actor)

    def test_gestionnaire_group_can_access_reenrollment_without_position(self):
        actor = User.objects.create_user(username="reenrollment_group_manager", password="pass1234", is_staff=True)
        Group.objects.get_or_create(name="gestionnaire")[0].user_set.add(actor)

        self.assertTrue(can_user_handle_reenrollment(actor))

    def test_suspension_can_be_applied_without_creating_target_enrollment(self):
        actor = User.objects.create_user(username="reenrollment_suspend_actor", password="pass1234", is_staff=True)
        actor.profile.position = "director_of_studies"
        actor.profile.branch = self.branch
        actor.profile.save(update_fields=["position", "branch", "updated_at"])
        decision = propose_student_decision(
            student=self.student,
            source_enrollment=self.enrollment,
            decision=StudentYearDecision.DECISION_SUSPENDED,
            annual_average=Decimal("9.00"),
            proposed_by=actor,
        )

        validate_student_decision_academic(decision=decision, actor=actor)
        actor.profile.position = "branch_manager"
        actor.profile.save(update_fields=["position", "updated_at"])
        validate_student_decision_finance(decision=decision, actor=actor)
        applied = apply_student_decision(decision=decision, actor=actor)

        self.student.refresh_from_db()
        self.enrollment.refresh_from_db()
        self.inscription.refresh_from_db()
        self.assertEqual(applied.workflow_status, StudentYearDecision.WORKFLOW_APPLIED)
        self.assertEqual(self.enrollment.status, AcademicEnrollment.STATUS_SUSPENDED)
        self.assertEqual(self.inscription.status, Inscription.STATUS_SUSPENDED)
        self.assertIsNone(self.student.current_academic_enrollment)
        self.assertFalse(self.student.is_active)
        self.assertIsNone(applied.target_enrollment)

    def test_completed_decision_requires_finance_clearance_then_closes_source(self):
        actor = User.objects.create_user(username="reenrollment_complete_actor", password="pass1234", is_staff=True)
        actor.profile.position = "director_of_studies"
        actor.profile.branch = self.branch
        actor.profile.save(update_fields=["position", "branch", "updated_at"])
        Payment.objects.create(
            inscription=self.inscription,
            amount=100000,
            method=Payment.METHOD_CASH,
            status=Payment.STATUS_VALIDATED,
        )
        self.inscription.update_financial_state()
        decision = propose_student_decision(
            student=self.student,
            source_enrollment=self.enrollment,
            decision=StudentYearDecision.DECISION_COMPLETED,
            annual_average=Decimal("14.00"),
            proposed_by=actor,
        )

        validate_student_decision_academic(decision=decision, actor=actor)
        actor.profile.position = "branch_manager"
        actor.profile.save(update_fields=["position", "updated_at"])
        validate_student_decision_finance(decision=decision, actor=actor)
        apply_student_decision(decision=decision, actor=actor)

        self.student.refresh_from_db()
        self.enrollment.refresh_from_db()
        self.inscription.refresh_from_db()
        self.assertEqual(self.enrollment.status, AcademicEnrollment.STATUS_COMPLETED)
        self.assertEqual(self.inscription.status, Inscription.STATUS_COMPLETED)
        self.assertIsNone(self.student.current_academic_enrollment)
        self.assertTrue(self.student.is_active)


class ReenrollmentPhaseTwoDashboardTests(ReenrollmentPhaseOneTests):
    """Exercise the three operational surfaces against the Phase 1 engine."""

    def setUp(self):
        super().setUp()
        self.director = User.objects.create_user(
            username="phase2_director", password="pass1234", is_staff=True,
        )
        self.director.profile.position = "director_of_studies"
        self.director.profile.branch = self.branch
        self.director.profile.save(update_fields=["position", "branch", "updated_at"])
        self.manager = User.objects.create_user(
            username="phase2_manager", password="pass1234", is_staff=True,
        )
        self.manager.profile.position = "branch_manager"
        self.manager.profile.branch = self.branch
        self.manager.profile.save(update_fields=["position", "branch", "updated_at"])
        self.finance = User.objects.create_user(
            username="phase2_finance", password="pass1234", is_staff=True,
        )
        self.finance.profile.position = "finance_manager"
        self.finance.profile.branch = self.branch
        self.finance.profile.save(update_fields=["position", "branch", "updated_at"])
        self.foreign_branch = Branch.objects.create(
            name="Annexe Phase 2 Exterieure", code="P2X", slug="annexe-phase2-exterieure",
        )
        self.foreign_manager = User.objects.create_user(
            username="phase2_foreign_manager", password="pass1234", is_staff=True,
        )
        self.foreign_manager.profile.position = "branch_manager"
        self.foreign_manager.profile.branch = self.foreign_branch
        self.foreign_manager.profile.save(update_fields=["position", "branch", "updated_at"])
        self.executive = User.objects.create_user(
            username="phase2_executive", password="pass1234", is_staff=True,
        )
        self.executive.profile.position = "executive_director"
        self.executive.profile.branch = self.branch
        self.executive.profile.save(update_fields=["position", "branch", "updated_at"])

    def _settle_source_inscription(self):
        with self.captureOnCommitCallbacks(execute=True):
            Payment.objects.create(
                inscription=self.inscription,
                amount=self.inscription.amount_due,
                method=Payment.METHOD_CASH,
                status=Payment.STATUS_VALIDATED,
            )
        self.inscription.refresh_from_db()

    def _decision_through_operational_endpoints(self):
        self._settle_source_inscription()
        candidate = build_reenrollment_candidates(
            source_year=self.source_year,
            source_class=self.source_class,
            branch=self.branch,
            target_year=self.target_year,
        )[0]
        self.client.force_login(self.director)
        proposal = self.client.post(
            reverse("accounts_portal:reenrollment_propose"),
            {
                "surface": "director",
                "enrollment_id": self.enrollment.id,
                "source_year": self.source_year.id,
                "target_year": self.target_year.id,
                "target_class": candidate["proposed_target_class"].id,
                "decision": candidate["proposed_decision"],
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(proposal.status_code, 200)
        decision = StudentYearDecision.objects.get(source_enrollment=self.enrollment)
        academic = self.client.post(
            reverse("accounts_portal:reenrollment_decision_action"),
            {"surface": "director", "decision_id": decision.id, "action": "academic_validate"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(academic.status_code, 200)
        self.assertEqual(academic.context["toast"]["level"], "success", academic.context["toast"])
        decision.refresh_from_db()
        self.assertEqual(decision.workflow_status, StudentYearDecision.WORKFLOW_ACADEMIC_VALIDATED)
        return decision

    def _prepare_target_inscription(self):
        decision = self._decision_through_operational_endpoints()
        self.client.force_login(self.finance)
        finance = self.client.post(
            reverse("accounts_portal:reenrollment_decision_action"),
            {"surface": "manager", "decision_id": decision.id, "action": "finance_validate"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(finance.status_code, 200)
        finance_apply = self.client.post(
            reverse("accounts_portal:reenrollment_decision_action"),
            {"surface": "manager", "decision_id": decision.id, "action": "apply"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(finance_apply.status_code, 200)
        decision.refresh_from_db()
        self.assertIsNone(decision.target_inscription)

        self.client.force_login(self.manager)
        prepare = self.client.post(
            reverse("accounts_portal:reenrollment_decision_action"),
            {"surface": "manager", "decision_id": decision.id, "action": "apply"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(prepare.status_code, 200)
        decision.refresh_from_db()
        self.assertIsNotNone(decision.target_inscription)
        self.assertIsNone(decision.target_enrollment)
        self.assertEqual(decision.target_inscription.status, Inscription.STATUS_AWAITING_PAYMENT)
        return decision

    def test_manager_dashboard_search_permissions_and_foreign_scope(self):
        self.client.force_login(self.manager)
        response = self.client.get(
            reverse("accounts_portal:portal_annex_manager"),
            {"section": "reenrollment", "source_year": self.source_year.id, "target_year": self.target_year.id, "q": "Awa"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["active_section"], "reenrollment")
        self.assertEqual(response.context["reenrollment_metrics"]["not_started"], 1)
        self.assertContains(response, "MAT-RIN-001")
        self.assertContains(response, "Réinscriptions")
        no_match = self.client.get(
            reverse("accounts_portal:portal_annex_manager"),
            {"section": "reenrollment", "source_year": self.source_year.id, "q": "inconnu"},
        )
        self.assertNotContains(no_match, "MAT-RIN-001")

        forbidden_proposal = self.client.post(
            reverse("accounts_portal:reenrollment_propose"),
            {
                "surface": "manager", "enrollment_id": self.enrollment.id,
                "target_year": self.target_year.id, "target_class": self.target_l1.id,
                "decision": StudentYearDecision.DECISION_REPEATED,
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(forbidden_proposal.status_code, 200)
        self.assertFalse(StudentYearDecision.objects.filter(source_enrollment=self.enrollment).exists())

        self.client.force_login(self.foreign_manager)
        foreign = self.client.get(
            reverse("accounts_portal:portal_annex_manager"),
            {"section": "reenrollment", "source_year": self.source_year.id, "q": "Awa"},
        )
        self.assertEqual(foreign.status_code, 200)
        self.assertNotContains(foreign, "MAT-RIN-001")

    def test_director_manager_payment_activation_and_dg_pilotage(self):
        director_view = self.client
        director_view.force_login(self.director)
        director_workspace = director_view.get(
            reverse("accounts_portal:director_evaluations_subcontent"),
            {"view": "reenrollments", "source_year": self.source_year.id, "target_year": self.target_year.id},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(director_workspace.status_code, 200)
        self.assertContains(director_workspace, "Intervention académique")
        self.assertNotContains(director_workspace, "Vérifier le solde source")

        decision = self._prepare_target_inscription()
        self.client.force_login(self.foreign_manager)
        cross_branch = self.client.post(
            reverse("accounts_portal:reenrollment_decision_action"),
            {"surface": "manager", "decision_id": decision.id, "action": "apply"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(cross_branch.status_code, 404)

        with self.captureOnCommitCallbacks(execute=True):
            Payment.objects.create(
                inscription=decision.target_inscription,
                amount=decision.target_inscription.amount_due,
                method=Payment.METHOD_CASH,
                status=Payment.STATUS_VALIDATED,
            )
        decision.refresh_from_db()
        self.student.refresh_from_db()
        self.enrollment.refresh_from_db()
        self.assertEqual(decision.workflow_status, StudentYearDecision.WORKFLOW_APPLIED)
        self.assertEqual(self.student.user_id, self.user.id)
        self.assertEqual(self.student.current_academic_enrollment_id, decision.target_enrollment_id)
        self.assertEqual(self.enrollment.status, AcademicEnrollment.STATUS_ARCHIVED)
        self.assertEqual(
            AcademicEnrollment.objects.filter(
                academic_class=decision.target_class,
                academic_year=self.target_year,
                status=AcademicEnrollment.STATUS_ACTIVE,
            ).count(),
            1,
        )

        self.client.force_login(self.executive)
        dg = self.client.get(
            reverse("accounts_portal:dg_section", kwargs={"section": "reenrollments"}),
            {"source_year": self.source_year.id, "target_year": self.target_year.id},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(dg.status_code, 200)
        self.assertEqual(dg.context["reenrollment_metrics"]["active"], 1)
        self.assertContains(dg, "Pilotage uniquement")
        self.assertContains(dg, "Actifs")
        self.assertNotContains(dg, "Démarrer la réinscription")
        active_only = self.client.get(
            reverse("accounts_portal:dg_section", kwargs={"section": "reenrollments"}),
            {
                "source_year": self.source_year.id,
                "target_year": self.target_year.id,
                "finance_state": "active",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(active_only.status_code, 200)
        self.assertEqual(active_only.context["finance_state"], "active")
        self.assertEqual(active_only.context["reenrollment_metrics"]["active"], 1)
        self.assertContains(active_only, "MAT-RIN-001")
        direct_operational_workspace = self.client.get(reverse("accounts_portal:reenrollment_workspace"))
        self.assertEqual(direct_operational_workspace.status_code, 403)
        direct_operational_action = self.client.post(
            reverse("accounts_portal:reenrollment_decision_action"),
            {"decision_id": decision.id, "action": "apply"},
        )
        self.assertEqual(direct_operational_action.status_code, 403)


class AttendanceServiceTests(TestCase):
    def setUp(self):
        self.recorder = User.objects.create_user(username="supervisor", password="x")
        self.teacher = User.objects.create_user(username="teacher_presence", password="x")
        self.student_user = User.objects.create_user(username="attendance_student", password="x")

        self.branch = Branch.objects.create(
            name="Annexe Presence",
            code="APR",
            slug="annexe-presence",
        )
        self.cycle = Cycle.objects.create(
            name="Cycle Presence",
            theme="accent",
            min_duration_years=1,
            max_duration_years=5,
        )
        self.diploma = Diploma.objects.create(name="Diplome Presence", level="superieur")
        self.filiere = Filiere.objects.create(name="Filiere Presence")
        self.programme = Programme.objects.create(
            title="Programme Presence",
            filiere=self.filiere,
            cycle=self.cycle,
            diploma_awarded=self.diploma,
            duration_years=3,
            short_description="Programme presence",
            description="Programme presence",
        )
        self.candidature = Candidature.objects.create(
            programme=self.programme,
            branch=self.branch,
            academic_year="2026-2027",
            entry_year=1,
            first_name="Awa",
            last_name="Diallo",
            birth_date="2001-02-03",
            birth_place="Bamako",
            gender="female",
            phone="70000001",
            email="awa.diallo@example.com",
            status="accepted",
        )
        self.inscription = Inscription.objects.create(
            candidature=self.candidature,
            amount_due=120000,
            status=Inscription.STATUS_ACTIVE,
        )
        self.student = Student.objects.create(
            user=self.student_user,
            inscription=self.inscription,
            matricule="MAT-PRES-01",
            is_active=True,
        )
        self.academic_year = AcademicYear.objects.create(
            name="2026-2027",
            start_date=date(2026, 10, 1),
            end_date=date(2027, 7, 31),
            is_active=True,
        )
        self.academic_class = AcademicClass.objects.create(
            programme=self.programme,
            branch=self.branch,
            academic_year=self.academic_year,
            level="L1",
            study_level="LICENCE",
            is_active=True,
        )
        semester = Semester.objects.create(
            academic_class=self.academic_class,
            number=1,
            total_required_credits=30,
        )
        ue = UE.objects.create(semester=semester, code="PRS101", title="Presence")
        self.ec = EC.objects.create(
            ue=ue,
            title="Suivi",
            credit_required=3,
            coefficient=3,
        )
        AcademicEnrollment.objects.create(
            inscription=self.inscription,
            student=self.student_user,
            programme=self.programme,
            branch=self.branch,
            academic_year=self.academic_year,
            academic_class=self.academic_class,
            is_active=True,
        )
        self.event_day_1 = AcademicScheduleEvent.objects.create(
            title="Cours J1",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=timezone.make_aware(datetime(2026, 10, 5, 8, 0)),
            end_datetime=timezone.make_aware(datetime(2026, 10, 5, 10, 0)),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle 1",
            created_by=self.recorder,
            updated_by=self.recorder,
            is_active=True,
        )
        self.event_day_2 = AcademicScheduleEvent.objects.create(
            title="Cours J2",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=timezone.make_aware(datetime(2026, 10, 6, 8, 0)),
            end_datetime=timezone.make_aware(datetime(2026, 10, 6, 10, 0)),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle 1",
            created_by=self.recorder,
            updated_by=self.recorder,
            is_active=True,
        )
        self.event_day_3 = AcademicScheduleEvent.objects.create(
            title="Cours J3",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=timezone.make_aware(datetime(2026, 10, 7, 8, 0)),
            end_datetime=timezone.make_aware(datetime(2026, 10, 7, 10, 0)),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle 1",
            created_by=self.recorder,
            updated_by=self.recorder,
            is_active=True,
        )

    def test_mark_student_attendance_creates_daily_record(self):
        result = mark_student_attendance(
            student=self.student,
            academic_class=self.academic_class,
            schedule_event=self.event_day_1,
            status=StudentAttendance.STATUS_PRESENT,
            recorded_by=self.recorder,
            branch=self.branch,
        )

        attendance = result["attendance"]
        self.assertEqual(attendance.branch, self.branch)
        self.assertEqual(attendance.academic_class, self.academic_class)
        self.assertEqual(attendance.schedule_event, self.event_day_1)
        self.assertEqual(StudentAttendance.objects.count(), 1)
        self.assertFalse(result["absence_alert"]["triggered"])
        self.assertFalse(result["late_alert"]["triggered"])

    def test_detect_repeated_absences_creates_alert_after_three_consecutive_events(self):
        for event in [self.event_day_3, self.event_day_2, self.event_day_1]:
            mark_student_attendance(
                student=self.student,
                academic_class=self.academic_class,
                schedule_event=event,
                status=StudentAttendance.STATUS_ABSENT,
                recorded_by=self.recorder,
                branch=self.branch,
                justification="Absence test",
            )

        result = detect_repeated_absences(self.student, branch=self.branch)

        self.assertTrue(result["triggered"])
        self.assertEqual(result["count"], 3)
        self.assertEqual(
            AttendanceAlert.objects.filter(
                student=self.student,
                alert_type=AttendanceAlert.TYPE_ABSENCE_REPETITION,
            ).count(),
            1,
        )

    def test_detect_repeated_lates_creates_alert_after_three_records(self):
        for event in [self.event_day_1, self.event_day_2, self.event_day_3]:
            mark_student_attendance(
                student=self.student,
                academic_class=self.academic_class,
                schedule_event=event,
                status=StudentAttendance.STATUS_LATE,
                recorded_by=self.recorder,
                branch=self.branch,
                arrival_time=timezone.datetime.strptime("08:15", "%H:%M").time(),
            )

        result = detect_repeated_lates(self.student, branch=self.branch)

        self.assertTrue(result["triggered"])
        self.assertEqual(result["count"], 3)
        self.assertEqual(
            AttendanceAlert.objects.filter(
                student=self.student,
                alert_type=AttendanceAlert.TYPE_LATE_REPETITION,
            ).count(),
            1,
        )

    def test_get_class_attendance_summary_returns_counts(self):
        mark_student_attendance(
            student=self.student,
            academic_class=self.academic_class,
            schedule_event=self.event_day_1,
            status=StudentAttendance.STATUS_PRESENT,
            recorded_by=self.recorder,
            branch=self.branch,
        )

        summary = get_class_attendance_summary(self.academic_class, date(2026, 10, 5))

        self.assertEqual(summary["summary"][StudentAttendance.STATUS_PRESENT], 1)
        self.assertEqual(summary["summary"][StudentAttendance.STATUS_ABSENT], 0)
        self.assertEqual(summary["records"][0]["matricule"], "MAT-PRES-01")

    def test_mark_teacher_attendance_creates_teacher_record(self):
        result = mark_teacher_attendance(
            teacher=self.teacher,
            schedule_event=self.event_day_1,
            status=TeacherAttendance.STATUS_ABSENT,
            recorded_by=self.recorder,
            branch=self.branch,
            justification="Indisponible",
        )
        attendance = result["attendance"]

        self.assertEqual(TeacherAttendance.objects.count(), 1)
        self.assertEqual(attendance.status, TeacherAttendance.STATUS_ABSENT)
        self.assertEqual(attendance.schedule_event, self.event_day_1)


class AttendanceApiTests(TestCase):
    def setUp(self):
        self.supervisor = User.objects.create_user(username="attendance_api", password="pass1234")
        self.supervisor.profile.position = "academic_supervisor"
        self.supervisor.profile.user_type = "staff"
        self.branch = Branch.objects.create(name="Annexe API", code="API", slug="annexe-api")
        self.other_branch = Branch.objects.create(name="Annexe API 2", code="AP2", slug="annexe-api-2")
        self.supervisor.profile.branch = self.branch
        self.supervisor.profile.save(update_fields=["position", "user_type", "branch", "updated_at"])

        self.teacher = User.objects.create_user(username="teacher_api", password="x")
        self.teacher_other = User.objects.create_user(username="teacher_other", password="x")
        self.student_user = User.objects.create_user(username="student_api", password="x")
        self.student_other_user = User.objects.create_user(username="student_other", password="x")

        self.cycle = Cycle.objects.create(name="Cycle API", theme="accent", min_duration_years=1, max_duration_years=5)
        self.diploma = Diploma.objects.create(name="Diplome API", level="superieur")
        self.filiere = Filiere.objects.create(name="Filiere API")
        self.programme = Programme.objects.create(
            title="Programme API",
            filiere=self.filiere,
            cycle=self.cycle,
            diploma_awarded=self.diploma,
            duration_years=3,
            short_description="API",
            description="API",
        )
        self.academic_year = AcademicYear.objects.create(
            name="2028-2029",
            start_date=date(2028, 10, 1),
            end_date=date(2029, 7, 31),
            is_active=True,
        )
        self.classroom = AcademicClass.objects.create(
            programme=self.programme,
            branch=self.branch,
            academic_year=self.academic_year,
            level="L1",
            study_level="LICENCE",
            is_active=True,
        )
        self.other_classroom = AcademicClass.objects.create(
            programme=self.programme,
            branch=self.other_branch,
            academic_year=self.academic_year,
            level="L1",
            study_level="LICENCE",
            is_active=True,
        )
        semester = Semester.objects.create(academic_class=self.classroom, number=1, total_required_credits=30)
        semester_other = Semester.objects.create(academic_class=self.other_classroom, number=1, total_required_credits=30)
        ue = UE.objects.create(semester=semester, code="API101", title="API")
        ue_other = UE.objects.create(semester=semester_other, code="API201", title="API2")
        self.ec = EC.objects.create(ue=ue, title="Assiduite", credit_required=3, coefficient=3)
        self.other_ec = EC.objects.create(ue=ue_other, title="Assiduite2", credit_required=3, coefficient=3)

        self.candidature = Candidature.objects.create(
            programme=self.programme,
            branch=self.branch,
            academic_year="2028-2029",
            entry_year=1,
            first_name="Moussa",
            last_name="Keita",
            birth_date="2002-01-01",
            birth_place="Bamako",
            gender="male",
            phone="70010000",
            email="moussa@example.com",
            status="accepted",
        )
        self.other_candidature = Candidature.objects.create(
            programme=self.programme,
            branch=self.other_branch,
            academic_year="2028-2029",
            entry_year=1,
            first_name="Fatou",
            last_name="Coulibaly",
            birth_date="2002-01-01",
            birth_place="Kayes",
            gender="female",
            phone="70020000",
            email="fatou@example.com",
            status="accepted",
        )
        self.inscription = Inscription.objects.create(candidature=self.candidature, amount_due=100000, status=Inscription.STATUS_ACTIVE)
        self.other_inscription = Inscription.objects.create(candidature=self.other_candidature, amount_due=100000, status=Inscription.STATUS_ACTIVE)
        self.student = Student.objects.create(user=self.student_user, inscription=self.inscription, matricule="MAT-API-01", is_active=True)
        self.other_student = Student.objects.create(user=self.student_other_user, inscription=self.other_inscription, matricule="MAT-API-02", is_active=True)
        AcademicEnrollment.objects.create(
            inscription=self.inscription,
            student=self.student_user,
            programme=self.programme,
            branch=self.branch,
            academic_year=self.academic_year,
            academic_class=self.classroom,
            is_active=True,
        )
        AcademicEnrollment.objects.create(
            inscription=self.other_inscription,
            student=self.student_other_user,
            programme=self.programme,
            branch=self.other_branch,
            academic_year=self.academic_year,
            academic_class=self.other_classroom,
            is_active=True,
        )
        self.event = AcademicScheduleEvent.objects.create(
            title="Cours API",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.classroom,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=timezone.make_aware(datetime(2028, 10, 5, 8, 0)),
            end_datetime=timezone.make_aware(datetime(2028, 10, 5, 10, 0)),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle API",
            created_by=self.supervisor,
            updated_by=self.supervisor,
            is_active=True,
        )
        self.event_other = AcademicScheduleEvent.objects.create(
            title="Cours API 2",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.other_classroom,
            ec=self.other_ec,
            teacher=self.teacher_other,
            branch=self.other_branch,
            academic_year=self.academic_year,
            start_datetime=timezone.make_aware(datetime(2028, 10, 5, 8, 0)),
            end_datetime=timezone.make_aware(datetime(2028, 10, 5, 10, 0)),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle API 2",
            created_by=self.supervisor,
            updated_by=self.supervisor,
            is_active=True,
        )
        self.client.force_login(self.supervisor)

    def test_student_attendance_api_creates_record(self):
        response = self.client.post(
            reverse("students:mark_student_attendance"),
            data={
                "student_id": self.student.id,
                "academic_class_id": self.classroom.id,
                "schedule_event_id": self.event.id,
                "status": StudentAttendance.STATUS_PRESENT,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(StudentAttendance.objects.count(), 1)
        self.assertEqual(StudentAttendance.objects.get().schedule_event, self.event)

    def test_student_attendance_api_rejects_cross_branch_data(self):
        response = self.client.post(
            reverse("students:mark_student_attendance"),
            data={
                "student_id": self.other_student.id,
                "academic_class_id": self.other_classroom.id,
                "schedule_event_id": self.event_other.id,
                "status": StudentAttendance.STATUS_PRESENT,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(StudentAttendance.objects.count(), 0)

    def test_student_attendance_api_rejects_invalid_payload(self):
        response = self.client.post(
            reverse("students:mark_student_attendance"),
            data={
                "student_id": self.student.id,
                "academic_class_id": self.classroom.id,
                "status": StudentAttendance.STATUS_PRESENT,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)

    def test_teacher_attendance_api_creates_record(self):
        response = self.client.post(
            reverse("students:mark_teacher_attendance"),
            data={
                "teacher_id": self.teacher.id,
                "schedule_event_id": self.event.id,
                "status": TeacherAttendance.STATUS_LATE,
                "arrival_time": "08:12",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(TeacherAttendance.objects.count(), 1)

    def test_student_attendance_history_api_returns_branch_scoped_data(self):
        StudentAttendance.objects.create(
            student=self.student,
            academic_class=self.classroom,
            schedule_event=self.event,
            date=self.event.start_datetime.date(),
            status=StudentAttendance.STATUS_PRESENT,
            recorded_by=self.supervisor,
            branch=self.branch,
        )

        response = self.client.get(reverse("students:student_attendance_history", args=[self.student.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["history"]), 1)

    def test_student_attendance_api_triggers_anomaly_after_three_absences(self):
        second_event = AcademicScheduleEvent.objects.create(
            title="Cours API B",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.classroom,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=timezone.make_aware(datetime(2028, 10, 6, 8, 0)),
            end_datetime=timezone.make_aware(datetime(2028, 10, 6, 10, 0)),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle API",
            created_by=self.supervisor,
            updated_by=self.supervisor,
            is_active=True,
        )
        third_event = AcademicScheduleEvent.objects.create(
            title="Cours API C",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.classroom,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=timezone.make_aware(datetime(2028, 10, 7, 8, 0)),
            end_datetime=timezone.make_aware(datetime(2028, 10, 7, 10, 0)),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle API",
            created_by=self.supervisor,
            updated_by=self.supervisor,
            is_active=True,
        )

        for event in [third_event, second_event, self.event]:
            response = self.client.post(
                reverse("students:mark_student_attendance"),
                data={
                    "student_id": self.student.id,
                    "academic_class_id": self.classroom.id,
                    "schedule_event_id": event.id,
                    "status": StudentAttendance.STATUS_ABSENT,
                },
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["absence_alert_triggered"])
