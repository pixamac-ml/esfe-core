"""Vues HTMX : gestion des cas de surveillance (superviseur général) — étudiants + enseignants."""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from accounts.access import get_user_position
from accounts.dashboards.helpers import get_user_branch
from portal.services.supervisor_dashboard_service import get_supervisor_class_picker_bundle
from students.models import Student, StudentCase, StudentCaseNote, TeacherCase, TeacherCaseNote
from students.services.case_service import advance_student_case, advance_teacher_case, list_open_cases


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


def _case_model(kind):
    return StudentCase if kind == "student" else TeacherCase


def _case_note_model(kind):
    return StudentCaseNote if kind == "student" else TeacherCaseNote


_FLOW_LABELS = {
    StudentCase.STATUS_NOUVEAU: "Nouveau",
    StudentCase.STATUS_EN_COURS: "En instruction",
    StudentCase.STATUS_CONVOQUE: "Convoqué",
    StudentCase.STATUS_RESOLU: "Résolu",
}


def _flow_steps(case):
    flow = StudentCase.SIMPLE_FLOW_STATUSES
    idx = flow.index(case.status) if case.status in flow else -1
    steps = []
    for i, key in enumerate(flow):
        if idx == -1:
            state = ""
        elif i < idx:
            state = "done"
        elif i == idx:
            state = "current"
        else:
            state = ""
        steps.append({"key": key, "label": _FLOW_LABELS[key], "state": state})
    return steps


# ─── Workspace liste des cas (fusion étudiants + enseignants) ─────────────────

@_require_supervisor
def supervisor_cases_workspace(request):
    """Liste fusionnée des cas étudiants + enseignants de l'annexe."""
    branch = get_user_branch(request.user)
    if not branch:
        return HttpResponseBadRequest("Aucune annexe rattachée.")

    status_filter = request.GET.get("status", "open")

    if status_filter == "all":
        student_cases = list(
            StudentCase.objects.select_related("student__inscription__candidature", "opened_by").filter(branch=branch)
        )
        teacher_cases = list(TeacherCase.objects.select_related("teacher", "opened_by").filter(branch=branch))
        priority_order = {
            StudentCase.PRIORITY_CRITIQUE: 0,
            StudentCase.PRIORITY_URGENTE: 1,
            StudentCase.PRIORITY_NORMALE: 2,
            StudentCase.PRIORITY_FAIBLE: 3,
        }
        combined = [("student", c) for c in student_cases] + [("teacher", c) for c in teacher_cases]
        combined.sort(key=lambda pair: (priority_order.get(pair[1].priority, 9), -pair[1].pk))
        combined = combined[:100]
    else:
        combined = list_open_cases(branch=branch, limit=100)

    open_count = (
        StudentCase.objects.filter(branch=branch).exclude(status=StudentCase.STATUS_RESOLU).count()
        + TeacherCase.objects.filter(branch=branch).exclude(status=TeacherCase.STATUS_RESOLU).count()
    )

    students_qs = (
        Student.objects.select_related("user", "inscription__candidature")
        .filter(inscription__candidature__branch=branch, is_active=True)
        .order_by("inscription__candidature__last_name", "inscription__candidature__first_name")[:200]
    )

    _, class_picker_items, _ = get_supervisor_class_picker_bundle(branch=branch)
    context = {
        "cases": combined,
        "open_count": open_count,
        "open_cases_count": open_count,
        "status_filter": status_filter,
        "case_type_choices": StudentCase.TYPE_CHOICES,
        "students": students_qs,
        "branch": branch,
        "section": "cases",
        "crumb": "Pilotage · Discipline",
        "panel_title": "Cas à traiter",
        "panel_lede": "Dossiers disciplinaires — étudiants et enseignants.",
        "class_picker_items": class_picker_items,
        "selected_class_id": None,
    }
    if not request.htmx:
        from portal.views.supervisor import _render_supervisor_dashboard

        return _render_supervisor_dashboard(request, section="cases")
    return render(request, "portal/staff/supervisor/partials/cases_workspace.html", context)


# ─── Détail d'un cas (étudiant ou enseignant) ─────────────────────────────────

@_require_supervisor
def supervisor_case_detail(request, kind: str, case_id: int):
    """Drawer de détail d'un cas (kind = 'student' ou 'teacher')."""
    branch = get_user_branch(request.user)
    model = _case_model(kind)
    related = (
        ["student__inscription__candidature", "opened_by"]
        if kind == "student"
        else ["teacher", "opened_by"]
    )
    case = get_object_or_404(
        model.objects.select_related(*related).prefetch_related("notes__author"),
        pk=case_id,
        branch=branch,
    )
    context = {"case": case, "kind": kind, "flow_steps": _flow_steps(case)}
    response = render(request, "portal/staff/supervisor/partials/case_detail.html", context)
    response["HX-Trigger"] = "supervisor-drawer-open"
    return response


# ─── Créer un cas étudiant ─────────────────────────────────────────────────────

@_require_supervisor
@require_POST
def supervisor_case_create(request):
    """Créer un nouveau cas étudiant."""
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


# ─── Faire avancer un cas dans le flux à 4 étapes ──────────────────────────────

@_require_supervisor
@require_POST
def supervisor_case_advance(request, kind: str, case_id: int):
    """Avance un cas (étudiant ou enseignant) à l'étape suivante du flux simplifié."""
    branch = get_user_branch(request.user)
    model = _case_model(kind)
    case = get_object_or_404(model, pk=case_id, branch=branch)

    if kind == "student":
        advance_student_case(case=case, user=request.user)
    else:
        advance_teacher_case(case=case, user=request.user)

    return supervisor_case_detail(request, kind=kind, case_id=case_id)


# ─── Ajouter une note ──────────────────────────────────────────────────────────

@_require_supervisor
@require_POST
def supervisor_case_add_note(request, kind: str, case_id: int):
    """Ajouter une note interne à un cas (étudiant ou enseignant)."""
    branch = get_user_branch(request.user)
    model = _case_model(kind)
    note_model = _case_note_model(kind)
    case = get_object_or_404(model, pk=case_id, branch=branch)

    content = request.POST.get("content", "").strip()
    if not content:
        return HttpResponseBadRequest("Note vide.")

    note_model.objects.create(case=case, author=request.user, content=content)

    return supervisor_case_detail(request, kind=kind, case_id=case_id)


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
