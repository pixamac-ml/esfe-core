import io
import json
import zipfile
from datetime import date, time

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET, require_POST

from academics.models import AcademicEnrollment, AcademicClass, AcademicScheduleEvent, EC, LessonLog, Semester
from academics.services.lesson_log_service import (
    create_lesson_log,
    get_class_lesson_logs,
    get_daily_lesson_status,
    get_teacher_lesson_logs,
    update_lesson_log,
)
from accounts.dashboards.helpers import get_user_branch
from branches.models import Branch
from academics.services.reporting import (
    build_annual_class_report,
    build_student_annual_report,
    build_student_semester_report,
)
from academics.services.workflow import get_semester_permissions
from academics.services.year import compute_year_result

try:
    from weasyprint import HTML
except Exception:  # pragma: no cover
    HTML = None


User = get_user_model()


def _ensure_pdf_backend():
    if HTML is None:
        return HttpResponse(
            "WeasyPrint n'est pas installe ou ses dependances systeme sont manquantes.",
            status=500,
            content_type="text/plain; charset=utf-8",
        )
    return None


def _build_semester_report_context(student_id, semester_id):
    semester = get_object_or_404(
        Semester.objects.select_related("academic_class"),
        id=semester_id,
    )
    permissions = get_semester_permissions(semester)
    if not permissions["can_generate_reports"]:
        raise PermissionDenied("Les releves ne sont disponibles qu'apres publication.")
    return build_student_semester_report(student_id, semester_id)


def _build_semester_report_filename(context):
    return f"releve-semestre-s{context['semester'].number}-{context['student_matricule']}.pdf"


def _render_semester_report_pdf(request, student_id, semester_id):
    backend_error = _ensure_pdf_backend()
    if backend_error is not None:
        return None, None, backend_error

    context = _build_semester_report_context(student_id, semester_id)
    html = render_to_string(
        "academics/reports/semester_report.html",
        context,
        request=request,
    )
    pdf_bytes = HTML(
        string=html,
        base_url=request.build_absolute_uri(),
    ).write_pdf()
    return pdf_bytes, context, None


def _normalize_selected_student_ids(raw_ids):
    normalized_ids = []
    for value in raw_ids:
        try:
            normalized_ids.append(int(value))
        except (TypeError, ValueError):
            continue
    # Preserve order while deduplicating.
    return list(dict.fromkeys(normalized_ids))


def _get_class_student_ids(semester):
    enrollments = (
        AcademicEnrollment.objects.select_related("student")
        .filter(
            academic_class=semester.academic_class,
            academic_year=semester.academic_class.academic_year,
            is_active=True,
        )
        .order_by(
            "student__student_profile__inscription__candidature__last_name",
            "student__student_profile__inscription__candidature__first_name",
        )
    )
    return [enrollment.student.student_profile.id for enrollment in enrollments]


def student_semester_report_view(request, student_id, semester_id):
    context = _build_semester_report_context(student_id, semester_id)
    return render(request, "academics/reports/semester_report.html", context)


def student_semester_pdf_view(request, student_id, semester_id):
    pdf_bytes, context, backend_error = _render_semester_report_pdf(request, student_id, semester_id)
    if backend_error is not None:
        return backend_error

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{_build_semester_report_filename(context)}"'
    return response


def export_selected_reports_view(request, semester_id):
    if request.method != "POST":
        return HttpResponse("Methode non autorisee.", status=405)

    semester = get_object_or_404(
        Semester.objects.select_related("academic_class"),
        id=semester_id,
    )
    selected_ids = _normalize_selected_student_ids(request.POST.getlist("selected_students"))
    if not selected_ids:
        return HttpResponse("Aucun etudiant selectionne.", status=400)

    backend_error = _ensure_pdf_backend()
    if backend_error is not None:
        return backend_error

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for student_id in selected_ids:
            pdf_bytes, context, backend_error = _render_semester_report_pdf(request, student_id, semester.id)
            if backend_error is not None:
                return backend_error
            archive.writestr(_build_semester_report_filename(context), pdf_bytes)

    response = HttpResponse(zip_buffer.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="releves-selection-s{semester.number}.zip"'
    return response


def export_class_reports_view(request, semester_id):
    semester = get_object_or_404(
        Semester.objects.select_related("academic_class"),
        id=semester_id,
    )
    backend_error = _ensure_pdf_backend()
    if backend_error is not None:
        return backend_error

    student_ids = _get_class_student_ids(semester)
    if not student_ids:
        return HttpResponse("Aucun etudiant disponible pour cette classe.", status=404)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for student_id in student_ids:
            pdf_bytes, context, backend_error = _render_semester_report_pdf(request, student_id, semester.id)
            if backend_error is not None:
                return backend_error
            archive.writestr(_build_semester_report_filename(context), pdf_bytes)

    response = HttpResponse(zip_buffer.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="releves-classe-s{semester.number}.zip"'
    return response


def class_reports_overview_view(request, semester_id):
    semester = get_object_or_404(
        Semester.objects.select_related("academic_class"),
        id=semester_id,
    )
    rows = []
    for student_id in _get_class_student_ids(semester):
        context = _build_semester_report_context(student_id, semester.id)
        rows.append({
            "student_id": student_id,
            "student_name": context["student_full_name"],
            "student_matricule": context["student_matricule"],
        })

    return render(
        request,
        "academics/reports/class_report_overview.html",
        {
            "semester": semester,
            "academic_class": semester.academic_class,
            "rows": rows,
        },
    )


def annual_class_report_view(request, class_id):
    data = build_annual_class_report(class_id)
    return render(
        request,
        "academics/reports/annual_class_report.html",
        data,
    )


def student_annual_report_view(request, student_id):
    data = build_student_annual_report(student_id)
    return render(
        request,
        "academics/reports/student_annual_report.html",
        data,
    )


def student_year_report_view(request, student_id, academic_year_id):
    context = compute_year_result(student_id, academic_year_id)
    return render(request, "academics/reports/year_report.html", context)


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


def _parse_iso_date(raw_value):
    try:
        return date.fromisoformat(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValidationError("date doit etre au format YYYY-MM-DD.") from exc


def _parse_time(raw_value, *, field_name):
    try:
        return time.fromisoformat(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field_name} doit etre au format HH:MM[:SS].") from exc


def _serialize_lesson_log(lesson_log):
    return {
        "id": lesson_log.id,
        "class_id": lesson_log.academic_class_id,
        "class_name": lesson_log.academic_class.display_name,
        "subject_id": lesson_log.ec_id,
        "subject_title": lesson_log.ec.title,
        "teacher_id": lesson_log.teacher_id,
        "teacher_name": lesson_log.teacher.get_full_name() or lesson_log.teacher.username,
        "date": lesson_log.date.isoformat(),
        "start_time": lesson_log.start_time.strftime("%H:%M"),
        "end_time": lesson_log.end_time.strftime("%H:%M"),
        "status": lesson_log.status,
        "content": lesson_log.content,
        "homework": lesson_log.homework,
        "observations": lesson_log.observations,
        "branch_id": lesson_log.branch_id,
        "schedule_event_id": lesson_log.schedule_event_id,
    }


@login_required
@require_POST
def lesson_log_create_view(request):
    try:
        payload = _parse_json_body(request)
        branch = _resolve_branch(request, payload)
        academic_class = get_object_or_404(AcademicClass.objects.select_related("branch"), pk=payload.get("academic_class_id"))
        ec = get_object_or_404(EC.objects.select_related("ue__semester__academic_class"), pk=payload.get("ec_id"))
        teacher = get_object_or_404(User, pk=payload.get("teacher_id"))
        schedule_event = None
        schedule_event_id = payload.get("schedule_event_id")
        if schedule_event_id:
            schedule_event = get_object_or_404(AcademicScheduleEvent, pk=schedule_event_id)

        lesson_log = create_lesson_log(
            academic_class=academic_class,
            ec=ec,
            teacher=teacher,
            schedule_event=schedule_event,
            date=_parse_iso_date(payload.get("date")),
            start_time=_parse_time(payload.get("start_time"), field_name="start_time"),
            end_time=_parse_time(payload.get("end_time"), field_name="end_time"),
            status=payload.get("status"),
            branch=branch,
            created_by=request.user,
            validated_by=request.user if payload.get("validated") else None,
            content=payload.get("content", ""),
            homework=payload.get("homework", ""),
            observations=payload.get("observations", ""),
        )
        return JsonResponse({"ok": True, "lesson_log": _serialize_lesson_log(lesson_log)}, status=201)
    except ValidationError as exc:
        return JsonResponse({"ok": False, "errors": exc.messages}, status=400)


@login_required
@require_POST
def lesson_log_update_view(request, lesson_log_id):
    try:
        payload = _parse_json_body(request)
        lesson_log = get_object_or_404(
            LessonLog.objects.select_related("academic_class__branch", "ec", "teacher", "branch", "schedule_event"),
            pk=lesson_log_id,
        )
        user_branch = get_user_branch(request.user)
        if user_branch and lesson_log.branch_id != user_branch.id:
            return JsonResponse({"ok": False, "errors": ["Acces refuse a cette annexe."]}, status=403)

        changes = {}
        simple_fields = ["status", "content", "homework", "observations"]
        for field in simple_fields:
            if field in payload:
                changes[field] = payload[field]
        if "date" in payload:
            changes["date"] = _parse_iso_date(payload.get("date"))
        if "start_time" in payload:
            changes["start_time"] = _parse_time(payload.get("start_time"), field_name="start_time")
        if "end_time" in payload:
            changes["end_time"] = _parse_time(payload.get("end_time"), field_name="end_time")
        if "validated" in payload and payload.get("validated"):
            changes["validated_by"] = request.user

        lesson_log = update_lesson_log(lesson_log, updated_by=request.user, **changes)
        return JsonResponse({"ok": True, "lesson_log": _serialize_lesson_log(lesson_log)})
    except ValidationError as exc:
        return JsonResponse({"ok": False, "errors": exc.messages}, status=400)


@login_required
@require_GET
def class_lesson_logs_view(request, class_id):
    academic_class = get_object_or_404(AcademicClass.objects.select_related("branch"), pk=class_id)
    user_branch = get_user_branch(request.user)
    if user_branch and academic_class.branch_id != user_branch.id:
        return JsonResponse({"ok": False, "errors": ["Acces refuse a cette annexe."]}, status=403)
    logs = get_class_lesson_logs(academic_class)
    return JsonResponse({"ok": True, "lesson_logs": [_serialize_lesson_log(log) for log in logs]})


@login_required
@require_GET
def teacher_lesson_logs_view(request, teacher_id):
    teacher = get_object_or_404(User, pk=teacher_id)
    branch = get_user_branch(request.user)
    logs = get_teacher_lesson_logs(teacher, branch=branch.id if branch else request.GET.get("branch_id"))
    return JsonResponse({"ok": True, "lesson_logs": [_serialize_lesson_log(log) for log in logs]})


@login_required
@require_GET
def daily_lesson_status_view(request):
    try:
        branch = _resolve_branch(request, request.GET)
        status_date = _parse_iso_date(request.GET.get("date"))
        data = get_daily_lesson_status(branch, status_date)
        payload = {
            **data,
            "date": data["date"].isoformat(),
            "lesson_logs": [_serialize_lesson_log(log) for log in data["lesson_logs"]],
        }
        return JsonResponse({"ok": True, "data": payload})
    except ValidationError as exc:
        return JsonResponse({"ok": False, "errors": exc.messages}, status=400)
