from datetime import date, datetime, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from academics.models import (
    AcademicClass,
    AcademicEnrollment,
    AcademicScheduleChangeLog,
    AcademicScheduleEvent,
    AcademicYear,
    EC,
    Semester,
    UE,
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
from students.models import Student


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
