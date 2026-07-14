from django.db.models import Q

from academics.models import AcademicCalendar, AcademicCalendarEntry


def _entries_queryset():
    return AcademicCalendarEntry.objects.select_related(
        "calendar",
        "calendar__branch",
        "calendar__academic_year",
        "programme",
        "academic_class",
        "semester",
        "semester__academic_class",
    )


def get_active_calendar(branch, academic_year):
    return (
        AcademicCalendar.objects.select_related("branch", "academic_year")
        .filter(
            branch=branch,
            academic_year=academic_year,
            status=AcademicCalendar.STATUS_PUBLISHED,
        )
        .first()
    )


def get_calendar_entries_by_academic_year(academic_year):
    return _entries_queryset().filter(calendar__academic_year=academic_year)


def get_calendar_entries_by_branch(branch):
    return _entries_queryset().filter(calendar__branch=branch)


def get_calendar_entries_by_period(start_datetime, end_datetime):
    return _entries_queryset().filter(
        start_datetime__lt=end_datetime,
        end_datetime__gt=start_datetime,
    )


def get_calendar_entries_by_programme(programme):
    return _entries_queryset().filter(
        Q(programme=programme)
        | Q(academic_class__programme=programme)
        | Q(semester__academic_class__programme=programme)
    ).distinct()


def get_calendar_entries_by_class(academic_class):
    return _entries_queryset().filter(
        Q(academic_class=academic_class)
        | Q(semester__academic_class=academic_class)
    ).distinct()
