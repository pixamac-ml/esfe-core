"""Vues HTMX : gestion des cas de surveillance (superviseur général)."""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest, HttpResponseForbidden, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from accounts.access import get_user_position
from accounts.dashboards.helpers import get_user_branch
from students.models import Student, StudentCase, StudentCaseNote


def _deny(request):
    return HttpResponseForbidden("Accès refusé.")


def _require_supervisor(func):
    """Décorateur : réserve la vue au surveillant général."""
    def wrapper(request, *args, **kwargs):
        if get_user_position(request.user) != "academic_supervisor":
            return _deny(request)
        return func(request, *args, **kwargs)
    wrapper.__name__ = func.__name__
    return login_required(wrapper)


# ─── Workspace liste des cas ───────────────────────────────────────────────────

@_require_supervisor
def supervisor_cases_workspace(request):
    """Liste des cas ouverts de l'annexe, avec filtres."""
    branch = get_user_branch(request.user)
    if not branch:
        return HttpResponseBadRequest("Aucune annexe rattachée.")

    status_filter = request.GET.get("status", "open")
    priority_filter = request.GET.get("priority", "")

    qs = StudentCase.objects.select_related(
        "student__inscription__candidature", "opened_by"
    ).filter(branch=branch)

    if status_filter == "open":
        qs = qs.exclude(status__in=[StudentCase.STATUS_RESOLU, StudentCase.STATUS_ESCALADE])
    elif status_filter != "all":
        qs = qs.filter(status=status_filter)

    if priority_filter:
        qs = qs.filter(priority=priority_filter)

    qs = qs.order_by(
        "priority",   # critique first (alphabétique: c < f < n < u)
        "-created_at",
    )

    # Reorder priority: critique > urgente > normale > faible
    PRIORITY_ORDER = {
        StudentCase.PRIORITY_CRITIQUE: 0,
        StudentCase.PRIORITY_URGENTE: 1,
        StudentCase.PRIORITY_NORMALE: 2,
        StudentCase.PRIORITY_FAIBLE: 3,
    }
    cases = sorted(qs[:100], key=lambda c: (PRIORITY_ORDER.get(c.priority, 9), -c.pk))

    open_count = StudentCase.objects.filter(branch=branch).exclude(
        status__in=[StudentCase.STATUS_RESOLU, StudentCase.STATUS_ESCALADE]
    ).count()

    students_qs = (
        Student.objects.select_related("user", "inscription__candidature")
        .filter(
            inscription__candidature__branch=branch,
            is_active=True,
        )
        .order_by("inscription__candidature__last_name", "inscription__candidature__first_name")[:200]
    )

    context = {
        "cases": cases,
        "open_count": open_count,
        "status_filter": status_filter,
        "priority_filter": priority_filter,
        "status_choices": StudentCase.STATUS_CHOICES,
        "priority_choices": StudentCase.PRIORITY_CHOICES,
        "case_type_choices": StudentCase.TYPE_CHOICES,
        "students": students_qs,
        "branch": branch,
    }
    return render(request, "portal/staff/supervisor/partials/cases_workspace.html", context)


# ─── Détail d'un cas ───────────────────────────────────────────────────────────

@_require_supervisor
def supervisor_case_detail(request, case_id: int):
    """Drawer de détail d'un cas."""
    branch = get_user_branch(request.user)
    case = get_object_or_404(
        StudentCase.objects.select_related(
            "student__inscription__candidature", "opened_by"
        ).prefetch_related("notes__author"),
        pk=case_id,
        branch=branch,
    )
    context = {
        "case": case,
        "status_choices": StudentCase.STATUS_CHOICES,
    }
    return render(request, "portal/staff/supervisor/partials/case_detail.html", context)


# ─── Créer un cas ──────────────────────────────────────────────────────────────

@_require_supervisor
@require_POST
def supervisor_case_create(request):
    """Créer un nouveau cas."""
    branch = get_user_branch(request.user)
    if not branch:
        return HttpResponseBadRequest("Aucune annexe rattachée.")

    student_id = request.POST.get("student_id", "").strip()
    case_type = request.POST.get("case_type", "").strip()
    priority = request.POST.get("priority", StudentCase.PRIORITY_NORMALE).strip()
    title = request.POST.get("title", "").strip()
    description = request.POST.get("description", "").strip()

    if not student_id or not case_type or not title:
        return HttpResponseBadRequest("Champs requis manquants.")

    student = get_object_or_404(
        Student,
        pk=student_id,
        inscription__candidature__branch=branch,
        is_active=True,
    )

    valid_types = {k for k, _ in StudentCase.TYPE_CHOICES}
    valid_priorities = {k for k, _ in StudentCase.PRIORITY_CHOICES}
    if case_type not in valid_types or priority not in valid_priorities:
        return HttpResponseBadRequest("Valeurs invalides.")

    StudentCase.objects.create(
        student=student,
        branch=branch,
        case_type=case_type,
        priority=priority,
        title=title,
        description=description,
        opened_by=request.user,
    )

    return supervisor_cases_workspace(request)


# ─── Changer le statut d'un cas ────────────────────────────────────────────────

@_require_supervisor
@require_POST
def supervisor_case_update_status(request, case_id: int):
    """Mettre à jour le statut d'un cas."""
    branch = get_user_branch(request.user)
    case = get_object_or_404(StudentCase, pk=case_id, branch=branch)

    new_status = request.POST.get("status", "").strip()
    valid_statuses = {k for k, _ in StudentCase.STATUS_CHOICES}
    if new_status not in valid_statuses:
        return HttpResponseBadRequest("Statut invalide.")

    if new_status == StudentCase.STATUS_RESOLU:
        case.resolve(request.user)
    else:
        case.status = new_status
        case.save(update_fields=["status", "updated_at"])

    context = {
        "case": StudentCase.objects.select_related(
            "student__inscription__candidature", "opened_by"
        ).prefetch_related("notes__author").get(pk=case_id),
        "status_choices": StudentCase.STATUS_CHOICES,
    }
    return render(request, "portal/staff/supervisor/partials/case_detail.html", context)


# ─── Ajouter une note ──────────────────────────────────────────────────────────

@_require_supervisor
@require_POST
def supervisor_case_add_note(request, case_id: int):
    """Ajouter une note interne à un cas."""
    branch = get_user_branch(request.user)
    case = get_object_or_404(StudentCase, pk=case_id, branch=branch)

    content = request.POST.get("content", "").strip()
    if not content:
        return HttpResponseBadRequest("Note vide.")

    StudentCaseNote.objects.create(
        case=case,
        author=request.user,
        content=content,
    )

    context = {
        "case": StudentCase.objects.select_related(
            "student__inscription__candidature", "opened_by"
        ).prefetch_related("notes__author").get(pk=case_id),
        "status_choices": StudentCase.STATUS_CHOICES,
    }
    return render(request, "portal/staff/supervisor/partials/case_detail.html", context)


# ─── Cas d'un étudiant (pour le drawer étudiant) ──────────────────────────────

@_require_supervisor
def supervisor_student_cases(request, student_id: int):
    """Cas liés à un étudiant, chargés dans le drawer."""
    branch = get_user_branch(request.user)
    student = get_object_or_404(
        Student.objects.select_related("inscription__candidature"),
        pk=student_id,
        inscription__candidature__branch=branch,
    )
    cases = StudentCase.objects.filter(student=student, branch=branch).order_by("-created_at")[:20]
    context = {
        "student": student,
        "cases": cases,
        "case_type_choices": StudentCase.TYPE_CHOICES,
        "priority_choices": StudentCase.PRIORITY_CHOICES,
        "status_choices": StudentCase.STATUS_CHOICES,
    }
    return render(request, "portal/staff/supervisor/partials/student_cases_panel.html", context)

