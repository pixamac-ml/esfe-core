import json
from datetime import date, time

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from academics.models import AcademicClass, AcademicScheduleEvent
from accounts.dashboards.helpers import get_user_branch
from branches.models import Branch
from students.models import Student
from students.services.attendance_service import (
    get_class_attendance_summary,
    get_student_attendance_history,
    mark_student_attendance,
    mark_teacher_attendance,
)

User = get_user_model()


def _parse_json_body(request):
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError(f"Corps JSON invalide: {exc.msg}") from exc


def _resolve_branch(request, payload):
    user_branch = get_user_branch(request.user)
    if user_branch is not None:
        return user_branch
    branch_id = payload.get("branch_id")
    if not branch_id:
        raise ValidationError("branch_id est obligatoire pour cet utilisateur.")
    return get_object_or_404(Branch, pk=branch_id)


def _parse_iso_date(raw_value, *, field_name="date"):
    try:
        return date.fromisoformat(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field_name} doit etre au format YYYY-MM-DD.") from exc


def _parse_time(raw_value, *, field_name="arrival_time"):
    if raw_value in (None, ""):
        return None
    try:
        return time.fromisoformat(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field_name} doit etre au format HH:MM[:SS].") from exc


def _serialize_attendance_record(record):
    return {
        "id": record.id,
        "status": record.status,
        "date": record.date.isoformat(),
        "arrival_time": record.arrival_time.strftime("%H:%M") if record.arrival_time else "",
        "justification": record.justification,
        "schedule_event_id": record.schedule_event_id,
    }


@login_required
@require_POST
def mark_student_attendance_view(request):
    try:
        payload = _parse_json_body(request)
        branch = _resolve_branch(request, payload)
        student = get_object_or_404(Student.objects.select_related("user", "inscription__candidature"), pk=payload.get("student_id"))
        schedule_event = get_object_or_404(
            AcademicScheduleEvent.objects.select_related("academic_class", "branch"),
            pk=payload.get("schedule_event_id"),
        )
        academic_class = get_object_or_404(AcademicClass.objects.select_related("branch"), pk=payload.get("academic_class_id"))
        result = mark_student_attendance(
            student=student,
            academic_class=academic_class,
            schedule_event=schedule_event,
            status=payload.get("status"),
            recorded_by=request.user,
            branch=branch,
            arrival_time=_parse_time(payload.get("arrival_time")),
            justification=payload.get("justification", ""),
        )
        attendance = result["attendance"]
        return JsonResponse(
            {
                "ok": True,
                "attendance": _serialize_attendance_record(attendance),
                "absence_alert_triggered": result["absence_alert"]["triggered"],
                "late_alert_triggered": result["late_alert"]["triggered"],
            },
            status=201,
        )
    except ValidationError as exc:
        return JsonResponse({"ok": False, "errors": exc.messages}, status=400)


@login_required
@require_POST
def mark_teacher_attendance_view(request):
    try:
        payload = _parse_json_body(request)
        branch = _resolve_branch(request, payload)
        teacher = get_object_or_404(User, pk=payload.get("teacher_id"))
        schedule_event = get_object_or_404(
            AcademicScheduleEvent.objects.select_related("branch", "teacher"),
            pk=payload.get("schedule_event_id"),
        )
        attendance = mark_teacher_attendance(
            teacher=teacher,
            schedule_event=schedule_event,
            status=payload.get("status"),
            recorded_by=request.user,
            branch=branch,
            arrival_time=_parse_time(payload.get("arrival_time")),
            justification=payload.get("justification", ""),
        )
        return JsonResponse(
            {
                "ok": True,
                "attendance": _serialize_attendance_record(attendance["attendance"]),
                "synced_lesson_log_ids": attendance["synced_lesson_log_ids"],
            },
            status=201,
        )
    except ValidationError as exc:
        return JsonResponse({"ok": False, "errors": exc.messages}, status=400)


@login_required
@require_GET
def class_attendance_summary_view(request, class_id):
    try:
        academic_class = get_object_or_404(AcademicClass.objects.select_related("branch"), pk=class_id)
        summary_date = _parse_iso_date(request.GET.get("date"))
        user_branch = get_user_branch(request.user)
        if user_branch and academic_class.branch_id != user_branch.id:
            return JsonResponse({"ok": False, "errors": ["Acces refuse a cette annexe."]}, status=403)
        return JsonResponse({"ok": True, "data": get_class_attendance_summary(academic_class, summary_date)})
    except ValidationError as exc:
        return JsonResponse({"ok": False, "errors": exc.messages}, status=400)


@login_required
@require_GET
def student_attendance_history_view(request, student_id):
    student = get_object_or_404(Student.objects.select_related("inscription__candidature__branch"), pk=student_id)
    user_branch = get_user_branch(request.user)
    student_branch = getattr(student.inscription.candidature, "branch", None)
    if user_branch and student_branch and user_branch.id != student_branch.id:
        return JsonResponse({"ok": False, "errors": ["Acces refuse a cette annexe."]}, status=403)
    return JsonResponse(
        {
            "ok": True,
            "student_id": student.id,
            "history": [
                {
                    **row,
                    "date": row["date"].isoformat(),
                }
                for row in get_student_attendance_history(student, branch=student_branch or user_branch)
            ],
        }
    )
