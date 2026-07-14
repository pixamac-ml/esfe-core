from django.core.exceptions import ValidationError
from django.db.models import Q
from django.db import transaction
from django.utils import timezone

from academics.models import AcademicCalendar, AcademicCalendarEntry
from academics.permissions.calendar_permissions import (
    require_calendar_access,
    require_calendar_branch_access,
)


CALENDAR_MUTABLE_FIELDS = {"version"}
ENTRY_MUTABLE_FIELDS = {
    "title",
    "description",
    "event_type",
    "start_datetime",
    "end_datetime",
    "all_day",
    "target_scope",
    "programme",
    "academic_class",
    "semester",
    "color",
    "icon",
    "is_blocking",
    "status",
}


def _apply_changes(instance, changes, allowed_fields):
    unknown = set(changes) - allowed_fields
    if unknown:
        raise ValidationError(f"Champs non modifiables : {', '.join(sorted(unknown))}.")
    for field, value in changes.items():
        setattr(instance, field, value)


@transaction.atomic
def create_calendar(*, actor, branch, academic_year, version=1):
    require_calendar_branch_access(actor, branch)
    calendar = AcademicCalendar(
        branch=branch,
        academic_year=academic_year,
        version=version,
        status=AcademicCalendar.STATUS_DRAFT,
        created_by=actor,
        updated_by=actor,
    )
    calendar.full_clean()
    calendar.save()
    return calendar


@transaction.atomic
def update_calendar(calendar, *, actor, **changes):
    require_calendar_access(actor, calendar)
    if calendar.status != AcademicCalendar.STATUS_DRAFT:
        raise ValidationError("Seul un calendrier brouillon peut etre modifie.")
    _apply_changes(calendar, changes, CALENDAR_MUTABLE_FIELDS)
    calendar.updated_by = actor
    calendar.full_clean()
    calendar.save()
    return calendar


@transaction.atomic
def validate_calendar(calendar, *, actor):
    require_calendar_access(actor, calendar)
    if calendar.status != AcademicCalendar.STATUS_DRAFT:
        raise ValidationError("Seul un calendrier brouillon peut etre valide.")
    if not calendar.entries.exists():
        raise ValidationError("Un calendrier vide ne peut pas etre valide.")
    for entry in calendar.entries.all():
        entry.full_clean()
    calendar.status = AcademicCalendar.STATUS_VALIDATED
    calendar.updated_by = actor
    calendar.save()
    return calendar


def _validate_no_entry_overlap(calendar):
    """Verifie les chevauchements entre entrees bloquantes de meme portee et meme classe/semestre."""
    entries = list(
        calendar.entries
        .filter(is_blocking=True)
        .exclude(status=AcademicCalendarEntry.STATUS_CANCELLED)
    )
    for index, entry in enumerate(entries):
        for other in entries[index + 1:]:
            if entry.start_datetime >= other.end_datetime or entry.end_datetime <= other.start_datetime:
                continue
            if entry.target_scope != other.target_scope:
                continue
            if entry.academic_class_id != other.academic_class_id:
                continue
            if entry.semester_id != other.semester_id:
                continue
            raise ValidationError(
                f"Les periodes bloquantes '{entry.title}' et '{other.title}' "
                f"se chevauchent sur la meme portee."
            )


@transaction.atomic
def publish_calendar(calendar, *, actor):
    require_calendar_access(actor, calendar)
    calendar = AcademicCalendar.objects.select_for_update().get(pk=calendar.pk)
    if calendar.status != AcademicCalendar.STATUS_VALIDATED:
        raise ValidationError("Seul un calendrier valide peut etre publie.")
    _validate_no_entry_overlap(calendar)
    AcademicCalendar.objects.select_for_update().filter(
        branch=calendar.branch,
        academic_year=calendar.academic_year,
        status=AcademicCalendar.STATUS_PUBLISHED,
    ).exclude(pk=calendar.pk).update(
        status=AcademicCalendar.STATUS_ARCHIVED,
        updated_by=actor,
        updated_at=timezone.now(),
    )
    calendar.status = AcademicCalendar.STATUS_PUBLISHED
    calendar.published_by = actor
    calendar.published_at = timezone.now()
    calendar.updated_by = actor
    calendar.full_clean()
    calendar.save()
    calendar.entries.exclude(status=AcademicCalendarEntry.STATUS_CANCELLED).update(
        status=AcademicCalendarEntry.STATUS_PUBLISHED,
        updated_by=actor,
        updated_at=timezone.now(),
    )
    return calendar


@transaction.atomic
def delete_calendar(calendar, *, actor):
    require_calendar_access(actor, calendar)
    if calendar.status != AcademicCalendar.STATUS_DRAFT:
        raise ValidationError(
            "Seul un calendrier en brouillon peut etre supprime. "
            "Archivez-le d'abord s'il est publie."
        )
    calendar.entries.all().delete()
    calendar.delete()


@transaction.atomic
def archive_calendar(calendar, *, actor):
    require_calendar_access(actor, calendar)
    if calendar.status != AcademicCalendar.STATUS_PUBLISHED:
        raise ValidationError("Seul un calendrier publie peut etre archive.")
    calendar.status = AcademicCalendar.STATUS_ARCHIVED
    calendar.updated_by = actor
    calendar.full_clean()
    calendar.save()
    calendar.entries.update(
        status=AcademicCalendarEntry.STATUS_ARCHIVED,
        updated_by=actor,
        updated_at=timezone.now(),
    )
    return calendar


@transaction.atomic
def create_calendar_entry(*, actor, calendar, **data):
    require_calendar_access(actor, calendar)
    if calendar.status != AcademicCalendar.STATUS_DRAFT:
        raise ValidationError("Seul un calendrier brouillon peut recevoir des entrees.")
    entry = AcademicCalendarEntry(
        calendar=calendar,
        created_by=actor,
        updated_by=actor,
        **data,
    )
    entry.full_clean()
    entry.save()
    return entry


@transaction.atomic
def update_calendar_entry(entry, *, actor, **changes):
    require_calendar_access(actor, entry.calendar)
    if entry.calendar.status != AcademicCalendar.STATUS_DRAFT:
        raise ValidationError("Seule l'entree d'un calendrier brouillon peut etre modifiee.")
    _apply_changes(entry, changes, ENTRY_MUTABLE_FIELDS)
    entry.updated_by = actor
    entry.full_clean()
    entry.save()
    return entry


@transaction.atomic
def delete_calendar_entry(entry, *, actor):
    require_calendar_access(actor, entry.calendar)
    if entry.calendar.status != AcademicCalendar.STATUS_DRAFT:
        raise ValidationError("Seule l'entree d'un calendrier brouillon peut etre supprimee.")
    entry.delete()


def assert_course_not_blocked(*, branch, academic_year, academic_class, start_datetime, end_datetime):
    scope = Q(target_scope=AcademicCalendarEntry.SCOPE_BRANCH)
    if academic_class is not None:
        scope |= Q(target_scope=AcademicCalendarEntry.SCOPE_PROGRAMME, programme=academic_class.programme)
        scope |= Q(target_scope=AcademicCalendarEntry.SCOPE_CLASS, academic_class=academic_class)
        scope |= Q(target_scope=AcademicCalendarEntry.SCOPE_SEMESTER, semester__academic_class=academic_class)
    conflict = (
        AcademicCalendarEntry.objects.filter(
            calendar__branch=branch,
            calendar__academic_year=academic_year,
            calendar__status=AcademicCalendar.STATUS_PUBLISHED,
            status=AcademicCalendarEntry.STATUS_PUBLISHED,
            is_blocking=True,
            start_datetime__lt=end_datetime,
            end_datetime__gt=start_datetime,
        )
        .filter(scope)
        .first()
    )
    if conflict:
        raise ValidationError(f"Cours impossible pendant la periode bloquante : {conflict.title}.")
