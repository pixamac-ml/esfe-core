from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from academics.models import AcademicClass, AcademicScheduleEvent, EC, LessonLog
from academics.services.schedule_service import get_class_week_schedule
from academics.services.session_service import get_supervisor_today_course_rows
from academics.services.timetable_service import build_timetable_view_payload
from students.models import Student, StudentAttendance, TeacherAttendance
from students.services.attendance_service import get_branch_attendance_anomalies, list_students_for_schedule_event
from students.services.attendance_workflow import build_attendance_workflow_payload, is_roll_locked_for_event
from students.services.case_service import count_open_cases


def build_home_section_context(*, branch, selected_class=None):
    """Vue d'ensemble du jour : presence, alertes utiles, seances du jour (donnees reelles)."""
    today = timezone.localdate()
    anomalies = get_branch_attendance_anomalies(branch=branch, date=today)

    attendance_scope = StudentAttendance.objects.filter(branch=branch, date=today)
    if selected_class:
        attendance_scope = attendance_scope.filter(academic_class=selected_class)
    total_marked = attendance_scope.count()
    present_count = attendance_scope.filter(status=StudentAttendance.STATUS_PRESENT).count()
    presence_rate = round((present_count / total_marked) * 100) if total_marked else None

    today_rows = get_supervisor_today_course_rows(branch=branch, target_date=today)
    if selected_class:
        today_rows = [row for row in today_rows if row["class_name"] == selected_class.display_name]
    pending_appel_rows = [row for row in today_rows if not row["course_started_flag"]]

    alerts = []
    if pending_appel_rows:
        first = pending_appel_rows[0]
        alerts.append(
            {
                "message": f"Appel non fait par {first['teacher_name']} — {first['subject_title']} ({first['time_range']})",
                "level": "warn",
                "section": "attendance",
            }
        )
    if anomalies["absent_teacher_event_count"]:
        alerts.append(
            {
                "message": f"{anomalies['absent_teacher_event_count']} enseignant(s) absent(s) aujourd'hui",
                "level": "bad",
                "section": "teachers",
            }
        )
    if anomalies["active_absence_alerts_count"]:
        alerts.append(
            {
                "message": f"{anomalies['active_absence_alerts_count']} alerte(s) d'absences répétées actives",
                "level": "bad",
                "section": "classes",
            }
        )

    return {
        "home_presence_rate": presence_rate,
        "home_pending_appel_count": len(pending_appel_rows),
        "home_absent_teachers_count": anomalies["absent_teacher_event_count"],
        "home_open_cases_count": count_open_cases(branch=branch),
        "home_today_sessions": today_rows[:8],
        "home_alerts": alerts[:5],
    }


def build_teachers_section_context(*, branch):
    """Vue du jour par enseignant : presence, ponctualite, appel fait/a faire (donnees reelles)."""
    today = timezone.localdate()
    events = list(
        AcademicScheduleEvent.objects.select_related("teacher", "ec", "academic_class")
        .filter(
            branch=branch,
            start_datetime__date=today,
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            is_active=True,
        )
        .exclude(status=AcademicScheduleEvent.STATUS_CANCELLED)
        .order_by("start_datetime")
    )
    event_ids = [e.id for e in events]
    attendance_map = {
        row.schedule_event_id: row
        for row in TeacherAttendance.objects.filter(branch=branch, date=today, schedule_event_id__in=event_ids)
    }
    lesson_map = {
        row.schedule_event_id: row
        for row in LessonLog.objects.filter(branch=branch, date=today, schedule_event_id__in=event_ids)
    }

    by_teacher = {}
    for event in events:
        teacher = event.teacher
        entry = by_teacher.setdefault(
            teacher.id,
            {
                "id": teacher.id,
                "name": teacher.get_full_name() or teacher.username,
                "subjects": [],
                "present": True,
                "punctual": True,
                "appel_done": False,
                "appel_pending": False,
                "current_event_id": None,
            },
        )
        if event.ec.title not in entry["subjects"]:
            entry["subjects"].append(event.ec.title)
        entry["current_event_id"] = event.id

        attendance = attendance_map.get(event.id)
        if attendance:
            if attendance.status == TeacherAttendance.STATUS_ABSENT:
                entry["present"] = False
            elif attendance.status == TeacherAttendance.STATUS_LATE:
                entry["punctual"] = False

        lesson = lesson_map.get(event.id)
        if lesson and lesson.status not in (LessonLog.STATUS_PLANNED, LessonLog.STATUS_CANCELLED):
            entry["appel_done"] = True
        else:
            entry["appel_pending"] = True

    teachers = []
    for entry in by_teacher.values():
        if entry["appel_pending"]:
            appel = "pending"
        elif entry["appel_done"]:
            appel = "done"
        else:
            appel = "na"
        teachers.append(
            {
                "id": entry["id"],
                "name": entry["name"],
                "subject": ", ".join(entry["subjects"]),
                "present": entry["present"],
                "punctual": entry["punctual"],
                "appel": appel,
                "current_event_id": entry["current_event_id"],
            }
        )
    teachers.sort(key=lambda t: t["name"])

    return {
        "teachers": teachers,
        "teachers_total_count": len(teachers),
        "teachers_present_count": sum(1 for t in teachers if t["present"]),
        "teachers_absent_count": sum(1 for t in teachers if not t["present"]),
        "teachers_pending_appel_count": sum(1 for t in teachers if t["appel"] == "pending"),
    }


def build_schedule_section_context(*, branch, academic_class, week_start):
    schedule = get_class_week_schedule(academic_class, week_start)
    summary = schedule.get("summary") or {}
    day_event_counts = schedule.get("day_event_counts") or []
    return {
        "schedule": schedule,
        "prev_week_start": schedule["week_start"] - timedelta(days=7),
        "next_week_start": schedule["week_start"] + timedelta(days=7),
        "schedule_week_total": len(schedule.get("events") or []),
        "schedule_week_planned": summary.get("planned", 0),
        "schedule_week_completed": summary.get("completed", 0),
        "schedule_empty_days_count": len([item for item in day_event_counts if not item.get("has_events")]),
        "timetable_view": build_timetable_view_payload(
            branch=branch,
            academic_class=academic_class,
            week_start=schedule["week_start"],
        ),
    }


def build_courses_section_context(*, request, branch, academic_class):
    User = get_user_model()
    ecs = list(
        EC.objects.select_related("ue", "ue__semester")
        .filter(ue__semester__academic_class=academic_class)
        .order_by("ue__semester__number", "ue__code", "title")[:250]
    )
    teacher_q = (request.GET.get("teacher_q") or "").strip()
    prefill_ec_raw = (request.GET.get("ec_id") or request.POST.get("ec_id") or "").strip()
    prefill_teacher_raw = (request.GET.get("teacher_id") or request.POST.get("teacher_id") or "").strip()
    prefill_date = (request.GET.get("date") or request.POST.get("date") or "").strip()
    prefill_start_time = (request.GET.get("start_time") or request.POST.get("start_time") or "").strip()
    prefill_end_time = (request.GET.get("end_time") or request.POST.get("end_time") or "").strip()
    prefill_location = (request.GET.get("location") or request.POST.get("location") or "").strip()
    teachers_qs = User.objects.filter(
        is_active=True,
        profile__branch=branch,
        profile__position="teacher",
    )
    if teacher_q:
        teachers_qs = teachers_qs.filter(
            Q(first_name__icontains=teacher_q)
            | Q(last_name__icontains=teacher_q)
            | Q(username__icontains=teacher_q)
        )
    return {
        "ecs": ecs,
        "teachers": list(teachers_qs.order_by("first_name", "last_name", "username")[:80]),
        "prefill_ec_id": int(prefill_ec_raw) if prefill_ec_raw.isdigit() else None,
        "prefill_teacher_id": int(prefill_teacher_raw) if prefill_teacher_raw.isdigit() else None,
        "prefill_date": prefill_date,
        "prefill_start_time": prefill_start_time,
        "prefill_end_time": prefill_end_time,
        "prefill_location": prefill_location,
    }


def build_attendance_monthly_report_context(*, branch, academic_class, month):
    """Rapport mensuel de présence par étudiant pour une classe donnée."""
    import calendar
    from datetime import timedelta as _td

    last_day = calendar.monthrange(month.year, month.month)[1]
    month_end = month.replace(day=last_day)
    prev_month = (month - _td(days=1)).replace(day=1)
    next_month = month_end + _td(days=1)

    attendances = list(
        StudentAttendance.objects.select_related("student", "student__inscription__candidature")
        .filter(
            branch=branch,
            academic_class=academic_class,
            date__gte=month,
            date__lte=month_end,
        )
        .order_by("student__inscription__candidature__last_name", "date")
    )

    by_student = {}
    for att in attendances:
        student = att.student
        entry = by_student.setdefault(
            student.id,
            {
                "student": student,
                "present": 0,
                "absent": 0,
                "late": 0,
                "justified": 0,
                "total": 0,
            },
        )
        entry["total"] += 1
        if att.status == StudentAttendance.STATUS_PRESENT:
            entry["present"] += 1
        elif att.status == StudentAttendance.STATUS_ABSENT:
            if att.justification:
                entry["justified"] += 1
            else:
                entry["absent"] += 1
        elif att.status == StudentAttendance.STATUS_LATE:
            entry["late"] += 1

    rows = []
    for entry in by_student.values():
        total = entry["total"]
        rate = round((entry["present"] / total) * 100) if total else None
        rows.append({**entry, "rate": rate})
    rows.sort(key=lambda r: (
        r["student"].inscription.candidature.last_name if hasattr(r["student"], "inscription") else "",
        r["student"].matricule,
    ))

    return {
        "attendance_report_month": month,
        "attendance_report_month_end": month_end,
        "attendance_report_prev_month": prev_month,
        "attendance_report_next_month": next_month,
        "attendance_report_rows": rows,
        "attendance_report_class": academic_class,
        "attendance_report_total_students": len(rows),
    }


def build_teachers_weekly_report_context(*, branch, week_start):
    """Rapport hebdomadaire de régularité pour chaque enseignant de l'annexe."""
    from datetime import timedelta as _td

    week_end = week_start + _td(days=7)

    events = list(
        AcademicScheduleEvent.objects.select_related("teacher", "ec", "academic_class")
        .filter(
            branch=branch,
            start_datetime__date__gte=week_start,
            start_datetime__date__lt=week_end,
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            is_active=True,
        )
        .exclude(status=AcademicScheduleEvent.STATUS_CANCELLED)
        .order_by("teacher__first_name", "teacher__last_name", "start_datetime")
    )
    event_ids = [e.id for e in events]

    attendance_map = {
        row.schedule_event_id: row
        for row in TeacherAttendance.objects.filter(
            branch=branch,
            date__gte=week_start,
            date__lt=week_end,
            schedule_event_id__in=event_ids,
        )
    }
    lesson_map = {
        row.schedule_event_id: row
        for row in LessonLog.objects.filter(
            branch=branch,
            date__gte=week_start,
            date__lt=week_end,
            schedule_event_id__in=event_ids,
        )
    }

    by_teacher = {}
    for event in events:
        teacher = event.teacher
        entry = by_teacher.setdefault(
            teacher.id,
            {
                "id": teacher.id,
                "name": teacher.get_full_name() or teacher.username,
                "subjects": set(),
                "planned": 0,
                "held": 0,
                "absent": 0,
                "late": 0,
                "cancelled": 0,
            },
        )
        entry["planned"] += 1
        entry["subjects"].add(event.ec.title)

        lesson = lesson_map.get(event.id)
        attendance = attendance_map.get(event.id)

        if lesson:
            if lesson.status == LessonLog.STATUS_DONE:
                entry["held"] += 1
            elif lesson.status == LessonLog.STATUS_ABSENT_TEACHER:
                entry["absent"] += 1
            elif lesson.status == LessonLog.STATUS_CANCELLED:
                entry["cancelled"] += 1

        if attendance and attendance.status == TeacherAttendance.STATUS_LATE:
            entry["late"] += 1

    teachers = []
    for entry in by_teacher.values():
        planned = entry["planned"]
        held = entry["held"]
        rate = round((held / planned) * 100) if planned else None
        teachers.append(
            {
                "id": entry["id"],
                "name": entry["name"],
                "subjects": sorted(entry["subjects"]),
                "planned": planned,
                "held": held,
                "absent": entry["absent"],
                "late": entry["late"],
                "cancelled": entry["cancelled"],
                "regularity_rate": rate,
            }
        )
    teachers.sort(key=lambda t: t["name"])

    return {
        "report_week_start": week_start,
        "report_week_end": week_end - _td(days=1),
        "report_prev_week": week_start - _td(days=7),
        "report_next_week": week_start + _td(days=7),
        "report_teachers": teachers,
        "report_total_events": len(events),
        "report_absent_count": sum(t["absent"] for t in teachers),
        "report_late_count": sum(t["late"] for t in teachers),
    }


_ATTENDANCE_CYCLE = {
    StudentAttendance.STATUS_PRESENT: StudentAttendance.STATUS_LATE,
    StudentAttendance.STATUS_LATE: StudentAttendance.STATUS_ABSENT,
    StudentAttendance.STATUS_ABSENT: StudentAttendance.STATUS_PRESENT,
}


def next_attendance_status(status):
    return _ATTENDANCE_CYCLE.get(status, StudentAttendance.STATUS_PRESENT)


def build_attendance_section_context(*, request, branch, academic_class, roll_date):
    events = list(
        AcademicScheduleEvent.objects.select_related("teacher", "ec", "academic_class")
        .filter(
            branch=branch,
            academic_class=academic_class,
            start_datetime__date=roll_date,
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            is_active=True,
        )
        .exclude(status=AcademicScheduleEvent.STATUS_CANCELLED)
        .order_by("start_datetime", "id")
    )
    selected_event = None
    selected_event_raw = (request.GET.get("schedule_event_id") or request.POST.get("schedule_event_id") or "").strip()
    if selected_event_raw.isdigit():
        selected_event = next((event for event in events if event.id == int(selected_event_raw)), None)
    if selected_event is None and events:
        selected_event = events[0]

    rows = []
    roll_locked = False
    if selected_event:
        roll_locked = is_roll_locked_for_event(branch=branch, event=selected_event)
        roster = list_students_for_schedule_event(schedule_event=selected_event, branch=branch)
        attendance_map = {
            row.student_id: row
            for row in StudentAttendance.objects.select_related("student")
            .filter(branch=branch, schedule_event=selected_event)
        }
        for student in roster:
            attendance = attendance_map.get(student.id)
            status = attendance.status if attendance else StudentAttendance.STATUS_PRESENT
            next_status = next_attendance_status(status)
            rows.append(
                {
                    "student": student,
                    "status": status,
                    "next_status": next_status,
                    "justification": attendance.justification if attendance else "",
                }
            )

    return {
        "roll_date": roll_date,
        "roll_date_iso": roll_date.isoformat(),
        "attendance_events": events,
        "selected_event": selected_event,
        "attendance_rows": rows,
        "roll_locked": roll_locked,
        "attendance_workflow": build_attendance_workflow_payload(
            branch=branch,
            user=request.user,
            academic_class_id=academic_class.id,
            roll_date=roll_date,
        ),
    }


def build_students_section_context(*, request, branch, academic_class):
    query = (request.GET.get("q") or request.POST.get("q") or "").strip()
    students_qs = (
        Student.objects.select_related("user", "inscription__candidature")
        .filter(
            inscription__candidature__branch=branch,
            is_active=True,
            user__academic_enrollments__academic_class=academic_class,
            user__academic_enrollments__branch=branch,
            user__academic_enrollments__is_active=True,
        )
        .distinct()
        .order_by("inscription__candidature__last_name", "inscription__candidature__first_name", "matricule")
    )
    if query:
        students_qs = students_qs.filter(
            Q(inscription__candidature__last_name__icontains=query)
            | Q(inscription__candidature__first_name__icontains=query)
            | Q(matricule__icontains=query)
        )
    today = timezone.localdate()
    attendance_today = StudentAttendance.objects.filter(
        branch=branch,
        academic_class=academic_class,
        date=today,
    )
    return {
        "students_list": list(students_qs[:200]),
        "student_query": query,
        "students_total_count": academic_class.enrollments.filter(is_active=True).count(),
        "students_present_today": attendance_today.filter(status=StudentAttendance.STATUS_PRESENT).count(),
        "students_absent_today": attendance_today.filter(status=StudentAttendance.STATUS_ABSENT).count(),
        "students_late_today": attendance_today.filter(status=StudentAttendance.STATUS_LATE).count(),
    }


def build_class_detail_context(request, *, branch, class_id: int, week_start):
    from django.db.models import Count

    User = get_user_model()

    academic_class = (
        AcademicClass.objects.select_related("programme", "academic_year", "branch")
        .annotate(student_count=Count("enrollments"))
        .filter(branch=branch, is_active=True)
        .get(pk=class_id)
    )

    schedule = get_class_week_schedule(academic_class, week_start)
    prev_week_start = schedule["week_start"] - timedelta(days=7)
    next_week_start = schedule["week_start"] + timedelta(days=7)

    students = list(
        Student.objects.select_related("user", "inscription__candidature")
        .filter(
            inscription__candidature__branch=branch,
            is_active=True,
            user__academic_enrollments__academic_class=academic_class,
            user__academic_enrollments__is_active=True,
        )
        .distinct()
        .order_by("inscription__candidature__last_name", "inscription__candidature__first_name", "matricule")[:200]
    )

    ecs = list(
        EC.objects.select_related("ue", "ue__semester")
        .filter(ue__semester__academic_class=academic_class)
        .order_by("ue__semester__number", "ue__code", "title")[:250]
    )

    teacher_q = (request.GET.get("teacher_q") or "").strip()
    teachers_qs = User.objects.filter(
        is_active=True,
        profile__branch=branch,
        profile__position="teacher",
    )
    if teacher_q:
        teachers_qs = teachers_qs.filter(
            Q(first_name__icontains=teacher_q)
            | Q(last_name__icontains=teacher_q)
            | Q(username__icontains=teacher_q)
        )
    teachers = list(teachers_qs.order_by("first_name", "last_name", "username")[:80])

    week_events = (
        AcademicScheduleEvent.objects.select_related("teacher", "ec", "academic_class")
        .filter(
            academic_class=academic_class,
            branch=branch,
            start_datetime__date__gte=schedule["week_start"],
            start_datetime__date__lt=schedule["week_start"] + timedelta(days=7),
            is_active=True,
        )
        .exclude(status=AcademicScheduleEvent.STATUS_CANCELLED)
        .order_by("start_datetime", "id")
    )
    subject_event_map = {}
    for event in week_events:
        subject_event_map.setdefault(
            event.ec_id,
            {
                "teacher_name": event.teacher.get_full_name() or event.teacher.username,
                "room": event.location or "Salle non precisee",
                "event_count": 0,
            },
        )
        subject_event_map[event.ec_id]["event_count"] += 1

    subject_rows = [
        {
            "title": ec.title,
            "ue_code": ec.ue.code,
            "teacher_name": subject_event_map.get(ec.id, {}).get("teacher_name", "Non assigne"),
            "room": subject_event_map.get(ec.id, {}).get("room", "A definir"),
            "event_count": subject_event_map.get(ec.id, {}).get("event_count", 0),
        }
        for ec in ecs
    ]

    prefill_teacher_raw = (request.GET.get("teacher_id") or request.POST.get("teacher_id") or "").strip()
    prefill_ec_raw = (request.GET.get("ec_id") or request.POST.get("ec_id") or "").strip()
    prefill_room = (request.GET.get("room_label") or request.POST.get("room_label") or "").strip()
    prefill_location = (request.GET.get("location") or request.POST.get("location") or "").strip()
    prefill_planned_hours = (request.GET.get("planned_hours") or request.POST.get("planned_hours") or "").strip()
    prefill_date = (request.GET.get("date") or request.POST.get("date") or "").strip()
    prefill_start_time = (request.GET.get("start_time") or request.POST.get("start_time") or "").strip()
    prefill_end_time = (request.GET.get("end_time") or request.POST.get("end_time") or "").strip()

    return {
        "branch": branch,
        "academic_class": academic_class,
        "students": students,
        "schedule": schedule,
        "prev_week_start": prev_week_start,
        "next_week_start": next_week_start,
        "ecs": ecs,
        "teachers": teachers,
        "subject_rows": subject_rows,
        "student_count": len(students),
        "scheduled_courses_count": week_events.count(),
        "prefill_teacher_id": int(prefill_teacher_raw) if prefill_teacher_raw.isdigit() else None,
        "prefill_ec_id": int(prefill_ec_raw) if prefill_ec_raw.isdigit() else None,
        "prefill_room_label": prefill_room,
        "prefill_location": prefill_location or prefill_room,
        "prefill_planned_hours": prefill_planned_hours,
        "prefill_date": prefill_date,
        "prefill_start_time": prefill_start_time,
        "prefill_end_time": prefill_end_time,
        "timetable_view": build_timetable_view_payload(
            branch=branch,
            academic_class=academic_class,
            week_start=schedule["week_start"],
        ),
    }
