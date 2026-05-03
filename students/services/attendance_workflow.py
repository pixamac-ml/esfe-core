from __future__ import annotations

from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from academics.models import AcademicClass, AcademicScheduleEvent
from branches.models import Branch
from students.models import AttendanceRollSheet

User = get_user_model()

STATE_EMPTY = "empty"
STATE_IN_PROGRESS = "in_progress"
STATE_VALIDATED = "validated"


def _normalize_branch(branch: Branch | int) -> Branch:
    if isinstance(branch, Branch):
        return branch
    return Branch.objects.get(pk=branch)


def list_day_course_events(*, branch: Branch, academic_class_id: int, day: date) -> list[AcademicScheduleEvent]:
    branch = _normalize_branch(branch)
    return list(
        AcademicScheduleEvent.objects.select_related("teacher", "ec", "academic_class")
        .filter(
            branch=branch,
            academic_class_id=academic_class_id,
            start_datetime__date=day,
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            is_active=True,
        )
        .exclude(status=AcademicScheduleEvent.STATUS_CANCELLED)
        .order_by("start_datetime", "id")
    )


def get_roll_sheet(*, branch: Branch | int, academic_class_id: int, day: date) -> AttendanceRollSheet | None:
    branch = _normalize_branch(branch)
    return (
        AttendanceRollSheet.objects.select_related("academic_class", "schedule_event", "validated_by")
        .filter(branch=branch, academic_class_id=academic_class_id, date=day)
        .first()
    )


def _workflow_state(sheet: AttendanceRollSheet | None) -> str:
    if sheet is None:
        return STATE_EMPTY
    if sheet.status == AttendanceRollSheet.STATUS_VALIDATED:
        return STATE_VALIDATED
    return STATE_IN_PROGRESS


def build_attendance_workflow_payload(
    *,
    branch: Branch | int | None,
    user: User,
    academic_class_id: int | None,
    roll_date: date,
) -> dict | None:
    if branch is None or not academic_class_id:
        return None
    branch = _normalize_branch(branch)
    academic_class = AcademicClass.objects.filter(pk=academic_class_id, branch=branch, is_active=True).first()
    if academic_class is None:
        return None

    sheet = get_roll_sheet(branch=branch, academic_class_id=academic_class_id, day=roll_date)
    state = _workflow_state(sheet)
    day_events = list_day_course_events(branch=branch, academic_class_id=academic_class_id, day=roll_date)

    event_options = []
    for event in day_events:
        local_start = timezone.localtime(event.start_datetime)
        label = f"{local_start.strftime('%H:%M')} — {event.ec.title} — {event.teacher.get_full_name() or event.teacher.username}"
        event_options.append({"id": event.id, "label": label})

    return {
        "academic_class_id": academic_class.id,
        "class_name": academic_class.display_name,
        "roll_date": roll_date,
        "roll_date_iso": roll_date.isoformat(),
        "state": state,
        "state_label": {
            STATE_EMPTY: "Non rempli",
            STATE_IN_PROGRESS: "En cours",
            STATE_VALIDATED: "Valide",
        }[state],
        "sheet_id": sheet.id if sheet else None,
        "can_start": state == STATE_EMPTY and bool(day_events),
        "can_edit": state == STATE_IN_PROGRESS,
        "can_validate": state == STATE_IN_PROGRESS and sheet is not None,
        "can_reopen": state == STATE_VALIDATED and sheet is not None,
        "validated_at": sheet.validated_at if sheet else None,
        "validated_by": (sheet.validated_by.get_full_name() or sheet.validated_by.username) if sheet and sheet.validated_by_id else "",
        "day_events": event_options,
        "has_courses_today": bool(day_events),
    }


@transaction.atomic
def start_daily_roll(
    *,
    user: User,
    branch: Branch | int,
    academic_class_id: int,
    roll_date: date,
    schedule_event_id: int | None = None,
) -> AttendanceRollSheet:
    branch = _normalize_branch(branch)
    academic_class = AcademicClass.objects.get(pk=academic_class_id, branch=branch, is_active=True)
    sheet = get_roll_sheet(branch=branch, academic_class_id=academic_class_id, day=roll_date)
    if sheet and sheet.status == AttendanceRollSheet.STATUS_VALIDATED:
        raise ValidationError("La feuille est deja validee. Rouvrez-la pour modifier.")
    if sheet:
        return sheet

    anchor = None
    if schedule_event_id:
        anchor = AcademicScheduleEvent.objects.get(
            pk=schedule_event_id,
            branch=branch,
            academic_class=academic_class,
        )
        if timezone.localtime(anchor.start_datetime).date() != roll_date:
            raise ValidationError("La seance choisie ne correspond pas a la date de la feuille.")
    else:
        events = list_day_course_events(branch=branch, academic_class_id=academic_class_id, day=roll_date)
        if not events:
            raise ValidationError("Aucun cours planifie ce jour pour cette classe.")
        anchor = events[0]

    return AttendanceRollSheet.objects.create(
        branch=branch,
        academic_class=academic_class,
        date=roll_date,
        schedule_event=anchor,
        status=AttendanceRollSheet.STATUS_DRAFT,
        updated_by=user,
    )


@transaction.atomic
def validate_daily_roll(*, user: User, sheet: AttendanceRollSheet) -> AttendanceRollSheet:
    if sheet.status != AttendanceRollSheet.STATUS_DRAFT:
        raise ValidationError("Seule une feuille en cours peut etre validee.")
    sheet.status = AttendanceRollSheet.STATUS_VALIDATED
    sheet.validated_by = user
    sheet.validated_at = timezone.now()
    sheet.updated_by = user
    sheet.save(update_fields=["status", "validated_by", "validated_at", "updated_by", "updated_at"])
    return sheet


@transaction.atomic
def reopen_daily_roll(*, user: User, sheet: AttendanceRollSheet) -> AttendanceRollSheet:
    if sheet.status != AttendanceRollSheet.STATUS_VALIDATED:
        raise ValidationError("Seule une feuille validee peut etre rouverte.")
    sheet.status = AttendanceRollSheet.STATUS_DRAFT
    sheet.validated_by = None
    sheet.validated_at = None
    sheet.updated_by = user
    sheet.save(update_fields=["status", "validated_by", "validated_at", "updated_by", "updated_at"])
    return sheet


def assert_roll_allows_editing(*, branch: Branch | int, academic_class_id: int, roll_date: date) -> None:
    sheet = get_roll_sheet(branch=branch, academic_class_id=academic_class_id, day=roll_date)
    if sheet and sheet.status == AttendanceRollSheet.STATUS_VALIDATED:
        raise ValidationError("Cette feuille d'appel est validee. Rouvrez-la avant toute modification.")


@transaction.atomic
def touch_roll_after_bulk_save(
    *,
    user: User,
    branch: Branch | int,
    academic_class: AcademicClass,
    roll_date: date,
    schedule_event: AcademicScheduleEvent,
) -> AttendanceRollSheet:
    branch = _normalize_branch(branch)
    sheet, _created = AttendanceRollSheet.objects.get_or_create(
        branch=branch,
        academic_class=academic_class,
        date=roll_date,
        defaults={
            "schedule_event": schedule_event,
            "status": AttendanceRollSheet.STATUS_DRAFT,
            "updated_by": user,
        },
    )
    if sheet.status == AttendanceRollSheet.STATUS_VALIDATED:
        raise ValidationError("Cette feuille d'appel est validee. Rouvrez-la avant toute modification.")
    sheet.schedule_event = schedule_event
    sheet.status = AttendanceRollSheet.STATUS_DRAFT
    sheet.updated_by = user
    sheet.save(update_fields=["schedule_event", "status", "updated_by", "updated_at"])
    return sheet


def is_roll_locked_for_event(*, branch: Branch | int, event: AcademicScheduleEvent) -> bool:
    roll_date = timezone.localtime(event.start_datetime).date()
    sheet = get_roll_sheet(branch=branch, academic_class_id=event.academic_class_id, day=roll_date)
    return bool(sheet and sheet.status == AttendanceRollSheet.STATUS_VALIDATED)
