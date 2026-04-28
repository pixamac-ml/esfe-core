from __future__ import annotations

from datetime import time

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from academics.models import AcademicClass, AcademicScheduleEvent, EC, LessonLog
from branches.models import Branch
from students.models import TeacherAttendance

User = get_user_model()


def _normalize_branch(branch: Branch | int | None) -> Branch:
    if branch is None:
        raise ValidationError("Une annexe est obligatoire.")
    if isinstance(branch, Branch):
        return branch
    return Branch.objects.get(pk=branch)


def _normalize_schedule_event(schedule_event: AcademicScheduleEvent | int | None) -> AcademicScheduleEvent | None:
    if schedule_event is None:
        return None
    if isinstance(schedule_event, AcademicScheduleEvent):
        return schedule_event
    return AcademicScheduleEvent.objects.select_related("academic_class", "branch", "teacher", "ec").get(pk=schedule_event)


def _validate_lesson_scope(*, academic_class: AcademicClass, ec: EC, teacher: User, branch: Branch, schedule_event=None):
    if academic_class.branch_id != branch.id:
        raise ValidationError("La classe n'appartient pas a cette annexe.")
    if ec.ue.semester.academic_class_id != academic_class.id:
        raise ValidationError("La matiere ne correspond pas a la classe academique.")
    if schedule_event is not None:
        if schedule_event.branch_id != branch.id:
            raise ValidationError("L'evenement ne correspond pas a l'annexe.")
        if schedule_event.event_type != AcademicScheduleEvent.EVENT_TYPE_COURSE:
            raise ValidationError("Le cahier de texte ne peut etre lie qu'a un cours planifie.")
        if schedule_event.academic_class_id != academic_class.id:
            raise ValidationError("L'evenement ne correspond pas a la classe.")
        if schedule_event.ec_id != ec.id:
            raise ValidationError("L'evenement ne correspond pas a la matiere.")
        if schedule_event.teacher_id != teacher.id:
            raise ValidationError("L'evenement ne correspond pas a l'enseignant.")


def _find_teacher_attendance(*, teacher: User, branch: Branch, date, schedule_event: AcademicScheduleEvent | None = None):
    queryset = TeacherAttendance.objects.filter(
        teacher=teacher,
        branch=branch,
        date=date,
    )
    if schedule_event is not None:
        queryset = queryset.filter(schedule_event=schedule_event)
    return queryset.order_by("-updated_at", "-id").first()


def _derive_absent_teacher_status(*, requested_status: str, teacher_attendance):
    if teacher_attendance and teacher_attendance.status == TeacherAttendance.STATUS_ABSENT:
        return LessonLog.STATUS_ABSENT_TEACHER
    return requested_status


@transaction.atomic
def create_lesson_log(
    *,
    academic_class: AcademicClass,
    ec: EC,
    teacher: User,
    date,
    start_time: time,
    end_time: time,
    status: str,
    branch: Branch | int,
    created_by: User,
    schedule_event: AcademicScheduleEvent | int | None = None,
    content: str = "",
    homework: str = "",
    observations: str = "",
    validated_by: User | None = None,
):
    branch = _normalize_branch(branch)
    schedule_event = _normalize_schedule_event(schedule_event)
    _validate_lesson_scope(
        academic_class=academic_class,
        ec=ec,
        teacher=teacher,
        branch=branch,
        schedule_event=schedule_event,
    )
    teacher_attendance = _find_teacher_attendance(
        teacher=teacher,
        branch=branch,
        date=date,
        schedule_event=schedule_event,
    )
    final_status = _derive_absent_teacher_status(requested_status=status, teacher_attendance=teacher_attendance)

    lesson_log = LessonLog.objects.create(
        academic_class=academic_class,
        ec=ec,
        teacher=teacher,
        schedule_event=schedule_event,
        date=date,
        start_time=start_time,
        end_time=end_time,
        status=final_status,
        content=content or "",
        homework=homework or "",
        observations=observations or "",
        branch=branch,
        created_by=created_by,
        validated_by=validated_by if final_status != LessonLog.STATUS_ABSENT_TEACHER else None,
    )
    return lesson_log


@transaction.atomic
def update_lesson_log(lesson_log: LessonLog, *, updated_by: User | None = None, **changes):
    if "schedule_event" in changes:
        changes["schedule_event"] = _normalize_schedule_event(changes["schedule_event"])
    for field, value in changes.items():
        setattr(lesson_log, field, value)

    _validate_lesson_scope(
        academic_class=lesson_log.academic_class,
        ec=lesson_log.ec,
        teacher=lesson_log.teacher,
        branch=lesson_log.branch,
        schedule_event=lesson_log.schedule_event,
    )

    teacher_attendance = _find_teacher_attendance(
        teacher=lesson_log.teacher,
        branch=lesson_log.branch,
        date=lesson_log.date,
        schedule_event=lesson_log.schedule_event,
    )
    lesson_log.status = _derive_absent_teacher_status(
        requested_status=lesson_log.status,
        teacher_attendance=teacher_attendance,
    )
    if updated_by and lesson_log.status == LessonLog.STATUS_DONE and not lesson_log.validated_by:
        lesson_log.validated_by = updated_by
    if lesson_log.status == LessonLog.STATUS_ABSENT_TEACHER:
        lesson_log.validated_by = None

    lesson_log.save()
    return lesson_log


def get_class_lesson_logs(academic_class: AcademicClass, *, limit: int | None = None):
    queryset = (
        LessonLog.objects.select_related("teacher", "ec", "branch", "schedule_event")
        .filter(academic_class=academic_class, branch=academic_class.branch)
        .order_by("-date", "-start_time", "-id")
    )
    if limit:
        queryset = queryset[:limit]
    return list(queryset)


def get_teacher_lesson_logs(teacher: User, *, branch: Branch | int | None = None, limit: int | None = None):
    queryset = LessonLog.objects.select_related("academic_class", "ec", "branch", "schedule_event").filter(teacher=teacher)
    if branch is not None:
        queryset = queryset.filter(branch=_normalize_branch(branch))
    queryset = queryset.order_by("-date", "-start_time", "-id")
    if limit:
        queryset = queryset[:limit]
    return list(queryset)


def get_missing_lesson_logs(branch: Branch | int, date):
    branch = _normalize_branch(branch)
    schedule_events = list(
        AcademicScheduleEvent.objects.select_related("academic_class", "teacher", "ec")
        .filter(
            branch=branch,
            start_datetime__date=date,
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            is_active=True,
        )
        .exclude(status=AcademicScheduleEvent.STATUS_CANCELLED)
        .order_by("start_datetime", "id")
    )
    lesson_logs_by_event_id = {
        log.schedule_event_id: log.id
        for log in LessonLog.objects.filter(branch=branch, date=date).exclude(schedule_event__isnull=True)
    }

    missing_logs = []
    for event in schedule_events:
        if event.id in lesson_logs_by_event_id:
            continue
        missing_logs.append(
            {
                "event_id": event.id,
                "classroom": event.academic_class.display_name,
                "teacher": event.teacher.get_full_name() or event.teacher.username,
                "subject": event.ec.title,
                "scheduled_time": timezone.localtime(event.start_datetime).strftime("%H:%M"),
                "status": "missing_lesson_log",
            }
        )
    return missing_logs


def get_daily_lesson_status(branch: Branch | int, date):
    branch = _normalize_branch(branch)
    schedule_events = list(
        AcademicScheduleEvent.objects.select_related("academic_class", "teacher", "ec")
        .filter(
            branch=branch,
            start_datetime__date=date,
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            is_active=True,
        )
        .exclude(status=AcademicScheduleEvent.STATUS_CANCELLED)
        .order_by("start_datetime", "id")
    )
    lesson_logs = list(
        LessonLog.objects.select_related("academic_class", "teacher", "ec", "schedule_event")
        .filter(branch=branch, date=date)
        .order_by("start_time", "id")
    )
    logs_by_event_id = {log.schedule_event_id: log for log in lesson_logs if log.schedule_event_id}
    teacher_attendances = {
        attendance.schedule_event_id: attendance
        for attendance in TeacherAttendance.objects.filter(branch=branch, date=date).exclude(schedule_event__isnull=True)
    }

    missing_logs = get_missing_lesson_logs(branch, date)
    critical_items = []
    for event in schedule_events:
        log = logs_by_event_id.get(event.id)
        teacher_attendance = teacher_attendances.get(event.id)
        if teacher_attendance and teacher_attendance.status == TeacherAttendance.STATUS_ABSENT:
            critical_items.append(
                {
                    "event_id": event.id,
                    "classroom": event.academic_class.display_name,
                    "teacher": event.teacher.get_full_name() or event.teacher.username,
                    "subject": event.ec.title,
                    "status": "teacher_absent_with_planned_lesson",
                }
            )
        elif log and log.status == LessonLog.STATUS_ABSENT_TEACHER:
            critical_items.append(
                {
                    "event_id": event.id,
                    "classroom": event.academic_class.display_name,
                    "teacher": event.teacher.get_full_name() or event.teacher.username,
                    "subject": event.ec.title,
                    "status": "teacher_absent_with_lesson_log",
                }
            )

    return {
        "branch_id": branch.id,
        "date": date,
        "scheduled_courses": len(schedule_events),
        "lesson_logs_count": len(lesson_logs),
        "missing_lesson_logs_count": len(missing_logs),
        "critical_count": len(critical_items),
        "missing_lesson_logs": missing_logs,
        "critical_items": critical_items,
        "lesson_logs": lesson_logs,
    }


def get_lesson_log_quality_controls(branch: Branch | int, date):
    branch = _normalize_branch(branch)
    daily_status = get_daily_lesson_status(branch, date)
    return {
        "branch_id": branch.id,
        "date": date,
        "missing_lesson_logs_count": daily_status["missing_lesson_logs_count"],
        "critical_count": daily_status["critical_count"],
        "is_clean": daily_status["missing_lesson_logs_count"] == 0 and daily_status["critical_count"] == 0,
    }
