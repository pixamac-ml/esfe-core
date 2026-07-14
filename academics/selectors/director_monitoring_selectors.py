from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db.models import Q

from academics.models import (
    AcademicBulletin,
    AcademicClass,
    AcademicScheduleEvent,
    ECGrade,
    LessonLog,
    Semester,
)
from students.models import TeacherAttendance


def get_monitoring_classes(*, branch=None, programme=None, academic_year=None):
    queryset = AcademicClass.objects.select_related("branch", "programme", "academic_year").filter(
        is_active=True,
        is_archived=False,
    )
    if branch is not None:
        queryset = queryset.filter(branch=branch)
    if programme is not None:
        queryset = queryset.filter(programme=programme)
    if academic_year is not None:
        queryset = queryset.filter(academic_year=academic_year)
    return queryset.order_by("branch__name", "programme__title", "level", "id")


def get_monitoring_semesters(*, academic_class):
    return Semester.objects.filter(academic_class=academic_class).select_related(
        "academic_class", "academic_class__branch", "academic_class__programme"
    ).order_by("number", "id")


def get_course_progress(*, semester):
    academic_class = semester.academic_class
    logs = LessonLog.objects.filter(
        academic_class=academic_class,
        branch=academic_class.branch,
        ec__ue__semester=semester,
    )
    events = AcademicScheduleEvent.objects.filter(
        academic_class=academic_class,
        branch=academic_class.branch,
        academic_year=academic_class.academic_year,
        ec__ue__semester=semester,
        event_type__in=[AcademicScheduleEvent.EVENT_TYPE_COURSE, AcademicScheduleEvent.EVENT_TYPE_PRACTICAL],
        is_active=True,
    )
    completed_logs = logs.filter(status=LessonLog.STATUS_DONE)
    completed_minutes = sum(
        max(0, int((row.end_time.hour * 60 + row.end_time.minute) - (row.start_time.hour * 60 + row.start_time.minute)))
        for row in completed_logs.only("start_time", "end_time")
    )
    planned_minutes = sum(event.duration_minutes for event in events.exclude(status=AcademicScheduleEvent.STATUS_CANCELLED))
    return {
        "planned_courses": events.count(),
        "completed_courses": completed_logs.count(),
        "not_completed_courses": events.filter(
            status__in=[AcademicScheduleEvent.STATUS_DRAFT, AcademicScheduleEvent.STATUS_PLANNED]
        ).count(),
        "postponed_courses": events.filter(status=AcademicScheduleEvent.STATUS_POSTPONED).count(),
        "completed_hours": Decimal(completed_minutes) / Decimal("60"),
        "planned_hours": Decimal(planned_minutes) / Decimal("60"),
        "remaining_hours": max(Decimal("0"), Decimal(planned_minutes - completed_minutes) / Decimal("60")),
    }


def get_teacher_absences(*, semester, start_date: date | None = None, end_date: date | None = None):
    queryset = TeacherAttendance.objects.filter(
        branch=semester.academic_class.branch,
        schedule_event__academic_class=semester.academic_class,
        schedule_event__ec__ue__semester=semester,
        status=TeacherAttendance.STATUS_ABSENT,
    ).select_related("teacher", "schedule_event")
    if start_date is not None:
        queryset = queryset.filter(date__gte=start_date)
    if end_date is not None:
        queryset = queryset.filter(date__lte=end_date)
    return queryset.order_by("-date", "teacher__last_name", "id")


def get_exam_events(*, semester):
    return AcademicScheduleEvent.objects.filter(
        academic_class=semester.academic_class,
        ec__ue__semester=semester,
        event_type=AcademicScheduleEvent.EVENT_TYPE_EXAM,
        is_active=True,
    ).exclude(status=AcademicScheduleEvent.STATUS_CANCELLED).order_by("start_datetime", "id")


def get_results_summary(*, semester):
    grades = ECGrade.objects.filter(
        enrollment__academic_class=semester.academic_class,
        enrollment__is_active=True,
        ec__ue__semester=semester,
    )
    bulletins = AcademicBulletin.objects.filter(
        semester=semester,
        bulletin_type=AcademicBulletin.TYPE_SEMESTER,
    )
    imported = grades.exclude(Q(normal_score__isnull=True) & Q(retake_score__isnull=True))
    return {
        "imported_grades": imported.count(),
        "validated_results": grades.filter(final_score__isnull=False, is_validated=True).count(),
        "published_bulletins": bulletins.filter(status=AcademicBulletin.STATUS_PUBLISHED).count(),
        "generated_bulletins": bulletins.exclude(status=AcademicBulletin.STATUS_CANCELLED).count(),
    }
