from django.contrib.auth import get_user_model
from django.utils import timezone

from academics.models import AcademicCalendarEntry, AcademicClass, Semester

User = get_user_model()

_EXAM_TYPES = {
    AcademicCalendarEntry.EVENT_EXAM_SESSION,
    AcademicCalendarEntry.EVENT_RETAKE_SESSION,
}


def build_director_exam_sessions_context(*, branch, class_cards):
    """
    Construit le contexte pour la section calendrier des évaluations.
    Retourne les sessions d'examen de la branche, groupées par classe.
    """
    if not branch:
        return {
            "exam_sessions": [],
            "upcoming_exam_sessions": [],
            "exam_session_classes": [],
            "exam_session_type_choices": _exam_type_choices(),
        }

    sessions = list(
        AcademicCalendarEntry.objects.select_related(
            "academic_class",
            "semester",
            "created_by",
        )
        .filter(
            calendar__branch=branch,
            event_type__in=_EXAM_TYPES,
        )
        .order_by("start_datetime", "id")
    )

    today = timezone.now()
    upcoming = [s for s in sessions if s.end_datetime >= today][:6]

    # Grouper par classe pour affichage
    sessions_by_class = {}
    for s in sessions:
        key = s.academic_class_id
        if key not in sessions_by_class:
            sessions_by_class[key] = {
                "class": s.academic_class,
                "sessions": [],
            }
        sessions_by_class[key]["sessions"].append(_session_row(s))

    # Classes disponibles pour le formulaire de création
    exam_classes = [item["class"] for item in class_cards if item["class"].is_active]

    return {
        "exam_sessions": sessions,
        "exam_session_rows": [_session_row(s) for s in sessions],
        "upcoming_exam_sessions": [_session_row(s) for s in upcoming],
        "exam_sessions_by_class": list(sessions_by_class.values()),
        "exam_session_classes": exam_classes,
        "exam_session_type_choices": _exam_type_choices(),
        "exam_session_total": len(sessions),
        "exam_session_upcoming_count": len(upcoming),
    }


def _session_row(entry):
    today = timezone.now()
    if entry.end_datetime < today:
        state = "termine"
        tone = "muted"
    elif entry.start_datetime <= today:
        state = "en_cours"
        tone = "success"
    elif entry.status == AcademicCalendarEntry.STATUS_PUBLISHED:
        state = "publie"
        tone = "school_primary"
    else:
        state = "brouillon"
        tone = "warning"

    return {
        "entry": entry,
        "state": state,
        "tone": tone,
        "is_published": entry.status == AcademicCalendarEntry.STATUS_PUBLISHED,
        "is_draft": entry.status == AcademicCalendarEntry.STATUS_DRAFT,
        "supervisors": [],
        "supervisor_count": 0,
        "class_label": entry.academic_class.display_name if entry.academic_class else "—",
        "semester_label": f"Semestre {entry.semester.number}" if entry.semester else "—",
        "type_label": entry.get_event_type_display(),
        "duration_days": max((entry.end_datetime - entry.start_datetime).days, 1),
    }


def _exam_type_choices():
    return [
        (AcademicCalendarEntry.EVENT_EXAM_SESSION, "Session d'examens"),
        (AcademicCalendarEntry.EVENT_RETAKE_SESSION, "Session de rattrapage"),
    ]


def get_upcoming_exam_sessions_for_class(*, academic_class, limit=3):
    """
    Sessions à venir pour une classe — utilisé dans les widgets enseignant/étudiant.
    """
    today = timezone.now()
    sessions = (
        AcademicCalendarEntry.objects.select_related("semester")
        .filter(
            academic_class=academic_class,
            event_type__in=_EXAM_TYPES,
            end_datetime__gte=today,
            status=AcademicCalendarEntry.STATUS_PUBLISHED,
        )
        .order_by("start_datetime")[:limit]
    )
    return [_session_row(s) for s in sessions]


def get_upcoming_exam_sessions_for_branch(*, branch, limit=5):
    """
    Sessions à venir pour toute la branche — widget dashboard superviseur/DG.
    """
    today = timezone.now()
    sessions = (
        AcademicCalendarEntry.objects.select_related("academic_class", "semester")
        .filter(
            calendar__branch=branch,
            event_type__in=_EXAM_TYPES,
            end_datetime__gte=today,
            status=AcademicCalendarEntry.STATUS_PUBLISHED,
        )
        .order_by("start_datetime")[:limit]
    )
    return [_session_row(s) for s in sessions]
