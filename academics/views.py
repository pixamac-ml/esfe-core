import io
import zipfile

from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string

from academics.models import AcademicEnrollment, Semester
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
