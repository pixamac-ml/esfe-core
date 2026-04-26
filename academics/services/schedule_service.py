from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from academics.models import (
    AcademicClass,
    AcademicScheduleChangeLog,
    AcademicScheduleEvent,
    AcademicScheduleExecutionLog,
)
from portal.student.widgets.academics import get_student_academic_snapshot


DEFAULT_TIME_SLOTS = [
    time(8, 0),
    time(10, 0),
    time(12, 0),
    time(14, 0),
    time(16, 0),
    time(18, 0),
]
ACTIVE_EVENT_STATUSES = {
    AcademicScheduleEvent.STATUS_DRAFT,
    AcademicScheduleEvent.STATUS_PLANNED,
    AcademicScheduleEvent.STATUS_ONGOING,
    AcademicScheduleEvent.STATUS_POSTPONED,
}
STANDARD_SLOT_WINDOWS = [
    (time(8, 0), time(10, 0)),
    (time(10, 0), time(12, 0)),
    (time(14, 0), time(16, 0)),
    (time(16, 0), time(18, 0)),
]


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


def _base_conflict_queryset(*, exclude_event_id: int | None = None):
    queryset = AcademicScheduleEvent.objects.filter(is_active=True).exclude(
        status__in=[AcademicScheduleEvent.STATUS_CANCELLED]
    )
    if exclude_event_id:
        queryset = queryset.exclude(pk=exclude_event_id)
    return queryset


def _overlap_filter(start_datetime: datetime, end_datetime: datetime):
    return Q(start_datetime__lt=end_datetime) & Q(end_datetime__gt=start_datetime)


def _conflict_item(conflict_type: str, message: str, event) -> dict:
    return {
        "type": conflict_type,
        "message": message,
        "event_id": event.id if event is not None else None,
        "event": event,
    }


def _serialize_event(event: AcademicScheduleEvent, *, highlight_today: date | None = None) -> dict:
    today = timezone.localdate()
    event_day = timezone.localtime(event.start_datetime).date()
    display_title = event.ec.title if event.ec_id else event.title
    return {
        "id": event.id,
        "title": display_title,
        "event_title": event.title,
        "description": event.description,
        "status": event.status,
        "event_type": event.event_type,
        "start_datetime": event.start_datetime,
        "end_datetime": event.end_datetime,
        "start_time": timezone.localtime(event.start_datetime).strftime("%H:%M"),
        "end_time": timezone.localtime(event.end_datetime).strftime("%H:%M"),
        "weekday_index": event_day.weekday(),
        "weekday_label": event_day.strftime("%A"),
        "teacher_name": (event.teacher.get_full_name() or event.teacher.username) if event.teacher_id else "Enseignant non defini",
        "location": event.location or ("En ligne" if event.is_online else "Salle non precisee"),
        "branch_name": event.branch.name,
        "class_name": event.academic_class.display_name,
        "ec_code": event.ec.ue.code if event.ec_id else "",
        "is_today": event_day == (highlight_today or today),
        "is_postponed": event.status == AcademicScheduleEvent.STATUS_POSTPONED,
        "is_cancelled": event.status == AcademicScheduleEvent.STATUS_CANCELLED,
    }


def _build_week_grid(events, week_start: date):
    days = []
    day_labels = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
    include_sunday = any(timezone.localtime(event.start_datetime).date().weekday() == 6 for event in events)
    day_count = 7 if include_sunday else 6
    today = timezone.localdate()
    for offset in range(day_count):
        current_day = week_start + timedelta(days=offset)
        days.append(
            {
                "date": current_day,
                "label": day_labels[offset],
                "day_number": current_day.day,
                "is_today": current_day == today,
            }
        )

    dynamic_slot_times = {slot for slot in DEFAULT_TIME_SLOTS}
    for event in events:
        local_start = timezone.localtime(event.start_datetime).time().replace(second=0, microsecond=0)
        dynamic_slot_times.add(local_start)

    slots = []
    for slot_time in sorted(dynamic_slot_times):
        row = {
            "label": slot_time.strftime("%H:%M"),
            "cells": [],
        }
        for offset, current_day in enumerate(days):
            day_date = current_day["date"]
            cell_events = []
            for event in events:
                event_start = timezone.localtime(event.start_datetime)
                if event_start.date() != day_date:
                    continue
                if event_start.time().hour == slot_time.hour and event_start.time().minute == slot_time.minute:
                    cell_events.append(_serialize_event(event, highlight_today=today))
            row["cells"].append({"day_index": offset, "events": cell_events})
        slots.append(row)

    return {
        "week_start": week_start,
        "days": days,
        "slots": slots,
        "events": [_serialize_event(event, highlight_today=today) for event in events],
    }


def get_schedule_conflicts(*, academic_class=None, teacher=None, branch=None, academic_year=None, ec=None, location="", start_datetime=None, end_datetime=None, exclude_event=None):
    queryset = _base_conflict_queryset(exclude_event_id=getattr(exclude_event, "id", None))
    if start_datetime and end_datetime:
        queryset = queryset.filter(_overlap_filter(start_datetime, end_datetime))

    class_conflicts = []
    teacher_conflicts = []
    location_conflicts = []
    ec_conflicts = []
    conflicts = []

    filtered_queryset = queryset
    if branch is not None:
        filtered_queryset = filtered_queryset.filter(branch=branch)
    if academic_year is not None:
        filtered_queryset = filtered_queryset.filter(academic_year=academic_year)

    if academic_class is not None:
        class_conflicts = list(filtered_queryset.filter(academic_class=academic_class))
        conflicts.extend(
            _conflict_item(
                "class_conflict",
                "La classe a deja un evenement planifie sur ce creneau.",
                event,
            )
            for event in class_conflicts
        )
    if teacher is not None:
        teacher_conflicts = list(filtered_queryset.filter(teacher=teacher))
        conflicts.extend(
            _conflict_item(
                "teacher_conflict",
                "L'enseignant est deja planifie sur ce creneau.",
                event,
            )
            for event in teacher_conflicts
        )
    if location:
        location_conflicts = list(filtered_queryset.filter(location=location))
        conflicts.extend(
            _conflict_item(
                "location_conflict",
                "La salle ou le lieu est deja occupe sur ce creneau.",
                event,
            )
            for event in location_conflicts
        )
    if ec is not None:
        ec_conflicts = list(filtered_queryset.filter(ec=ec))
        conflicts.extend(
            _conflict_item(
                "ec_conflict",
                "Cet EC est deja planifie sur le meme creneau.",
                event,
            )
            for event in ec_conflicts
        )
    if academic_class is not None and branch is not None and academic_class.branch_id != branch.id:
        conflicts.append(
            _conflict_item(
                "branch_conflict",
                "L'annexe selectionnee est incoherente avec la classe academique.",
                exclude_event,
            )
        )
    if academic_class is not None and academic_year is not None and academic_class.academic_year_id != academic_year.id:
        conflicts.append(
            _conflict_item(
                "academic_year_conflict",
                "L'annee academique selectionnee est incoherente avec la classe academique.",
                exclude_event,
            )
        )

    return {
        "has_conflict": bool(conflicts),
        "conflicts": conflicts,
        "class_conflicts": class_conflicts,
        "teacher_conflicts": teacher_conflicts,
        "location_conflicts": location_conflicts,
        "ec_conflicts": ec_conflicts,
    }


def _ensure_no_conflicts(*, event, exclude_event=None):
    conflicts = get_schedule_conflicts(
        academic_class=event.academic_class,
        teacher=event.teacher,
        branch=event.branch,
        academic_year=event.academic_year,
        ec=event.ec,
        location=event.location,
        start_datetime=event.start_datetime,
        end_datetime=event.end_datetime,
        exclude_event=exclude_event,
    )
    if conflicts["has_conflict"]:
        messages = []
        for item in conflicts["conflicts"]:
            if item["message"] not in messages:
                messages.append(item["message"])
        raise ValidationError(messages)


def _log_change(*, event, action_type, user, old_start_datetime=None, old_end_datetime=None, new_start_datetime=None, new_end_datetime=None, old_status="", new_status="", reason=""):
    return AcademicScheduleChangeLog.objects.create(
        event=event,
        action_type=action_type,
        old_start_datetime=old_start_datetime,
        old_end_datetime=old_end_datetime,
        new_start_datetime=new_start_datetime,
        new_end_datetime=new_end_datetime,
        old_status=old_status or "",
        new_status=new_status or "",
        reason=reason or "",
        changed_by=user,
    )


@transaction.atomic
def create_schedule_event(*, user, **data):
    event = AcademicScheduleEvent(created_by=user, updated_by=user, **data)
    event.full_clean()
    _ensure_no_conflicts(event=event)
    event.save()
    _log_change(
        event=event,
        action_type=AcademicScheduleChangeLog.ACTION_CREATED,
        user=user,
        new_start_datetime=event.start_datetime,
        new_end_datetime=event.end_datetime,
        new_status=event.status,
    )
    return event


@transaction.atomic
def update_schedule_event(event, *, user, **changes):
    old_start = event.start_datetime
    old_end = event.end_datetime
    old_status = event.status
    for field, value in changes.items():
        setattr(event, field, value)
    event.updated_by = user
    event.full_clean()
    _ensure_no_conflicts(event=event, exclude_event=event)
    event.save()
    _log_change(
        event=event,
        action_type=AcademicScheduleChangeLog.ACTION_UPDATED,
        user=user,
        old_start_datetime=old_start,
        old_end_datetime=old_end,
        new_start_datetime=event.start_datetime,
        new_end_datetime=event.end_datetime,
        old_status=old_status,
        new_status=event.status,
    )
    return event


@transaction.atomic
def postpone_schedule_event(event, new_start, new_end, reason, user):
    if not reason or not reason.strip():
        raise ValidationError("Le motif du report est obligatoire.")
    old_start = event.start_datetime
    old_end = event.end_datetime
    old_status = event.status
    event.start_datetime = new_start
    event.end_datetime = new_end
    event.status = AcademicScheduleEvent.STATUS_POSTPONED
    event.updated_by = user
    event.full_clean()
    _ensure_no_conflicts(event=event, exclude_event=event)
    event.save()
    _log_change(
        event=event,
        action_type=AcademicScheduleChangeLog.ACTION_POSTPONED,
        user=user,
        old_start_datetime=old_start,
        old_end_datetime=old_end,
        new_start_datetime=new_start,
        new_end_datetime=new_end,
        old_status=old_status,
        new_status=AcademicScheduleEvent.STATUS_POSTPONED,
        reason=reason,
    )
    return event


@transaction.atomic
def cancel_schedule_event(event, reason, user):
    if not reason or not reason.strip():
        raise ValidationError("Le motif d'annulation est obligatoire.")
    old_status = event.status
    event.status = AcademicScheduleEvent.STATUS_CANCELLED
    event.updated_by = user
    event.save(update_fields=["status", "updated_by", "updated_at"])
    _log_change(
        event=event,
        action_type=AcademicScheduleChangeLog.ACTION_CANCELLED,
        user=user,
        old_start_datetime=event.start_datetime,
        old_end_datetime=event.end_datetime,
        new_start_datetime=event.start_datetime,
        new_end_datetime=event.end_datetime,
        old_status=old_status,
        new_status=event.status,
        reason=reason,
    )
    return event


@transaction.atomic
def start_schedule_event(event, user, notes=""):
    execution_log = event.execution_logs.filter(is_completed=False).order_by("-created_at").first()
    if execution_log is None:
        execution_log = AcademicScheduleExecutionLog.objects.create(
            event=event,
            started_at=timezone.now(),
            actual_teacher=user,
            notes=notes,
            completed_by=None,
        )
    else:
        if execution_log.started_at is None:
            execution_log.started_at = timezone.now()
        execution_log.actual_teacher = user
        execution_log.notes = notes or execution_log.notes
        execution_log.save()
    if event.status != AcademicScheduleEvent.STATUS_ONGOING:
        update_schedule_event(event, user=user, status=AcademicScheduleEvent.STATUS_ONGOING)
    return execution_log


@transaction.atomic
def complete_schedule_event(event, user, notes="", started_at=None, ended_at=None):
    execution_log = event.execution_logs.order_by("-created_at").first()
    started_at = started_at or timezone.now()
    ended_at = ended_at or timezone.now()
    if execution_log is None:
        execution_log = AcademicScheduleExecutionLog.objects.create(
            event=event,
            started_at=started_at,
            actual_teacher=user,
            notes=notes,
            ended_at=ended_at,
            is_completed=True,
            completed_by=user,
        )
    else:
        execution_log.started_at = execution_log.started_at or started_at
        execution_log.ended_at = ended_at
        execution_log.actual_teacher = execution_log.actual_teacher or user
        execution_log.notes = notes or execution_log.notes
        execution_log.is_completed = True
        execution_log.completed_by = user
        execution_log.full_clean()
        execution_log.save()

    old_status = event.status
    event.status = AcademicScheduleEvent.STATUS_COMPLETED
    event.updated_by = user
    event.save(update_fields=["status", "updated_by", "updated_at"])
    _log_change(
        event=event,
        action_type=AcademicScheduleChangeLog.ACTION_COMPLETED,
        user=user,
        old_start_datetime=event.start_datetime,
        old_end_datetime=event.end_datetime,
        new_start_datetime=event.start_datetime,
        new_end_datetime=event.end_datetime,
        old_status=old_status,
        new_status=event.status,
        reason=notes,
    )
    return execution_log


def _week_queryset(queryset, week_start):
    start, end, normalized = _week_bounds(week_start)
    queryset = queryset.filter(
        is_active=True,
        start_datetime__gte=start,
        start_datetime__lt=end,
    ).select_related(
        "academic_class",
        "teacher",
        "branch",
        "ec",
        "ec__ue",
        "academic_year",
    ).order_by("start_datetime", "id")
    return queryset, normalized


def suggest_available_slots(*, academic_class, teacher, branch, academic_year, duration_minutes, week_start):
    normalized = _normalize_week_start(week_start)
    suggestions = []
    duration = timedelta(minutes=duration_minutes)
    for day_offset in range(5):
        current_day = normalized + timedelta(days=day_offset)
        existing_class_events = list(
            _base_conflict_queryset().filter(
                academic_class=academic_class,
                start_datetime__date=current_day,
            )
        )
        existing_teacher_events = list(
            _base_conflict_queryset().filter(
                teacher=teacher,
                start_datetime__date=current_day,
            )
        )
        for window_start, window_end in STANDARD_SLOT_WINDOWS:
            slot_start = timezone.make_aware(datetime.combine(current_day, window_start))
            slot_end = slot_start + duration
            latest_end = timezone.make_aware(datetime.combine(current_day, window_end))
            if slot_end > latest_end:
                continue
            conflicts = get_schedule_conflicts(
                academic_class=academic_class,
                teacher=teacher,
                branch=branch,
                academic_year=academic_year,
                start_datetime=slot_start,
                end_datetime=slot_end,
            )
            if conflicts["has_conflict"]:
                continue
            class_events_same_day = sum(1 for event in existing_class_events if event.status in ACTIVE_EVENT_STATUSES)
            teacher_events_same_day = sum(1 for event in existing_teacher_events if event.status in ACTIVE_EVENT_STATUSES)
            score = 100 - (class_events_same_day * 8) - (teacher_events_same_day * 6)
            if window_start >= time(16, 0):
                score -= 5
            suggestions.append(
                {
                    "start": slot_start,
                    "end": slot_end,
                    "score": max(score, 40),
                    "reason": "Classe et enseignant disponibles sur un creneau standard.",
                }
            )
    return sorted(suggestions, key=lambda item: (-item["score"], item["start"]))


def get_class_week_schedule(academic_class: AcademicClass, week_start):
    queryset, normalized = _week_queryset(
        AcademicScheduleEvent.objects.filter(academic_class=academic_class),
        week_start,
    )
    events = list(queryset)
    return _build_week_grid(events, normalized)


def get_student_week_schedule(student, week_start):
    user = getattr(student, "user", student)
    snapshot = get_student_academic_snapshot(user)
    academic_class = snapshot["academic_class"]
    if academic_class is None:
        normalized = _normalize_week_start(week_start)
        return _build_week_grid([], normalized)
    return get_class_week_schedule(academic_class, week_start)


def get_teacher_week_schedule(user, week_start):
    teacher_user = getattr(user, "user", user)
    queryset, normalized = _week_queryset(
        AcademicScheduleEvent.objects.filter(teacher=teacher_user),
        week_start,
    )
    events = list(queryset)
    return _build_week_grid(events, normalized)


def get_branch_week_schedule(branch, week_start):
    queryset, normalized = _week_queryset(
        AcademicScheduleEvent.objects.filter(branch=branch),
        week_start,
    )
    events = list(queryset)
    return _build_week_grid(events, normalized)


def get_weekly_schedule_stats(branch, week_start):
    queryset, _ = _week_queryset(
        AcademicScheduleEvent.objects.filter(branch=branch),
        week_start,
    )
    events = list(queryset)
    hours_by_status = defaultdict(Decimal)
    teacher_load = defaultdict(lambda: {"count": 0, "hours": Decimal("0")})
    class_load = defaultdict(lambda: {"count": 0, "hours": Decimal("0")})
    for event in events:
        duration_hours = Decimal(event.duration_minutes) / Decimal(60)
        hours_by_status[event.status] += duration_hours
        teacher_key = event.teacher.get_full_name() or event.teacher.username if event.teacher_id else "Non assigne"
        class_key = event.academic_class.display_name
        teacher_load[teacher_key]["count"] += 1
        teacher_load[teacher_key]["hours"] += duration_hours
        class_load[class_key]["count"] += 1
        class_load[class_key]["hours"] += duration_hours
    total_events = len(events)
    completed_count = sum(1 for event in events if event.status == AcademicScheduleEvent.STATUS_COMPLETED)
    cancelled_count = sum(1 for event in events if event.status == AcademicScheduleEvent.STATUS_CANCELLED)
    return {
        "total_events": total_events,
        "planned_count": sum(1 for event in events if event.status == AcademicScheduleEvent.STATUS_PLANNED),
        "completed_count": completed_count,
        "cancelled_count": cancelled_count,
        "postponed_count": sum(1 for event in events if event.status == AcademicScheduleEvent.STATUS_POSTPONED),
        "ongoing_count": sum(1 for event in events if event.status == AcademicScheduleEvent.STATUS_ONGOING),
        "completion_rate": round((completed_count / total_events) * 100, 2) if total_events else 0,
        "cancellation_rate": round((cancelled_count / total_events) * 100, 2) if total_events else 0,
        "teacher_load": dict(teacher_load),
        "class_load": dict(class_load),
        "hours_by_status": hours_by_status,
    }


def get_schedule_alerts(branch, week_start):
    queryset, normalized = _week_queryset(
        AcademicScheduleEvent.objects.filter(branch=branch),
        week_start,
    )
    events = list(queryset)
    alerts = []
    teacher_hours = defaultdict(Decimal)
    teacher_counts = defaultdict(int)
    for event in events:
        if event.teacher_id:
            teacher_key = event.teacher.get_full_name() or event.teacher.username
            teacher_hours[teacher_key] += Decimal(event.duration_minutes) / Decimal(60)
            teacher_counts[teacher_key] += 1
        else:
            alerts.append(
                {
                    "level": "warning",
                    "type": "missing_teacher",
                    "message": f"L'evenement '{event.title}' n'a pas d'enseignant assigne.",
                    "target": event.id,
                }
            )
        if not event.location and not event.is_online:
            alerts.append(
                {
                    "level": "warning",
                    "type": "missing_location",
                    "message": f"L'evenement '{event.title}' n'a pas de salle renseignee.",
                    "target": event.id,
                }
            )
        if event.status == AcademicScheduleEvent.STATUS_POSTPONED:
            latest_log = event.change_logs.filter(action_type=AcademicScheduleChangeLog.ACTION_POSTPONED).first()
            if latest_log and latest_log.new_start_datetime and latest_log.new_start_datetime == latest_log.old_start_datetime:
                alerts.append(
                    {
                        "level": "warning",
                        "type": "postponed_not_rescheduled",
                        "message": f"L'evenement '{event.title}' est reporte sans vraie reprogrammation.",
                        "target": event.id,
                    }
                )
    for teacher_key, hours in teacher_hours.items():
        if hours > Decimal("12"):
            alerts.append(
                {
                    "level": "warning",
                    "type": "teacher_overload",
                    "message": f"{teacher_key} depasse 12h de charge sur la semaine.",
                    "target": teacher_key,
                }
            )

    stats = get_weekly_schedule_stats(branch, normalized)
    if stats["cancellation_rate"] >= 25:
        alerts.append(
            {
                "level": "warning",
                "type": "high_cancellation_rate",
                "message": "Le taux d'annulation depasse le seuil de 25% sur la semaine.",
                "target": branch.id,
            }
        )

    class_ids_with_events = {event.academic_class_id for event in events}
    for academic_class in AcademicClass.objects.filter(branch=branch, academic_year__start_date__lte=normalized + timedelta(days=6), academic_year__end_date__gte=normalized):
        if academic_class.id not in class_ids_with_events:
            alerts.append(
                {
                    "level": "info",
                    "type": "class_without_events",
                    "message": f"La classe {academic_class.display_name} n'a aucun cours programme cette semaine.",
                    "target": academic_class.id,
                }
            )

    for event in events:
        conflicts = get_schedule_conflicts(
            academic_class=event.academic_class,
            teacher=event.teacher,
            branch=event.branch,
            academic_year=event.academic_year,
            ec=event.ec,
            location=event.location,
            start_datetime=event.start_datetime,
            end_datetime=event.end_datetime,
            exclude_event=event,
        )
        if conflicts["has_conflict"]:
            alerts.append(
                {
                    "level": "warning",
                    "type": "unresolved_conflict",
                    "message": f"L'evenement '{event.title}' conserve un conflit non resolu.",
                    "target": event.id,
                }
            )
    return alerts


def get_schedule_quality_score(branch, week_start):
    queryset, normalized = _week_queryset(
        AcademicScheduleEvent.objects.filter(branch=branch),
        week_start,
    )
    events = list(queryset)
    stats = get_weekly_schedule_stats(branch, normalized)
    alerts = get_schedule_alerts(branch, normalized)
    warnings = [alert["message"] for alert in alerts]
    score = 100
    score -= stats["cancelled_count"] * 8
    score -= stats["postponed_count"] * 5
    score -= sum(1 for alert in alerts if alert["type"] == "unresolved_conflict") * 12
    if stats["total_events"]:
        score += min(stats["completed_count"] * 2, 10)

    events_by_day = defaultdict(list)
    for event in events:
        local_start = timezone.localtime(event.start_datetime)
        events_by_day[local_start.date()].append(event)
    for day_events in events_by_day.values():
        ordered = sorted(day_events, key=lambda event: event.start_datetime)
        for previous, current in zip(ordered, ordered[1:]):
            gap_minutes = int((current.start_datetime - previous.end_datetime).total_seconds() // 60)
            if gap_minutes >= 180:
                score -= 3
                warnings.append("Des trous importants existent dans certaines journees.")
                break

    score = max(min(score, 100), 0)
    if score >= 85:
        status = "excellent"
    elif score >= 70:
        status = "good"
    elif score >= 50:
        status = "medium"
    else:
        status = "critical"
    return {
        "score": score,
        "status": status,
        "warnings": list(dict.fromkeys(warnings)),
    }


def get_director_schedule_overview(branch, week_start):
    normalized = _normalize_week_start(week_start)
    return {
        "week_start": normalized,
        "stats": get_weekly_schedule_stats(branch, normalized),
        "quality": get_schedule_quality_score(branch, normalized),
        "alerts": get_schedule_alerts(branch, normalized),
        "timetable": get_branch_week_schedule(branch, normalized),
    }


def get_class_schedule_overview(academic_class, week_start):
    normalized = _normalize_week_start(week_start)
    return {
        "week_start": normalized,
        "academic_class": academic_class,
        "timetable": get_class_week_schedule(academic_class, normalized),
    }


def get_teacher_today_schedule(user):
    teacher_user = getattr(user, "user", user)
    start = timezone.make_aware(datetime.combine(timezone.localdate(), time.min))
    end = start + timedelta(days=1)
    queryset = AcademicScheduleEvent.objects.filter(
        teacher=teacher_user,
        is_active=True,
        start_datetime__gte=start,
        start_datetime__lt=end,
    ).select_related("academic_class", "teacher", "branch", "ec", "ec__ue", "academic_year").order_by("start_datetime", "id")
    events = list(queryset)
    return {
        "date": timezone.localdate(),
        "events": [_serialize_event(event) for event in events],
    }


def get_teacher_next_events(user, limit=5):
    teacher_user = getattr(user, "user", user)
    now = timezone.now()
    queryset = AcademicScheduleEvent.objects.filter(
        teacher=teacher_user,
        is_active=True,
        start_datetime__gte=now,
    ).exclude(
        status=AcademicScheduleEvent.STATUS_CANCELLED,
    ).select_related("academic_class", "teacher", "branch", "ec", "ec__ue", "academic_year").order_by("start_datetime", "id")[:limit]
    return [_serialize_event(event) for event in queryset]


def get_branch_activity_summary(branch, week_start):
    normalized = _normalize_week_start(week_start)
    stats = get_weekly_schedule_stats(branch, normalized)
    quality = get_schedule_quality_score(branch, normalized)
    alerts = get_schedule_alerts(branch, normalized)
    return {
        "week_start": normalized,
        "stats": stats,
        "quality": quality,
        "alert_count": len(alerts),
        "alerts": alerts,
    }
