"""
Indicateurs pedagogiques et assiduite pour le pilotage annexe (pas de logique dans les templates).
"""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from academics.models import AcademicScheduleEvent, LessonLog
from students.models import StudentAttendance, TeacherAttendance


def compute_class_progress(*, academic_class, days: int = 30):
    """Ratio cours traces (cahier « fait ») sur cours planifies sur la periode pour une classe."""
    branch = academic_class.branch
    end = timezone.localdate()
    start = end - timedelta(days=days)
    scheduled = (
        AcademicScheduleEvent.objects.filter(
            academic_class=academic_class,
            branch=branch,
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            is_active=True,
            start_datetime__date__gte=start,
            start_datetime__date__lte=end,
        )
        .exclude(status=AcademicScheduleEvent.STATUS_CANCELLED)
        .count()
    )
    done = LessonLog.objects.filter(
        academic_class=academic_class,
        branch=branch,
        date__gte=start,
        date__lte=end,
        status=LessonLog.STATUS_DONE,
    ).count()
    missed = max(0, scheduled - done)
    rate = round((done / scheduled) * 100, 1) if scheduled else None
    return {
        "class_id": academic_class.id,
        "class_name": academic_class.display_name,
        "period_start": start,
        "period_end": end,
        "scheduled_sessions": scheduled,
        "logged_done_sessions": done,
        "missing_lesson_logs_estimate": missed,
        "completion_percent": rate,
    }


def compute_attendance_rate(*, branch, start_date=None, end_date=None):
    """Taux de presences etudiants et enseignants sur une plage de dates (annexe obligatoire)."""
    if branch is None:
        return {
            "branch_id": None,
            "start_date": None,
            "end_date": None,
            "student_present_rate": None,
            "teacher_present_rate": None,
            "student_records": 0,
            "teacher_records": 0,
        }

    end_date = end_date or timezone.localdate()
    start_date = start_date or (end_date - timedelta(days=30))

    st_counts = StudentAttendance.objects.filter(
        branch=branch,
        date__gte=start_date,
        date__lte=end_date,
    ).aggregate(
        total=Count("id"),
        present=Count("id", filter=Q(status=StudentAttendance.STATUS_PRESENT)),
        late=Count("id", filter=Q(status=StudentAttendance.STATUS_LATE)),
    )
    te_counts = TeacherAttendance.objects.filter(
        branch=branch,
        date__gte=start_date,
        date__lte=end_date,
    ).aggregate(
        total=Count("id"),
        present=Count("id", filter=Q(status=TeacherAttendance.STATUS_PRESENT)),
        late=Count("id", filter=Q(status=TeacherAttendance.STATUS_LATE)),
    )

    st_total = st_counts["total"] or 0
    te_total = te_counts["total"] or 0
    st_ok = (st_counts["present"] or 0) + (st_counts["late"] or 0)
    te_ok = (te_counts["present"] or 0) + (te_counts["late"] or 0)

    return {
        "branch_id": branch.id,
        "start_date": start_date,
        "end_date": end_date,
        "student_present_rate": round((st_ok / st_total) * 100, 1) if st_total else None,
        "teacher_present_rate": round((te_ok / te_total) * 100, 1) if te_total else None,
        "student_records": st_total,
        "teacher_records": te_total,
        "student_absent_count": (st_total - st_ok) if st_total else 0,
        "teacher_absent_count": (te_total - te_ok) if te_total else 0,
    }


def compute_branch_pedagogy_snapshot(*, branch, days: int = 30):
    """Vue agregee annexe : volumes et taux utiles au dashboard surveillant."""
    if branch is None:
        today = timezone.localdate()
        return {
            "period_days": days,
            "period_start": today - timedelta(days=days),
            "period_end": today,
            "scheduled_courses": 0,
            "lesson_done": 0,
            "lesson_cancelled": 0,
            "lesson_absent_teacher": 0,
            "cancelled_events": 0,
            "attendance": compute_attendance_rate(branch=None),
        }

    end = timezone.localdate()
    start = end - timedelta(days=days)

    scheduled_qs = AcademicScheduleEvent.objects.filter(
        branch=branch,
        event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
        is_active=True,
        start_datetime__date__gte=start,
        start_datetime__date__lte=end,
    )
    cancelled_events = scheduled_qs.filter(status=AcademicScheduleEvent.STATUS_CANCELLED).count()
    active_scheduled = scheduled_qs.exclude(status=AcademicScheduleEvent.STATUS_CANCELLED).count()

    lesson_agg = LessonLog.objects.filter(branch=branch, date__gte=start, date__lte=end).aggregate(
        done=Count("id", filter=Q(status=LessonLog.STATUS_DONE)),
        cancelled=Count("id", filter=Q(status=LessonLog.STATUS_CANCELLED)),
        absent_teacher=Count("id", filter=Q(status=LessonLog.STATUS_ABSENT_TEACHER)),
    )

    return {
        "period_days": days,
        "period_start": start,
        "period_end": end,
        "scheduled_courses": active_scheduled,
        "lesson_done": lesson_agg["done"] or 0,
        "lesson_cancelled": lesson_agg["cancelled"] or 0,
        "lesson_absent_teacher": lesson_agg["absent_teacher"] or 0,
        "cancelled_events": cancelled_events,
        "attendance": compute_attendance_rate(branch=branch, start_date=start, end_date=end),
    }
