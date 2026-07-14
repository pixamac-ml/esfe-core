from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from academics.models import AcademicClass, AcademicScheduleEvent, Semester, WeeklyScheduleSlot
from academics.permissions.timetable_permissions import require_timetable_access
from academics.selectors.timetable_selectors import (
    get_auto_assigned_teachers_for_semester,
    get_free_timetable_slots,
    get_timetable_conflicts,
    get_timetable_events_for_class,
    get_timetable_load,
    get_timetable_slots_for_class,
)
from academics.services.schedule_service import (
    create_schedule_event,
    create_weekly_schedule_slot,
    deactivate_weekly_schedule_slot,
    materialize_week_events_from_weekly_slots,
    update_weekly_schedule_slot,
)


@dataclass
class TimetableResult:
    state: str
    created: int = 0
    skipped: int = 0
    archived: int = 0
    warnings: list[str] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)


def _normalize_week_start(week_start: date | datetime | None) -> date:
    if week_start is None:
        week_start = timezone.localdate()
    if isinstance(week_start, datetime):
        week_start = timezone.localtime(week_start).date()
    return week_start - timedelta(days=week_start.weekday())


def _ensure_class_scope(academic_class: AcademicClass, branch):
    if branch is not None and academic_class.branch_id != branch.id:
        raise ValidationError("La classe selectionnee ne correspond pas a l'annexe.")


def _ensure_semester_scope(semester: Semester, academic_class: AcademicClass, branch):
    if semester.academic_class_id != academic_class.id:
        raise ValidationError("Le semestre selectionne ne correspond pas a la classe.")
    if branch is not None and semester.academic_class.branch_id != branch.id:
        raise ValidationError("Le semestre selectionne ne correspond pas a l'annexe.")


def _workflow_state(*, academic_class: AcademicClass, week_start) -> str:
    slots = list(get_timetable_slots_for_class(academic_class, active_only=True))
    events = list(get_timetable_events_for_class(academic_class, week_start=week_start, active_only=True))
    conflicts = get_timetable_conflicts(branch=academic_class.branch, academic_class=academic_class)
    if not slots and not events:
        return "archived"
    if conflicts["has_conflict"]:
        return "draft"
    if events:
        return "published"
    return "validated"


def build_timetable_overview(*, actor=None, academic_class: AcademicClass, week_start=None):
    if actor is not None:
        require_timetable_access(actor, academic_class.branch)
    normalized = _normalize_week_start(week_start)
    conflicts = get_timetable_conflicts(branch=academic_class.branch, academic_class=academic_class, week_start=normalized)
    load = get_timetable_load(branch=academic_class.branch, academic_class=academic_class)
    free_slots = get_free_timetable_slots(academic_class, week_start=normalized)
    auto_assignments = get_auto_assigned_teachers_for_semester(academic_class.semesters.order_by("number", "id").first()) if academic_class.semesters.exists() else []
    return {
        "week_start": normalized,
        "state": _workflow_state(academic_class=academic_class, week_start=normalized),
        "load": load,
        "conflicts": conflicts,
        "free_slots": free_slots,
        "auto_assignments": auto_assignments,
        "weekly_slots": list(get_timetable_slots_for_class(academic_class, active_only=True)),
        "week_events": list(get_timetable_events_for_class(academic_class, week_start=normalized, active_only=True)),
    }


@transaction.atomic
def create_weekly_timetable_slot(*, actor, academic_class, ec, teacher, weekday, start_time, end_time, room=""):
    require_timetable_access(actor, academic_class.branch)
    _ensure_class_scope(academic_class, academic_class.branch)
    return create_weekly_schedule_slot(
        user=actor,
        academic_class=academic_class,
        ec=ec,
        teacher=teacher,
        branch=academic_class.branch,
        academic_year=academic_class.academic_year,
        weekday=weekday,
        start_time=start_time,
        end_time=end_time,
        room=room,
        is_active=True,
    )


@transaction.atomic
def update_weekly_timetable_slot(*, actor, slot: WeeklyScheduleSlot, **changes):
    require_timetable_access(actor, slot.branch)
    return update_weekly_schedule_slot(slot, **changes)


@transaction.atomic
def validate_timetable(*, actor, academic_class: AcademicClass, week_start=None):
    require_timetable_access(actor, academic_class.branch)
    normalized = _normalize_week_start(week_start)
    conflicts = get_timetable_conflicts(branch=academic_class.branch, academic_class=academic_class, week_start=normalized)
    if conflicts["has_conflict"]:
        messages = []
        for item in conflicts["event_conflicts"] + conflicts["class_slot_conflicts"] + conflicts["teacher_slot_conflicts"] + conflicts["room_slot_conflicts"]:
            message = item.get("message")
            if message and message not in messages:
                messages.append(message)
        raise ValidationError(messages or ["Le planning contient des conflits."])
    return TimetableResult(state="validated")


@transaction.atomic
def publish_timetable_week(*, actor, academic_class: AcademicClass, week_start=None):
    require_timetable_access(actor, academic_class.branch)
    normalized = _normalize_week_start(week_start)
    validate_timetable(actor=actor, academic_class=academic_class, week_start=normalized)
    materialization = materialize_week_events_from_weekly_slots(user=actor, academic_class=academic_class, week_start=normalized)
    return TimetableResult(
        state="published",
        created=materialization["created"],
        skipped=materialization["skipped_existing"],
    )


@transaction.atomic
def publish_timetable_semester(*, actor, semester: Semester, week_start=None, weeks_count: int = 1):
    academic_class = semester.academic_class
    require_timetable_access(actor, academic_class.branch)
    _ensure_semester_scope(semester, academic_class, academic_class.branch)
    normalized = _normalize_week_start(week_start)
    created = 0
    skipped = 0
    for offset in range(max(1, weeks_count)):
        cursor = normalized + timedelta(days=7 * offset)
        validate_timetable(actor=actor, academic_class=academic_class, week_start=cursor)
        result = materialize_week_events_from_weekly_slots(user=actor, academic_class=academic_class, week_start=cursor)
        created += result["created"]
        skipped += result["skipped_existing"]
    return TimetableResult(state="published", created=created, skipped=skipped)


@transaction.atomic
def archive_timetable(*, actor, academic_class: AcademicClass, preserve_events: bool = True):
    require_timetable_access(actor, academic_class.branch)
    archived = 0
    for slot in get_timetable_slots_for_class(academic_class, active_only=True):
        deactivate_weekly_schedule_slot(slot)
        archived += 1
    if not preserve_events:
        events = list(get_timetable_events_for_class(academic_class, active_only=True))
        for event in events:
            event.status = AcademicScheduleEvent.STATUS_CANCELLED
            event.is_active = False
            event.updated_by = actor
            event.save(update_fields=["status", "is_active", "updated_by", "updated_at"])
        archived += len(events)
    return TimetableResult(state="archived", archived=archived)


def suggest_timetable_free_slots(*, actor, academic_class: AcademicClass, week_start=None):
    require_timetable_access(actor, academic_class.branch)
    return get_free_timetable_slots(academic_class, week_start=week_start)
