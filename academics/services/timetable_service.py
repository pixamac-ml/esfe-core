from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from academics.models import AcademicClass, AcademicScheduleEvent
from academics.services.schedule_service import (
    get_class_schedule_overview,
    get_schedule_alerts,
    list_weekly_slots_for_class,
    serialize_weekly_slot_for_ui,
)
from branches.models import Branch


def _weekly_slots_internal_conflicts(slots) -> list[dict]:
    by_weekday = defaultdict(list)
    for slot in slots:
        by_weekday[slot.weekday].append(slot)
    out = []
    for weekday, day_slots in by_weekday.items():
        ordered = sorted(day_slots, key=lambda s: (s.start_time, s.end_time, s.id))
        for i, a in enumerate(ordered):
            for b in ordered[i + 1 :]:
                if a.start_time < b.end_time and a.end_time > b.start_time:
                    out.append(
                        {
                            "weekday": weekday,
                            "message": (
                                f"Creneaux qui se chevauchent : {a.start_time.strftime('%H:%M')}-{a.end_time.strftime('%H:%M')} "
                                f"et {b.start_time.strftime('%H:%M')}-{b.end_time.strftime('%H:%M')}."
                            ),
                        }
                    )
    return out


def build_timetable_view_payload(*, branch: Branch, academic_class: AcademicClass, week_start) -> dict:
    """Contexte unique pour le composant « emploi du temps » (grille + modele hebdo + enseignants)."""
    overview = get_class_schedule_overview(academic_class, week_start)
    normalized_week = overview["week_start"]
    timetable = overview["timetable"]

    slots = list_weekly_slots_for_class(academic_class, active_only=True)
    slot_rows = [serialize_weekly_slot_for_ui(s) for s in slots]
    slot_conflicts = _weekly_slots_internal_conflicts(slots)

    teachers_map: dict[int, dict] = {}
    for s in slots:
        if not s.teacher_id:
            continue
        entry = teachers_map.setdefault(
            s.teacher_id,
            {"id": s.teacher_id, "name": s.teacher.get_full_name() or s.teacher.username, "weekly_slots": 0, "week_events": 0},
        )
        entry["weekly_slots"] += 1

    week_events = list(
        AcademicScheduleEvent.objects.filter(
            academic_class=academic_class,
            branch=branch,
            start_datetime__date__gte=normalized_week,
            start_datetime__date__lt=normalized_week + timedelta(days=7),
            is_active=True,
        )
        .exclude(status=AcademicScheduleEvent.STATUS_CANCELLED)
        .select_related("teacher")
    )
    for event in week_events:
        tid = event.teacher_id
        if not tid:
            continue
        name = event.teacher.get_full_name() or event.teacher.username
        entry = teachers_map.setdefault(
            tid,
            {"id": tid, "name": name, "weekly_slots": 0, "week_events": 0},
        )
        entry["week_events"] += 1
        entry["name"] = name

    branch_alerts = get_schedule_alerts(branch, normalized_week)
    class_name = academic_class.display_name
    class_alerts = [
        item
        for item in branch_alerts
        if class_name in (item.get("message") or "") or (item.get("target") and str(academic_class.id) in str(item.get("target")))
    ]

    return {
        "academic_class_name": class_name,
        "week_start": normalized_week,
        "timetable": timetable,
        "weekly_slots": slot_rows,
        "weekly_slot_conflicts": slot_conflicts,
        "teachers_for_sync": sorted(teachers_map.values(), key=lambda r: r["name"].lower()),
        "schedule_alert_count": len(class_alerts),
        "schedule_alerts": class_alerts[:6],
    }
