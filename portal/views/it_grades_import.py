from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, render

from academics.models import AcademicClass, Semester
from academics.services.workflow import get_semester_permissions
from accounts.access import get_user_position
from accounts.dashboards.helpers import get_user_branch


def _build_import_preview(*, selected_class, selected_semester, ues):
    if not selected_class or not selected_semester:
        return None

    subject_headers = []
    for ue in ues:
        for ec in ue.ecs.all():
            subject_headers.append(f"{ue.code} - {ec.title}")

    sample_headers = ["NOM", "PRENOM", *subject_headers[:4]]
    sample_row = ["CAMARA", "BOUBACAR", *(["12,50"] if subject_headers else [])]
    if len(sample_headers) > 3:
        sample_row.extend([""] * (len(sample_headers) - len(sample_row)))

    return {
        "meta_rows": [
            ["Ecole", "ESFE"],
            ["Classe", selected_class.display_name],
            ["Année académique", str(selected_class.academic_year)],
            ["Semestre", f"Semestre {selected_semester.number}"],
        ],
        "headers": sample_headers,
        "sample_row": sample_row,
        "subject_count": len(subject_headers),
    }


def build_it_grade_selection_context(user, *, class_id=None, semester_id=None):
    branch = get_user_branch(user)
    classes_qs = (
        AcademicClass.objects.select_related("programme", "branch", "academic_year")
        .filter(is_active=True)
        .annotate(student_count=Count("enrollments"))
        .order_by("branch__name", "level", "programme__title")
    )
    if branch:
        classes_qs = classes_qs.filter(branch=branch)

    classes = list(classes_qs[:200])

    selected_class = None
    semesters = []
    selected_semester = None
    ues = []
    workflow_permissions = None

    if class_id and str(class_id).isdigit():
        selected_class = get_object_or_404(classes_qs, pk=int(class_id))
        semesters = list(
            Semester.objects.filter(academic_class=selected_class)
            .select_related("academic_class")
            .order_by("number")
        )

    if selected_class and semester_id and str(semester_id).isdigit():
        selected_semester = get_object_or_404(
            Semester.objects.select_related("academic_class"),
            pk=int(semester_id),
            academic_class=selected_class,
        )
        ues = list(selected_semester.ues.prefetch_related("ecs").order_by("id"))
        workflow_permissions = get_semester_permissions(selected_semester)

    return {
        "classes": classes,
        "selected_class": selected_class,
        "semesters": semesters,
        "selected_semester": selected_semester,
        "ues": ues,
        "workflow_permissions": workflow_permissions,
        "import_preview": _build_import_preview(
            selected_class=selected_class,
            selected_semester=selected_semester,
            ues=ues,
        ),
    }


@login_required
def it_grades_import_view(request):
    """Page portail (informaticien) : Import des notes via endpoints academics.

    Ne modifie aucune logique métier: consomme uniquement:
    - academics:download_import_template
    - academics:upload_grades
    """

    if get_user_position(request.user) != "it_support":
        return HttpResponseForbidden("Acces refuse.")

    context = build_it_grade_selection_context(
        request.user,
        class_id=request.GET.get("class_id"),
        semester_id=request.GET.get("semester_id"),
    )

    return render(
        request,
        "portal/staff/it_grades_import.html",
        context,
    )

