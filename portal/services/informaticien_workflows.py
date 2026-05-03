from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse

from academics.imports.import_service import import_grades
from academics.models import Language, Profession
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
    return {
        "branch": branch,
        "classes": classes,
        "selected_class": selected_class,
        "semesters": list(selected_class.semesters.order_by("number")) if selected_class else [],
        "selected_semester": selected_semester,
        "feedback": feedback,
    }


@transaction.atomic
def import_notes_file(*, actor, branch, academic_class, semester, file):
    if academic_class.branch_id != getattr(branch, "id", None):
        raise ValidationError("Classe hors annexe refusee.")
    if semester.academic_class_id != academic_class.id:
        raise ValidationError("Le semestre ne correspond pas a la classe.")

    result = import_grades(file, academic_class, semester)
    log_support_action(
        actor=actor,
        branch=branch,
        action_type=SupportAuditLog.ACTION_GRADES_IMPORTED,
        target_label=f"Import notes {academic_class.display_name} S{semester.number}",
        details=f"{result.updated} note(s) importee(s), {len(result.student_issues)} ligne(s) invalide(s).",
    )
    return ImportFeedback(
        level="success" if result.updated else "error",
        message=f"{result.updated} note(s) importee(s). {len(result.student_issues)} ligne(s) invalide(s).",
        invalid_lines=result.student_issues,
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
