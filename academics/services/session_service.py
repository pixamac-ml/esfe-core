"""
Orchestration des seances cours pour le surveillant (ouverture / cloture / presence prof).

Les donnees canoniques restent AcademicScheduleEvent, AcademicScheduleExecutionLog,
LessonLog et TeacherAttendance — pas de duplication de modele « Session » separé.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from academics.models import AcademicScheduleEvent, LessonLog
from academics.services.schedule_service import complete_schedule_event, start_schedule_event
from students.models import TeacherAttendance
from students.services.attendance_service import mark_teacher_attendance

User = get_user_model()


def get_supervisor_today_course_rows(*, branch, target_date=None):
    """
    Liste des cours du jour avec phase pedagogique et indicateurs d'action (sans logique dans les templates).
    """
    if branch is None:
        return []

    target_date = target_date or timezone.localdate()
    start = timezone.make_aware(datetime.combine(target_date, time.min))
    end = start + timedelta(days=1)

    events = list(
        AcademicScheduleEvent.objects.select_related("academic_class", "teacher", "ec", "branch")
        .prefetch_related("execution_logs")
        .filter(
            branch=branch,
            start_datetime__gte=start,
            start_datetime__lt=end,
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            is_active=True,
        )
        .exclude(status=AcademicScheduleEvent.STATUS_CANCELLED)
        .order_by("start_datetime", "id")
    )

    event_ids = [e.id for e in events]
    lesson_by_event = {
        row.schedule_event_id: row
        for row in LessonLog.objects.select_related("schedule_event")
        .filter(branch=branch, date=target_date, schedule_event_id__in=event_ids)
    }
    teacher_att_by_event = {
        row.schedule_event_id: row
        for row in TeacherAttendance.objects.select_related("teacher", "schedule_event")
        .filter(branch=branch, date=target_date, schedule_event_id__in=event_ids)
    }

    now = timezone.now()
    rows = []
    for event in events:
        local_start = timezone.localtime(event.start_datetime)
        local_end = timezone.localtime(event.end_datetime)
        lesson_log = lesson_by_event.get(event.id)
        teacher_att = teacher_att_by_event.get(event.id)

        if event.status == AcademicScheduleEvent.STATUS_COMPLETED:
            phase_code = "done"
            phase_label = "Termine"
        elif event.status == AcademicScheduleEvent.STATUS_ONGOING:
            phase_code = "ongoing"
            phase_label = "En cours"
        elif now < event.start_datetime:
            phase_code = "planned"
            phase_label = "Prevu"
        elif now <= event.end_datetime:
            phase_code = "ongoing"
            phase_label = "En cours"
        else:
            phase_code = "followup"
            phase_label = "A cloturer"

        teacher_present_code = None
        teacher_present_label = ""
        if teacher_att:
            teacher_present_code = teacher_att.status
            teacher_present_label = teacher_att.get_status_display()

        course_started_flag = bool(
            lesson_log
            and lesson_log.status
            not in {
                LessonLog.STATUS_PLANNED,
                LessonLog.STATUS_CANCELLED,
            }
        )

        exec_open = any(
            log.is_completed is False and log.started_at is not None for log in event.execution_logs.all()
        )

        rows.append(
            {
                "event_id": event.id,
                "time_range": f"{local_start.strftime('%H:%M')} - {local_end.strftime('%H:%M')}",
                "class_name": event.academic_class.display_name,
                "teacher_name": event.teacher.get_full_name() or event.teacher.username,
                "subject_title": event.ec.title,
                "room": event.location or ("En ligne" if event.is_online else "Salle non precisee"),
                "event_status": event.status,
                "event_status_label": event.get_status_display(),
                "phase_code": phase_code,
                "phase_label": phase_label,
                "teacher_present_code": teacher_present_code,
                "teacher_present_label": teacher_present_label,
                "course_started_flag": course_started_flag,
                "lesson_status_code": lesson_log.status if lesson_log else "",
                "lesson_status_label": lesson_log.get_status_display() if lesson_log else "",
                "can_open_session": phase_code in {"planned", "ongoing", "followup"}
                and event.status
                not in {
                    AcademicScheduleEvent.STATUS_COMPLETED,
                    AcademicScheduleEvent.STATUS_CANCELLED,
                },
                "can_close_session": event.status
                in {
                    AcademicScheduleEvent.STATUS_ONGOING,
                    AcademicScheduleEvent.STATUS_PLANNED,
                }
                or (phase_code == "followup" and event.status != AcademicScheduleEvent.STATUS_COMPLETED),
                "execution_started": exec_open,
            }
        )
    return rows


def start_session(*, event: AcademicScheduleEvent, supervisor: User, notes: str = ""):
    """Marque le cours comme demarre (execution + statut ongoing). L'enseignant reference reste celui du cours."""
    teacher = event.teacher
    note_value = (notes or "").strip()
    if supervisor and supervisor.pk:
        prefix = f"Ouvert par surveillant ({supervisor.get_full_name() or supervisor.username}). "
        note_value = prefix + note_value
    return start_schedule_event(event, teacher, notes=note_value.strip())


def close_session(*, event: AcademicScheduleEvent, supervisor: User, notes: str = ""):
    """Cloture officielle de la seance planifiee."""
    return complete_schedule_event(event, supervisor, notes=notes or "")


def assign_session_replacement(*, event: AcademicScheduleEvent, replacement_teacher: User, supervisor: User, note: str = ""):
    """
    Affecte un enseignant remplaçant à une séance datée précise (instance, pas le modèle
    récurrent). L'enseignant d'origine reste visible via TeacherAttendance (marqué absent
    séparément par le surveillant) ; cette fonction ne fait que réassigner qui dispense la
    séance concernée.
    """
    event.teacher = replacement_teacher
    event.updated_by = supervisor
    event.save(update_fields=["teacher", "updated_by"])
    return event


def mark_teacher_presence(
    *,
    event: AcademicScheduleEvent,
    supervisor: User,
    branch,
    present: bool,
    late_minutes: int | None = None,
    justification: str = "",
):
    """
    Enregistre la presence enseignant pour la seance (reutilise TeacherAttendance / mark_teacher_attendance).

    late_minutes: si present et > 0 -> statut 'late' avec arrival_time derivee du debut du cours.
    """
    status = TeacherAttendance.STATUS_PRESENT
    arrival_time = None
    if not present:
        status = TeacherAttendance.STATUS_ABSENT
    elif late_minutes and late_minutes > 0:
        status = TeacherAttendance.STATUS_LATE
        course_start = timezone.localtime(event.start_datetime)
        arrival_dt = course_start + timedelta(minutes=late_minutes)
        arrival_time = arrival_dt.time()

    return mark_teacher_attendance(
        teacher=event.teacher,
        schedule_event=event,
        status=status,
        recorded_by=supervisor,
        branch=branch,
        arrival_time=arrival_time,
        justification=justification or "",
    )