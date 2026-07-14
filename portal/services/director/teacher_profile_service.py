from __future__ import annotations

from decimal import Decimal

from django.db.models import Count
from django.utils import timezone

from academics.models import (
    AcademicScheduleEvent,
    LessonLog,
    WeeklyScheduleSlot,
)
from portal.models import DirectorTeacherAssignment


def build_teacher_profile_context(*, teacher, branch):
    """
    Construit le contexte complet pour la fiche d'un enseignant :
    - Identite et informations de base
    - Affectations (classes, matieres, salles, volume prevu)
    - Suivi pedagogique par EC : heures prevues / faites / annulees / restantes
    - Derniers cahiers de texte (LessonLog)
    - Creneaux hebdomadaires (WeeklyScheduleSlot)
    """
    profile = getattr(teacher, "profile", None)

    # ── Affectations actives ──────────────────────────────────────────────────
    assignments = list(
        DirectorTeacherAssignment.objects.select_related("academic_class", "ec", "ec__ue", "ec__ue__semester")
        .filter(teacher=teacher, branch=branch, is_active=True)
        .order_by("academic_class__level", "academic_class__id", "ec__title")
    )

    # ── Creneaux hebdomadaires ────────────────────────────────────────────────
    weekly_slots = list(
        WeeklyScheduleSlot.objects.select_related("academic_class", "ec")
        .filter(teacher=teacher, branch=branch, is_active=True)
        .order_by("weekday", "start_time")
    )

    # ── LessonLogs (suivi reel) ───────────────────────────────────────────────
    lesson_logs = list(
        LessonLog.objects.select_related("academic_class", "ec")
        .filter(teacher=teacher, branch=branch)
        .order_by("-date", "-start_time")[:60]
    )

    # ── Stats globales depuis LessonLog ───────────────────────────────────────
    stats_qs = (
        LessonLog.objects.filter(teacher=teacher, branch=branch)
        .values("status")
        .annotate(total=Count("id"))
    )
    stats_map = {row["status"]: row["total"] for row in stats_qs}
    total_done      = stats_map.get(LessonLog.STATUS_DONE, 0)
    total_planned   = stats_map.get(LessonLog.STATUS_PLANNED, 0)
    total_cancelled = stats_map.get(LessonLog.STATUS_CANCELLED, 0)
    total_absent    = stats_map.get(LessonLog.STATUS_ABSENT_TEACHER, 0)
    total_logs      = total_done + total_planned + total_cancelled + total_absent

    # ── Suivi par EC ──────────────────────────────────────────────────────────
    # Initialiser TOUTES les EC depuis les affectations (meme sans LessonLog)
    ec_stats: dict[int, dict] = {}
    for asgn in assignments:
        if not asgn.ec_id:
            continue
        if asgn.ec_id not in ec_stats:
            ec_stats[asgn.ec_id] = {
                "ec_id": asgn.ec_id,
                "ec_title": asgn.ec.title if asgn.ec_id else "",
                "done": 0, "planned": 0, "cancelled": 0, "absent": 0,
                "planned_hours": Decimal("0"),
            }
        if asgn.planned_hours:
            ec_stats[asgn.ec_id]["planned_hours"] += asgn.planned_hours

    # Agreger les LessonLogs par EC
    ec_logs_qs = (
        LessonLog.objects.filter(teacher=teacher, branch=branch)
        .values("ec_id", "ec__title", "status")
        .annotate(count=Count("id"))
    )
    for row in ec_logs_qs:
        ec_id = row["ec_id"]
        if ec_id not in ec_stats:
            ec_stats[ec_id] = {
                "ec_id": ec_id,
                "ec_title": row["ec__title"] or "",
                "done": 0, "planned": 0, "cancelled": 0, "absent": 0,
                "planned_hours": Decimal("0"),
            }
        # Mettre a jour le titre si on l'a depuis les logs
        if row["ec__title"] and not ec_stats[ec_id]["ec_title"]:
            ec_stats[ec_id]["ec_title"] = row["ec__title"]
        if row["status"] == LessonLog.STATUS_DONE:
            ec_stats[ec_id]["done"] += row["count"]
        elif row["status"] == LessonLog.STATUS_PLANNED:
            ec_stats[ec_id]["planned"] += row["count"]
        elif row["status"] == LessonLog.STATUS_CANCELLED:
            ec_stats[ec_id]["cancelled"] += row["count"]
        elif row["status"] == LessonLog.STATUS_ABSENT_TEACHER:
            ec_stats[ec_id]["absent"] += row["count"]

    ec_rows = []
    for ec_id, data in ec_stats.items():
        done     = data["done"]
        planned  = data["planned"]
        absent   = data["absent"]
        cancelled = data["cancelled"]
        total    = done + planned + cancelled + absent
        planned_h = float(data["planned_hours"])
        # Estimation heures realisees (approximation : 2h par seance faite)
        done_h   = done * 2
        remaining_h = max(planned_h - done_h, 0)
        progress_pct = int((done_h / planned_h * 100)) if planned_h > 0 else 0
        ec_rows.append({
            "ec_id":       ec_id,
            "ec_title":    data["ec_title"],
            "done":        done,
            "planned":     planned,
            "cancelled":   cancelled,
            "absent":      absent,
            "total_logs":  total,
            "planned_h":   planned_h,
            "done_h":      done_h,
            "remaining_h": remaining_h,
            "progress_pct": min(progress_pct, 100),
        })
    ec_rows.sort(key=lambda r: r["ec_title"])

    # ── Grouper les creneaux par jour ─────────────────────────────────────────
    JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"]
    slots_by_day: dict[str, list] = {j: [] for j in JOURS}
    for slot in weekly_slots:
        label = JOURS[slot.weekday] if slot.weekday < len(JOURS) else str(slot.weekday)
        slots_by_day.setdefault(label, []).append(slot)
    weekly_grid = [
        {"day": day, "slots": slots_by_day[day]}
        for day in JOURS
        if slots_by_day.get(day)
    ]

    # ── Prochains evenements planifies ────────────────────────────────────────
    now = timezone.now()
    upcoming_events = list(
        AcademicScheduleEvent.objects.select_related("academic_class", "ec")
        .filter(teacher=teacher, branch=branch, is_active=True, start_datetime__gte=now)
        .order_by("start_datetime")[:5]
    )

    # ── Classes et matieres distinctes ───────────────────────────────────────
    class_set = {asgn.academic_class for asgn in assignments if asgn.academic_class_id}
    ec_set    = {asgn.ec for asgn in assignments if asgn.ec_id}

    # ── Volume horaire global prevu ───────────────────────────────────────────
    total_planned_hours = sum(
        (asgn.planned_hours or Decimal("0")) for asgn in assignments
    )

    return {
        "profile_teacher":        teacher,
        "profile_teacher_profile": profile,
        "profile_assignments":    assignments,
        "profile_classes":        sorted(class_set, key=lambda c: c.display_name),
        "profile_ecs":            sorted(ec_set, key=lambda e: e.title),
        "profile_weekly_grid":    weekly_grid,
        "profile_upcoming_events": upcoming_events,
        "profile_lesson_logs":    lesson_logs[:20],
        "profile_ec_rows":        ec_rows,
        "profile_total_done":     total_done,
        "profile_total_planned":  total_planned,
        "profile_total_cancelled": total_cancelled,
        "profile_total_absent":   total_absent,
        "profile_total_logs":     total_logs,
        "profile_total_planned_hours": float(total_planned_hours),
        "profile_done_h":         total_done * 2,
        "profile_remaining_h":    max(float(total_planned_hours) - total_done * 2, 0),
        "profile_global_progress": min(
            int(total_done * 2 / float(total_planned_hours) * 100)
            if total_planned_hours > 0 else 0,
            100,
        ),
    }
