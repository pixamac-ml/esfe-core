from io import StringIO
from datetime import date, datetime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from django.urls import reverse

from academics.models import AcademicClass, AcademicEnrollment, AcademicScheduleEvent, AcademicYear, EC, Semester, UE
from admissions.models import Candidature
from branches.models import Branch
from formations.models import Cycle, Diploma, Filiere, Programme
from inscriptions.models import Inscription
from payments.models import Payment
from students.models import AttendanceAlert, Student, StudentAttendance, TeacherAttendance
from students.services.attendance_service import (
    detect_repeated_absences,
    detect_repeated_lates,
    get_class_attendance_summary,
    mark_student_attendance,
    mark_teacher_attendance,
)
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
