from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from academics.models import AcademicClass, ClassPresenceCheck, SurveillanceNote
from academics.services.schedule_service import get_director_schedule_overview


def create_surveillance_note(*, branch, user, cleaned_data):
    note = SurveillanceNote(
        branch=branch,
        note_type=cleaned_data["note_type"],
        severity=cleaned_data["severity"],
        title=cleaned_data["title"],
        details=cleaned_data.get("details", ""),
        academic_class=cleaned_data.get("academic_class"),
        event=cleaned_data.get("event"),
        teacher=cleaned_data.get("teacher"),
        student=cleaned_data.get("student"),
        created_by=user,
        status=SurveillanceNote.STATUS_OPEN,
    )
    note.full_clean()
    note.save()
    return note


def resolve_surveillance_note(note, user, action_taken=""):
    note.status = SurveillanceNote.STATUS_RESOLVED
    note.action_taken = action_taken or note.action_taken
    note.resolved_by = user
    note.resolved_at = timezone.now()
    note.full_clean()
    note.save()
    return note


def create_presence_check(*, branch, user, cleaned_data):
    presence = ClassPresenceCheck(
        branch=branch,
        academic_class=cleaned_data["academic_class"],
        event=cleaned_data.get("event"),
        expected_count=cleaned_data.get("expected_count") or 0,
        present_count=cleaned_data.get("present_count") or 0,
        late_count=cleaned_data.get("late_count") or 0,
        absent_count=cleaned_data.get("absent_count") or 0,
        note=cleaned_data.get("note", ""),
        created_by=user,
    )
    presence.full_clean()
    presence.save()
    return presence


def get_supervisor_dashboard_context(branch, week_start):
    overview = get_director_schedule_overview(branch, week_start) if branch else {"stats": {}, "quality": {"score": 0, "status": "critical", "warnings": []}, "alerts": []}
    notes_qs = SurveillanceNote.objects.filter(branch=branch).select_related("academic_class", "event", "teacher", "student", "created_by", "resolved_by").order_by("-created_at", "-id")
    presence_qs = ClassPresenceCheck.objects.filter(branch=branch).select_related("academic_class", "event", "created_by").order_by("-created_at", "-id")
    classes_qs = AcademicClass.objects.filter(branch=branch, is_active=True).annotate(student_count=Count("enrollments")).order_by("level", "programme__title")

    open_notes = notes_qs.filter(status__in=[SurveillanceNote.STATUS_OPEN, SurveillanceNote.STATUS_IN_PROGRESS])
    critical_notes = notes_qs.filter(severity=SurveillanceNote.SEVERITY_CRITICAL)
    discipline_notes = notes_qs.filter(note_type=SurveillanceNote.NOTE_TYPE_DISCIPLINE)
    presence_today = presence_qs.filter(created_at__date=timezone.localdate())

    return {
        "schedule_overview": overview,
        "notes_stats": {
            "total": notes_qs.count(),
            "open": open_notes.count(),
            "critical": critical_notes.count(),
            "discipline": discipline_notes.count(),
            "resolved": notes_qs.filter(status=SurveillanceNote.STATUS_RESOLVED).count(),
        },
        "presence_stats": {
            "total": presence_qs.count(),
            "today": presence_today.count(),
            "avg_rate": round(sum(item.attendance_rate for item in presence_qs[:10]) / max(min(presence_qs.count(), 10), 1), 2) if presence_qs.exists() else 0,
        },
        "open_notes": list(open_notes[:8]),
        "recent_notes": list(notes_qs[:10]),
        "presence_checks": list(presence_qs[:8]),
        "classes": list(classes_qs[:8]),
        "follow_up_classes": list(
            classes_qs.annotate(open_notes=Count("surveillance_notes", filter=Q(surveillance_notes__status__in=[SurveillanceNote.STATUS_OPEN, SurveillanceNote.STATUS_IN_PROGRESS])))
            .filter(open_notes__gt=0)
            .order_by("-open_notes", "level")[:5]
        ),
    }
