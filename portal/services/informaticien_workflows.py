from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse

from academics.imports.import_service import import_grades
from academics.models import Language, Profession
from academics.services.workflow import get_semester_permissions
from portal.models import AccountSupportState
from portal.models import BranchITSettings, SupportAuditLog, SupportTicket
from portal.selectors.informaticien import (
    active_academic_year,
    academic_classes_for_branch,
    audit_logs_for_branch,
    classes_without_notes_for_branch,
    ecs_without_schedule_teacher_for_branch,
    enrollments_without_grades_for_branch,
    support_tickets_for_branch,
)
from portal.services.notes_workflow import get_notes_state
from portal.services.it_support_service import (
    assign_support_ticket,
    create_support_ticket,
    log_support_action,
    update_support_ticket_status,
)


@dataclass
class ImportFeedback:
    level: str
    message: str
    invalid_lines: list[dict]
    updated: int = 0
    skipped_empty: int = 0
    skipped_unknown_columns: int = 0
    skipped_unknown_students: int = 0
    skipped_invalid_scores: int = 0
    unknown_columns: list[str] | None = None


def _build_import_preview(*, selected_class, selected_semester, ues):
    if not selected_class or not selected_semester:
        return None
    subject_headers = []
    for ue in ues:
        for ec in ue.ecs.all():
            subject_headers.append(f"NOTE /20 - {ue.code} - {ec.title}")
    sample_headers = ["ENROLLMENT_ID", "MATRICULE", "NOM", "PRENOM", *subject_headers[:4]]
    sample_row = ["1024", "ESFE-0001", "CAMARA", "BOUBACAR", *(["12,50"] if subject_headers else [])]
    if len(sample_headers) > len(sample_row):
        sample_row.extend([""] * (len(sample_headers) - len(sample_row)))
    return {
        "headers": sample_headers,
        "sample_row": sample_row,
        "subject_count": len(subject_headers),
    }


def build_home_context(*, branch):
    classes = list(academic_classes_for_branch(branch=branch).filter(is_active=True)[:60])
    incomplete_classes = []
    calculable_classes = []
    resume_target = None

    for academic_class in classes:
        for semester in academic_class.semesters.all().order_by("number"):
            state = get_notes_state(academic_class=academic_class, semester=semester)
            if state is None:
                continue
            query = f"?classe={academic_class.id}&semester={semester.id}"
            item = {
                "class": academic_class,
                "semester": semester,
                "state": state,
                "url": f"{reverse('accounts_portal:it_notes_flow_workspace')}{query}",
            }
            if state.entered_grades and resume_target is None:
                resume_target = item
            if state.missing_grades and state.entered_grades:
                incomplete_classes.append(item)
            if state.code == "ready_to_calculate":
                calculable_classes.append(item)

    blocked_accounts = AccountSupportState.objects.select_related("user__profile").filter(
        is_blocked=True,
        user__profile__branch=branch,
    )[:10]
    import_errors = audit_logs_for_branch(branch=branch).filter(
        action_type=SupportAuditLog.ACTION_GRADES_IMPORTED,
        details__icontains="invalide",
    )[:10]

    return {
        "branch": branch,
        "resume_target": resume_target,
        "incomplete_classes": incomplete_classes[:10],
        "calculable_classes": calculable_classes[:10],
        "blocked_accounts": list(blocked_accounts),
        "import_errors": list(import_errors),
    }


def build_support_context(*, branch, status="", toast=None):
    tickets = support_tickets_for_branch(branch=branch, status=status)
    return {
        "branch": branch,
        "status": status,
        "status_choices": SupportTicket.STATUS_CHOICES,
        "tickets": list(tickets[:80]),
        "toast": toast,
    }


def create_branch_ticket(*, actor, branch, title, description):
    return create_support_ticket(
        actor=actor,
        branch=branch,
        title=title,
        description=description,
        category=SupportTicket.CATEGORY_OTHER,
        priority=SupportTicket.PRIORITY_NORMAL,
    )


def take_branch_ticket(*, actor, branch, ticket):
    _validate_ticket_branch(branch=branch, ticket=ticket)
    return assign_support_ticket(actor=actor, branch=branch, ticket=ticket)


def resolve_branch_ticket(*, actor, branch, ticket, resolution=""):
    _validate_ticket_branch(branch=branch, ticket=ticket)
    return update_support_ticket_status(
        actor=actor,
        branch=branch,
        ticket=ticket,
        status=SupportTicket.STATUS_RESOLVED,
        resolution=resolution or "Ticket resolu depuis le dashboard informaticien.",
    )


def build_audit_context(*, branch):
    return {
        "branch": branch,
        "logs": list(audit_logs_for_branch(branch=branch)[:120]),
    }


def build_import_context(*, branch, classes, selected_class=None, selected_semester=None, feedback=None):
    semesters = list(selected_class.semesters.order_by("number")) if selected_class else []
    ues = list(selected_semester.ues.prefetch_related("ecs").order_by("id")) if selected_semester else []
    student_count = (
        selected_class.enrollments.filter(
            academic_year=selected_class.academic_year,
            is_active=True,
        ).count()
        if selected_class
        else 0
    )
    ec_count = sum(ue.ecs.count() for ue in ues)
    permissions = get_semester_permissions(selected_semester) if selected_semester else None
    state = get_notes_state(academic_class=selected_class, semester=selected_semester) if selected_class and selected_semester else None
    return {
        "branch": branch,
        "classes": classes,
        "selected_class": selected_class,
        "semesters": semesters,
        "selected_semester": selected_semester,
        "ues": ues,
        "student_count": student_count,
        "ec_count": ec_count,
        "workflow_permissions": permissions,
        "notes_state": state,
        "import_preview": _build_import_preview(
            selected_class=selected_class,
            selected_semester=selected_semester,
            ues=ues,
        ),
        "feedback": feedback,
    }


@transaction.atomic
def import_notes_file(*, actor, branch, academic_class, semester, file):
    if academic_class.branch_id != getattr(branch, "id", None):
        raise ValidationError("Classe hors annexe refusee.")
    if semester.academic_class_id != academic_class.id:
        raise ValidationError("Le semestre ne correspond pas a la classe.")

    result = import_grades(file, academic_class, semester)
    has_critical_errors = bool(result.skipped_invalid_scores or result.skipped_unknown_students)
    log_support_action(
        actor=actor,
        branch=branch,
        action_type=SupportAuditLog.ACTION_GRADES_IMPORTED,
        target_label=f"Import notes {academic_class.display_name} S{semester.number}",
        details=f"{result.updated} note(s) importee(s), {len(result.student_issues)} ligne(s) invalide(s).",
    )
    if has_critical_errors:
        message = (
            f"Import refuse: {len(result.student_issues)} erreur(s) critique(s). "
            "Aucune note n'a ete inseree."
        )
    else:
        message = f"{result.updated} note(s) importee(s). {len(result.student_issues)} ligne(s) invalide(s)."
    return ImportFeedback(
        level="error" if has_critical_errors or not result.updated else "success",
        message=message,
        invalid_lines=result.student_issues,
        updated=result.updated,
        skipped_empty=result.skipped_empty,
        skipped_unknown_columns=result.skipped_unknown_columns,
        skipped_unknown_students=result.skipped_unknown_students,
        skipped_invalid_scores=result.skipped_invalid_scores,
        unknown_columns=result.unknown_columns,
    )


def build_structure_context(*, branch):
    classes = list(academic_classes_for_branch(branch=branch)[:120])
    return {
        "branch": branch,
        "classes": classes,
        "active_year": active_academic_year(),
        "classes_without_notes": list(classes_without_notes_for_branch(branch=branch)[:30]),
        "ecs_without_teacher": list(ecs_without_schedule_teacher_for_branch(branch=branch)[:30]),
    }


def build_supervision_context(*, branch):
    classes_without_notes = list(classes_without_notes_for_branch(branch=branch)[:40])
    ecs_without_teacher = list(ecs_without_schedule_teacher_for_branch(branch=branch)[:40])
    enrollments_without_grades = list(enrollments_without_grades_for_branch(branch=branch)[:40])
    alerts = []
    for academic_class in classes_without_notes:
        semester = academic_class.semesters.order_by("number").first()
        query = f"?classe={academic_class.id}"
        if semester:
            query += f"&semester={semester.id}"
        alerts.append({
            "level": "warning",
            "title": "Classe sans notes",
            "detail": academic_class.display_name,
            "action_label": "Ouvrir la classe",
            "action_url": f"{reverse('accounts_portal:it_notes_flow_workspace')}{query}",
        })
    for ec in ecs_without_teacher:
        academic_class = ec.ue.semester.academic_class
        alerts.append({
            "level": "warning",
            "title": "EC sans enseignant planifie",
            "detail": f"{ec.title} - {academic_class.display_name}",
            "action_label": "Voir anomalies",
            "action_url": reverse("accounts_portal:it_structure_workspace"),
        })
    for enrollment in enrollments_without_grades:
        semester = enrollment.academic_class.semesters.order_by("number").first()
        query = f"?classe={enrollment.academic_class_id}"
        if semester:
            query += f"&semester={semester.id}"
        alerts.append({
            "level": "info",
            "title": "Etudiant sans note",
            "detail": f"{enrollment.student} - {enrollment.academic_class.display_name}",
            "action_label": "Corriger les notes",
            "action_url": f"{reverse('accounts_portal:it_notes_flow_workspace')}{query}",
        })
    calculated_not_sent = academic_classes_for_branch(branch=branch).filter(
        semesters__status="FINALIZED",
        is_active=True,
    ).distinct()
    for academic_class in calculated_not_sent[:30]:
        semester = academic_class.semesters.filter(status="FINALIZED").order_by("number").first()
        query = f"?classe={academic_class.id}"
        if semester:
            query += f"&semester={semester.id}"
        alerts.append({
            "level": "info",
            "title": "Resultats calcules non envoyes",
            "detail": academic_class.display_name,
            "action_label": "Envoyer au Directeur",
            "action_url": f"{reverse('accounts_portal:it_notes_flow_workspace')}{query}",
        })
    open_tickets = support_tickets_for_branch(branch=branch).exclude(status=SupportTicket.STATUS_RESOLVED)
    for ticket in open_tickets[:30]:
        alerts.append({
            "level": "warning",
            "title": "Ticket ouvert",
            "detail": f"#{ticket.id} - {ticket.title}",
            "action_label": "Traiter",
            "action_url": reverse("accounts_portal:it_support_flow_workspace"),
        })
    return {
        "branch": branch,
        "alerts": alerts[:80],
    }


def build_catalog_context(*, toast=None):
    return {
        "languages": list(Language.objects.order_by("name")[:120]),
        "professions": list(Profession.objects.order_by("name")[:120]),
        "toast": toast,
    }


def create_catalog_item(*, kind, name, code="", description=""):
    name = (name or "").strip()
    if not name:
        raise ValidationError("Le nom est obligatoire.")
    if kind == "language":
        return Language.objects.create(name=name, code=(code or "").strip())
    if kind == "profession":
        return Profession.objects.create(name=name, description=(description or "").strip())
    raise ValidationError("Type de catalogue invalide.")


def get_branch_settings(*, branch):
    settings, _created = BranchITSettings.objects.get_or_create(branch=branch)
    return settings


def update_branch_settings(*, actor, branch, validation_threshold, active_academic_year, local_config):
    settings = get_branch_settings(branch=branch)
    try:
        settings.validation_threshold = Decimal(str(validation_threshold).replace(",", "."))
    except (InvalidOperation, TypeError):
        raise ValidationError("Seuil de validation invalide.")
    settings.active_academic_year = (active_academic_year or "").strip()
    settings.local_config = (local_config or "").strip()
    settings.updated_by = actor
    settings.full_clean()
    settings.save()
    log_support_action(
        actor=actor,
        branch=branch,
        action_type=SupportAuditLog.ACTION_BRANCH_SETTINGS_UPDATED,
        target_label="Parametres annexe",
        details="Parametres informaticien mis a jour.",
    )
    return settings


def _validate_ticket_branch(*, branch, ticket):
    if branch and ticket.branch_id != branch.id:
        raise ValidationError("Ticket hors annexe refuse.")
