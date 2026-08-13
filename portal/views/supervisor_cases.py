"""Signalements factuels du Surveillant général, strictement limités à son annexe."""
from __future__ import annotations

from datetime import datetime
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.access import get_user_position
from academics.models import AcademicClass, AcademicScheduleEvent
from academics.permissions import require_director_branch_scope
from students.models import Student, StudentCase, TeacherCase
from students.services.case_service import escalate_case_to_director


TRANSMITTED_NOTE = "Cas transmis à la Direction des études."
STUDENT_SIGNAL_TYPES = {
    StudentCase.TYPE_ABSENCE_REPETEE,
    StudentCase.TYPE_RETARD_FREQUENT,
    StudentCase.TYPE_ABSENCE_LONGUE,
    StudentCase.TYPE_SIGNALEMENT_COMPORTEMENTAL,
}
TEACHER_SIGNAL_TYPES = {
    TeacherCase.TYPE_RETARD_REPETE,
    TeacherCase.TYPE_ABSENCE_NON_JUSTIFIEE,
    TeacherCase.TYPE_APPEL_NON_FAIT,
    TeacherCase.TYPE_INCIDENT,
    TeacherCase.TYPE_AUTRE,
}


def _deny(_request=None):
    return HttpResponseForbidden("Accès refusé.")


def _removed_decision_capability():
    return HttpResponseForbidden(
        "Le Surveillant général transmet les faits au Directeur des études, "
        "mais ne fait pas progresser les dossiers disciplinaires."
    )


def _require_supervisor(func):
    @wraps(func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if get_user_position(request.user) != "academic_supervisor":
            return _deny(request)
        return func(request, *args, **kwargs)

    return wrapper


def _resolve_supervisor_branch(request):
    return require_director_branch_scope(
        request.user,
        additional_scoped_positions={"academic_supervisor"},
    )


def _case_model(kind):
    return {"student": StudentCase, "teacher": TeacherCase}.get(kind)


def _parse_occurred_on(raw_value, event):
    event_date = timezone.localtime(event.start_datetime).date()
    if not raw_value:
        return event_date
    try:
        occurred_on = datetime.strptime(raw_value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("Date du fait invalide.") from exc
    if occurred_on != event_date:
        raise ValueError("La date du fait doit correspondre à la séance sélectionnée.")
    return occurred_on


def _render_signals_workspace(request, *, toast=None):
    """Return the canonical transmitted-signals subwindow after a mutation."""
    from portal.views.supervisor import _render_supervisor_workflow_workspace

    mutable_get = request.GET.copy()
    mutable_get["section"] = "signals"
    mutable_get["view"] = "transmitted"
    mutable_get["fragment"] = "subcontent"
    request.GET = mutable_get
    return _render_supervisor_workflow_workspace(
        request,
        section="signals",
        toast=toast,
        force_subcontent=True,
    )


@_require_supervisor
def supervisor_cases_workspace(request):
    """Compatibility entrypoint for old links; the official screen is Signals."""
    canonical = f"{reverse('accounts_portal:portal_dashboard')}?section=signals&view=transmitted"
    if not request.htmx:
        return redirect(canonical)
    return _render_signals_workspace(request)


@_require_supervisor
def supervisor_case_detail(request, kind: str, case_id: int):
    """Read-only drawer: the supervisor can review facts already transmitted."""
    branch = _resolve_supervisor_branch(request)
    model = _case_model(kind)
    if branch is None or model is None:
        return HttpResponseBadRequest("Signalement invalide.")
    related = (
        ["student__inscription__candidature", "opened_by", "academic_class", "schedule_event__ec"]
        if kind == "student"
        else ["teacher", "opened_by", "academic_class", "schedule_event__ec"]
    )
    signalment = get_object_or_404(
        model.objects.select_related(*related).prefetch_related("notes__author"),
        pk=case_id,
        branch=branch,
    )
    transmitted = (
        signalment.status == StudentCase.STATUS_ESCALADE
        if kind == "student"
        else signalment.notes.filter(content=TRANSMITTED_NOTE).exists()
    )
    response = render(
        request,
        "portal/staff/supervisor/partials/case_detail.html",
        {"case": signalment, "kind": kind, "is_escalated": transmitted},
    )
    response["HX-Trigger"] = "supervisor-drawer-open"
    return response


@_require_supervisor
@require_POST
def supervisor_case_create(request):
    """Record factual context and immediately transmit it to the branch DE."""
    branch = _resolve_supervisor_branch(request)
    if branch is None:
        return HttpResponseBadRequest("Aucune annexe rattachée.")

    kind = (request.POST.get("kind") or "student").strip().lower()
    case_type = (request.POST.get("case_type") or "").strip()
    priority = (request.POST.get("priority") or StudentCase.PRIORITY_NORMALE).strip()
    title = (request.POST.get("title") or "").strip()
    description = (request.POST.get("description") or "").strip()
    if kind not in {"student", "teacher"} or not title or not description:
        return HttpResponseBadRequest("La personne, le titre et les faits constatés sont obligatoires.")
    if priority not in {value for value, _label in StudentCase.PRIORITY_CHOICES}:
        return HttpResponseBadRequest("Priorité invalide.")

    event = get_object_or_404(
        AcademicScheduleEvent.objects.select_related("academic_class", "teacher", "ec"),
        pk=request.POST.get("schedule_event_id"),
        branch=branch,
        event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
        is_active=True,
    )
    if event.status in {
        AcademicScheduleEvent.STATUS_DRAFT,
        AcademicScheduleEvent.STATUS_CANCELLED,
    }:
        return HttpResponseBadRequest("Le signalement doit concerner une séance publiée.")
    academic_class = get_object_or_404(
        AcademicClass,
        pk=request.POST.get("class_id") or event.academic_class_id,
        branch=branch,
        is_active=True,
    )
    if academic_class.pk != event.academic_class_id:
        return HttpResponseBadRequest("La classe ne correspond pas à la séance.")
    try:
        occurred_on = _parse_occurred_on(request.POST.get("occurred_on"), event)
    except ValueError as exc:
        return HttpResponseBadRequest(str(exc))

    if kind == "student":
        if case_type not in STUDENT_SIGNAL_TYPES:
            return HttpResponseBadRequest("Type de fait étudiant invalide.")
        student = get_object_or_404(
            Student.objects.select_related("user", "inscription__candidature"),
            pk=request.POST.get("student_id"),
            inscription__candidature__branch=branch,
            is_active=True,
            user__academic_enrollments__academic_class=academic_class,
            user__academic_enrollments__branch=branch,
            user__academic_enrollments__is_active=True,
        )
        signalment = StudentCase.objects.create(
            student=student,
            branch=branch,
            academic_class=academic_class,
            schedule_event=event,
            occurred_on=occurred_on,
            case_type=case_type,
            priority=priority,
            title=title,
            description=description,
            opened_by=request.user,
        )
    else:
        if case_type not in TEACHER_SIGNAL_TYPES:
            return HttpResponseBadRequest("Type de fait enseignant invalide.")
        if not event.teacher_id or str(event.teacher_id) != (request.POST.get("teacher_id") or "").strip():
            return HttpResponseBadRequest("L'enseignant doit être celui de la séance sélectionnée.")
        signalment = TeacherCase.objects.create(
            teacher=event.teacher,
            branch=branch,
            academic_class=academic_class,
            schedule_event=event,
            occurred_on=occurred_on,
            case_type=case_type,
            priority=priority,
            title=title,
            description=description,
            opened_by=request.user,
        )

    escalate_case_to_director(case=signalment, user=request.user)
    return _render_signals_workspace(
        request,
        toast={
            "level": "success",
            "message": "Le signalement factuel a été enregistré et transmis au Directeur des études.",
        },
    )


@_require_supervisor
@require_POST
def supervisor_case_advance(request, kind: str, case_id: int):
    return _removed_decision_capability()


@_require_supervisor
@require_POST
def supervisor_case_escalate(request, kind: str, case_id: int):
    """Compatibility action: transmission is allowed, decisions are not."""
    branch = _resolve_supervisor_branch(request)
    model = _case_model(kind)
    if branch is None or model is None:
        return HttpResponseBadRequest("Signalement invalide.")
    signalment = get_object_or_404(model, pk=case_id, branch=branch)
    already_transmitted = (
        signalment.status == StudentCase.STATUS_ESCALADE
        if kind == "student"
        else signalment.notes.filter(content=TRANSMITTED_NOTE).exists()
    )
    if not already_transmitted:
        escalate_case_to_director(case=signalment, user=request.user)
    return supervisor_case_detail(request, kind=kind, case_id=case_id)


@_require_supervisor
@require_POST
def supervisor_case_add_note(request, kind: str, case_id: int):
    return _removed_decision_capability()


@_require_supervisor
def supervisor_student_cases(request, student_id: int):
    branch = _resolve_supervisor_branch(request)
    student = get_object_or_404(
        Student.objects.select_related("inscription__candidature"),
        pk=student_id,
        inscription__candidature__branch=branch,
    )
    signalments = StudentCase.objects.filter(student=student, branch=branch).order_by("-created_at")[:20]
    return render(
        request,
        "portal/staff/supervisor/partials/student_cases_panel.html",
        {"student": student, "cases": signalments, "read_only": True},
    )
