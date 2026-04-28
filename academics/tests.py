from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from academics.models import (
    AcademicClass,
    AcademicEnrollment,
    AcademicScheduleChangeLog,
    AcademicScheduleEvent,
    AcademicYear,
    EC,
    LessonLog,
    Semester,
    UE,
)
from academics.services.lesson_log_service import (
    create_lesson_log,
    get_class_lesson_logs,
    get_daily_lesson_status,
    get_teacher_lesson_logs,
    update_lesson_log,
)
from academics.services.schedule_service import (
    cancel_schedule_event,
    complete_schedule_event,
    create_schedule_event,
    get_branch_activity_summary,
    get_schedule_alerts,
    get_schedule_conflicts,
    get_schedule_quality_score,
    get_student_week_schedule,
    get_teacher_next_events,
    get_weekly_schedule_stats,
    postpone_schedule_event,
    suggest_available_slots,
)
from admissions.models import Candidature
from branches.models import Branch
from formations.models import Cycle, Diploma, Filiere, Programme
from inscriptions.models import Inscription
from students.models import Student, TeacherAttendance


User = get_user_model()


class AcademicScheduleServiceTests(TestCase):
    def setUp(self):
        self.director = User.objects.create_user(username="director", password="x")
        self.teacher = User.objects.create_user(username="teacher_1", password="x", first_name="Ada", last_name="Lovelace")
        self.teacher_two = User.objects.create_user(username="teacher_2", password="x", first_name="Alan", last_name="Turing")
        self.student_user = User.objects.create_user(username="student_1", password="x")

        self.branch = Branch.objects.create(name="ESFE Bamako", code="BKO", slug="esfe-bamako")
        cycle = Cycle.objects.create(
            name="Licence",
            min_duration_years=3,
            max_duration_years=3,
        )
        diploma = Diploma.objects.create(name="Licence", level="superieur")
        filiere = Filiere.objects.create(name="Sciences")
        self.programme = Programme.objects.create(
            title="Informatique de gestion",
            filiere=filiere,
            cycle=cycle,
            diploma_awarded=diploma,
            duration_years=3,
            short_description="Programme test",
            description="Programme de test",
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
            validation_threshold=Decimal("10.00"),
            is_active=True,
        )
        semester = Semester.objects.create(
            academic_class=self.academic_class,
            number=1,
            total_required_credits=Decimal("30.00"),
        )
        ue = UE.objects.create(semester=semester, code="INF101", title="Fondamentaux")
        self.ec = EC.objects.create(
            ue=ue,
            title="Algorithmique",
            credit_required=Decimal("3.00"),
            coefficient=Decimal("3.00"),
        )
        self.ec_two = EC.objects.create(
            ue=ue,
            title="Base de donnees",
            credit_required=Decimal("3.00"),
            coefficient=Decimal("3.00"),
        )

        candidature = Candidature.objects.create(
            programme=self.programme,
            branch=self.branch,
            academic_year=self.academic_year.name,
            first_name="Jane",
            last_name="Doe",
            birth_date=date(2004, 1, 2),
            birth_place="Bamako",
            gender="female",
            phone="70000000",
            email="jane@example.com",
            status="accepted",
        )
        inscription = Inscription.objects.create(
            candidature=candidature,
            amount_due=100000,
            status=Inscription.STATUS_PARTIAL,
        )
        self.student = Student.objects.create(
            user=self.student_user,
            inscription=inscription,
            matricule="MAT-0001",
            is_active=True,
        )
        self.enrollment = AcademicEnrollment.objects.create(
            inscription=inscription,
            student=self.student_user,
            programme=self.programme,
            branch=self.branch,
            academic_year=self.academic_year,
            academic_class=self.academic_class,
            is_active=True,
        )
        self.week_start = date(2026, 10, 5)

    def _aware_dt(self, day_offset, hour, minute=0):
        return timezone.make_aware(datetime.combine(self.week_start + timedelta(days=day_offset), datetime.min.time().replace(hour=hour, minute=minute)))

    def test_create_schedule_event_valid(self):
        event = create_schedule_event(
            user=self.director,
            title="Cours Algorithmique",
            description="Introduction",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=self._aware_dt(0, 8),
            end_datetime=self._aware_dt(0, 10),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle A1",
            is_online=False,
            meeting_link="",
            is_active=True,
        )

        self.assertEqual(event.academic_class, self.academic_class)
        self.assertEqual(event.teacher, self.teacher)
        self.assertEqual(event.change_logs.count(), 1)
        self.assertEqual(event.change_logs.first().action_type, AcademicScheduleChangeLog.ACTION_CREATED)

    def test_refuse_class_conflict(self):
        create_schedule_event(
            user=self.director,
            title="Cours 1",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=self._aware_dt(0, 8),
            end_datetime=self._aware_dt(0, 10),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle A1",
            is_online=False,
            meeting_link="",
            is_active=True,
        )

        with self.assertRaises(ValidationError):
            create_schedule_event(
                user=self.director,
                title="Cours 2",
                description="",
                event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
                academic_class=self.academic_class,
                ec=self.ec_two,
                teacher=self.teacher_two,
                branch=self.branch,
                academic_year=self.academic_year,
                start_datetime=self._aware_dt(0, 9),
                end_datetime=self._aware_dt(0, 11),
                status=AcademicScheduleEvent.STATUS_PLANNED,
                location="Salle B2",
                is_online=False,
                meeting_link="",
                is_active=True,
            )

    def test_refuse_teacher_conflict(self):
        other_class = AcademicClass.objects.create(
            programme=self.programme,
            branch=self.branch,
            academic_year=self.academic_year,
            level="L2",
            study_level="LICENCE",
            validation_threshold=Decimal("10.00"),
            is_active=True,
        )
        semester = Semester.objects.create(
            academic_class=other_class,
            number=1,
            total_required_credits=Decimal("30.00"),
        )
        ue = UE.objects.create(semester=semester, code="INF201", title="Suite")
        ec_other = EC.objects.create(
            ue=ue,
            title="Reseaux",
            credit_required=Decimal("3.00"),
            coefficient=Decimal("3.00"),
        )

        create_schedule_event(
            user=self.director,
            title="Cours 1",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=self._aware_dt(1, 10),
            end_datetime=self._aware_dt(1, 12),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle A1",
            is_online=False,
            meeting_link="",
            is_active=True,
        )

        with self.assertRaises(ValidationError):
            create_schedule_event(
                user=self.director,
                title="Cours 2",
                description="",
                event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
                academic_class=other_class,
                ec=ec_other,
                teacher=self.teacher,
                branch=self.branch,
                academic_year=self.academic_year,
                start_datetime=self._aware_dt(1, 11),
                end_datetime=self._aware_dt(1, 13),
                status=AcademicScheduleEvent.STATUS_PLANNED,
                location="Salle C1",
                is_online=False,
                meeting_link="",
                is_active=True,
            )

    def test_get_schedule_conflicts_returns_structured_payload(self):
        existing = create_schedule_event(
            user=self.director,
            title="Cours structure",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=self._aware_dt(0, 8),
            end_datetime=self._aware_dt(0, 10),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle A1",
            is_online=False,
            meeting_link="",
            is_active=True,
        )

        conflicts = get_schedule_conflicts(
            academic_class=self.academic_class,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            ec=self.ec,
            location="Salle A1",
            start_datetime=self._aware_dt(0, 9),
            end_datetime=self._aware_dt(0, 11),
        )

        self.assertTrue(conflicts["has_conflict"])
        self.assertTrue(conflicts["class_conflicts"])
        self.assertTrue(conflicts["teacher_conflicts"])
        self.assertTrue(conflicts["location_conflicts"])
        self.assertTrue(conflicts["ec_conflicts"])
        self.assertEqual(conflicts["class_conflicts"][0].id, existing.id)
        self.assertIn("class_conflict", {item["type"] for item in conflicts["conflicts"]})
        self.assertIn("teacher_conflict", {item["type"] for item in conflicts["conflicts"]})

    def test_postpone_schedule_event_creates_log(self):
        event = create_schedule_event(
            user=self.director,
            title="Cours reporte",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=self._aware_dt(2, 8),
            end_datetime=self._aware_dt(2, 10),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle A1",
            is_online=False,
            meeting_link="",
            is_active=True,
        )

        postpone_schedule_event(
            event,
            self._aware_dt(3, 14),
            self._aware_dt(3, 16),
            "Decalage pour indisponibilite",
            self.director,
        )

        self.assertEqual(event.change_logs.count(), 2)
        log = event.change_logs.order_by("-changed_at").first()
        self.assertEqual(log.action_type, AcademicScheduleChangeLog.ACTION_POSTPONED)
        self.assertEqual(log.reason, "Decalage pour indisponibilite")
        self.assertEqual(log.old_start_datetime, self._aware_dt(2, 8))
        self.assertEqual(log.new_start_datetime, self._aware_dt(3, 14))

    def test_cancel_schedule_event_creates_log(self):
        event = create_schedule_event(
            user=self.director,
            title="Cours annule",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=self._aware_dt(4, 14),
            end_datetime=self._aware_dt(4, 16),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle A1",
            is_online=False,
            meeting_link="",
            is_active=True,
        )

        cancel_schedule_event(event, "Jour ferie", self.director)

        event.refresh_from_db()
        self.assertEqual(event.status, AcademicScheduleEvent.STATUS_CANCELLED)
        log = event.change_logs.order_by("-changed_at").first()
        self.assertEqual(log.action_type, AcademicScheduleChangeLog.ACTION_CANCELLED)
        self.assertEqual(log.reason, "Jour ferie")

    def test_postpone_and_cancel_require_reason(self):
        event = create_schedule_event(
            user=self.director,
            title="Cours valide",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=self._aware_dt(1, 14),
            end_datetime=self._aware_dt(1, 16),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle A1",
            is_online=False,
            meeting_link="",
            is_active=True,
        )

        with self.assertRaises(ValidationError):
            postpone_schedule_event(event, self._aware_dt(2, 14), self._aware_dt(2, 16), "", self.director)
        with self.assertRaises(ValidationError):
            cancel_schedule_event(event, "   ", self.director)

    def test_suggest_available_slots_returns_free_standard_slots(self):
        create_schedule_event(
            user=self.director,
            title="Cours occupe",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=self._aware_dt(0, 8),
            end_datetime=self._aware_dt(0, 10),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle A1",
            is_online=False,
            meeting_link="",
            is_active=True,
        )

        suggestions = suggest_available_slots(
            academic_class=self.academic_class,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            duration_minutes=120,
            week_start=self.week_start,
        )

        self.assertTrue(suggestions)
        self.assertNotEqual(suggestions[0]["start"], self._aware_dt(0, 8))
        self.assertGreaterEqual(suggestions[0]["score"], 40)
        self.assertEqual(suggestions[0]["end"] - suggestions[0]["start"], timedelta(minutes=120))

    def test_get_weekly_schedule_stats_returns_enriched_counts(self):
        event_planned = create_schedule_event(
            user=self.director,
            title="Cours 1",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=self._aware_dt(0, 8),
            end_datetime=self._aware_dt(0, 10),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle A1",
            is_online=False,
            meeting_link="",
            is_active=True,
        )
        event_cancelled = create_schedule_event(
            user=self.director,
            title="Cours 2",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec_two,
            teacher=self.teacher_two,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=self._aware_dt(1, 10),
            end_datetime=self._aware_dt(1, 12),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle B1",
            is_online=False,
            meeting_link="",
            is_active=True,
        )
        cancel_schedule_event(event_cancelled, "Indisponible", self.director)
        complete_schedule_event(
            event_planned,
            self.director,
            notes="Termine",
            started_at=self._aware_dt(0, 8),
            ended_at=self._aware_dt(0, 10),
        )

        stats = get_weekly_schedule_stats(self.branch, self.week_start)

        self.assertEqual(stats["total_events"], 2)
        self.assertEqual(stats["completed_count"], 1)
        self.assertEqual(stats["cancelled_count"], 1)
        self.assertIn("Ada Lovelace", stats["teacher_load"])
        self.assertIn(self.academic_class.display_name, stats["class_load"])
        self.assertEqual(stats["completion_rate"], 50.0)
        self.assertEqual(stats["cancellation_rate"], 50.0)

    def test_quality_score_alerts_and_branch_summary(self):
        postponed = create_schedule_event(
            user=self.director,
            title="Cours reporte",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=self._aware_dt(2, 8),
            end_datetime=self._aware_dt(2, 10),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="",
            is_online=False,
            meeting_link="",
            is_active=True,
        )
        postpone_schedule_event(
            postponed,
            self._aware_dt(3, 14),
            self._aware_dt(3, 16),
            "Report maintenu",
            self.director,
        )

        alerts = get_schedule_alerts(self.branch, self.week_start)
        quality = get_schedule_quality_score(self.branch, self.week_start)
        summary = get_branch_activity_summary(self.branch, self.week_start)

        self.assertTrue(any(alert["type"] == "missing_location" for alert in alerts))
        self.assertIn("score", quality)
        self.assertIn("status", quality)
        self.assertEqual(summary["alert_count"], len(summary["alerts"]))
        self.assertIn("stats", summary)

    def test_complete_schedule_event_creates_execution_log(self):
        event = create_schedule_event(
            user=self.director,
            title="Cours execution",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=self._aware_dt(4, 8),
            end_datetime=self._aware_dt(4, 10),
            status=AcademicScheduleEvent.STATUS_ONGOING,
            location="Salle A1",
            is_online=False,
            meeting_link="",
            is_active=True,
        )

        execution_log = complete_schedule_event(
            event,
            self.director,
            notes="Cours bien termine",
            started_at=self._aware_dt(4, 8),
            ended_at=self._aware_dt(4, 9, 45),
        )

        event.refresh_from_db()
        self.assertEqual(event.status, AcademicScheduleEvent.STATUS_COMPLETED)
        self.assertTrue(execution_log.is_completed)
        self.assertEqual(execution_log.started_at, self._aware_dt(4, 8))
        self.assertEqual(execution_log.ended_at, self._aware_dt(4, 9, 45))

    def test_get_teacher_next_events_returns_future_items(self):
        create_schedule_event(
            user=self.director,
            title="Cours suivant",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=timezone.now() + timedelta(days=1),
            end_datetime=timezone.now() + timedelta(days=1, hours=2),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle A1",
            is_online=False,
            meeting_link="",
            is_active=True,
        )

        events = get_teacher_next_events(self.teacher)

        self.assertTrue(events)
        self.assertEqual(events[0]["teacher_name"], "Ada Lovelace")

    def test_get_student_week_schedule_returns_weekly_grid(self):
        create_schedule_event(
            user=self.director,
            title="Cours dashboard",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=self._aware_dt(0, 8),
            end_datetime=self._aware_dt(0, 10),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle A1",
            is_online=False,
            meeting_link="",
            is_active=True,
        )

        schedule = get_student_week_schedule(self.student, self.week_start)

        self.assertEqual(schedule["week_start"], self.week_start)
        self.assertTrue(schedule["events"])
        self.assertEqual(schedule["events"][0]["title"], "Algorithmique")
        self.assertTrue(any(cell["events"] for slot in schedule["slots"] for cell in slot["cells"]))
        self.assertIn("summary", schedule)
        self.assertIn("empty_days", schedule)

    def test_get_student_week_schedule_handles_empty_week(self):
        schedule = get_student_week_schedule(self.student, self.week_start)

        self.assertEqual(schedule["events"], [])
        self.assertEqual(len(schedule["slots"]), 4)
        self.assertEqual(len(schedule["empty_days"]), 6)
        self.assertFalse(schedule["has_extra_slots"])

    def test_get_student_week_schedule_exposes_non_standard_slots(self):
        create_schedule_event(
            user=self.director,
            title="Cours hors grille",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=self._aware_dt(2, 11),
            end_datetime=self._aware_dt(2, 13),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle A1",
            is_online=False,
            meeting_link="",
            is_active=True,
        )

        schedule = get_student_week_schedule(self.student, self.week_start)

        self.assertTrue(schedule["has_extra_slots"])
        self.assertEqual(schedule["extra_slots"][0]["label"], "11:00")
        self.assertEqual(schedule["extra_slots"][0]["cells"][2]["events"][0]["title"], "Algorithmique")

    def test_get_student_week_schedule_keeps_cancelled_and_planned_same_slot(self):
        cancelled_event = create_schedule_event(
            user=self.director,
            title="Cours annule cellule",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=self._aware_dt(0, 8),
            end_datetime=self._aware_dt(0, 10),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle A1",
            is_online=False,
            meeting_link="",
            is_active=True,
        )
        cancel_schedule_event(cancelled_event, "Annulation test", self.director)
        create_schedule_event(
            user=self.director,
            title="Cours maintenu cellule",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec_two,
            teacher=self.teacher_two,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=self._aware_dt(0, 8),
            end_datetime=self._aware_dt(0, 10),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle B1",
            is_online=False,
            meeting_link="",
            is_active=True,
        )

        schedule = get_student_week_schedule(self.student, self.week_start)

        monday_first_cell = schedule["slots"][0]["cells"][0]
        self.assertEqual(len(monday_first_cell["events"]), 2)
        self.assertEqual({event["status"] for event in monday_first_cell["events"]}, {"cancelled", "planned"})

    def test_get_student_week_schedule_marks_completed_events(self):
        event = create_schedule_event(
            user=self.director,
            title="Cours termine affichage",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=self._aware_dt(4, 16),
            end_datetime=self._aware_dt(4, 18),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle A1",
            is_online=False,
            meeting_link="",
            is_active=True,
        )
        complete_schedule_event(
            event,
            self.director,
            notes="Fin de cours",
            started_at=self._aware_dt(4, 16),
            ended_at=self._aware_dt(4, 18),
        )

        schedule = get_student_week_schedule(self.student, self.week_start)
        completed = next(item for item in schedule["events"] if item["id"] == event.id)

        self.assertTrue(completed["is_completed"])
        self.assertEqual(completed["status_label"], "Termine")
        self.assertEqual(schedule["summary"]["completed"], 1)


class LessonLogServiceTests(TestCase):
    def setUp(self):
        self.supervisor = User.objects.create_user(username="supervisor_log", password="x")
        self.teacher = User.objects.create_user(username="teacher_log", password="x", first_name="Grace", last_name="Hopper")

        self.branch = Branch.objects.create(name="ESFE Kayes", code="KYS", slug="esfe-kayes")
        cycle = Cycle.objects.create(name="Licence Log", min_duration_years=3, max_duration_years=3)
        diploma = Diploma.objects.create(name="Licence Log", level="superieur")
        filiere = Filiere.objects.create(name="Gestion")
        self.programme = Programme.objects.create(
            title="Gestion des organisations",
            filiere=filiere,
            cycle=cycle,
            diploma_awarded=diploma,
            duration_years=3,
            short_description="Programme log",
            description="Programme log",
        )
        self.academic_year = AcademicYear.objects.create(
            name="2027-2028",
            start_date=date(2027, 10, 1),
            end_date=date(2028, 7, 31),
            is_active=True,
        )
        self.academic_class = AcademicClass.objects.create(
            programme=self.programme,
            branch=self.branch,
            academic_year=self.academic_year,
            level="L2",
            study_level="LICENCE",
            validation_threshold=Decimal("10.00"),
            is_active=True,
        )
        semester = Semester.objects.create(
            academic_class=self.academic_class,
            number=1,
            total_required_credits=Decimal("30.00"),
        )
        ue = UE.objects.create(semester=semester, code="GST201", title="Pilotage")
        self.ec = EC.objects.create(
            ue=ue,
            title="Management",
            credit_required=Decimal("3.00"),
            coefficient=Decimal("3.00"),
        )
        self.lesson_date = date(2027, 10, 5)
        self.schedule_event = create_schedule_event(
            user=self.supervisor,
            title="Cours Management",
            description="Seance 1",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=timezone.make_aware(datetime.combine(self.lesson_date, datetime.min.time().replace(hour=8))),
            end_datetime=timezone.make_aware(datetime.combine(self.lesson_date, datetime.min.time().replace(hour=10))),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle M1",
            is_online=False,
            meeting_link="",
            is_active=True,
        )

    def test_create_lesson_log_creates_expected_record(self):
        lesson_log = create_lesson_log(
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            schedule_event=self.schedule_event,
            date=self.lesson_date,
            start_time=time(8, 0),
            end_time=time(10, 0),
            status=LessonLog.STATUS_DONE,
            branch=self.branch,
            created_by=self.supervisor,
            content="Introduction au management",
            homework="Lire le chapitre 1",
        )

        self.assertEqual(LessonLog.objects.count(), 1)
        self.assertEqual(lesson_log.schedule_event, self.schedule_event)
        self.assertEqual(lesson_log.status, LessonLog.STATUS_DONE)

    def test_update_lesson_log_updates_content_and_validation(self):
        lesson_log = create_lesson_log(
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            schedule_event=self.schedule_event,
            date=self.lesson_date,
            start_time=time(8, 0),
            end_time=time(10, 0),
            status=LessonLog.STATUS_PLANNED,
            branch=self.branch,
            created_by=self.supervisor,
        )

        updated = update_lesson_log(
            lesson_log,
            updated_by=self.supervisor,
            status=LessonLog.STATUS_DONE,
            content="Cours dispense",
            homework="Exercice 1",
        )

        self.assertEqual(updated.status, LessonLog.STATUS_DONE)
        self.assertEqual(updated.validated_by, self.supervisor)
        self.assertEqual(updated.content, "Cours dispense")

    def test_get_daily_lesson_status_flags_missing_logs_and_teacher_absence(self):
        TeacherAttendance.objects.create(
            teacher=self.teacher,
            schedule_event=self.schedule_event,
            date=self.lesson_date,
            status=TeacherAttendance.STATUS_ABSENT,
            recorded_by=self.supervisor,
            branch=self.branch,
        )

        daily_status = get_daily_lesson_status(self.branch, self.lesson_date)

        self.assertEqual(daily_status["scheduled_courses"], 1)
        self.assertEqual(daily_status["missing_lesson_logs_count"], 1)
        self.assertEqual(daily_status["critical_count"], 1)
        self.assertEqual(daily_status["critical_items"][0]["status"], "teacher_absent_with_planned_lesson")

    def test_create_lesson_log_for_absent_teacher_forces_absent_teacher_status(self):
        TeacherAttendance.objects.create(
            teacher=self.teacher,
            schedule_event=self.schedule_event,
            date=self.lesson_date,
            status=TeacherAttendance.STATUS_ABSENT,
            recorded_by=self.supervisor,
            branch=self.branch,
        )

        lesson_log = create_lesson_log(
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            schedule_event=self.schedule_event,
            date=self.lesson_date,
            start_time=time(8, 0),
            end_time=time(10, 0),
            status=LessonLog.STATUS_DONE,
            branch=self.branch,
            created_by=self.supervisor,
            content="Cours non tenu",
        )

        self.assertEqual(lesson_log.status, LessonLog.STATUS_ABSENT_TEACHER)

    def test_get_class_and_teacher_lesson_logs_return_created_items(self):
        lesson_log = create_lesson_log(
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            schedule_event=self.schedule_event,
            date=self.lesson_date,
            start_time=time(8, 0),
            end_time=time(10, 0),
            status=LessonLog.STATUS_DONE,
            branch=self.branch,
            created_by=self.supervisor,
            content="Cours dispense",
        )

        class_logs = get_class_lesson_logs(self.academic_class)
        teacher_logs = get_teacher_lesson_logs(self.teacher, branch=self.branch)

        self.assertEqual(class_logs[0].id, lesson_log.id)
        self.assertEqual(teacher_logs[0].id, lesson_log.id)


class LessonLogApiTests(TestCase):
    def setUp(self):
        self.supervisor = User.objects.create_user(username="lesson_api", password="pass1234")
        self.supervisor.profile.position = "academic_supervisor"
        self.supervisor.profile.user_type = "staff"
        self.branch = Branch.objects.create(name="ESFE Sikasso", code="SKO", slug="esfe-sikasso")
        self.other_branch = Branch.objects.create(name="ESFE Gao", code="GAO", slug="esfe-gao")
        self.supervisor.profile.branch = self.branch
        self.supervisor.profile.save(update_fields=["position", "user_type", "branch", "updated_at"])

        self.teacher = User.objects.create_user(username="teacher_api_log", password="x", first_name="Marie", last_name="Curie")
        self.teacher_other = User.objects.create_user(username="teacher_api_log_other", password="x")

        cycle = Cycle.objects.create(name="Licence API Log", min_duration_years=3, max_duration_years=3)
        diploma = Diploma.objects.create(name="Licence API Log", level="superieur")
        filiere = Filiere.objects.create(name="Informatique API Log")
        self.programme = Programme.objects.create(
            title="Developpement logiciel",
            filiere=filiere,
            cycle=cycle,
            diploma_awarded=diploma,
            duration_years=3,
            short_description="Prog API log",
            description="Prog API log",
        )
        self.academic_year = AcademicYear.objects.create(
            name="2029-2030",
            start_date=date(2029, 10, 1),
            end_date=date(2030, 7, 31),
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
        self.other_class = AcademicClass.objects.create(
            programme=self.programme,
            branch=self.other_branch,
            academic_year=self.academic_year,
            level="L1",
            study_level="LICENCE",
            validation_threshold=Decimal("10.00"),
            is_active=True,
        )
        semester = Semester.objects.create(academic_class=self.academic_class, number=1, total_required_credits=Decimal("30.00"))
        other_semester = Semester.objects.create(academic_class=self.other_class, number=1, total_required_credits=Decimal("30.00"))
        ue = UE.objects.create(semester=semester, code="LOG101", title="Log")
        other_ue = UE.objects.create(semester=other_semester, code="LOG201", title="Log2")
        self.ec = EC.objects.create(ue=ue, title="Python", credit_required=Decimal("3.00"), coefficient=Decimal("3.00"))
        self.other_ec = EC.objects.create(ue=other_ue, title="Java", credit_required=Decimal("3.00"), coefficient=Decimal("3.00"))
        self.event = AcademicScheduleEvent.objects.create(
            title="Cours Python",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=timezone.make_aware(datetime(2029, 10, 5, 8, 0)),
            end_datetime=timezone.make_aware(datetime(2029, 10, 5, 10, 0)),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle L1",
            created_by=self.supervisor,
            updated_by=self.supervisor,
            is_active=True,
        )
        self.other_event = AcademicScheduleEvent.objects.create(
            title="Cours Java",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.other_class,
            ec=self.other_ec,
            teacher=self.teacher_other,
            branch=self.other_branch,
            academic_year=self.academic_year,
            start_datetime=timezone.make_aware(datetime(2029, 10, 5, 8, 0)),
            end_datetime=timezone.make_aware(datetime(2029, 10, 5, 10, 0)),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle G1",
            created_by=self.supervisor,
            updated_by=self.supervisor,
            is_active=True,
        )
        self.client.force_login(self.supervisor)

    def test_lesson_log_create_api_creates_record(self):
        response = self.client.post(
            reverse("academics:lesson_log_create"),
            data={
                "academic_class_id": self.academic_class.id,
                "ec_id": self.ec.id,
                "teacher_id": self.teacher.id,
                "schedule_event_id": self.event.id,
                "date": "2029-10-05",
                "start_time": "08:00",
                "end_time": "10:00",
                "status": LessonLog.STATUS_DONE,
                "content": "Variables et boucles",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(LessonLog.objects.count(), 1)
        self.assertEqual(LessonLog.objects.get().schedule_event, self.event)

    def test_lesson_log_create_api_rejects_cross_branch_event(self):
        response = self.client.post(
            reverse("academics:lesson_log_create"),
            data={
                "academic_class_id": self.other_class.id,
                "ec_id": self.other_ec.id,
                "teacher_id": self.teacher_other.id,
                "schedule_event_id": self.other_event.id,
                "date": "2029-10-05",
                "start_time": "08:00",
                "end_time": "10:00",
                "status": LessonLog.STATUS_DONE,
                "content": "Test",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(LessonLog.objects.count(), 0)

    def test_lesson_log_create_api_rejects_invalid_time(self):
        response = self.client.post(
            reverse("academics:lesson_log_create"),
            data={
                "academic_class_id": self.academic_class.id,
                "ec_id": self.ec.id,
                "teacher_id": self.teacher.id,
                "schedule_event_id": self.event.id,
                "date": "2029-10-05",
                "start_time": "10:00",
                "end_time": "08:00",
                "status": LessonLog.STATUS_DONE,
                "content": "Test",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(LessonLog.objects.count(), 0)

    def test_lesson_log_daily_status_api_returns_missing_course(self):
        response = self.client.get(
            reverse("academics:daily_lesson_status"),
            {"date": "2029-10-05"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertEqual(payload["missing_lesson_logs_count"], 1)

    def test_lesson_log_create_api_marks_absent_teacher_automatically(self):
        TeacherAttendance.objects.create(
            teacher=self.teacher,
            schedule_event=self.event,
            date=date(2029, 10, 5),
            status=TeacherAttendance.STATUS_ABSENT,
            recorded_by=self.supervisor,
            branch=self.branch,
        )

        response = self.client.post(
            reverse("academics:lesson_log_create"),
            data={
                "academic_class_id": self.academic_class.id,
                "ec_id": self.ec.id,
                "teacher_id": self.teacher.id,
                "schedule_event_id": self.event.id,
                "date": "2029-10-05",
                "start_time": "08:00",
                "end_time": "10:00",
                "status": LessonLog.STATUS_DONE,
                "content": "Tentative",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["lesson_log"]["status"], LessonLog.STATUS_ABSENT_TEACHER)
