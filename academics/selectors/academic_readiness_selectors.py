from __future__ import annotations

from django.db.models import Q

from academics.models import (
    AcademicBulletin,
    AcademicCalendar,
    AcademicCalendarEntry,
    AcademicClass,
    AcademicEnrollment,
    AcademicScheduleEvent,
    EC,
    ECGrade,
    LessonLog,
    Semester,
    UE,
    WeeklyScheduleSlot,
)


def get_classes_for_programme(*, programme, branch=None, academic_year=None):
    queryset = (
        AcademicClass.objects.select_related("programme", "branch", "academic_year")
        .filter(programme=programme, is_archived=False)
        .order_by("branch__name", "level", "id")
    )
    if branch is not None:
        queryset = queryset.filter(branch=branch)
    if academic_year is not None:
        queryset = queryset.filter(academic_year=academic_year)
    return queryset


def get_semesters_for_class(academic_class):
    return (
        Semester.objects.filter(academic_class=academic_class)
        .prefetch_related("ues__ecs")
        .order_by("number", "id")
    )


def get_active_ues_for_semester(semester):
    return (
        UE.objects.filter(semester=semester)
        .exclude(structure_status=UE.STRUCTURE_ARCHIVED)
        .prefetch_related("ecs")
        .order_by("code", "id")
    )


def get_active_ecs_for_semester(semester):
    return (
        EC.objects.filter(ue__semester=semester)
        .exclude(structure_status=EC.STRUCTURE_ARCHIVED)
        .select_related("ue", "ue__semester", "ue__semester__academic_class")
        .order_by("ue__code", "id")
    )


def get_active_enrollments_for_class(academic_class):
    return (
        AcademicEnrollment.objects.filter(
            academic_class=academic_class,
            academic_year=academic_class.academic_year,
            is_active=True,
        )
        .select_related("student", "academic_class")
        .order_by("id")
    )


def get_published_calendar(*, branch, academic_year):
    return (
        AcademicCalendar.objects.filter(
            branch=branch,
            academic_year=academic_year,
            status=AcademicCalendar.STATUS_PUBLISHED,
        )
        .order_by("-version", "-published_at", "-id")
        .first()
    )


def get_calendar_entries(*, branch, academic_year, academic_class=None, semester=None, event_types=None):
    queryset = AcademicCalendarEntry.objects.filter(
        calendar__branch=branch,
        calendar__academic_year=academic_year,
        calendar__status=AcademicCalendar.STATUS_PUBLISHED,
        status=AcademicCalendarEntry.STATUS_PUBLISHED,
    )
    if event_types:
        queryset = queryset.filter(event_type__in=event_types)
    if academic_class is not None:
        queryset = queryset.filter(
            Q(target_scope=AcademicCalendarEntry.SCOPE_BRANCH)
            | Q(programme=academic_class.programme)
            | Q(academic_class=academic_class)
            | Q(semester__academic_class=academic_class)
        )
    if semester is not None:
        queryset = queryset.filter(
            Q(target_scope=AcademicCalendarEntry.SCOPE_BRANCH)
            | Q(programme=semester.academic_class.programme)
            | Q(academic_class=semester.academic_class)
            | Q(semester=semester)
        )
    return queryset.order_by("start_datetime", "id")


def get_weekly_slots_for_class(academic_class):
    return (
        WeeklyScheduleSlot.objects.filter(
            academic_class=academic_class,
            branch=academic_class.branch,
            academic_year=academic_class.academic_year,
            is_active=True,
        )
        .select_related("teacher", "ec")
        .order_by("weekday", "start_time", "id")
    )


def get_schedule_events_for_class(academic_class):
    return (
        AcademicScheduleEvent.objects.filter(
            academic_class=academic_class,
            branch=academic_class.branch,
            academic_year=academic_class.academic_year,
            is_active=True,
        )
        .exclude(status=AcademicScheduleEvent.STATUS_CANCELLED)
        .select_related("teacher", "ec")
        .order_by("start_datetime", "id")
    )


def get_teacher_weekly_conflicts(*, branch, academic_year, academic_class=None):
    slots = (
        WeeklyScheduleSlot.objects.filter(branch=branch, academic_year=academic_year, is_active=True)
        .select_related("teacher", "academic_class", "ec")
        .order_by("teacher_id", "weekday", "start_time", "id")
    )
    if academic_class is not None:
        slots = slots.filter(academic_class=academic_class)

    conflicts = []
    by_teacher_day = {}
    for slot in slots:
        key = (slot.teacher_id, slot.weekday)
        for existing in by_teacher_day.get(key, []):
            if slot.start_time < existing.end_time and slot.end_time > existing.start_time:
                conflicts.append({"first": existing, "second": slot})
        by_teacher_day.setdefault(key, []).append(slot)
    return conflicts


def get_lesson_logs_for_class(academic_class):
    return (
        LessonLog.objects.filter(academic_class=academic_class, branch=academic_class.branch)
        .select_related("teacher", "ec", "schedule_event")
        .order_by("-date", "-start_time", "-id")
    )


def get_grades_for_semester(semester):
    return ECGrade.objects.filter(ec__ue__semester=semester).select_related("enrollment", "ec")


def get_bulletins_for_semester(semester):
    return AcademicBulletin.objects.filter(
        semester=semester,
        bulletin_type=AcademicBulletin.TYPE_SEMESTER,
    )
