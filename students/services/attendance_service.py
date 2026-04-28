from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from academics.models import AcademicClass, AcademicEnrollment, AcademicScheduleEvent
from branches.models import Branch
from students.models import AttendanceAlert, Student, StudentAttendance, TeacherAttendance

User = get_user_model()


def _normalize_branch(branch: Branch | int | None) -> Branch:
    if branch is None:
        raise ValidationError("Une annexe est obligatoire.")
    if isinstance(branch, Branch):
        return branch
    return Branch.objects.get(pk=branch)


def _normalize_schedule_event(schedule_event: AcademicScheduleEvent | int | None) -> AcademicScheduleEvent:
    if schedule_event is None:
        raise ValidationError("schedule_event est obligatoire.")
    if isinstance(schedule_event, AcademicScheduleEvent):
        return schedule_event
    return AcademicScheduleEvent.objects.select_related("academic_class", "branch", "teacher").get(pk=schedule_event)


def _student_branch(student: Student):
    candidature = getattr(getattr(student, "inscription", None), "candidature", None)
    return getattr(candidature, "branch", None)


def _ensure_student_belongs_to_branch(student: Student, branch: Branch):
    student_branch = _student_branch(student)
    if student_branch is None or student_branch.id != branch.id:
        raise ValidationError("L'etudiant n'appartient pas a cette annexe.")


def _ensure_student_enrollment(student: Student, academic_class: AcademicClass, branch: Branch):
    enrollment = (
        AcademicEnrollment.objects.select_related("academic_class", "branch")
        .filter(
            student=student.user,
            academic_class=academic_class,
            branch=branch,
            is_active=True,
        )
        .first()
    )
    if enrollment is None:
        raise ValidationError("L'etudiant n'est pas affecte a cette classe dans cette annexe.")
    return enrollment


def _ensure_schedule_event_scope(*, schedule_event: AcademicScheduleEvent, branch: Branch, academic_class: AcademicClass | None = None):
    if schedule_event.branch_id != branch.id:
        raise ValidationError("L'evenement planifie n'appartient pas a cette annexe.")
    if academic_class is not None and schedule_event.academic_class_id != academic_class.id:
        raise ValidationError("L'evenement planifie ne correspond pas a la classe fournie.")


def _maybe_create_alert(*, student: Student, branch: Branch, alert_type: str, count: int):
    existing = (
        AttendanceAlert.objects.filter(
            student=student,
            branch=branch,
            alert_type=alert_type,
            is_resolved=False,
        )
        .order_by("-triggered_at")
        .first()
    )
    if existing and existing.count == count:
        return existing
    return AttendanceAlert.objects.create(
        student=student,
        branch=branch,
        alert_type=alert_type,
        count=count,
    )


def _attendance_queryset_for_student(student: Student, branch: Branch):
    return (
        StudentAttendance.objects.select_related("schedule_event", "academic_class", "recorded_by", "branch")
        .filter(student=student, branch=branch)
        .exclude(schedule_event__isnull=True)
        .order_by("-schedule_event__start_datetime", "-created_at")
    )


def _sync_lesson_logs_for_teacher_absence(*, teacher: User, branch: Branch, date_value):
    from academics.models import LessonLog

    updated_ids = []
    attendances = TeacherAttendance.objects.filter(
        teacher=teacher,
        branch=branch,
        date=date_value,
        status=TeacherAttendance.STATUS_ABSENT,
    ).exclude(schedule_event__isnull=True)

    for attendance in attendances.select_related("schedule_event"):
        updated = LessonLog.objects.filter(
            branch=branch,
            teacher=teacher,
            date=date_value,
        ).filter(
            Q(schedule_event=attendance.schedule_event)
            | Q(
                schedule_event__isnull=True,
                academic_class=attendance.schedule_event.academic_class,
                ec=attendance.schedule_event.ec,
                start_time=timezone.localtime(attendance.schedule_event.start_datetime).time(),
                end_time=timezone.localtime(attendance.schedule_event.end_datetime).time(),
            )
        ).exclude(status=LessonLog.STATUS_ABSENT_TEACHER)
        ids = list(updated.values_list("id", flat=True))
        if ids:
            updated.update(status=LessonLog.STATUS_ABSENT_TEACHER, validated_by=None)
            updated_ids.extend(ids)
    return updated_ids


def detect_repeated_absences(student: Student, *, branch: Branch | int | None = None):
    branch = _normalize_branch(branch or _student_branch(student))
    attendances = list(_attendance_queryset_for_student(student, branch)[:10])
    consecutive_absences = 0
    for attendance in attendances:
        if attendance.status != StudentAttendance.STATUS_ABSENT:
            break
        consecutive_absences += 1

    triggered = consecutive_absences >= 3
    alert = None
    if triggered:
        alert = _maybe_create_alert(
            student=student,
            branch=branch,
            alert_type=AttendanceAlert.TYPE_ABSENCE_REPETITION,
            count=consecutive_absences,
        )
    return {
        "student_id": student.id,
        "branch_id": branch.id,
        "count": consecutive_absences,
        "triggered": triggered,
        "alert": alert,
    }


def detect_repeated_lates(student: Student, *, branch: Branch | int | None = None):
    branch = _normalize_branch(branch or _student_branch(student))
    late_count = _attendance_queryset_for_student(student, branch).filter(status=StudentAttendance.STATUS_LATE).count()
    triggered = late_count >= 3
    alert = None
    if triggered:
        alert = _maybe_create_alert(
            student=student,
            branch=branch,
            alert_type=AttendanceAlert.TYPE_LATE_REPETITION,
            count=late_count,
        )
    return {
        "student_id": student.id,
        "branch_id": branch.id,
        "count": late_count,
        "triggered": triggered,
        "alert": alert,
    }


def get_branch_attendance_anomalies(*, branch: Branch | int, date):
    branch = _normalize_branch(branch)
    absent_teachers = TeacherAttendance.objects.filter(
        branch=branch,
        date=date,
        status=TeacherAttendance.STATUS_ABSENT,
    ).exclude(schedule_event__isnull=True)
    repeated_absence_alerts = AttendanceAlert.objects.filter(
        branch=branch,
        alert_type=AttendanceAlert.TYPE_ABSENCE_REPETITION,
        is_resolved=False,
    )
    repeated_late_alerts = AttendanceAlert.objects.filter(
        branch=branch,
        alert_type=AttendanceAlert.TYPE_LATE_REPETITION,
        is_resolved=False,
    )
    return {
        "branch_id": branch.id,
        "date": date,
        "absent_teacher_event_count": absent_teachers.count(),
        "active_absence_alerts_count": repeated_absence_alerts.count(),
        "active_late_alerts_count": repeated_late_alerts.count(),
    }


@transaction.atomic
def mark_student_attendance(
    *,
    student: Student,
    academic_class: AcademicClass,
    schedule_event: AcademicScheduleEvent | int,
    status: str,
    recorded_by: User,
    branch: Branch | int,
    arrival_time=None,
    justification: str = "",
):
    branch = _normalize_branch(branch)
    schedule_event = _normalize_schedule_event(schedule_event)
    _ensure_student_belongs_to_branch(student, branch)
    _ensure_schedule_event_scope(schedule_event=schedule_event, branch=branch, academic_class=academic_class)
    _ensure_student_enrollment(student, academic_class, branch)

    attendance_date = timezone.localtime(schedule_event.start_datetime).date()
    attendance, _ = StudentAttendance.objects.update_or_create(
        student=student,
        schedule_event=schedule_event,
        defaults={
            "academic_class": academic_class,
            "date": attendance_date,
            "status": status,
            "arrival_time": arrival_time,
            "justification": justification or "",
            "recorded_by": recorded_by,
            "branch": branch,
        },
    )

    absence_alert = detect_repeated_absences(student, branch=branch)
    late_alert = detect_repeated_lates(student, branch=branch)
    return {
        "attendance": attendance,
        "absence_alert": absence_alert,
        "late_alert": late_alert,
    }


@transaction.atomic
def mark_teacher_attendance(
    *,
    teacher: User,
    schedule_event: AcademicScheduleEvent | int,
    status: str,
    recorded_by: User,
    branch: Branch | int,
    arrival_time=None,
    justification: str = "",
):
    branch = _normalize_branch(branch)
    schedule_event = _normalize_schedule_event(schedule_event)
    _ensure_schedule_event_scope(schedule_event=schedule_event, branch=branch)
    if schedule_event.teacher_id != teacher.id:
        raise ValidationError("L'evenement planifie ne correspond pas a l'enseignant fourni.")

    attendance_date = timezone.localtime(schedule_event.start_datetime).date()
    attendance, _ = TeacherAttendance.objects.update_or_create(
        teacher=teacher,
        schedule_event=schedule_event,
        defaults={
            "date": attendance_date,
            "status": status,
            "arrival_time": arrival_time,
            "justification": justification or "",
            "recorded_by": recorded_by,
            "branch": branch,
        },
    )
    synced_lesson_log_ids = []
    if status == TeacherAttendance.STATUS_ABSENT:
        synced_lesson_log_ids = _sync_lesson_logs_for_teacher_absence(
            teacher=teacher,
            branch=branch,
            date_value=attendance_date,
        )
    return {
        "attendance": attendance,
        "synced_lesson_log_ids": synced_lesson_log_ids,
    }


def get_class_attendance_summary(academic_class: AcademicClass, date):
    attendances = list(
        StudentAttendance.objects.select_related("student__user", "schedule_event")
        .filter(academic_class=academic_class, date=date, branch=academic_class.branch)
        .order_by(
            "schedule_event__start_datetime",
            "student__inscription__candidature__last_name",
            "student__inscription__candidature__first_name",
        )
    )
    counts = (
        StudentAttendance.objects.filter(academic_class=academic_class, date=date, branch=academic_class.branch)
        .values("status")
        .annotate(total=Count("id"))
    )
    summary_by_status = {
        StudentAttendance.STATUS_PRESENT: 0,
        StudentAttendance.STATUS_ABSENT: 0,
        StudentAttendance.STATUS_LATE: 0,
    }
    for row in counts:
        summary_by_status[row["status"]] = row["total"]

    return {
        "class_id": academic_class.id,
        "class_name": academic_class.display_name,
        "branch_id": academic_class.branch_id,
        "date": date,
        "summary": summary_by_status,
        "records": [
            {
                "student_id": attendance.student_id,
                "student_name": attendance.student.full_name,
                "matricule": attendance.student.matricule,
                "status": attendance.status,
                "arrival_time": attendance.arrival_time.strftime("%H:%M") if attendance.arrival_time else "",
                "justification": attendance.justification,
                "schedule_event_id": attendance.schedule_event_id,
                "schedule_event_time": timezone.localtime(attendance.schedule_event.start_datetime).strftime("%H:%M")
                if attendance.schedule_event_id
                else "",
            }
            for attendance in attendances
        ],
    }


def get_student_attendance_history(student: Student, *, branch: Branch | int | None = None, limit: int = 30):
    queryset = StudentAttendance.objects.select_related(
        "academic_class",
        "branch",
        "recorded_by",
        "schedule_event",
    ).filter(student=student)
    if branch is not None:
        queryset = queryset.filter(branch=_normalize_branch(branch))
    attendances = queryset.order_by("-schedule_event__start_datetime", "-updated_at")[:limit]
    return [
        {
            "date": attendance.date,
            "status": attendance.status,
            "classroom": attendance.academic_class.display_name,
            "branch": attendance.branch.name,
            "arrival_time": attendance.arrival_time.strftime("%H:%M") if attendance.arrival_time else "",
            "justification": attendance.justification,
            "recorded_by": attendance.recorded_by.get_full_name() or attendance.recorded_by.username,
            "schedule_event_id": attendance.schedule_event_id,
            "schedule_event_time": timezone.localtime(attendance.schedule_event.start_datetime).strftime("%H:%M")
            if attendance.schedule_event_id
            else "",
        }
        for attendance in attendances
    ]
