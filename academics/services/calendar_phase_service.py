"""
calendar_phase_service.py
=========================
Moteur de phases actives du calendrier académique.

Responsabilités :
- Déterminer la phase courante d'une annexe à un instant donné
- Lister toutes les phases de l'année avec leur statut (passé/actif/à venir)
- Calculer les alertes J-14 et J-7 pour chaque phase
- Fournir un contexte riche pour les dashboards et les notifications

Usage :
    from academics.services.calendar_phase_service import get_calendar_phase_context

    ctx = get_calendar_phase_context(branch=branch, academic_year=year)
    ctx["current_phase"]       # phase active maintenant (ou None)
    ctx["next_phase"]          # prochaine phase à venir (ou None)
    ctx["phases"]              # toutes les phases de l'année
    ctx["alert_phases"]        # phases en alerte J-14 ou J-7
    ctx["calendar"]            # AcademicCalendar publié (ou None)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Optional

from django.utils import timezone

from academics.models import AcademicCalendar, AcademicCalendarEntry

# ---------------------------------------------------------------------------
# Types de phases — ordonnées dans le déroulement de l'année
# ---------------------------------------------------------------------------

PHASE_ORDER = [
    AcademicCalendarEntry.EVENT_ACADEMIC_START,
    AcademicCalendarEntry.EVENT_REGISTRATION,
    AcademicCalendarEntry.EVENT_REREGISTRATION,
    AcademicCalendarEntry.EVENT_SEMESTER_START,
    AcademicCalendarEntry.EVENT_EXAM_SESSION,
    AcademicCalendarEntry.EVENT_RETAKE_SESSION,
    AcademicCalendarEntry.EVENT_JURY,
    AcademicCalendarEntry.EVENT_RESULT_PUBLICATION,
    AcademicCalendarEntry.EVENT_SEMESTER_END,
    AcademicCalendarEntry.EVENT_HOLIDAY,
    AcademicCalendarEntry.EVENT_PUBLIC_HOLIDAY,
    AcademicCalendarEntry.EVENT_CEREMONY,
    AcademicCalendarEntry.EVENT_MEETING,
    AcademicCalendarEntry.EVENT_ACADEMIC_END,
    AcademicCalendarEntry.EVENT_OTHER,
]

# Phases qui méritent une alerte J-14 au directeur des études
DIRECTOR_ALERT_TYPES = {
    AcademicCalendarEntry.EVENT_SEMESTER_START,
    AcademicCalendarEntry.EVENT_EXAM_SESSION,
    AcademicCalendarEntry.EVENT_RETAKE_SESSION,
    AcademicCalendarEntry.EVENT_JURY,
    AcademicCalendarEntry.EVENT_ACADEMIC_END,
}

# Phases qui méritent une alerte J-7 aux étudiants
STUDENT_ALERT_TYPES = {
    AcademicCalendarEntry.EVENT_SEMESTER_START,
    AcademicCalendarEntry.EVENT_EXAM_SESSION,
    AcademicCalendarEntry.EVENT_RETAKE_SESSION,
    AcademicCalendarEntry.EVENT_RESULT_PUBLICATION,
}

# Libellés courts pour affichage
PHASE_LABELS = {
    AcademicCalendarEntry.EVENT_ACADEMIC_START: "Rentrée académique",
    AcademicCalendarEntry.EVENT_ACADEMIC_END: "Clôture académique",
    AcademicCalendarEntry.EVENT_SEMESTER_START: "Début de semestre",
    AcademicCalendarEntry.EVENT_SEMESTER_END: "Fin de semestre",
    AcademicCalendarEntry.EVENT_EXAM_SESSION: "Session d'examens",
    AcademicCalendarEntry.EVENT_RETAKE_SESSION: "Session de rattrapage",
    AcademicCalendarEntry.EVENT_JURY: "Jury",
    AcademicCalendarEntry.EVENT_RESULT_PUBLICATION: "Publication des résultats",
    AcademicCalendarEntry.EVENT_HOLIDAY: "Vacances",
    AcademicCalendarEntry.EVENT_PUBLIC_HOLIDAY: "Jour férié",
    AcademicCalendarEntry.EVENT_REGISTRATION: "Inscriptions",
    AcademicCalendarEntry.EVENT_REREGISTRATION: "Réinscriptions",
    AcademicCalendarEntry.EVENT_CEREMONY: "Cérémonie",
    AcademicCalendarEntry.EVENT_MEETING: "Réunion",
    AcademicCalendarEntry.EVENT_OTHER: "Autre",
}

PHASE_ICONS = {
    AcademicCalendarEntry.EVENT_ACADEMIC_START: "flag",
    AcademicCalendarEntry.EVENT_ACADEMIC_END: "flag-off",
    AcademicCalendarEntry.EVENT_SEMESTER_START: "play-circle",
    AcademicCalendarEntry.EVENT_SEMESTER_END: "stop-circle",
    AcademicCalendarEntry.EVENT_EXAM_SESSION: "pencil-ruler",
    AcademicCalendarEntry.EVENT_RETAKE_SESSION: "repeat",
    AcademicCalendarEntry.EVENT_JURY: "gavel",
    AcademicCalendarEntry.EVENT_RESULT_PUBLICATION: "megaphone",
    AcademicCalendarEntry.EVENT_HOLIDAY: "sun",
    AcademicCalendarEntry.EVENT_PUBLIC_HOLIDAY: "star",
    AcademicCalendarEntry.EVENT_REGISTRATION: "user-plus",
    AcademicCalendarEntry.EVENT_REREGISTRATION: "refresh-cw",
    AcademicCalendarEntry.EVENT_CEREMONY: "award",
    AcademicCalendarEntry.EVENT_MEETING: "users",
    AcademicCalendarEntry.EVENT_OTHER: "circle-dot",
}

PHASE_TONES = {
    AcademicCalendarEntry.EVENT_ACADEMIC_START: "primary",
    AcademicCalendarEntry.EVENT_ACADEMIC_END: "muted",
    AcademicCalendarEntry.EVENT_SEMESTER_START: "primary",
    AcademicCalendarEntry.EVENT_SEMESTER_END: "muted",
    AcademicCalendarEntry.EVENT_EXAM_SESSION: "danger",
    AcademicCalendarEntry.EVENT_RETAKE_SESSION: "danger",
    AcademicCalendarEntry.EVENT_JURY: "accent",
    AcademicCalendarEntry.EVENT_RESULT_PUBLICATION: "accent",
    AcademicCalendarEntry.EVENT_HOLIDAY: "warning",
    AcademicCalendarEntry.EVENT_PUBLIC_HOLIDAY: "warning",
    AcademicCalendarEntry.EVENT_REGISTRATION: "success",
    AcademicCalendarEntry.EVENT_REREGISTRATION: "success",
    AcademicCalendarEntry.EVENT_CEREMONY: "success",
    AcademicCalendarEntry.EVENT_MEETING: "muted",
    AcademicCalendarEntry.EVENT_OTHER: "muted",
}


# ---------------------------------------------------------------------------
# Dataclass Phase
# ---------------------------------------------------------------------------

@dataclass
class CalendarPhase:
    entry: AcademicCalendarEntry
    label: str
    icon: str
    tone: str
    is_past: bool
    is_active: bool
    is_upcoming: bool
    days_until_start: Optional[int]      # None si déjà commencée
    days_until_end: Optional[int]        # None si déjà terminée
    days_elapsed: Optional[int]          # None si pas encore commencée
    duration_days: int
    progress_pct: int                    # 0-100, pourcentage d'avancement si active
    alert_director: bool                 # True si J-14 ou J-7 pour le directeur
    alert_students: bool                 # True si J-7 pour les étudiants
    alert_days: Optional[int]            # combien de jours restants avant le début (pour l'alerte)


# ---------------------------------------------------------------------------
# Sélecteur interne
# ---------------------------------------------------------------------------

def _get_published_calendar(branch, academic_year) -> Optional[AcademicCalendar]:
    return (
        AcademicCalendar.objects.filter(
            branch=branch,
            academic_year=academic_year,
            status=AcademicCalendar.STATUS_PUBLISHED,
        )
        .prefetch_related("entries")
        .order_by("-version", "-published_at", "-id")
        .first()
    )


def _get_active_academic_year(branch):
    """Retourne l'année académique active pour une branche donnée."""
    from academics.models import AcademicYear
    return AcademicYear.objects.filter(is_active=True).order_by("-id").first()


def _build_phase(entry: AcademicCalendarEntry, now) -> CalendarPhase:
    start = entry.start_datetime
    end = entry.end_datetime

    is_past = end < now
    is_active = start <= now <= end
    is_upcoming = start > now

    days_until_start = (start.date() - now.date()).days if is_upcoming else None
    days_until_end = (end.date() - now.date()).days if is_active else None
    days_elapsed = (now.date() - start.date()).days if is_active else None
    duration_days = max((end.date() - start.date()).days, 1)

    if is_active and duration_days > 0:
        elapsed = (now - start).total_seconds()
        total = (end - start).total_seconds()
        progress_pct = min(100, int(elapsed / total * 100))
    elif is_past:
        progress_pct = 100
    else:
        progress_pct = 0

    # Alertes : J-14 directeur, J-7 étudiants (uniquement si upcoming)
    alert_director = False
    alert_students = False
    alert_days = days_until_start

    if is_upcoming and days_until_start is not None:
        if entry.event_type in DIRECTOR_ALERT_TYPES and days_until_start <= 14:
            alert_director = True
        if entry.event_type in STUDENT_ALERT_TYPES and days_until_start <= 7:
            alert_students = True

    return CalendarPhase(
        entry=entry,
        label=PHASE_LABELS.get(entry.event_type, entry.title),
        icon=PHASE_ICONS.get(entry.event_type, "circle-dot"),
        tone=PHASE_TONES.get(entry.event_type, "muted"),
        is_past=is_past,
        is_active=is_active,
        is_upcoming=is_upcoming,
        days_until_start=days_until_start,
        days_until_end=days_until_end,
        days_elapsed=days_elapsed,
        duration_days=duration_days,
        progress_pct=progress_pct,
        alert_director=alert_director,
        alert_students=alert_students,
        alert_days=alert_days,
    )


# ---------------------------------------------------------------------------
# API publique
# ---------------------------------------------------------------------------

def get_calendar_phase_context(*, branch, academic_year) -> dict:
    """
    Retourne le contexte complet des phases du calendrier académique.

    Clés retournées :
        calendar        : AcademicCalendar publié, ou None
        phases          : liste de CalendarPhase (toutes les entrées triées)
        current_phase   : CalendarPhase active maintenant, ou None
        next_phase      : CalendarPhase à venir la plus proche, ou None
        prev_phase      : CalendarPhase passée la plus récente, ou None
        alert_phases    : liste de CalendarPhase avec alert_director ou alert_students
        has_calendar    : bool
        year_progress_pct : progression globale de l'année (0-100)
    """
    now = timezone.now()
    calendar = _get_published_calendar(branch, academic_year)

    if calendar is None:
        return {
            "calendar": None,
            "phases": [],
            "current_phase": None,
            "next_phase": None,
            "prev_phase": None,
            "alert_phases": [],
            "has_calendar": False,
            "year_progress_pct": 0,
        }

    entries = list(
        calendar.entries
        .filter(status=AcademicCalendarEntry.STATUS_PUBLISHED)
        .exclude(event_type=AcademicCalendarEntry.EVENT_OTHER)
        .order_by("start_datetime", "id")
    )

    phases = [_build_phase(e, now) for e in entries]

    current_phase = next((p for p in phases if p.is_active), None)
    next_phase = next((p for p in phases if p.is_upcoming), None)
    prev_phase = next((p for p in reversed(phases) if p.is_past), None)
    alert_phases = [p for p in phases if p.alert_director or p.alert_students]

    # Progression globale de l'année académique
    year = academic_year
    year_progress_pct = 0
    if year and year.start_date and year.end_date:
        total_days = (year.end_date - year.start_date).days
        elapsed_days = (now.date() - year.start_date).days
        if total_days > 0:
            year_progress_pct = max(0, min(100, int(elapsed_days / total_days * 100)))

    return {
        "calendar": calendar,
        "phases": phases,
        "current_phase": current_phase,
        "next_phase": next_phase,
        "prev_phase": prev_phase,
        "alert_phases": alert_phases,
        "has_calendar": True,
        "year_progress_pct": year_progress_pct,
    }


def get_current_phase(*, branch, academic_year) -> Optional[CalendarPhase]:
    """Raccourci : retourne uniquement la phase active maintenant."""
    ctx = get_calendar_phase_context(branch=branch, academic_year=academic_year)
    return ctx["current_phase"]


def get_alert_phases(*, branch, academic_year) -> list[CalendarPhase]:
    """Retourne uniquement les phases en alerte (J-14 directeur ou J-7 étudiants)."""
    ctx = get_calendar_phase_context(branch=branch, academic_year=academic_year)
    return ctx["alert_phases"]


def is_branch_in_exam_period(*, branch, academic_year) -> bool:
    """True si l'annexe est actuellement en session d'examens."""
    phase = get_current_phase(branch=branch, academic_year=academic_year)
    return phase is not None and phase.entry.event_type in {
        AcademicCalendarEntry.EVENT_EXAM_SESSION,
        AcademicCalendarEntry.EVENT_RETAKE_SESSION,
    }


def is_branch_in_blocking_period(*, branch, academic_year) -> bool:
    """True si l'annexe est dans une période bloquante (examens, rattrapage, férié…)."""
    phase = get_current_phase(branch=branch, academic_year=academic_year)
    return phase is not None and phase.entry.is_blocking
