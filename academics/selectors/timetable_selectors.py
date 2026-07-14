from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db.models import Q, Sum
from django.utils import timezone

from academics.models import AcademicClass, AcademicScheduleEvent, WeeklyScheduleSlot
from academics.permissions.timetable_permissions import is_global_timetable_user, user_has_branch_scope
from academics.selectors.academic_readiness_selectors import get_teacher_weekly_conflicts
from academics.selectors.teacher_assignment_selectors import (
    get_teacher_assignments_for_semester,
    get_teacher_assignments_for_teacher,
)
from academics.services.schedule_service import STANDARD_SLOT_WINDOWS, get_schedule_conflicts
from portal.models import DirectorTeacherAssignment


def _normalize_week_start(week_start: date | datetime | None) -> date:
    if week_start is None:
        week_start = timezone.localdate()
    if isinstance(week_start, datetime):
        week_start = timezone.localtime(week_start).date()
    return week_start - timedelta(days=week_start.weekday())


def _week_bounds(week_start: date | datetime | None) -> tuple[datetime, datetime, date]:
    normalized = _normalize_week_start(week_start)
    start = timezone.make_aware(datetime.combine(normalized, time.min))
    end = start + timedelta(days=7)
    return start, end, normalized


def _slot_conflicts_for_class(slots):
    conflicts = []
    by_day = defaultdict(list)
    for slot in slots:
        by_day[slot.weekday].append(slot)
    for weekday, day_slots in by_day.items():
        ordered = sorted(day_slots, key=lambda item: (item.start_time, item.end_time, item.id))
        for index, current in enumerate(ordered):
            for other in ordered[index + 1 :]:
                if current.start_time < other.end_time and current.end_time > other.start_time:
                    conflicts.append(
                        {
                            "type": "weekly_slot_overlap",
                            "weekday": weekday,
                            "message": (
                                f"Classe deja occupee : {current.start_time.strftime('%H:%M')}-{current.end_time.strftime('%H:%M')} "
                                f"et {other.start_time.strftime('%H:%M')}-{other.end_time.strftime('%H:%M')}."
                            ),
                            "first_slot_id": current.id,
                            "second_slot_id": other.id,
                        }
                    )
    return conflicts


def _slot_conflicts_for_teacher(slots):
    conflicts = []
    by_day = defaultdict(list)
    for slot in slots:
        by_day[slot.weekday].append(slot)
    for weekday, day_slots in by_day.items():
        ordered = sorted(day_slots, key=lambda item: (item.start_time, item.end_time, item.id))
        for index, current in enumerate(ordered):
            for other in ordered[index + 1 :]:
                if current.start_time < other.end_time and current.end_time > other.start_time:
                    conflicts.append(
                        {
                            "type": "teacher_conflict",
                            "weekday": weekday,
                            "message": (
                                f"Enseignant deja occupe : {current.start_time.strftime('%H:%M')}-{current.end_time.strftime('%H:%M')} "
                                f"et {other.start_time.strftime('%H:%M')}-{other.end_time.strftime('%H:%M')}."
                            ),
                            "first_slot_id": current.id,
                            "second_slot_id": other.id,
                        }
                    )
    return conflicts


def _slot_conflicts_for_room(slots):
    conflicts = []
    by_room = defaultdict(list)
    for slot in slots:
        if not slot.room:
            continue
        by_room[(slot.weekday, slot.room.strip().lower())].append(slot)
    for (weekday, _room_key), room_slots in by_room.items():
        ordered = sorted(room_slots, key=lambda item: (item.start_time, item.end_time, item.id))
        for index, current in enumerate(ordered):
            for other in ordered[index + 1 :]:
                if current.start_time < other.end_time and current.end_time > other.start_time:
                    conflicts.append(
                        {
                            "type": "room_conflict",
                            "weekday": weekday,
                            "message": (
                                f"Salle deja occupee : {current.room} ({current.academic_class.display_name})."
                            ),
                            "first_slot_id": current.id,
                            "second_slot_id": other.id,
                        }
                    )
    return conflicts


def get_timetable_slots_for_class(academic_class: AcademicClass, *, active_only: bool = True):
    queryset = WeeklyScheduleSlot.objects.select_related("teacher", "ec", "branch", "academic_year").filter(
        academic_class=academic_class,
        branch=academic_class.branch,
    )
    if active_only:
        queryset = queryset.filter(is_active=True)
    return queryset.order_by("weekday", "start_time", "id")


def get_timetable_slots_for_teacher(teacher, *, branch=None, active_only: bool = True):
    queryset = WeeklyScheduleSlot.objects.select_related("academic_class", "ec", "branch", "academic_year").filter(
        teacher=teacher,
    )
    if branch is not None:
        queryset = queryset.filter(branch=branch)
    if active_only:
        queryset = queryset.filter(is_active=True)
    return queryset.order_by("weekday", "start_time", "id")


def get_timetable_events_for_class(academic_class: AcademicClass, *, week_start=None, active_only: bool = True):
    queryset = AcademicScheduleEvent.objects.select_related(
        "teacher",
        "ec",
        "branch",
        "academic_year",
    ).filter(academic_class=academic_class)
    if active_only:
        queryset = queryset.filter(is_active=True).exclude(status=AcademicScheduleEvent.STATUS_CANCELLED)
    if week_start is not None:
        week_start_dt, week_end_dt, _ = _week_bounds(week_start)
        queryset = queryset.filter(start_datetime__gte=week_start_dt, start_datetime__lt=week_end_dt)
    return queryset.order_by("start_datetime", "id")


def get_timetable_events_for_teacher(teacher, *, branch=None, week_start=None, active_only: bool = True):
    queryset = AcademicScheduleEvent.objects.select_related(
        "academic_class",
        "ec",
        "branch",
        "academic_year",
    ).filter(teacher=teacher)
    if branch is not None:
        queryset = queryset.filter(branch=branch)
    if active_only:
        queryset = queryset.filter(is_active=True).exclude(status=AcademicScheduleEvent.STATUS_CANCELLED)
    if week_start is not None:
        week_start_dt, week_end_dt, _ = _week_bounds(week_start)
        queryset = queryset.filter(start_datetime__gte=week_start_dt, start_datetime__lt=week_end_dt)
    return queryset.order_by("start_datetime", "id")


def get_timetable_conflicts(*, branch=None, academic_class=None, teacher=None, week_start=None):
    effective_branch = branch or (academic_class.branch if academic_class is not None else None)
    week_start_dt = None
    week_end_dt = None
    if week_start is not None:
        week_start_dt, week_end_dt, _ = _week_bounds(week_start)
    event_conflicts = []
    if academic_class is not None or teacher is not None:
        conflicts = get_schedule_conflicts(
            academic_class=academic_class,
            teacher=teacher,
            branch=effective_branch,
            start_datetime=week_start_dt,
            end_datetime=week_end_dt,
        )
        event_conflicts.extend(conflicts["conflicts"])

    class_slot_conflicts = _slot_conflicts_for_class(list(get_timetable_slots_for_class(academic_class, active_only=True))) if academic_class is not None else []
    teacher_slot_conflicts = _slot_conflicts_for_teacher(list(get_timetable_slots_for_teacher(teacher, branch=effective_branch, active_only=True))) if teacher is not None else []
    room_slot_conflicts = _slot_conflicts_for_room(
        list(
            WeeklyScheduleSlot.objects.select_related("academic_class", "teacher").filter(
                branch=effective_branch,
                is_active=True,
            )
        )
    ) if effective_branch is not None else []

    return {
        "has_conflict": bool(event_conflicts or class_slot_conflicts or teacher_slot_conflicts or room_slot_conflicts),
        "event_conflicts": event_conflicts,
        "class_slot_conflicts": class_slot_conflicts,
        "teacher_slot_conflicts": teacher_slot_conflicts,
        "room_slot_conflicts": room_slot_conflicts,
    }


def get_timetable_load(*, branch=None, teacher=None, academic_class=None):
    slots = WeeklyScheduleSlot.objects.filter(is_active=True)
    events = AcademicScheduleEvent.objects.filter(is_active=True).exclude(status=AcademicScheduleEvent.STATUS_CANCELLED)
    if branch is not None:
        slots = slots.filter(branch=branch)
        events = events.filter(branch=branch)
    if teacher is not None:
        slots = slots.filter(teacher=teacher)
        events = events.filter(teacher=teacher)
    if academic_class is not None:
        slots = slots.filter(academic_class=academic_class)
        events = events.filter(academic_class=academic_class)

    weekly_hours = Decimal("0.00")
    for slot in slots.select_related("teacher", "ec"):
        duration_minutes = int((datetime.combine(date.min, slot.end_time) - datetime.combine(date.min, slot.start_time)).total_seconds() // 60)
        weekly_hours += Decimal(duration_minutes) / Decimal("60")

    event_hours = Decimal("0.00")
    for event in events.select_related("teacher", "ec"):
        event_hours += Decimal(event.duration_minutes) / Decimal("60")

    return {
        "weekly_hours": weekly_hours,
        "event_hours": event_hours,
        "total_hours": weekly_hours + event_hours,
        "slot_count": slots.count(),
        "event_count": events.count(),
    }


def get_free_timetable_slots(academic_class: AcademicClass, *, week_start=None):
    week_start_dt, _, normalized = _week_bounds(week_start)
    class_slots = list(get_timetable_slots_for_class(academic_class, active_only=True))
    class_events = list(get_timetable_events_for_class(academic_class, week_start=normalized, active_only=True))

    occupied = set()
    for slot in class_slots:
        occupied.add((slot.weekday, slot.start_time.strftime("%H:%M"), slot.end_time.strftime("%H:%M")))
    for event in class_events:
        local_start = timezone.localtime(event.start_datetime)
        local_end = timezone.localtime(event.end_datetime)
        occupied.add((local_start.weekday(), local_start.time().strftime("%H:%M"), local_end.time().strftime("%H:%M")))

    free_slots = []
    for weekday in range(6):
        current_day = normalized + timedelta(days=weekday)
        for start_time, end_time in STANDARD_SLOT_WINDOWS:
            key = (weekday, start_time.strftime("%H:%M"), end_time.strftime("%H:%M"))
            if key in occupied:
                continue
            free_slots.append(
                {
                    "weekday": weekday,
                    "date": current_day,
                    "start_time": start_time,
                    "end_time": end_time,
                    "label": f"{start_time.strftime('%H:%M')}-{end_time.strftime('%H:%M')}",
                }
            )
    return free_slots


def get_auto_assigned_teachers_for_semester(semester):
    assignments = list(get_teacher_assignments_for_semester(semester))
    assignments_by_ec = defaultdict(list)
    assignments_by_ue = defaultdict(list)
    assignments_by_class = []
    assignments_by_semester = []
    for assignment in assignments:
        if assignment.ec_id:
            assignments_by_ec[assignment.ec_id].append(assignment)
        elif assignment.ue_id:
            assignments_by_ue[assignment.ue_id].append(assignment)
        elif assignment.semester_id:
            assignments_by_semester.append(assignment)
        else:
            assignments_by_class.append(assignment)

    ecs = semester.ues.select_related("semester", "semester__academic_class").prefetch_related("ecs").all()
    resolved = []
    for ue in ecs:
        for ec in ue.ecs.all():
            candidate = None
            if assignments_by_ec.get(ec.id):
                candidate = assignments_by_ec[ec.id][0]
            elif assignments_by_ue.get(ue.id):
                candidate = assignments_by_ue[ue.id][0]
            elif assignments_by_semester:
                candidate = assignments_by_semester[0]
            elif assignments_by_class:
                candidate = assignments_by_class[0]
            if candidate is not None:
                resolved.append(
                    {
                        "ec": ec,
                        "teacher": candidate.teacher,
                        "assignment": candidate,
                    }
                )
    return resolved
