from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from academics.models import AcademicClass, AcademicEnrollment, AcademicYear
from accounts.dashboards.helpers import get_user_branch, is_global_viewer
from portal.services.reenrollment_service import (
    apply_student_decision,
    can_user_handle_reenrollment,
    can_user_propose_reenrollment,
    get_reenrollment_dashboard_context,
    propose_student_decision,
    reject_student_decision,
    validate_student_decision_academic,
    validate_student_decision_finance,
)
from students.models import StudentYearDecision


def _require_reenrollment_access(request):
    if not can_user_handle_reenrollment(request.user):
        return False
    return get_user_branch(request.user) is not None or is_global_viewer(request.user) or request.user.is_superuser


def _resolve_reenrollment_filters(request):
    branch = get_user_branch(request.user)
    source_year = None
    source_class = None
    target_year = None
    target_class = None
    programme = None

    source_year_id = (request.GET.get("source_year") or request.POST.get("source_year") or "").strip()
    source_class_id = (request.GET.get("source_class") or request.POST.get("source_class") or "").strip()
    target_year_id = (request.GET.get("target_year") or request.POST.get("target_year") or "").strip()
    target_class_id = (request.GET.get("target_class") or request.POST.get("target_class") or "").strip()
    programme_id = (request.GET.get("programme") or request.POST.get("programme") or "").strip()

    if source_year_id.isdigit():
        source_year = AcademicYear.objects.filter(pk=source_year_id).first()
    if target_year_id.isdigit():
        target_year = AcademicYear.objects.filter(pk=target_year_id).first()
    if source_class_id.isdigit():
        class_qs = AcademicClass.objects.select_related("branch", "academic_year", "programme")
        if branch:
            class_qs = class_qs.filter(branch=branch)
        source_class = class_qs.filter(pk=source_class_id).first()
        if source_class is not None:
            source_year = source_class.academic_year

    class_qs = AcademicClass.objects.select_related("branch", "academic_year", "programme").filter(
        is_archived=False,
    )
    if branch:
        class_qs = class_qs.filter(branch=branch)
    if target_class_id.isdigit():
        target_class = class_qs.filter(pk=target_class_id, is_active=True).first()
        if target_class is not None:
            target_year = target_class.academic_year
    if programme_id.isdigit():
        programme = class_qs.filter(programme_id=programme_id).values_list("programme", flat=True).first()
        if programme is not None:
            from formations.models import Programme

            programme = Programme.objects.filter(pk=programme).first()

    return branch, source_year, source_class, target_year, target_class, programme


def _resolve_surface(request):
    raw_surface = (request.GET.get("surface") or request.POST.get("surface") or "").strip().lower()
    if raw_surface == "director":
        return "director", "#director-reenrollment-workspace"
    return "manager", "#reenrollment-workspace"


def _render_workspace(request, *, toast=None):
    branch, source_year, source_class, target_year, target_class, programme = _resolve_reenrollment_filters(request)
    surface, workspace_target = _resolve_surface(request)
    context = get_reenrollment_dashboard_context(
        branch=branch,
        source_year=source_year,
        source_class=source_class,
        target_year=target_year,
        target_class=target_class,
        programme=programme,
        decision_value=(request.GET.get("decision") or request.POST.get("decision_filter") or "").strip(),
        workflow_status=(request.GET.get("workflow_status") or request.POST.get("workflow_status") or "").strip(),
        finance_state=(request.GET.get("finance_state") or request.POST.get("finance_state") or "").strip(),
        search=(request.GET.get("q") or request.POST.get("q") or "").strip()[:120],
        actor=request.user,
        toast=toast,
        surface=surface,
        workspace_target=workspace_target,
    )
    context["manager_inscriptions_url"] = (
        f"{reverse('accounts_portal:portal_annex_manager')}?section=inscriptions"
    )
    template_name = "portal/reenrollment/workspace.html"
    if request.headers.get("HX-Request") != "true" and surface != "director":
        template_name = "portal/reenrollment/page.html"
    return render(
        request,
        template_name,
        context,
    )


@login_required
def reenrollment_workspace(request):
    if not _require_reenrollment_access(request):
        return HttpResponseForbidden("Acces refuse.")
    return _render_workspace(request)


@login_required
@require_POST
def reenrollment_propose(request):
    if not _require_reenrollment_access(request):
        return HttpResponseForbidden("Acces refuse.")
    if not can_user_propose_reenrollment(request.user):
        return _render_workspace(
            request,
            toast={"level": "error", "message": "Seul le Directeur des études peut enregistrer la décision académique."},
        )

    toast = {"level": "success", "message": "Decision proposee."}
    try:
        branch, _source_year, _source_class, target_year, _target_class, _programme = _resolve_reenrollment_filters(request)
        enrollment_qs = AcademicEnrollment.objects.select_related("student__student_profile", "branch")
        if branch is not None:
            enrollment_qs = enrollment_qs.filter(branch=branch)
        enrollment = get_object_or_404(enrollment_qs, pk=request.POST.get("enrollment_id"))
        student = getattr(enrollment.student, "student_profile", None)
        if student is None:
            raise ValidationError("Aucun profil etudiant officiel n'est lie a ce compte.")
        target_class = None
        target_class_id = (request.POST.get("target_class") or "").strip()
        if target_class_id.isdigit():
            target_class_qs = AcademicClass.objects.filter(
                pk=target_class_id,
                is_active=True,
                is_archived=False,
            )
            if branch is not None:
                target_class_qs = target_class_qs.filter(branch=branch)
            target_class = target_class_qs.first()
        propose_student_decision(
            student=student,
            source_enrollment=enrollment,
            target_academic_year=target_year,
            target_class=target_class,
            decision=request.POST.get("decision") or None,
            proposed_by=request.user,
            note=request.POST.get("note", ""),
        )
    except ValidationError as exc:
        toast = {"level": "error", "message": " ".join(exc.messages)}

    return _render_workspace(request, toast=toast)


@login_required
@require_POST
def reenrollment_decision_action(request):
    if not _require_reenrollment_access(request):
        return HttpResponseForbidden("Acces refuse.")

    action = (request.POST.get("action") or "").strip()
    branch = get_user_branch(request.user)
    decision_qs = StudentYearDecision.objects.select_related("source_enrollment")
    if branch is not None:
        decision_qs = decision_qs.filter(source_enrollment__branch=branch)
    decision = get_object_or_404(decision_qs, pk=request.POST.get("decision_id"))
    toast = {"level": "success", "message": "Decision mise a jour."}
    try:
        if action == "academic_validate":
            validate_student_decision_academic(decision=decision, actor=request.user)
            toast = {"level": "success", "message": "Validation pedagogique enregistree."}
        elif action == "finance_validate":
            validate_student_decision_finance(decision=decision, actor=request.user)
            toast = {"level": "success", "message": "Visa financier enregistre."}
        elif action == "apply":
            apply_student_decision(decision=decision, actor=request.user)
            toast = {"level": "success", "message": "Inscription cible preparee. Son paiement activera la nouvelle annee."}
        elif action == "reject":
            reject_student_decision(decision=decision, actor=request.user, reason=request.POST.get("reason", ""))
            toast = {"level": "success", "message": "Decision rejetee."}
        else:
            raise ValidationError("Action inconnue.")
    except ValidationError as exc:
        toast = {"level": "error", "message": " ".join(exc.messages)}

    return _render_workspace(request, toast=toast)
