from datetime import date, datetime, time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.utils import timezone

from accounts.models import Profile
from academics.models import (
    AcademicBulletin,
    AcademicCalendar,
    AcademicCalendarEntry,
    AcademicClass,
    AcademicEnrollment,
    AcademicScheduleEvent,
    AcademicYear,
    EC,
    ECGrade,
    LessonLog,
    Semester,
    UE,
    WeeklyScheduleSlot,
)
from academics.services.academic_readiness_service import build_semester_readiness
from admissions.models import Candidature
from branches.models import Branch
from formations.models import Cycle, Diploma, Filiere, Programme
from inscriptions.models import Inscription
from portal.models import DirectorTeacherAssignment
from students.models import Student


User = get_user_model()


class AcademicReadinessServiceTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(name="Annexe Readiness", code="ARD", slug="annexe-readiness")
        self.other_branch = Branch.objects.create(name="Annexe Readiness 2", code="AR2", slug="annexe-readiness-2")
        cycle = Cycle.objects.create(name="Licence Readiness", theme="accent", min_duration_years=1, max_duration_years=3)
        diploma = Diploma.objects.create(name="Diplome Readiness", level="superieur")
        filiere = Filiere.objects.create(name="Filiere Readiness")
        self.programme = Programme.objects.create(
            title="Programme Readiness",
            filiere=filiere,
            cycle=cycle,
            diploma_awarded=diploma,
            duration_years=3,
            short_description="Readiness",
            description="Readiness",
        )
        self.academic_year = AcademicYear.objects.create(
            name="2042-2043",
            start_date=date(2042, 10, 1),
            end_date=date(2043, 7, 31),
            is_active=True,
        )
        self.academic_class = AcademicClass.objects.create(
            programme=self.programme,
            branch=self.branch,
            academic_year=self.academic_year,
            level="L1",
            study_level="LICENCE",
            validation_threshold=Decimal("10.00"),
            is_active=True,
        )
        self.semester = Semester.objects.create(
            academic_class=self.academic_class,
            number=1,
            total_required_credits=Decimal("3.00"),
        )
        self.director = self._user("readiness_director", "director_of_studies", self.branch)
        self.other_director = self._user("readiness_other_director", "director_of_studies", self.other_branch)
        self.teacher = self._user("readiness_teacher", "teacher", self.branch)
        self.it_user = self._user("readiness_it", "it_support", self.branch)

    def _user(self, username, position, branch):
        user = User.objects.create_user(username=username, password="pass1234")
        profile, _ = Profile.objects.get_or_create(user=user)
        profile.position = position
        profile.branch = branch
        profile.save(update_fields=["position", "branch", "updated_at"])
        user.refresh_from_db()
        return user

    def _aware(self, month, day, hour=8):
        return timezone.make_aware(datetime(2042 if month >= 10 else 2043, month, day, hour, 0))

    def _add_structure(self):
        ue = UE.objects.create(semester=self.semester, code="RD101", title="Fondamentaux")
        ec = EC.objects.create(
            ue=ue,
            title="Pilotage",
            credit_required=Decimal("3.00"),
            coefficient=Decimal("2.00"),
        )
        return ue, ec

    def _add_teacher_and_timetable(self, ec):
        DirectorTeacherAssignment.objects.create(
            branch=self.branch,
            teacher=self.teacher,
            academic_class=self.academic_class,
            ec=ec,
            room_label="Salle A",
            planned_hours=Decimal("12.00"),
            created_by=self.director,
        )
        WeeklyScheduleSlot.objects.create(
            academic_class=self.academic_class,
            ec=ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            weekday=0,
            start_time=time(8, 0),
            end_time=time(10, 0),
            room="Salle A",
            created_by=self.director,
        )

    def _add_calendar(self, ec):
        calendar = AcademicCalendar.objects.create(
            branch=self.branch,
            academic_year=self.academic_year,
            version=1,
            status=AcademicCalendar.STATUS_PUBLISHED,
            created_by=self.director,
            updated_by=self.director,
            published_by=self.director,
            published_at=timezone.now(),
        )
        for event_type, title, day in [
            (AcademicCalendarEntry.EVENT_SEMESTER_START, "Debut semestre", 2),
            (AcademicCalendarEntry.EVENT_EXAM_SESSION, "Examens", 20),
            (AcademicCalendarEntry.EVENT_RETAKE_SESSION, "Rattrapages", 25),
        ]:
            AcademicCalendarEntry.objects.create(
                calendar=calendar,
                title=title,
                event_type=event_type,
                start_datetime=self._aware(10, day),
                end_datetime=self._aware(10, day, 18),
                target_scope=AcademicCalendarEntry.SCOPE_CLASS,
                academic_class=self.academic_class,
                status=AcademicCalendarEntry.STATUS_PUBLISHED,
                created_by=self.director,
                updated_by=self.director,
            )
        AcademicScheduleEvent.objects.create(
            title="Examen Pilotage",
            event_type=AcademicScheduleEvent.EVENT_TYPE_EXAM,
            academic_class=self.academic_class,
            ec=ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=self._aware(11, 3),
            end_datetime=self._aware(11, 3, 10),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            created_by=self.director,
            updated_by=self.director,
        )

    def _add_student_notes_and_bulletin(self, ec):
        candidature = Candidature.objects.create(
            programme=self.programme,
            branch=self.branch,
            academic_year=self.academic_year.name,
            entry_year=1,
            first_name="Awa",
            last_name="Readiness",
            birth_date=date(2002, 1, 1),
            birth_place="Bamako",
            gender="female",
            phone="71000000",
            email="awa.readiness@example.com",
            status="accepted",
        )
        inscription = Inscription.objects.create(
            candidature=candidature,
            academic_class=self.academic_class,
            amount_due=100000,
            status=Inscription.STATUS_ACTIVE,
        )
        student = Student.objects.create(user=User.objects.create_user("student_readiness"), inscription=inscription, matricule="RD-001")
        enrollment = AcademicEnrollment.objects.create(
            inscription=inscription,
            student=student.user,
            programme=self.programme,
            branch=self.branch,
            academic_year=self.academic_year,
            academic_class=self.academic_class,
        )
        ECGrade.objects.create(
            enrollment=enrollment,
            ec=ec,
            normal_score=Decimal("14.00"),
            final_score=Decimal("14.00"),
            is_validated=True,
        )
        AcademicBulletin.objects.create(
            student=student,
            enrollment=enrollment,
            academic_year=self.academic_year,
            academic_class=self.academic_class,
            branch=self.branch,
            semester=self.semester,
            bulletin_type=AcademicBulletin.TYPE_SEMESTER,
            status=AcademicBulletin.STATUS_GENERATED,
            generated_by=self.it_user,
            generated_at=timezone.now(),
        )

    def _make_ready_context(self):
        _ue, ec = self._add_structure()
        self._add_teacher_and_timetable(ec)
        self._add_calendar(ec)
        LessonLog.objects.create(
            academic_class=self.academic_class,
            ec=ec,
            teacher=self.teacher,
            date=date(2042, 10, 5),
            start_time=time(8, 0),
            end_time=time(10, 0),
            status=LessonLog.STATUS_DONE,
            content="Cours realise",
            branch=self.branch,
            created_by=self.director,
            validated_by=self.director,
        )
        self._add_student_notes_and_bulletin(ec)
        return ec

    def _report(self):
        return build_semester_readiness(actor=self.director, semester=self.semester)

    def test_programme_incomplete_blocks_validation(self):
        report = self._report()
        self.assertEqual(report["validation"]["answer"], "NON")
        self.assertIn("Aucune UE configuree.", report["validation"]["blocking_anomalies"])

    def test_missing_ec_blocks_validation(self):
        UE.objects.create(semester=self.semester, code="RD102", title="Sans EC")
        report = self._report()
        self.assertEqual(report["validation"]["answer"], "NON")
        self.assertTrue(any("aucun EC" in item for item in report["validation"]["blocking_anomalies"]))

    def test_missing_teacher_blocks_validation(self):
        self._add_structure()
        report = self._report()
        self.assertEqual(report["validation"]["answer"], "NON")
        self.assertTrue(any("EC sans enseignant" in item for item in report["validation"]["blocking_anomalies"]))

    def test_missing_calendar_blocks_validation(self):
        _ue, ec = self._add_structure()
        self._add_teacher_and_timetable(ec)
        report = self._report()
        self.assertEqual(report["validation"]["answer"], "NON")
        self.assertTrue(any("calendrier" in item.lower() for item in report["validation"]["blocking_anomalies"]))

    def test_missing_timetable_blocks_validation(self):
        _ue, ec = self._add_structure()
        self._add_calendar(ec)
        report = self._report()
        self.assertEqual(report["validation"]["answer"], "NON")
        self.assertTrue(any("creneau" in item.lower() or "emploi du temps" in item.lower() for item in report["validation"]["blocking_anomalies"]))

    def test_missing_exams_blocks_validation(self):
        _ue, ec = self._add_structure()
        self._add_teacher_and_timetable(ec)
        calendar = AcademicCalendar.objects.create(
            branch=self.branch,
            academic_year=self.academic_year,
            version=1,
            status=AcademicCalendar.STATUS_PUBLISHED,
            created_by=self.director,
            updated_by=self.director,
            published_by=self.director,
            published_at=timezone.now(),
        )
        AcademicCalendarEntry.objects.create(
            calendar=calendar,
            title="Debut semestre",
            event_type=AcademicCalendarEntry.EVENT_SEMESTER_START,
            start_datetime=self._aware(10, 2),
            end_datetime=self._aware(10, 2, 18),
            target_scope=AcademicCalendarEntry.SCOPE_CLASS,
            academic_class=self.academic_class,
            status=AcademicCalendarEntry.STATUS_PUBLISHED,
            created_by=self.director,
            updated_by=self.director,
        )
        report = self._report()
        self.assertEqual(report["validation"]["answer"], "NON")
        self.assertTrue(any("examen" in item.lower() for item in report["validation"]["blocking_anomalies"]))

    def test_notes_not_imported_blocks_validation(self):
        _ue, ec = self._add_structure()
        self._add_teacher_and_timetable(ec)
        self._add_calendar(ec)
        candidature = Candidature.objects.create(
            programme=self.programme,
            branch=self.branch,
            academic_year=self.academic_year.name,
            entry_year=1,
            first_name="Moussa",
            last_name="Readiness",
            birth_date=date(2002, 1, 1),
            birth_place="Bamako",
            gender="male",
            phone="72000000",
            email="moussa.readiness@example.com",
            status="accepted",
        )
        inscription = Inscription.objects.create(candidature=candidature, academic_class=self.academic_class, amount_due=100000, status=Inscription.STATUS_ACTIVE)
        student_user = User.objects.create_user("student_without_grades")
        Student.objects.create(user=student_user, inscription=inscription, matricule="RD-002")
        AcademicEnrollment.objects.create(
            inscription=inscription,
            student=student_user,
            programme=self.programme,
            branch=self.branch,
            academic_year=self.academic_year,
            academic_class=self.academic_class,
        )
        report = self._report()
        self.assertEqual(report["validation"]["answer"], "NON")
        self.assertTrue(any("Notes non importees" in item for item in report["validation"]["blocking_anomalies"]))

    def test_validation_authorized_when_all_controls_are_green(self):
        self._make_ready_context()
        report = self._report()
        self.assertEqual(report["validation"]["answer"], "OUI")
        self.assertTrue(report["validation"]["can_publish"])
        self.assertEqual(report["validation"]["blocking_anomalies"], [])

    def test_director_cannot_access_other_branch_readiness(self):
        self._make_ready_context()
        with self.assertRaises(PermissionDenied):
            build_semester_readiness(actor=self.other_director, semester=self.semester)
