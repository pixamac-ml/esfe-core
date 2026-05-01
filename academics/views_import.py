from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from academics.imports.import_service import import_grades
from academics.imports.template_service import generate_import_template
from academics.models import AcademicClass, Semester


@login_required
@require_GET
def download_template(request, class_id: int, semester_id: int):
    """Téléchargement du template Excel dynamique (classe + semestre)."""

    academic_class = get_object_or_404(AcademicClass, pk=class_id)
    semester = get_object_or_404(Semester.objects.select_related("academic_class"), pk=semester_id)

    output = generate_import_template(academic_class=academic_class, semester=semester)

    filename = f"import-notes-{academic_class.id}-S{semester.number}-{semester.id}.xlsx"
    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
@require_POST
def upload_grades(request):
    """Upload du fichier Excel et import des notes.

    Attend des champs POST:
    - class_id
    - semester_id
    - file (xlsx)

    Retourne JSON.
    """

    class_id = request.POST.get("class_id")
    semester_id = request.POST.get("semester_id")
    excel_file = request.FILES.get("file")

    if not class_id or not semester_id or not excel_file:
        return JsonResponse(
            {
                "ok": False,
                "error": "Paramètres requis: class_id, semester_id et file.",
            },
            status=400,
        )

    academic_class = get_object_or_404(AcademicClass, pk=class_id)
    semester = get_object_or_404(Semester.objects.select_related("academic_class"), pk=semester_id)

    try:
        result = import_grades(excel_file, academic_class=academic_class, semester=semester)
    except Exception as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    return JsonResponse(
        {
            "ok": True,
            "result": {
                "updated": result.updated,
                "skipped_empty": result.skipped_empty,
                "skipped_unknown_columns": result.skipped_unknown_columns,
                "skipped_unknown_students": result.skipped_unknown_students,
                "skipped_invalid_scores": result.skipped_invalid_scores,
                "student_issues": result.student_issues,
            },
        }
    )

