from __future__ import annotations

from datetime import time, timedelta
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.utils import timezone

from academics.models import AcademicClass, AcademicEnrollment, AcademicScheduleEvent, EC, WeeklyScheduleSlot
from academics.services.schedule_service import serialize_weekly_slot_for_ui


TIMETABLE_SUBVIEWS = {"overview", "builder", "preview"}
TIMETABLE_WEEKDAYS = tuple(WeeklyScheduleSlot.WEEKDAY_CHOICES[:6])
DEFAULT_PERIODS = (
    (time(8, 0), time(10, 0)),
    (time(10, 15), time(12, 15)),
    (time(14, 0), time(16, 0)),
    (time(16, 15), time(18, 15)),
)


def _active_classes(branch):
    if branch is None:
        return AcademicClass.objects.none()
    return (
        AcademicClass.objects.select_related(
            "programme", "programme__cycle", "academic_year", "branch"
        )
        .filter(branch=branch, is_active=True, is_archived=False)
        .annotate(
            timetable_student_count=Count(
                "enrollments",
                filter=Q(
                    enrollments__is_active=True,
                    enrollments__status=AcademicEnrollment.STATUS_ACTIVE,
                ),
                distinct=True,
            ),
            timetable_slot_count=Count(
                "weekly_schedule_slots",
                filter=Q(weekly_schedule_slots__is_active=True),
                distinct=True,
            ),
        )
        .order_by("programme__title", "level", "academic_year__name", "id")
    )


def _slot_payload(slot):
    payload = serialize_weekly_slot_for_ui(slot)
    payload["is_active"] = slot.is_active
    payload["duration_minutes"] = int(
        (
            slot.end_time.hour * 60
            + slot.end_time.minute
            - slot.start_time.hour * 60
            - slot.start_time.minute
        )
    )
    payload["ec_code"] = slot.ec.ue.code
    return payload


def _event_payload(event):
    start = timezone.localtime(event.start_datetime)
    end = timezone.localtime(event.end_datetime)
    duration = max(0, int((event.end_datetime - event.start_datetime).total_seconds() // 60))
    return {
        "id": event.id,
        "title": event.ec.title if event.ec_id else event.title,
        "event_title": event.title,
        "status": event.status,
        "status_label": event.get_status_display(),
        "event_type": event.event_type,
        "ec_id": event.ec_id,
        "teacher_id": event.teacher_id,
        "start_datetime": event.start_datetime,
        "end_datetime": event.end_datetime,
        "start_time": start.strftime("%H:%M"),
        "end_time": end.strftime("%H:%M"),
        "_start_time_obj": start.time().replace(second=0, microsecond=0),
        "_end_time_obj": end.time().replace(second=0, microsecond=0),
        "time_range": f"{start:%H:%M} - {end:%H:%M}",
        "weekday_index": start.weekday(),
        "weekday_label": start.strftime("%A"),
        "teacher_name": (event.teacher.get_full_name() or event.teacher.username) if event.teacher_id else "Enseignant non defini",
        "location": event.location or "Salle non precisee",
        "room": event.location or "",
        "branch_name": event.branch.name,
        "class_name": event.academic_class.display_name,
        "ec_code": event.ec.ue.code if event.ec_id and event.ec.ue_id else "",
        "is_online": event.is_online,
        "slot_label": start.strftime("%H:%M"),
        "is_standard_slot": False,
        "duration_minutes": duration,
        "is_today": start.date() == timezone.localdate(),
        "is_postponed": False,
        "is_cancelled": event.status == AcademicScheduleEvent.STATUS_CANCELLED,
        "is_completed": False,
        "is_active": True,
        "is_week_event": True,
    }


def _normalize_week_start(week_start):
    value = week_start or timezone.localdate()
    return value - timedelta(days=value.weekday())


def build_weekly_timetable_grid(
    academic_class, *, week_start=None, include_inactive=False, display_mode="week"
):
    normalized_week = _normalize_week_start(week_start)
    if academic_class is None:
        return {
            "weekdays": [],
            "rows": [],
            "slots": [],
            "total_hours": 0,
            "missing_room_count": 0,
            "week_start": normalized_week,
            "week_end": normalized_week + timedelta(days=5),
        }

    slots_qs = WeeklyScheduleSlot.objects.select_related("ec", "ec__ue", "teacher").filter(
        academic_class=academic_class,
        branch=academic_class.branch,
    )
    if not include_inactive:
        slots_qs = slots_qs.filter(is_active=True)
    slots = list(
        slots_qs
        .order_by("weekday", "start_time", "end_time", "id")
    )
    slot_payloads = [_slot_payload(slot) for slot in slots] if display_mode == "template" else []
    week_end = normalized_week + timedelta(days=6)
    week_events = list(
        AcademicScheduleEvent.objects.select_related("ec", "ec__ue", "teacher", "branch", "academic_class")
        .filter(
            academic_class=academic_class,
            branch=academic_class.branch,
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            is_active=True,
            start_datetime__date__gte=normalized_week,
            start_datetime__date__lte=week_end,
        )
        .exclude(status=AcademicScheduleEvent.STATUS_CANCELLED)
        .order_by("start_datetime", "id")
    )
    show_week_events = display_mode == "week"
    if show_week_events:
        slot_payloads = [_event_payload(event) for event in week_events]
    periods = set(DEFAULT_PERIODS)
    if show_week_events and week_events:
        periods.update((payload["_start_time_obj"], payload["_end_time_obj"]) for payload in slot_payloads)
    elif display_mode == "template":
        periods.update((slot.start_time, slot.end_time) for slot in slots if slot.weekday < 6)
    ordered_periods = sorted(periods, key=lambda value: (value[0], value[1]))

    by_cell = {}
    source_items = week_events if show_week_events else slots
    for source, payload in zip(source_items, slot_payloads):
        weekday = payload["weekday_index"] if "weekday_index" in payload else source.weekday
        if weekday >= 6:
            continue
        start_value = payload.get("_start_time_obj") or source.start_time
        end_value = payload.get("_end_time_obj") or source.end_time
        by_cell.setdefault((weekday, start_value, end_value), []).append(payload)

    weekdays = [
        {
            "value": value,
            "label": label,
            "date": normalized_week + timedelta(days=value),
        }
        for value, label in TIMETABLE_WEEKDAYS
    ]
    rows = []
    for start_time, end_time in ordered_periods:
        cells = []
        for weekday in weekdays:
            cells.append(
                {
                    "weekday": weekday["value"],
                    "weekday_label": weekday["label"],
                    "date": weekday["date"],
                    "slots": by_cell.get(
                        (weekday["value"], start_time, end_time), []
                    ),
                }
            )
        rows.append(
            {
                "start_time": start_time.strftime("%H:%M"),
                "end_time": end_time.strftime("%H:%M"),
                "label": f"{start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}",
                "cells": cells,
            }
        )

    total_minutes = sum(item["duration_minutes"] for item in slot_payloads)
    return {
        "weekdays": weekdays,
        "rows": rows,
        "slots": slot_payloads,
        "total_hours": round(total_minutes / 60, 1),
        "missing_room_count": sum(1 for item in slot_payloads if not item["room"]),
        "sunday_slot_count": sum(1 for slot in slots if slot.weekday == 6),
        "uses_week_events": bool(week_events),
        "week_event_count": len(week_events),
        "recurring_slot_count": len([slot for slot in slots if slot.is_active]),
        "week_start": normalized_week,
        "week_end": normalized_week + timedelta(days=5),
    }


def build_director_timetable_context(
    *, branch, subview="overview", selected_class_id=None, week_start=None, page_number=1, display_mode="week"
):
    subview = subview if subview in TIMETABLE_SUBVIEWS else "overview"
    display_mode = display_mode if display_mode in {"week", "template"} else "week"
    classes = list(_active_classes(branch))

    selected_class = None
    if str(selected_class_id or "").isdigit():
        selected_class = next(
            (
                academic_class
                for academic_class in classes
                if academic_class.id == int(selected_class_id)
            ),
            None,
        )

    normalized_week = _normalize_week_start(week_start)
    grid = build_weekly_timetable_grid(
        selected_class,
        week_start=normalized_week,
        include_inactive=subview == "builder" and display_mode == "template",
        display_mode=display_mode,
    )
    slot_count = sum(item.timetable_slot_count for item in classes)
    configured_count = sum(1 for item in classes if item.timetable_slot_count)
    class_cards = [
        {
            "class": academic_class,
            "student_count": academic_class.timetable_student_count,
            "slot_count": academic_class.timetable_slot_count,
            "is_configured": bool(academic_class.timetable_slot_count),
        }
        for academic_class in classes
    ]
    class_cards_page = Paginator(class_cards, 10).get_page(page_number)

    query_params = {"view": subview}
    if selected_class is not None:
        query_params["class_id"] = selected_class.id
    query_params["week_start"] = normalized_week.isoformat()
    query_params["mode"] = display_mode

    return {
        "timetable_subview": subview,
        "timetable_display_mode": display_mode,
        "timetable_classes": classes,
        "timetable_class_cards": class_cards_page.object_list,
        "timetable_class_cards_page": class_cards_page,
        "timetable_selected_class": selected_class,
        "timetable_grid": grid,
        "timetable_metrics": {
            "classes": len(classes),
            "configured_classes": configured_count,
            "classes_to_configure": len(classes) - configured_count,
            "slots": slot_count,
        },
        "timetable_query_suffix": urlencode(query_params),
        "timetable_overview_query_suffix": urlencode(
            {"view": "overview", "week_start": normalized_week.isoformat()}
        ),
        "timetable_week_start": normalized_week,
        "timetable_week_end": normalized_week + timedelta(days=5),
        "timetable_previous_week": normalized_week - timedelta(days=7),
        "timetable_next_week": normalized_week + timedelta(days=7),
        "timetable_current_week": _normalize_week_start(None),
        "timetable_is_current_week": normalized_week == _normalize_week_start(None),
        "timetable_subject_count": (
            EC.objects.filter(
                ue__semester__academic_class=selected_class,
            )
            .exclude(structure_status=EC.STRUCTURE_ARCHIVED)
            .count()
            if selected_class is not None
            else 0
        ),
        "timetable_teacher_count": (
            get_user_model()
            .objects.filter(
                is_active=True,
                profile__position="teacher",
                profile__branch=branch,
            )
            .count()
            if branch is not None
            else 0
        ),
    }
