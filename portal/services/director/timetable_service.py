from __future__ import annotations

from datetime import time, timedelta
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.utils import timezone

from academics.models import AcademicClass, AcademicEnrollment, EC, WeeklyScheduleSlot
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


def _normalize_week_start(week_start):
    value = week_start or timezone.localdate()
    return value - timedelta(days=value.weekday())


def build_weekly_timetable_grid(academic_class, *, week_start=None):
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

    slots = list(
        WeeklyScheduleSlot.objects.select_related("ec", "ec__ue", "teacher")
        .filter(
            academic_class=academic_class,
            branch=academic_class.branch,
            is_active=True,
        )
        .order_by("weekday", "start_time", "end_time", "id")
    )
    slot_payloads = [_slot_payload(slot) for slot in slots]
    periods = set(DEFAULT_PERIODS)
    periods.update((slot.start_time, slot.end_time) for slot in slots if slot.weekday < 6)
    ordered_periods = sorted(periods, key=lambda value: (value[0], value[1]))

    by_cell = {}
    for slot, payload in zip(slots, slot_payloads):
        if slot.weekday >= 6:
            continue
        by_cell.setdefault((slot.weekday, slot.start_time, slot.end_time), []).append(payload)

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
        "week_start": normalized_week,
        "week_end": normalized_week + timedelta(days=5),
    }


def build_director_timetable_context(
    *, branch, subview="overview", selected_class_id=None, week_start=None, page_number=1
):
    subview = subview if subview in TIMETABLE_SUBVIEWS else "overview"
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
    grid = build_weekly_timetable_grid(selected_class, week_start=normalized_week)
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

    return {
        "timetable_subview": subview,
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
