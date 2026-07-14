from __future__ import annotations

from datetime import date, datetime, time
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from academics.models import AcademicClass, AcademicScheduleEvent, AcademicYear, EC, Semester, UE, WeeklyScheduleSlot
from academics.permissions.timetable_permissions import can_manage_timetable, require_timetable_access
from academics.selectors.timetable_selectors import (
    get_free_timetable_slots,
    get_timetable_conflicts,
    get_timetable_events_for_class,
    get_timetable_load,
    get_timetable_slots_for_class,
    get_timetable_slots_for_teacher,
)
from academics.services.timetable_management_service import (
    archive_timetable,
    build_timetable_overview,
    publish_timetable_semester,
    validate_timetable,
)
from branches.models import Branch
from formations.models import Cycle, Diploma, Filiere, Programme


User = get_user_model()


class TimetableManagementTests(TestCase):
    def setUp(self):
        suffix = uuid4().hex[:6]
        self.branch = Branch.objects.create(code=f"TM{suffix[:4].upper()}", name=f"TM{suffix[:5]}", slug=f"tm-{suffix}")
        self.other_branch = Branch.objects.create(code=f"OT{suffix[:4].upper()}", name=f"OT{suffix[:5]}", slug=f"ot-{suffix}")
        self.filiere = Filiere.objects.create(name=f"Filiere {suffix}", description="")
        self.cycle = Cycle.objects.create(
            name=f"Cycle {suffix}",
            description="",
            theme="accent",
            min_duration_years=3,
            max_duration_years=3,
        )
        self.diploma = Diploma.objects.create(name=f"Diplome {suffix}", level="superieur")
        self.programme = Programme.objects.create(
            title=f"Licence {suffix}",
            filiere=self.filiere,
            cycle=self.cycle,
            diploma_awarded=self.diploma,
            duration_years=3,
            short_description="Programme de test",
            description="Programme de test",
        )
        self.academic_year = AcademicYear.objects.create(
            name=f"2026-2027 {suffix}",
            start_date="2026-10-01",
            end_date="2027-07-31",
            is_active=True,
        )
        self.academic_class = AcademicClass.objects.create(
            programme=self.programme,
            branch=self.branch,
            academic_year=self.academic_year,
            level="D1A",
            study_level="LICENCE",
            is_active=True,
        )
        self.semester = Semester.objects.create(academic_class=self.academic_class, number=1)
        self.ue = UE.objects.create(semester=self.semester, code="UE-TIM", title="UE Timetable")
        self.ec = EC.objects.create(ue=self.ue, title="EC Timetable", credit_required=3, coefficient=2)
        self.teacher = User.objects.create_user(username=f"tim.teacher.{suffix}", email=f"tim.teacher.{suffix}@example.com", password="pwd")
        self.teacher.profile.position = "teacher"
        self.teacher.profile.branch = self.branch
        self.teacher.profile.employment_status = "active"
        self.teacher.profile.save()
        self.director = User.objects.create_user(username=f"tim.director.{suffix}", email=f"tim.director.{suffix}@example.com", password="pwd")
        self.director.profile.position = "director_of_studies"
        self.director.profile.branch = self.branch
        self.director.profile.save()
        self.other_director = User.objects.create_user(username=f"tim.other.{suffix}", email=f"tim.other.{suffix}@example.com", password="pwd")
        self.other_director.profile.position = "director_of_studies"
        self.other_director.profile.branch = self.other_branch
        self.other_director.profile.save()
        self.dg = User.objects.create_user(username=f"tim.dg.{suffix}", email=f"tim.dg.{suffix}@example.com", password="pwd")
        self.dg.profile.position = "executive_director"
        self.dg.profile.branch = None
        self.dg.profile.save()

    def _create_slot(self, *, weekday=0, start="08:00", end="10:00", room="Salle A1"):
        return WeeklyScheduleSlot.objects.create(
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            weekday=weekday,
            start_time=time.fromisoformat(start),
            end_time=time.fromisoformat(end),
            room=room,
            is_active=True,
            created_by=self.director,
        )

    def _create_event(self, *, date_value="2026-10-05", start="08:00", end="10:00"):
        event_date = datetime.strptime(date_value, "%Y-%m-%d").date()
        start_dt = timezone.make_aware(datetime.combine(event_date, time.fromisoformat(start)))
        end_dt = timezone.make_aware(datetime.combine(event_date, time.fromisoformat(end)))
        return AcademicScheduleEvent.objects.create(
            title="EC Timetable - D1A",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=start_dt,
            end_datetime=end_dt,
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle A1",
            is_online=False,
            meeting_link="",
            created_by=self.director,
            updated_by=self.director,
            is_active=True,
        )

    def test_permissions_respect_branch_scope(self):
        self.assertTrue(can_manage_timetable(self.director, self.branch))
        self.assertFalse(can_manage_timetable(self.other_director, self.branch))
        self.assertTrue(can_manage_timetable(self.dg, self.branch))
        with self.assertRaises(PermissionDenied):
            require_timetable_access(self.other_director, self.branch)

    def test_selectors_cover_class_teacher_load_and_free_slots(self):
        slot = self._create_slot()
        event = self._create_event()

        class_slots = list(get_timetable_slots_for_class(self.academic_class))
        teacher_slots = list(get_timetable_slots_for_teacher(self.teacher))
        events = list(get_timetable_events_for_class(self.academic_class, week_start=date(2026, 10, 5)))
        load = get_timetable_load(branch=self.branch, teacher=self.teacher)
        free_slots = get_free_timetable_slots(self.academic_class, week_start=date(2026, 10, 5))
        conflicts = get_timetable_conflicts(branch=self.branch, academic_class=self.academic_class, teacher=self.teacher)

        self.assertEqual(class_slots[0].id, slot.id)
        self.assertEqual(teacher_slots[0].id, slot.id)
        self.assertEqual(events[0].id, event.id)
        self.assertEqual(load["slot_count"], 1)
        self.assertEqual(load["event_count"], 1)
        self.assertGreaterEqual(load["total_hours"], 2)
        self.assertTrue(any(item["weekday"] == 0 and item["label"] == "10:00-12:00" for item in free_slots))
        self.assertTrue(conflicts["has_conflict"])

    def test_validate_and_publish_semester_timetable(self):
        self._create_slot()
        validation = validate_timetable(actor=self.director, academic_class=self.academic_class, week_start=date(2026, 10, 5))
        self.assertEqual(validation.state, "validated")

        publish = publish_timetable_semester(
            actor=self.director,
            semester=self.semester,
            week_start=date(2026, 10, 5),
            weeks_count=2,
        )
        self.assertEqual(publish.state, "published")
        self.assertEqual(publish.created, 2)
        self.assertEqual(
            AcademicScheduleEvent.objects.filter(
                academic_class=self.academic_class,
                academic_year=self.academic_year,
                ec=self.ec,
                teacher=self.teacher,
            ).count(),
            2,
        )

    def test_archive_timetable_deactivates_slots(self):
        slot = self._create_slot()
        archive = archive_timetable(actor=self.director, academic_class=self.academic_class)
        self.assertEqual(archive.state, "archived")
        slot.refresh_from_db()
        self.assertFalse(slot.is_active)

    def test_build_overview_reports_state_and_load(self):
        self._create_slot()
        overview = build_timetable_overview(actor=self.director, academic_class=self.academic_class, week_start=date(2026, 10, 5))
        self.assertIn(overview["state"], {"validated", "published"})
        self.assertIn("load", overview)
        self.assertIn("free_slots", overview)
