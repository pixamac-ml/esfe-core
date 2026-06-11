from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.urls import reverse
from django.utils import timezone

from academics.models import AcademicClass, AcademicEnrollment, AcademicScheduleEvent, LessonLog, WeeklyScheduleSlot
from academics.services.schedule_service import get_class_week_schedule_with_weekly_slots
from accounts.access import get_user_position
from accounts.models import BranchExpense, Profile
from payments.models import Payment
from portal.models import SupportAuditLog, SupportTicket
from students.models import Student
from students.models import AttendanceAlert, AttendanceRollSheet, StudentAttendance, StudentCase, StudentYearDecision, TeacherAttendance

from .selectors import (
    get_active_branches,
    get_branch_finance,
    get_dg_base_querysets,
    get_latest_payments_for_branch,
    get_recent_candidatures_count,
    get_top_classes_for_branch,
    get_top_programmes_for_branch,
)


@dataclass(frozen=True)
class DgAlert:
    key: str
    severity: str
    type: str
    branch_name: str
    description: str
    owner: str
    status: str
    age: str
    tone: str
    drawer_url: str
    action_name: str
    action_id: int | None


def _percent(part, total):
    if not total:
        return 0
    return round((part / total) * 100)


def _money(value):
    return int(value or 0)


def _parse_period_scope(request):
    period = (request.GET.get("period") or "month").strip().lower()
    allowed = {
        "today": ("Aujourdhui", 1),
        "week": ("7 jours", 7),
        "month": ("30 jours", 30),
        "quarter": ("90 jours", 90),
        "year": ("12 mois", 365),
    }
    label, days = allowed.get(period, allowed["month"])
    if period not in allowed:
        period = "month"
    start = timezone.localdate() - timedelta(days=max(days - 1, 0))
    return period, label, days, start


def _resolve_branch_scope(request, branches):
    raw_branch_id = (request.GET.get("branch_id") or "").strip()
    if not raw_branch_id.isdigit():
        return branches, None, ""
    branch_id = int(raw_branch_id)
    selected_branch = next((branch for branch in branches if branch.id == branch_id), None)
    if selected_branch is None:
        return branches, None, ""
    return [selected_branch], selected_branch, str(branch_id)


def _age_label(value):
    if not value:
        return "-"
    delta = timezone.now() - value
    if delta.days >= 1:
        return f"{delta.days}j"
    hours = int(delta.total_seconds() // 3600)
    if hours >= 1:
        return f"{hours}h"
    minutes = max(int(delta.total_seconds() // 60), 1)
    return f"{minutes}min"


def _performance_label(student_count, class_count, alert_count, balance):
    ratio = int(student_count / class_count) if class_count else 0
    if alert_count >= 5 or balance < 0 or ratio > 55:
        return "Attention", "orange"
    if alert_count >= 2 or ratio > 42:
        return "Correct", "blue"
    if student_count == 0:
        return "A surveiller", "gray"
    return "Excellent", "green"


def _build_alerts(branches, base):
    alerts = []
    open_attendance = (
        base["attendance_alerts"]
        .select_related("branch", "student", "student__user")
        .order_by("-triggered_at")[:8]
    )
    for alert in open_attendance:
        student_name = getattr(alert.student, "full_name", "") or str(alert.student)
        alerts.append(
            DgAlert(
                key=f"attendance-{alert.id}",
                severity="Critique" if alert.count >= 5 else "Elevee",
                type="Assiduite",
                branch_name=alert.branch.name,
                description=f"{alert.get_alert_type_display()} - {student_name}",
                owner="Surveillance",
                status="Nouveau",
                age=_age_label(alert.triggered_at),
                tone="red" if alert.count >= 5 else "orange",
                drawer_url=reverse("accounts_portal:dg_drawer") + f"?kind=alert&id={alert.id}",
                action_name="resolve_alert",
                action_id=alert.id,
            )
        )

    if len(alerts) < 8:
        cases = (
            base["student_cases"]
            .exclude(status__in={StudentCase.STATUS_RESOLU, StudentCase.STATUS_ESCALADE})
            .select_related("branch", "student", "student__user")
            .order_by("-created_at")[: 8 - len(alerts)]
        )
        for case in cases:
            alerts.append(
                DgAlert(
                    key=f"case-{case.id}",
                    severity="Critique" if case.priority == StudentCase.PRIORITY_CRITIQUE else "Elevee",
                    type="Suivi etudiant",
                    branch_name=case.branch.name,
                    description=case.title,
                    owner="Surveillance",
                    status=case.get_status_display(),
                    age=_age_label(case.created_at),
                    tone="red" if case.priority == StudentCase.PRIORITY_CRITIQUE else "orange",
                    drawer_url=reverse("accounts_portal:dg_drawer") + f"?kind=case&id={case.id}",
                    action_name="escalate_case",
                    action_id=case.id,
                )
            )

    for branch in branches:
        if len(alerts) >= 10:
            break
        pending_payments = base["pending_payments"].filter(inscription__candidature__branch=branch).count()
        if pending_payments >= 10:
            alerts.append(
                DgAlert(
                    key=f"finance-{branch.id}",
                    severity="Elevee",
                    type="Finance",
                    branch_name=branch.name,
                    description=f"{pending_payments} paiements en attente",
                    owner="Comptable",
                    status="Nouveau",
                    age="-",
                    tone="orange",
                    drawer_url=reverse("accounts_portal:dg_drawer") + f"?kind=finance&branch_id={branch.id}",
                    action_name="followup_finance",
                    action_id=branch.id,
                )
            )
    return alerts


def _build_workflow(base):
    total = base["year_decisions"].count()
    steps = [
        {
            "key": "academic",
            "number": 1,
            "label": "Decision academique",
            "count": base["year_decisions"].filter(workflow_status=StudentYearDecision.WORKFLOW_DRAFT).count(),
            "tone": "emerald",
        },
        {
            "key": "finance",
            "number": 2,
            "label": "Validation finance",
            "count": base["year_decisions"].filter(workflow_status=StudentYearDecision.WORKFLOW_ACADEMIC_VALIDATED).count(),
            "tone": "blue",
        },
        {
            "key": "apply",
            "number": 3,
            "label": "Application passage",
            "count": base["year_decisions"].filter(workflow_status=StudentYearDecision.WORKFLOW_FINANCE_VALIDATED).count(),
            "tone": "orange",
        },
        {
            "key": "done",
            "number": 4,
            "label": "Reinscription confirmee",
            "count": base["year_decisions"].filter(workflow_status=StudentYearDecision.WORKFLOW_APPLIED).count(),
            "tone": "violet",
        },
    ]
    for step in steps:
        step["percent"] = _percent(step["count"], total)
        step["drawer_url"] = reverse("accounts_portal:dg_drawer") + f"?kind=workflow&step={step['key']}"

    blocked = list(
        base["year_decisions"]
        .exclude(workflow_status=StudentYearDecision.WORKFLOW_APPLIED)
        .select_related("student", "student__user", "source_enrollment__branch", "source_class")
        .order_by("created_at")[:6]
    )
    return {
        "total": total,
        "steps": steps,
        "blocked_count": base["year_decisions"].exclude(
            workflow_status__in={StudentYearDecision.WORKFLOW_APPLIED, StudentYearDecision.WORKFLOW_REJECTED}
        ).count(),
        "blocked_rows": blocked,
    }


def _build_branch_summaries(branches, base):
    summaries = []
    for branch in branches:
        revenue, expenses, balance = get_branch_finance(branch)
        student_count = base["students"].filter(inscription__candidature__branch=branch).count()
        class_count = base["classes"].filter(branch=branch).count()
        open_alert_count = base["attendance_alerts"].filter(branch=branch).count()
        label, tone = _performance_label(student_count, class_count, open_alert_count, balance)
        summaries.append(
            {
                "branch": branch,
                "manager_name": (
                    branch.manager.get_full_name() or branch.manager.username
                    if branch.manager
                    else "Non assigne"
                ),
                "student_count": student_count,
                "class_count": class_count,
                "active_inscription_count": base["inscriptions"].filter(candidature__branch=branch).count(),
                "candidature_count": base["candidatures"].filter(branch=branch).count(),
                "accepted_candidature_count": base["candidatures"].filter(
                    branch=branch,
                    status__in={"accepted", "accepted_with_reserve"},
                ).count(),
                "revenue_total": revenue,
                "expense_total": expenses,
                "balance_total": balance,
                "pending_expense_count": base["expenses"].filter(
                    branch=branch,
                    status__in={BranchExpense.STATUS_SUBMITTED, BranchExpense.STATUS_APPROVED},
                ).count(),
                "open_alert_count": open_alert_count,
                "top_classes": get_top_classes_for_branch(branch),
                "top_programmes": get_top_programmes_for_branch(branch),
                "latest_payments": get_latest_payments_for_branch(branch),
                "performance_label": label,
                "performance_tone": tone,
                "drawer_url": reverse("accounts_portal:dg_drawer") + f"?kind=branch&branch_id={branch.id}",
            }
        )
    return summaries


def _build_finance(base, branch_summaries):
    revenue = _money(base["payments"].aggregate(total=Sum("amount"))["total"])
    expenses = _money(base["expenses"].filter(
        status__in={
            BranchExpense.STATUS_SUBMITTED,
            BranchExpense.STATUS_APPROVED,
            BranchExpense.STATUS_PAID,
        }
    ).aggregate(total=Sum("amount"))["total"])
    closures = list(
        base["monthly_closures"]
        .order_by("-period_month", "branch__name")[:12]
    )
    return {
        "revenue": revenue,
        "expenses": expenses,
        "balance": revenue - expenses,
        "balance_chart": abs(revenue - expenses),
        "validated_payments": base["payments"].count(),
        "pending_payments": base["pending_payments"].count(),
        "cancelled_payments": Payment.objects.filter(
            status=Payment.STATUS_CANCELLED,
            inscription__candidature__branch_id__in=base["branch_filter"]["id__in"],
        ).count(),
        "latest_payments": list(
            base["payments"]
            .select_related("inscription__candidature", "inscription__candidature__branch")
            .order_by("-paid_at")[:8]
        ),
        "top_revenue_branches": sorted(branch_summaries, key=lambda item: item["revenue_total"], reverse=True)[:5],
        "closures": closures,
    }


def _last_12_month_keys():
    today = timezone.localdate().replace(day=1)
    months = []
    for offset in range(11, -1, -1):
        year = today.year
        month = today.month - offset
        while month <= 0:
            month += 12
            year -= 1
        months.append(timezone.datetime(year, month, 1).date())
    return months


def _monthly_count(qs, date_field):
    rows = (
        qs.annotate(month=TruncMonth(date_field))
        .values("month")
        .annotate(total=Count("id"))
    )
    return {row["month"].date().replace(day=1): row["total"] for row in rows if row["month"]}


def _monthly_sum(qs, date_field, value_field):
    rows = (
        qs.annotate(month=TruncMonth(date_field))
        .values("month")
        .annotate(total=Sum(value_field))
    )
    return {row["month"].date().replace(day=1): _money(row["total"]) for row in rows if row["month"]}


def _week_scope(request=None):
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    if request is not None:
        raw_week_start = (request.GET.get("week_start") or "").strip()
        if raw_week_start:
            try:
                parsed = datetime.strptime(raw_week_start, "%Y-%m-%d").date()
                week_start = parsed - timedelta(days=parsed.weekday())
            except ValueError:
                pass
    week_end = week_start + timedelta(days=7)
    week_start_dt = timezone.make_aware(datetime.combine(week_start, time.min))
    week_end_dt = timezone.make_aware(datetime.combine(week_end, time.min))
    today_start_dt = timezone.make_aware(datetime.combine(today, time.min))
    today_end_dt = today_start_dt + timedelta(days=1)
    return today, week_start, week_end, week_start_dt, week_end_dt, today_start_dt, today_end_dt


def _event_row(event):
    start = timezone.localtime(event.start_datetime)
    end = timezone.localtime(event.end_datetime)
    teacher_name = event.teacher.get_full_name() or event.teacher.username if event.teacher_id else "Non assigne"
    return {
        "id": event.id,
        "title": event.ec.title if event.ec_id else event.title,
        "class_name": event.academic_class.display_name,
        "branch_name": event.branch.name,
        "teacher_name": teacher_name,
        "location": event.location or ("En ligne" if event.is_online else "Salle non precisee"),
        "date": start.date(),
        "start": start,
        "end": end,
        "time_range": f"{start:%H:%M} - {end:%H:%M}",
        "status": event.status,
        "status_label": event.get_status_display(),
        "has_lesson_log": bool(getattr(event, "lesson_log_count", 0)),
        "weekday_index": start.date().weekday(),
        "slot_label": start.strftime("%H:%M"),
    }


def _build_calendar_grid(events, week_start):
    days = []
    labels = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam"]
    today = timezone.localdate()
    for offset, label in enumerate(labels):
        day = week_start + timedelta(days=offset)
        days.append({"label": label, "date": day, "is_today": day == today})

    event_rows = [_event_row(event) for event in events if timezone.localtime(event.start_datetime).date().weekday() < 6]
    standard_slots = ["08:00", "10:00", "14:00", "16:00"]
    all_slots = sorted({event["slot_label"] for event in event_rows})
    slot_labels = standard_slots + [slot for slot in all_slots if slot not in standard_slots]
    slots = []
    for slot_label in slot_labels:
        cells = []
        for offset, day in enumerate(days):
            cell_events = [
                event
                for event in event_rows
                if event["weekday_index"] == offset and event["slot_label"] == slot_label
            ]
            cells.append({"day_date": day["date"], "events": cell_events})
        slots.append({"label": slot_label, "cells": cells})
    return {"days": days, "slots": slots, "week_start": week_start}


def _build_schedule(request, branches, base):
    branch_ids = base["branch_filter"]["id__in"]
    today, week_start, week_end, week_start_dt, week_end_dt, today_start_dt, today_end_dt = _week_scope(request)
    now = timezone.now()
    selected_class_id = (request.GET.get("class_id") or "").strip()
    class_options = list(
        AcademicClass.objects.filter(
            is_active=True,
            is_archived=False,
            branch_id__in=branch_ids,
        )
        .select_related("branch", "programme", "academic_year")
        .annotate(student_count=Count("enrollments", filter=Q(enrollments__is_active=True)))
        .order_by("branch__name", "level", "programme__title", "id")
    )
    selected_class = None
    if selected_class_id.isdigit():
        selected_class = next((item for item in class_options if item.id == int(selected_class_id)), None)
    if selected_class is None and len(branch_ids) == 1 and class_options:
        selected_class = class_options[0]

    weekly_events_qs = (
        AcademicScheduleEvent.objects.filter(
            branch_id__in=branch_ids,
            is_active=True,
            start_datetime__gte=week_start_dt,
            start_datetime__lt=week_end_dt,
        )
        .select_related("academic_class", "branch", "teacher", "ec", "academic_year")
        .annotate(lesson_log_count=Count("lesson_logs"))
        .order_by("start_datetime", "id")
    )
    if selected_class is not None:
        weekly_events_qs = weekly_events_qs.filter(academic_class=selected_class)
    today_events_qs = weekly_events_qs.filter(start_datetime__gte=today_start_dt, start_datetime__lt=today_end_dt)
    past_course_events = weekly_events_qs.filter(
        event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
        start_datetime__lt=now,
    ).exclude(status=AcademicScheduleEvent.STATUS_CANCELLED)
    missing_lesson_logs_qs = past_course_events.filter(lesson_logs__isnull=True)
    lesson_logs_qs = LessonLog.objects.filter(
        branch_id__in=branch_ids,
        date__gte=week_start,
        date__lt=week_end,
    )
    teacher_attendance_qs = TeacherAttendance.objects.filter(
        branch_id__in=branch_ids,
        date__gte=week_start,
        date__lt=week_end,
    )
    student_attendance_qs = StudentAttendance.objects.filter(
        branch_id__in=branch_ids,
        date__gte=week_start,
        date__lt=week_end,
    )
    roll_sheets_qs = AttendanceRollSheet.objects.filter(
        branch_id__in=branch_ids,
        date__gte=week_start,
        date__lt=week_end,
    )
    weekly_events = list(weekly_events_qs)
    class_schedule = None
    if selected_class is not None:
        class_schedule = get_class_week_schedule_with_weekly_slots(selected_class, week_start)
        weekly_events = class_schedule.get("events") or []
    total_events = len(weekly_events)
    completed_events = sum(1 for event in weekly_events if (event.get("status") if isinstance(event, dict) else event.status) == AcademicScheduleEvent.STATUS_COMPLETED)
    cancelled_events = sum(1 for event in weekly_events if (event.get("status") if isinstance(event, dict) else event.status) == AcademicScheduleEvent.STATUS_CANCELLED)
    postponed_events = sum(1 for event in weekly_events if (event.get("status") if isinstance(event, dict) else event.status) == AcademicScheduleEvent.STATUS_POSTPONED)
    ongoing_events = sum(1 for event in weekly_events if (event.get("status") if isinstance(event, dict) else event.status) == AcademicScheduleEvent.STATUS_ONGOING)
    planned_events = sum(1 for event in weekly_events if (event.get("status") if isinstance(event, dict) else event.status) == AcademicScheduleEvent.STATUS_PLANNED)
    past_course_count = past_course_events.count()
    lesson_done_count = lesson_logs_qs.filter(status=LessonLog.STATUS_DONE).count()
    missing_lesson_logs_count = missing_lesson_logs_qs.count()
    event_status_rows = [
        {"label": "Planifies", "count": planned_events, "tone": "blue"},
        {"label": "En cours", "count": ongoing_events, "tone": "emerald"},
        {"label": "Termines", "count": completed_events, "tone": "slate"},
        {"label": "Reportes", "count": postponed_events, "tone": "amber"},
        {"label": "Annules", "count": cancelled_events, "tone": "rose"},
    ]
    weekday_labels = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
    weekday_rows = []
    today_events_count = 0
    for offset, label in enumerate(weekday_labels):
        day = week_start + timedelta(days=offset)
        count = sum(
            1
            for event in weekly_events
            if (event.get("start_datetime") if isinstance(event, dict) else timezone.localtime(event.start_datetime)).date() == day
        )
        if day == today:
            today_events_count = count
        weekday_rows.append({"label": label, "date": day, "count": count, "percent": _percent(count, total_events)})
    teacher_load = {}
    for event in weekly_events:
        if isinstance(event, dict):
            teacher_name = event.get("teacher_name") or "Non assigne"
            duration_minutes = event.get("duration_minutes") or 0
        else:
            teacher_name = event.teacher.get_full_name() or event.teacher.username if event.teacher_id else "Non assigne"
            duration_minutes = event.duration_minutes
        item = teacher_load.setdefault(teacher_name, {"teacher_name": teacher_name, "count": 0, "minutes": 0})
        item["count"] += 1
        item["minutes"] += duration_minutes
    teacher_load_rows = sorted(teacher_load.values(), key=lambda item: (item["minutes"], item["count"]), reverse=True)[:6]
    for item in teacher_load_rows:
        item["hours"] = round(item["minutes"] / 60, 1)

    branch_rows = []
    for branch in branches:
        branch_events = [
            event
            for event in weekly_events
            if (event.get("branch_name") if isinstance(event, dict) else event.branch_id) == (branch.name if isinstance(event, dict) else branch.id)
        ]
        branch_past_count = past_course_events.filter(branch=branch).count()
        branch_missing_count = missing_lesson_logs_qs.filter(branch=branch).count()
        branch_teacher_absent = teacher_attendance_qs.filter(branch=branch, status=TeacherAttendance.STATUS_ABSENT).count()
        branch_cancelled = sum(1 for event in branch_events if event.status == AcademicScheduleEvent.STATUS_CANCELLED)
        risk_score = branch_missing_count * 8 + branch_teacher_absent * 10 + branch_cancelled * 5
        branch_rows.append(
            {
                "branch": branch,
                "events": len(branch_events),
                "today_events": sum(
                    1
                    for event in branch_events
                    if (event.get("start_datetime") if isinstance(event, dict) else timezone.localtime(event.start_datetime)).date() == today
                ),
                "missing_lesson_logs": branch_missing_count,
                "coverage_rate": _percent(max(branch_past_count - branch_missing_count, 0), branch_past_count),
                "teacher_absences": branch_teacher_absent,
                "cancelled": branch_cancelled,
                "risk_score": risk_score,
            }
        )
    branch_rows = sorted(branch_rows, key=lambda item: (item["risk_score"], item["events"]), reverse=True)
    upcoming_events = list(
        AcademicScheduleEvent.objects.filter(
            branch_id__in=branch_ids,
            is_active=True,
            start_datetime__gte=now,
        )
        .exclude(status=AcademicScheduleEvent.STATUS_CANCELLED)
        .select_related("academic_class", "branch", "teacher", "ec", "academic_year")
        .annotate(lesson_log_count=Count("lesson_logs"))
        .order_by("start_datetime", "id")[:8]
    )
    weekly_slot_count = WeeklyScheduleSlot.objects.filter(branch_id__in=branch_ids, is_active=True).count()
    return {
        "today": today,
        "week_start": week_start,
        "week_end": week_end - timedelta(days=1),
        "prev_week_start": week_start - timedelta(days=7),
        "next_week_start": week_start + timedelta(days=7),
        "calendar": class_schedule or _build_calendar_grid(weekly_events, week_start),
        "class_options": class_options,
        "selected_class": selected_class,
        "selected_class_id": str(selected_class.id) if selected_class else "",
        "requires_class_selection": selected_class is None,
        "total_events": total_events,
        "today_events_count": today_events_count if selected_class is not None else today_events_qs.count(),
        "planned_events": planned_events,
        "ongoing_events": ongoing_events,
        "completed_events": completed_events,
        "cancelled_events": cancelled_events,
        "postponed_events": postponed_events,
        "weekly_slot_count": weekly_slot_count,
        "lesson_logs_count": lesson_logs_qs.count(),
        "lesson_done_count": lesson_done_count,
        "missing_lesson_logs_count": missing_lesson_logs_count,
        "lesson_log_coverage_rate": _percent(max(past_course_count - missing_lesson_logs_count, 0), past_course_count),
        "teacher_absences": teacher_attendance_qs.filter(status=TeacherAttendance.STATUS_ABSENT).count(),
        "teacher_lates": teacher_attendance_qs.filter(status=TeacherAttendance.STATUS_LATE).count(),
        "student_absences": student_attendance_qs.filter(status=StudentAttendance.STATUS_ABSENT).count(),
        "student_lates": student_attendance_qs.filter(status=StudentAttendance.STATUS_LATE).count(),
        "roll_sheets_total": roll_sheets_qs.count(),
        "roll_sheets_validated": roll_sheets_qs.filter(status=AttendanceRollSheet.STATUS_VALIDATED).count(),
        "roll_validation_rate": _percent(roll_sheets_qs.filter(status=AttendanceRollSheet.STATUS_VALIDATED).count(), roll_sheets_qs.count()),
        "event_status_rows": event_status_rows,
        "weekday_rows": weekday_rows,
        "branch_rows": branch_rows[:8],
        "teacher_load_rows": teacher_load_rows,
        "today_events": [_event_row(event) for event in today_events_qs[:8]],
        "upcoming_events": [_event_row(event) for event in upcoming_events],
        "missing_lesson_rows": [_event_row(event) for event in missing_lesson_logs_qs.select_related("academic_class", "branch", "teacher", "ec")[:8]],
    }


def _build_analytics(base, branch_summaries):
    total_classes = base["classes"].count()
    total_enrollments = base["enrollments"].count()
    avg_fill = int(total_enrollments / total_classes) if total_classes else 0
    sensitive = sorted(branch_summaries, key=lambda item: item["open_alert_count"], reverse=True)[:4]
    months = _last_12_month_keys()
    labels = [month.strftime("%b %Y") for month in months]
    candidature_counts = _monthly_count(base["candidatures"], "submitted_at")
    payment_revenue = _monthly_sum(base["payments"], "paid_at", "amount")
    payment_counts = _monthly_count(base["payments"], "paid_at")
    risk_values = [
        base["pending_payments"].count(),
        base["student_cases"].exclude(status__in={StudentCase.STATUS_RESOLU, StudentCase.STATUS_ESCALADE}).count(),
        base["attendance_alerts"].count(),
        base["year_decisions"].exclude(
            workflow_status__in={StudentYearDecision.WORKFLOW_APPLIED, StudentYearDecision.WORKFLOW_REJECTED}
        ).count(),
    ]
    total_candidatures = base["candidatures"].count()
    accepted_candidatures = base["candidatures"].filter(status__in={"accepted", "accepted_with_reserve"}).count()
    rejected_candidatures = base["candidatures"].filter(status="rejected").count()
    to_complete_candidatures = base["candidatures"].filter(status="to_complete").count()
    active_inscriptions = base["inscriptions"].count()
    validated_payments = base["payments"].count()
    pending_payments = base["pending_payments"].count()
    pending_payment_amount = _money(base["pending_payments"].aggregate(total=Sum("amount"))["total"])
    revenue_total = _money(base["payments"].aggregate(total=Sum("amount"))["total"])
    average_payment = int(revenue_total / validated_payments) if validated_payments else 0
    risk_labels = ["Finance", "Suivi etudiant", "Assiduite", "Workflow"]
    risk_tones = ["amber", "rose", "orange", "blue"]
    risk_total = sum(risk_values)
    risk_breakdown = [
        {
            "label": label,
            "value": value,
            "percent": _percent(value, risk_total),
            "tone": tone,
        }
        for label, value, tone in zip(risk_labels, risk_values, risk_tones)
    ]
    monthly_candidatures = [candidature_counts.get(month, 0) for month in months]
    monthly_revenue = [payment_revenue.get(month, 0) for month in months]
    monthly_payments = [payment_counts.get(month, 0) for month in months]
    monthly_table = [
        {
            "label": labels[index],
            "candidatures": monthly_candidatures[index],
            "payments": monthly_payments[index],
            "revenue": monthly_revenue[index],
        }
        for index in range(max(len(months) - 6, 0), len(months))
    ]
    candidature_status_rows = [
        {
            "label": "Acceptees",
            "count": accepted_candidatures,
            "percent": _percent(accepted_candidatures, total_candidatures),
            "tone": "emerald",
        },
        {
            "label": "A completer",
            "count": to_complete_candidatures,
            "percent": _percent(to_complete_candidatures, total_candidatures),
            "tone": "amber",
        },
        {
            "label": "Refusees",
            "count": rejected_candidatures,
            "percent": _percent(rejected_candidatures, total_candidatures),
            "tone": "rose",
        },
    ]
    workflow_status_rows = [
        {
            "label": "Brouillon",
            "count": base["year_decisions"].filter(workflow_status=StudentYearDecision.WORKFLOW_DRAFT).count(),
            "tone": "slate",
        },
        {
            "label": "Pedagogie validee",
            "count": base["year_decisions"].filter(workflow_status=StudentYearDecision.WORKFLOW_ACADEMIC_VALIDATED).count(),
            "tone": "blue",
        },
        {
            "label": "Finance validee",
            "count": base["year_decisions"].filter(workflow_status=StudentYearDecision.WORKFLOW_FINANCE_VALIDATED).count(),
            "tone": "orange",
        },
        {
            "label": "Appliquees",
            "count": base["year_decisions"].filter(workflow_status=StudentYearDecision.WORKFLOW_APPLIED).count(),
            "tone": "emerald",
        },
        {
            "label": "Rejetees",
            "count": base["year_decisions"].filter(workflow_status=StudentYearDecision.WORKFLOW_REJECTED).count(),
            "tone": "rose",
        },
    ]
    top_programmes = list(
        base["candidatures"]
        .values("programme__title")
        .annotate(total=Count("id"))
        .order_by("-total", "programme__title")[:5]
    )
    overloaded_classes = list(
        base["classes"]
        .select_related("branch", "programme")
        .annotate(active_students=Count("enrollments", filter=Q(enrollments__is_active=True)))
        .filter(active_students__gt=0)
        .order_by("-active_students", "branch__name", "level")[:6]
    )
    for item in branch_summaries:
        item["analytics_pending_payment_count"] = base["pending_payments"].filter(
            inscription__candidature__branch=item["branch"]
        ).count()
        item["analytics_risk_score"] = (
            item["open_alert_count"] * 10
            + item["analytics_pending_payment_count"] * 3
            + item["pending_expense_count"] * 2
            + (12 if item["balance_total"] < 0 else 0)
        )
    branch_health_rows = sorted(
        branch_summaries,
        key=lambda item: (item["analytics_risk_score"], item["student_count"]),
        reverse=True,
    )[:6]
    return {
        "class_fill_rate": min(avg_fill * 2, 100),
        "average_students_per_class": avg_fill,
        "total_enrollments": total_enrollments,
        "classes_total": total_classes,
        "classes_normal": max(total_classes - sum(1 for item in branch_summaries if item["open_alert_count"] > 0), 0),
        "classes_attention": sum(1 for item in branch_summaries if item["open_alert_count"] > 0),
        "classes_overloaded": sum(1 for item in branch_summaries if item["student_count"] and item["class_count"] and item["student_count"] / item["class_count"] > 55),
        "classes_empty": base["classes"].annotate(active_count=Count("enrollments")).filter(active_count=0).count(),
        "sensitive_branches": sensitive,
        "branch_health_rows": branch_health_rows,
        "overloaded_classes": overloaded_classes,
        "total_candidatures": total_candidatures,
        "accepted_candidatures": accepted_candidatures,
        "rejected_candidatures": rejected_candidatures,
        "to_complete_candidatures": to_complete_candidatures,
        "admission_conversion_rate": _percent(accepted_candidatures, total_candidatures),
        "inscription_conversion_rate": _percent(active_inscriptions, accepted_candidatures),
        "payment_conversion_rate": _percent(validated_payments, active_inscriptions),
        "active_inscriptions": active_inscriptions,
        "validated_payments": validated_payments,
        "pending_payments": pending_payments,
        "pending_payment_amount": pending_payment_amount,
        "average_payment": average_payment,
        "candidature_status_rows": candidature_status_rows,
        "workflow_status_rows": workflow_status_rows,
        "top_programmes": top_programmes,
        "risk_breakdown": risk_breakdown,
        "risk_total": risk_total,
        "monthly_table": monthly_table,
        "monthly_labels": labels,
        "monthly_labels_json": json.dumps(labels),
        "monthly_candidatures_json": json.dumps(monthly_candidatures),
        "monthly_revenue_json": json.dumps(monthly_revenue),
        "monthly_payments_json": json.dumps(monthly_payments),
        "risk_labels_json": json.dumps(risk_labels),
        "risk_values_json": json.dumps(risk_values),
    }


def _build_rh(base, branches):
    staff_by_position = list(
        Profile.objects.filter(user_type="staff")
        .values("position")
        .annotate(total=Count("id"))
        .order_by("-total")[:5]
    )
    return {
        "active_staff": base["staff"].count(),
        "branches_with_manager": sum(1 for branch in branches if branch.manager_id),
        "branches_without_manager": sum(1 for branch in branches if not branch.manager_id),
        "positions": staff_by_position,
        "recruitment_drawer_url": reverse("accounts_portal:dg_drawer") + "?kind=recruitment",
    }


def _build_executive_summary(base, branch_summaries, finance, analytics, schedule, workflow, rh):
    total_students = base["students"].count()
    total_classes = base["classes"].count()
    open_alerts = base["attendance_alerts"].count()
    total_candidatures = analytics["total_candidatures"]
    accepted_candidatures = analytics["accepted_candidatures"]
    pending_candidatures = base["candidatures"].filter(status__in={"submitted", "under_review", "to_complete"}).count()
    active_inscriptions = analytics["active_inscriptions"]
    pending_payments = analytics["pending_payments"]
    pending_payment_amount = analytics["pending_payment_amount"]
    validated_payments = analytics["validated_payments"]
    finance_balance = finance["balance"]
    total_events = schedule["total_events"]
    completed_events = schedule["completed_events"]
    missing_lesson_logs = schedule["missing_lesson_logs_count"]
    teacher_absences = schedule["teacher_absences"]
    student_absences = schedule["student_absences"]
    workflow_blocked = workflow["blocked_count"]
    branches_without_manager = rh["branches_without_manager"]
    operational_flags = [
        {"label": "Alertes", "value": open_alerts, "tone": "rose" if open_alerts else "emerald"},
        {"label": "Paiements attente", "value": pending_payments, "tone": "amber" if pending_payments else "emerald"},
        {"label": "Cahiers manquants", "value": missing_lesson_logs, "tone": "rose" if missing_lesson_logs else "emerald"},
        {"label": "Dossiers bloques", "value": workflow_blocked, "tone": "rose" if workflow_blocked else "emerald"},
        {"label": "Managers a affecter", "value": branches_without_manager, "tone": "amber" if branches_without_manager else "emerald"},
    ]
    executive_cards = [
        {
            "label": "Conversion admissions",
            "value": f"{_percent(accepted_candidatures, total_candidatures)}%",
            "detail": f"{accepted_candidatures} acceptees / {total_candidatures}",
            "tone": "blue",
            "icon": "fa-user-check",
        },
        {
            "label": "Inscriptions actives",
            "value": active_inscriptions,
            "detail": f"{pending_candidatures} candidatures a traiter",
            "tone": "emerald",
            "icon": "fa-id-card",
        },
        {
            "label": "Solde consolide",
            "value": finance_balance,
            "detail": f"{finance['revenue']} revenus / {finance['expenses']} depenses",
            "tone": "rose" if finance_balance < 0 else "slate",
            "icon": "fa-scale-balanced",
        },
        {
            "label": "Paiements en attente",
            "value": pending_payments,
            "detail": f"{pending_payment_amount} FCFA",
            "tone": "amber" if pending_payments else "emerald",
            "icon": "fa-clock",
        },
        {
            "label": "Cours semaine",
            "value": total_events,
            "detail": f"{completed_events} termines, {missing_lesson_logs} cahiers manquants",
            "tone": "cyan",
            "icon": "fa-calendar-days",
        },
        {
            "label": "Assiduite",
            "value": student_absences + teacher_absences,
            "detail": f"{student_absences} abs. etudiants / {teacher_absences} abs. profs",
            "tone": "orange" if student_absences or teacher_absences else "emerald",
            "icon": "fa-user-clock",
        },
        {
            "label": "Workflow passages",
            "value": workflow_blocked,
            "detail": f"{workflow['total']} decisions en base",
            "tone": "rose" if workflow_blocked else "emerald",
            "icon": "fa-arrows-rotate",
        },
        {
            "label": "Couverture RH",
            "value": rh["active_staff"],
            "detail": f"{branches_without_manager} annexes sans manager",
            "tone": "violet",
            "icon": "fa-user-group",
        },
    ]
    top_balance_branches = sorted(branch_summaries, key=lambda item: item["balance_total"])[:5]
    top_risk_branches = sorted(
        branch_summaries,
        key=lambda item: (
            item["open_alert_count"],
            item["pending_expense_count"],
            item.get("analytics_pending_payment_count", 0),
            -item["balance_total"],
        ),
        reverse=True,
    )[:5]
    action_center = [
        {
            "label": "Traiter les alertes",
            "detail": f"{open_alerts} alertes ouvertes",
            "section": "alerts",
            "drawer_url": reverse("accounts_portal:dg_drawer") + "?kind=alert",
            "icon": "fa-triangle-exclamation",
            "tone": "rose" if open_alerts else "emerald",
            "count": open_alerts,
        },
        {
            "label": "Relancer la finance",
            "detail": f"{pending_payment_amount} FCFA en attente",
            "section": "finance",
            "drawer_url": reverse("accounts_portal:dg_drawer") + "?kind=finance",
            "icon": "fa-money-bill-transfer",
            "tone": "amber" if pending_payments else "emerald",
            "count": pending_payments,
        },
        {
            "label": "Suivre les passages",
            "detail": f"{workflow_blocked} dossiers a arbitrer",
            "section": "workflows",
            "drawer_url": reverse("accounts_portal:dg_drawer") + "?kind=workflow&step=blocked",
            "icon": "fa-arrows-rotate",
            "tone": "rose" if workflow_blocked else "blue",
            "count": workflow_blocked,
        },
        {
            "label": "Verifier le planning",
            "detail": f"{missing_lesson_logs} cahiers manquants",
            "section": "schedule",
            "drawer_url": "",
            "icon": "fa-calendar-check",
            "tone": "amber" if missing_lesson_logs else "emerald",
            "count": missing_lesson_logs,
        },
        {
            "label": "Affecter les managers",
            "detail": f"{branches_without_manager} annexes sans manager",
            "section": "rh",
            "drawer_url": reverse("accounts_portal:dg_drawer") + "?kind=rh",
            "icon": "fa-building-user",
            "tone": "amber" if branches_without_manager else "emerald",
            "count": branches_without_manager,
        },
        {
            "label": "Analyser les annexes",
            "detail": f"{len(top_risk_branches)} annexes a surveiller",
            "section": "analytics",
            "drawer_url": reverse("accounts_portal:dg_drawer") + "?kind=analytics",
            "icon": "fa-chart-line",
            "tone": "blue",
            "count": len(top_risk_branches),
        },
    ]
    return {
        "total_students": total_students,
        "total_classes": total_classes,
        "validated_payments": validated_payments,
        "pending_candidatures": pending_candidatures,
        "operational_flags": operational_flags,
        "executive_cards": executive_cards,
        "top_balance_branches": top_balance_branches,
        "top_risk_branches": top_risk_branches,
        "action_center": action_center,
    }


def build_dg_dashboard_context(request, base_context_builder):
    period, period_label, period_days, period_start = _parse_period_scope(request)
    user_position = get_user_position(request.user)
    is_deputy = user_position == "deputy_executive_director"
    all_branches = list(get_active_branches())
    branches, selected_branch, selected_branch_id = _resolve_branch_scope(request, all_branches)
    branch_ids = [branch.id for branch in branches]
    base = get_dg_base_querysets(branch_ids)
    branch_summaries = _build_branch_summaries(branches, base)
    alerts = _build_alerts(branches, base)
    workflow = _build_workflow(base)
    finance = _build_finance(base, branch_summaries)
    analytics = _build_analytics(base, branch_summaries)
    schedule = _build_schedule(request, branches, base)
    rh = _build_rh(base, branches)
    executive_summary = _build_executive_summary(base, branch_summaries, finance, analytics, schedule, workflow, rh)

    context = base_context_builder(
        request,
        page_title="Dashboard Directeur General",
        module_cards=[
            "Pilotage multi-annexes",
            "Monitoring live",
            "Alertes et risques",
            "RH strategique",
        ],
    )
    context.update(
        {
            "dashboard_kind": "Direction generale",
            "executive_display_name": "Directrice Generale Adjointe" if is_deputy else "Directeur General",
            "executive_display_short": "DGA" if is_deputy else "DG",
            "executive_display_subtitle": "Direction generale adjointe" if is_deputy else "PDG / Fondateur",
            "generated_at": timezone.now(),
            "dashboard_period": period,
            "dashboard_period_label": period_label,
            "dashboard_period_days": period_days,
            "dashboard_period_start": period_start,
            "all_branches": all_branches,
            "selected_branch": selected_branch,
            "selected_branch_id": selected_branch_id,
            "dashboard_scope_label": selected_branch.name if selected_branch else "Toutes les annexes",
            "total_branches": len(branches),
            "total_students": base["students"].count(),
            "total_classes": base["classes"].count(),
            "total_active_inscriptions": base["inscriptions"].count(),
            "new_candidatures_30d": get_recent_candidatures_count(branch_ids, days=period_days),
            "open_alerts": len(alerts),
            "critical_alerts": sum(1 for alert in alerts if alert.tone == "red"),
            "total_staff": base["staff"].count(),
            "branch_summaries": branch_summaries,
            "priority_alerts": alerts,
            "workflow": workflow,
            "finance": finance,
            "analytics": analytics,
            "schedule": schedule,
            "rh": rh,
            "executive_summary": executive_summary,
            "realtime": {
                "today_inscriptions": base["candidatures"].filter(submitted_at__date__gte=period_start).count(),
                "today_payments": base["payments"].filter(paid_at__date__gte=period_start).count(),
                "today_courses": schedule["today_events_count"],
                "system_status": "operationnel",
            },
            "empty_list": [],
        }
    )
    return context


def build_dg_section_context(request, section, base_context_builder):
    context = build_dg_dashboard_context(request, base_context_builder)
    context["dg_section"] = section
    return context


def build_dg_drawer_context(request):
    kind = (request.GET.get("kind") or "overview").strip().lower()
    branch_id = (request.GET.get("branch_id") or "").strip()
    item_id = (request.GET.get("id") or "").strip()
    student_id = (request.GET.get("student_id") or item_id).strip()
    payment_id = (request.GET.get("payment_id") or item_id).strip()
    staff_id = (request.GET.get("staff_id") or item_id).strip()
    event_id = (request.GET.get("event_id") or item_id).strip()
    step = (request.GET.get("step") or "").strip()
    branch = None
    if branch_id.isdigit():
        branch = get_active_branches().filter(id=int(branch_id)).first()
    alert = None
    case = None
    student = None
    payment = None
    staff_profile = None
    schedule_event = None
    alert_rows = []
    case_rows = []
    if item_id.isdigit():
        if kind == "alert":
            alert = AttendanceAlert.objects.select_related("branch", "student", "student__user").filter(id=int(item_id)).first()
        elif kind == "case":
            case = StudentCase.objects.select_related("branch", "student", "student__user").filter(id=int(item_id)).first()
    if kind == "student" and student_id.isdigit():
        student = (
            Student.objects.select_related(
                "user",
                "inscription",
                "inscription__candidature",
                "inscription__candidature__branch",
                "inscription__candidature__programme",
                "current_academic_enrollment",
                "current_academic_enrollment__academic_class",
                "current_academic_enrollment__branch",
            )
            .filter(id=int(student_id))
            .first()
        )
    if kind == "payment" and payment_id.isdigit():
        payment = (
            Payment.objects.select_related(
                "agent",
                "agent__user",
                "inscription",
                "inscription__candidature",
                "inscription__candidature__branch",
                "inscription__candidature__programme",
            )
            .filter(id=int(payment_id))
            .first()
        )
    if kind == "staff" and staff_id.isdigit():
        staff_profile = Profile.objects.select_related("user", "branch").filter(id=int(staff_id)).first()
    if kind == "schedule" and event_id.isdigit():
        schedule_event = (
            AcademicScheduleEvent.objects.select_related("academic_class", "branch", "teacher", "ec", "academic_year")
            .filter(id=int(event_id))
            .first()
        )
    if kind == "alert" and alert is None:
        alert_qs = AttendanceAlert.objects.filter(is_resolved=False)
        if branch:
            alert_qs = alert_qs.filter(branch=branch)
        alert_rows = list(
            alert_qs
            .select_related("branch", "student", "student__user")
            .order_by("-triggered_at")[:12]
        )
    if kind == "case" and case is None:
        case_qs = StudentCase.objects.exclude(status__in={StudentCase.STATUS_RESOLU, StudentCase.STATUS_ESCALADE})
        if branch:
            case_qs = case_qs.filter(branch=branch)
        case_rows = list(
            case_qs
            .select_related("branch", "student", "student__user")
            .order_by("-created_at")[:12]
        )
    workflow_rows = []
    if kind == "workflow":
        workflow_rows = list(
            StudentYearDecision.objects.exclude(
                workflow_status__in={StudentYearDecision.WORKFLOW_APPLIED, StudentYearDecision.WORKFLOW_REJECTED}
            )
            .select_related("student", "student__user", "source_enrollment__branch", "source_class")
            .order_by("created_at")[:12]
        )
    drawer_branches = [branch] if branch else list(get_active_branches())
    drawer_branch_ids = [item.id for item in drawer_branches]
    drawer_base = get_dg_base_querysets(drawer_branch_ids) if drawer_branch_ids else get_dg_base_querysets([])
    drawer_branch_summaries = _build_branch_summaries(drawer_branches, drawer_base) if drawer_branch_ids else []
    drawer_finance = _build_finance(drawer_base, drawer_branch_summaries) if drawer_branch_ids else {}
    drawer_analytics = _build_analytics(drawer_base, drawer_branch_summaries) if drawer_branch_ids else {}
    drawer_rh = _build_rh(drawer_base, drawer_branches) if drawer_branch_ids else {}
    drawer_schedule = _build_schedule(request, drawer_branches, drawer_base) if drawer_branch_ids else {}
    student_rows = []
    payment_rows = []
    staff_rows = []
    audit_rows = []
    if kind in {"students", "student", "branch"} and drawer_branch_ids:
        student_rows = list(
            Student.objects.filter(
                is_active=True,
                inscription__candidature__branch_id__in=drawer_branch_ids,
            )
            .select_related(
                "user",
                "inscription",
                "inscription__candidature",
                "inscription__candidature__branch",
                "inscription__candidature__programme",
                "current_academic_enrollment",
                "current_academic_enrollment__academic_class",
            )
            .order_by("inscription__candidature__last_name", "inscription__candidature__first_name")[:20]
        )
    if kind in {"payments", "payment", "finance", "branch"} and drawer_branch_ids:
        payment_rows = list(
            Payment.objects.filter(inscription__candidature__branch_id__in=drawer_branch_ids)
            .select_related(
                "agent",
                "agent__user",
                "inscription",
                "inscription__candidature",
                "inscription__candidature__branch",
            )
            .order_by("-paid_at", "-id")[:20]
        )
    if kind in {"staff", "rh", "branch"} and drawer_branch_ids:
        staff_rows = list(
            Profile.objects.filter(user_type="staff")
            .filter(Q(branch_id__in=drawer_branch_ids) | Q(branch__isnull=True))
            .select_related("user", "branch")
            .order_by("branch__name", "position", "user__last_name")[:20]
        )
    if kind in {"audit", "branch"}:
        audit_qs = SupportAuditLog.objects.select_related("actor", "branch").order_by("-created_at")
        if drawer_branch_ids:
            audit_qs = audit_qs.filter(Q(branch_id__in=drawer_branch_ids) | Q(branch__isnull=True))
        audit_rows = list(audit_qs[:20])
    branch_finance = None
    branch_summary = None
    if branch:
        branch_summary = drawer_branch_summaries[0] if drawer_branch_summaries else None
        revenue, expenses, balance = get_branch_finance(branch)
        branch_finance = {"revenue": revenue, "expenses": expenses, "balance": balance}
    return {
        "drawer_kind": kind,
        "drawer_branch": branch,
        "drawer_alert": alert,
        "drawer_case": case,
        "drawer_student": student,
        "drawer_payment": payment,
        "drawer_staff_profile": staff_profile,
        "drawer_schedule_event": schedule_event,
        "drawer_alert_rows": alert_rows,
        "drawer_case_rows": case_rows,
        "drawer_student_rows": student_rows,
        "drawer_payment_rows": payment_rows,
        "drawer_staff_rows": staff_rows,
        "drawer_audit_rows": audit_rows,
        "drawer_item_id": item_id,
        "drawer_step": step,
        "drawer_workflow_rows": workflow_rows,
        "drawer_branch_finance": branch_finance,
        "drawer_branch_summary": branch_summary,
        "drawer_branch_summaries": drawer_branch_summaries,
        "drawer_finance": drawer_finance,
        "drawer_analytics": drawer_analytics,
        "drawer_rh": drawer_rh,
        "drawer_schedule": drawer_schedule,
        "generated_at": timezone.now(),
    }
