from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from django.db.models import Count
from django.utils import timezone

from academics.models import AcademicClass, AcademicScheduleEvent, LessonLog
from academics.services.lesson_log_service import get_daily_lesson_status
from academics.services.schedule_service import get_director_schedule_overview
from students.models import AttendanceAlert, Student, StudentAttendance, TeacherAttendance
from students.services.attendance_service import get_branch_attendance_anomalies


ALERT_LEVEL_CRITICAL = "critical"
ALERT_LEVEL_WARNING = "warning"
ALERT_LEVEL_INFO = "info"
ALERT_ORDER = {
    ALERT_LEVEL_CRITICAL: 0,
    ALERT_LEVEL_WARNING: 1,
    ALERT_LEVEL_INFO: 2,
}


def _build_alert(level, alert_type, message, *, target=None, action_label="A traiter"):
    return {
        "level": level,
        "type": alert_type,
        "message": message,
        "target": target,
        "action_label": action_label,
    }


def _schedule_alert_level(alert_type, default_level="warning"):
    mapping = {
        "missing_teacher": ALERT_LEVEL_CRITICAL,
        "missing_location": ALERT_LEVEL_WARNING,
        "postponed_not_rescheduled": ALERT_LEVEL_WARNING,
        "unresolved_conflict": ALERT_LEVEL_CRITICAL,
        "class_without_events": ALERT_LEVEL_INFO,
        "teacher_overload": ALERT_LEVEL_WARNING,
        "high_cancellation_rate": ALERT_LEVEL_WARNING,
    }
    return mapping.get(alert_type, default_level)


def _lesson_status_theme(item):
    status = item.get("status")
    if status in {"teacher_absent_with_planned_lesson", "teacher_absent_with_lesson_log"}:
        return "critical"
    if status == "missing_lesson_log":
        return "warning"
    if status in {"done", "completed"}:
        return "good"
    return "neutral"


def _serialize_today_event(event, *, teacher_attendance_map, lesson_log_map):
    teacher_attendance = teacher_attendance_map.get(event.id)
    lesson_log = lesson_log_map.get(event.id)
    local_start = timezone.localtime(event.start_datetime)
    local_end = timezone.localtime(event.end_datetime)
    if teacher_attendance and teacher_attendance.status == TeacherAttendance.STATUS_ABSENT:
        supervision_status = "Enseignant absent"
        supervision_level = "critical"
    elif lesson_log and lesson_log.status == LessonLog.STATUS_ABSENT_TEACHER:
        supervision_status = "Cours non tenu"
        supervision_level = "critical"
    elif lesson_log and lesson_log.status == LessonLog.STATUS_DONE:
        supervision_status = "Cours trace"
        supervision_level = "good"
    elif lesson_log:
        supervision_status = lesson_log.get_status_display()
        supervision_level = "warning"
    elif event.status == AcademicScheduleEvent.STATUS_COMPLETED:
        supervision_status = "Termine sans cahier"
        supervision_level = "warning"
    else:
        supervision_status = "Suivi attendu"
        supervision_level = "warning"

    return {
        "id": event.id,
        "time_range": f"{local_start.strftime('%H:%M')} - {local_end.strftime('%H:%M')}",
        "class_name": event.academic_class.display_name,
        "teacher_name": event.teacher.get_full_name() or event.teacher.username,
        "subject_title": event.ec.title,
        "event_status": event.get_status_display(),
        "supervision_status": supervision_status,
        "supervision_level": supervision_level,
        "location": event.location or "Salle non precisee",
    }


def _build_event_action_options(events):
    options = []
    for event in events:
        local_start = timezone.localtime(event.start_datetime)
        options.append(
            {
                "id": event.id,
                "label": (
                    f"{local_start.strftime('%H:%M')} - {event.academic_class.display_name} - "
                    f"{event.ec.title} - {event.teacher.get_full_name() or event.teacher.username}"
                ),
                "class_name": event.academic_class.display_name,
                "teacher_name": event.teacher.get_full_name() or event.teacher.username,
                "subject_title": event.ec.title,
            }
        )
    return options


def _build_student_action_options(branch):
    students_qs = (
        Student.objects.select_related("user", "inscription__candidature")
        .filter(
            inscription__candidature__branch=branch,
            is_active=True,
            user__academic_enrollments__branch=branch,
            user__academic_enrollments__is_active=True,
        )
        .distinct()
        .order_by(
            "inscription__candidature__last_name",
            "inscription__candidature__first_name",
            "matricule",
        )
    )
    return [
        {
            "id": student.id,
            "label": f"{student.full_name} - {student.matricule}",
        }
        for student in students_qs[:200]
    ]


def _serialize_student_attendance_row(attendance):
    return {
        "student_name": attendance.student.full_name,
        "class_name": attendance.academic_class.display_name,
        "status": attendance.get_status_display(),
        "status_code": attendance.status,
        "event_time": timezone.localtime(attendance.schedule_event.start_datetime).strftime("%H:%M")
        if attendance.schedule_event_id
        else "",
        "recorded_by": attendance.recorded_by.get_full_name() or attendance.recorded_by.username,
    }


def _serialize_teacher_attendance_row(attendance):
    return {
        "teacher_name": attendance.teacher.get_full_name() or attendance.teacher.username,
        "status": attendance.get_status_display(),
        "status_code": attendance.status,
        "event_time": timezone.localtime(attendance.schedule_event.start_datetime).strftime("%H:%M")
        if attendance.schedule_event_id
        else "",
        "class_name": attendance.schedule_event.academic_class.display_name if attendance.schedule_event_id else "",
    }


def _serialize_lesson_log_row(lesson_log):
    return {
        "class_name": lesson_log.academic_class.display_name,
        "subject_title": lesson_log.ec.title,
        "teacher_name": lesson_log.teacher.get_full_name() or lesson_log.teacher.username,
        "status": lesson_log.get_status_display(),
        "status_code": lesson_log.status,
        "time_range": f"{lesson_log.start_time.strftime('%H:%M')} - {lesson_log.end_time.strftime('%H:%M')}",
    }


def _build_class_watchlist(*, classes, today, attendance_by_class, lesson_issues_by_class):
    watchlist = []
    for academic_class in classes:
        attendance_rows = attendance_by_class.get(academic_class.id, [])
        absent_count = sum(1 for row in attendance_rows if row.status == StudentAttendance.STATUS_ABSENT)
        late_count = sum(1 for row in attendance_rows if row.status == StudentAttendance.STATUS_LATE)
        issue_count = lesson_issues_by_class.get(academic_class.id, 0)
        severity = ALERT_LEVEL_INFO
        if issue_count > 0:
            severity = ALERT_LEVEL_CRITICAL
        elif absent_count >= 3 or late_count >= 3:
            severity = ALERT_LEVEL_WARNING
        watchlist.append(
            {
                "class_name": academic_class.display_name,
                "programme_title": academic_class.programme.title,
                "student_count": getattr(academic_class, "student_count", 0),
                "absent_count": absent_count,
                "late_count": late_count,
                "issue_count": issue_count,
                "severity": severity,
            }
        )
    return sorted(
        watchlist,
        key=lambda item: (
            ALERT_ORDER[item["severity"]],
            -(item["issue_count"] + item["absent_count"] + item["late_count"]),
            item["class_name"],
        ),
    )


def build_supervisor_dashboard_context(request, *, branch, page_title, page_kicker, sidebar_links, highlight, base_context_builder):
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=7)
    overview = get_director_schedule_overview(branch, week_start) if branch else {"stats": {}, "quality": {"score": 0, "warnings": []}, "alerts": [], "timetable": []}

    classes_qs = AcademicClass.objects.select_related("programme", "academic_year", "branch").filter(is_active=True)
    if branch:
        classes_qs = classes_qs.filter(branch=branch)
    classes_qs = classes_qs.annotate(student_count=Count("enrollments")).order_by("level", "programme__title")
    classes = list(classes_qs[:8])

    week_events_qs = AcademicScheduleEvent.objects.select_related("academic_class", "teacher", "ec", "branch").filter(
        start_datetime__date__gte=week_start,
        start_datetime__date__lt=week_end,
    )
    if branch:
        week_events_qs = week_events_qs.filter(branch=branch)
    current_week_events = list(week_events_qs.order_by("start_datetime", "id")[:10])

    today_events_qs = AcademicScheduleEvent.objects.select_related("academic_class", "teacher", "ec", "branch").filter(
        start_datetime__date=today,
        event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
        is_active=True,
    ).exclude(status=AcademicScheduleEvent.STATUS_CANCELLED)
    if branch:
        today_events_qs = today_events_qs.filter(branch=branch)
    today_events = list(today_events_qs.order_by("start_datetime", "id"))
    today_event_ids = [event.id for event in today_events]

    total_students = branch.academic_enrollments.count() if branch else 0
    total_classes = classes_qs.count()
    total_teachers = week_events_qs.values("teacher_id").distinct().count() if branch else 0

    today_student_attendances = list(
        StudentAttendance.objects.select_related("student__user", "academic_class", "schedule_event")
        .filter(branch=branch, date=today)
        .order_by("schedule_event__start_datetime", "student__inscription__candidature__last_name")
    ) if branch else []
    today_teacher_attendances = list(
        TeacherAttendance.objects.select_related("teacher", "schedule_event")
        .filter(branch=branch, date=today)
        .order_by("schedule_event__start_datetime")
    ) if branch else []
    today_lesson_logs = list(
        LessonLog.objects.select_related("teacher", "academic_class", "ec", "schedule_event")
        .filter(branch=branch, date=today)
        .order_by("start_time", "id")
    ) if branch else []

    daily_lesson_status = get_daily_lesson_status(branch, today) if branch else {
        "scheduled_courses": 0,
        "lesson_logs_count": 0,
        "missing_lesson_logs_count": 0,
        "critical_count": 0,
        "missing_lesson_logs": [],
        "critical_items": [],
        "lesson_logs": [],
    }
    attendance_anomalies = get_branch_attendance_anomalies(branch=branch, date=today) if branch else {
        "absent_teacher_event_count": 0,
        "active_absence_alerts_count": 0,
        "active_late_alerts_count": 0,
    }

    teacher_attendance_map = {attendance.schedule_event_id: attendance for attendance in today_teacher_attendances if attendance.schedule_event_id}
    lesson_log_map = {lesson_log.schedule_event_id: lesson_log for lesson_log in today_lesson_logs if lesson_log.schedule_event_id}

    attendance_by_class = defaultdict(list)
    for attendance in today_student_attendances:
        attendance_by_class[attendance.academic_class_id].append(attendance)

    lesson_issues_by_class = defaultdict(int)
    for issue in daily_lesson_status["missing_lesson_logs"]:
        event = next((event for event in today_events if event.id == issue["event_id"]), None)
        if event:
            lesson_issues_by_class[event.academic_class_id] += 1
    for issue in daily_lesson_status["critical_items"]:
        event = next((event for event in today_events if event.id == issue["event_id"]), None)
        if event:
            lesson_issues_by_class[event.academic_class_id] += 1

    absent_students_count = sum(1 for row in today_student_attendances if row.status == StudentAttendance.STATUS_ABSENT)
    late_students_count = sum(1 for row in today_student_attendances if row.status == StudentAttendance.STATUS_LATE)
    risk_students_count = (
        AttendanceAlert.objects.filter(branch=branch, is_resolved=False)
        .values("student_id")
        .distinct()
        .count()
        if branch
        else 0
    )

    schedule_alerts = overview.get("alerts", [])
    dashboard_alerts = []
    for item in daily_lesson_status["critical_items"]:
        dashboard_alerts.append(
            _build_alert(
                ALERT_LEVEL_CRITICAL,
                item["status"],
                f"{item['classroom']} - {item['subject']} : {item['teacher']} absent sur un cours planifie.",
                target=item["event_id"],
            )
        )
    for item in daily_lesson_status["missing_lesson_logs"]:
        dashboard_alerts.append(
            _build_alert(
                ALERT_LEVEL_WARNING,
                item["status"],
                f"{item['classroom']} - {item['subject']} a {item['scheduled_time']} sans cahier de texte.",
                target=item["event_id"],
            )
        )
    active_alerts = AttendanceAlert.objects.select_related("student__inscription__candidature").filter(
        branch=branch,
        is_resolved=False,
    ) if branch else []
    for alert in active_alerts:
        student_name = alert.student.full_name
        label = "absences repetitives" if alert.alert_type == AttendanceAlert.TYPE_ABSENCE_REPETITION else "retards repetitifs"
        dashboard_alerts.append(
            _build_alert(
                ALERT_LEVEL_WARNING,
                alert.alert_type,
                f"{student_name} est signale pour {label} ({alert.count}).",
                target=alert.student_id,
            )
        )
    for alert in schedule_alerts:
        dashboard_alerts.append(
            _build_alert(
                _schedule_alert_level(alert.get("type"), alert.get("level", "warning")),
                alert.get("type", "schedule_alert"),
                alert.get("message", ""),
                target=alert.get("target"),
            )
        )
    dashboard_alerts = sorted(
        dashboard_alerts,
        key=lambda item: (ALERT_ORDER.get(item["level"], 9), item["type"], item["message"]),
    )[:12]

    class_watchlist = _build_class_watchlist(
        classes=classes,
        today=today,
        attendance_by_class=attendance_by_class,
        lesson_issues_by_class=lesson_issues_by_class,
    )
    today_course_statuses = [
        _serialize_today_event(
            event,
            teacher_attendance_map=teacher_attendance_map,
            lesson_log_map=lesson_log_map,
        )
        for event in today_events
    ]
    attention_actions = []
    if daily_lesson_status["critical_count"]:
        attention_actions.append("Traiter les cours critiques du jour")
    if daily_lesson_status["missing_lesson_logs_count"]:
        attention_actions.append("Relancer les cahiers de texte manquants")
    if attendance_anomalies["active_absence_alerts_count"]:
        attention_actions.append("Suivre les etudiants en absences repetitives")
    if attendance_anomalies["active_late_alerts_count"]:
        attention_actions.append("Recadrer les retards repetitifs")
    if not attention_actions:
        attention_actions.append("Aucune action urgente detectee")

    kpis = {
        "absent_students": absent_students_count,
        "late_students": late_students_count,
        "absent_teachers": attendance_anomalies["absent_teacher_event_count"],
        "missing_lesson_logs": daily_lesson_status["missing_lesson_logs_count"],
        "critical_courses": daily_lesson_status["critical_count"],
        "risk_students": risk_students_count,
    }

    return {
        **base_context_builder(
            request,
            page_title=page_title,
            module_cards=highlight,
        ),
        "dashboard_kind": page_kicker,
        "branch": branch,
        "week_start": week_start,
        "week_end": week_end,
        "today": today,
        "current_week_events": current_week_events,
        "today_course_statuses": today_course_statuses,
        "classes": classes,
        "class_watchlist": class_watchlist,
        "total_students": total_students,
        "total_classes": total_classes,
        "total_teachers": total_teachers,
        "schedule_stats": overview.get("stats", {}),
        "quality": overview.get("quality", {}),
        "alerts": dashboard_alerts,
        "timetable": overview.get("timetable", []),
        "class_load_items": sorted(
            (overview.get("stats", {}).get("class_load") or {}).items(),
            key=lambda item: (-item[1]["hours"], item[0]),
        )[:5],
        "teacher_load_items": sorted(
            (overview.get("stats", {}).get("teacher_load") or {}).items(),
            key=lambda item: (-item[1]["hours"], item[0]),
        )[:5],
        "sidebar_links": sidebar_links,
        "supervisor_kpis": kpis,
        "today_attendance_total": len(today_student_attendances),
        "today_teacher_attendance_total": len(today_teacher_attendances),
        "daily_lesson_status": daily_lesson_status,
        "attendance_anomalies": attendance_anomalies,
        "attention_actions": attention_actions,
        "course_action_options": _build_event_action_options(today_events),
        "teacher_action_options": _build_event_action_options(today_events),
        "student_action_options": _build_student_action_options(branch) if branch else [],
        "recent_student_attendances": [
            _serialize_student_attendance_row(attendance) for attendance in today_student_attendances[:6]
        ],
        "recent_teacher_attendances": [
            _serialize_teacher_attendance_row(attendance) for attendance in today_teacher_attendances[:6]
        ],
        "recent_lesson_logs": [
            _serialize_lesson_log_row(lesson_log) for lesson_log in today_lesson_logs[:6]
        ],
    }
