from django.db.models import Count
from django.utils import timezone

from academics.models import AcademicClass
from academics.services.lesson_log_service import get_daily_lesson_status
from academics.services.schedule_service import get_director_schedule_overview
from students.models import AttendanceRollSheet, StudentCase, StudentAttendance, TeacherAttendance


def create_surveillance_note(*, branch, user, cleaned_data):
    case = StudentCase.objects.create(
        branch=branch,
        case_type=StudentCase.TYPE_SUIVI_PEDAGOGIQUE,
        priority=StudentCase.PRIORITY_NORMALE,
        title=cleaned_data.get("title") or "Observation academique",
        description=cleaned_data.get("details", ""),
        opened_by=user,
    )
    return case


def resolve_surveillance_note(note, user, action_taken=""):
    if hasattr(note, "resolve"):
        note.resolve(user)
        return note
    note.status = getattr(note, "STATUS_RESOLU", "resolu")
    note.resolved_at = timezone.now()
    note.save(update_fields=["status", "resolved_at", "updated_at"])
    return note


def create_presence_check(*, branch, user, cleaned_data):
    return AttendanceRollSheet.objects.create(
        branch=branch,
        academic_class=cleaned_data["academic_class"],
        date=timezone.localdate(),
        schedule_event=cleaned_data.get("event"),
        updated_by=user,
    )


def get_supervisor_dashboard_context(branch, week_start):
    today = timezone.localdate()
    overview = (
        get_director_schedule_overview(branch, week_start)
        if branch
        else {"stats": {}, "quality": {"score": 0, "status": "critical", "warnings": []}, "alerts": []}
    )
    cases_qs = StudentCase.objects.filter(branch=branch).select_related("student", "opened_by").order_by("-created_at", "-id")
    roll_sheets_qs = AttendanceRollSheet.objects.filter(branch=branch).select_related("academic_class", "updated_by").order_by("-date", "-updated_at")
    classes_qs = AcademicClass.objects.filter(branch=branch, is_active=True).annotate(student_count=Count("enrollments")).order_by("level", "programme__title")
    student_attendance_qs = StudentAttendance.objects.filter(branch=branch, date=today)
    teacher_attendance_qs = TeacherAttendance.objects.filter(branch=branch, date=today)
    daily_lessons = get_daily_lesson_status(branch, today) if branch else {}
    open_statuses = {
        StudentCase.STATUS_NOUVEAU,
        StudentCase.STATUS_EN_COURS,
        StudentCase.STATUS_ATTENTE_PARENT,
        StudentCase.STATUS_EN_OBSERVATION,
    }

    return {
        "schedule_overview": overview,
        "lesson_status": daily_lessons,
        "notes_stats": {
            "total": cases_qs.count(),
            "open": cases_qs.filter(status__in=open_statuses).count(),
            "critical": cases_qs.filter(priority=StudentCase.PRIORITY_CRITIQUE).count(),
            "discipline": cases_qs.filter(case_type=StudentCase.TYPE_SIGNALEMENT_COMPORTEMENTAL).count(),
            "resolved": cases_qs.filter(status=StudentCase.STATUS_RESOLU).count(),
        },
        "presence_stats": {
            "total": roll_sheets_qs.count(),
            "today": roll_sheets_qs.filter(date=today).count(),
            "student_present_today": student_attendance_qs.filter(status=StudentAttendance.STATUS_PRESENT).count(),
            "teacher_present_today": teacher_attendance_qs.filter(status=TeacherAttendance.STATUS_PRESENT).count(),
        },
        "open_notes": list(cases_qs.filter(status__in=open_statuses)[:8]),
        "recent_notes": list(cases_qs[:10]),
        "presence_checks": list(roll_sheets_qs[:8]),
        "classes": list(classes_qs[:8]),
        "follow_up_classes": list(classes_qs[:5]),
    }
