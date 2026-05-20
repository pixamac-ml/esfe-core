from __future__ import annotations

from django.db import transaction

from portal.models import SupportAuditLog, SupportTicket
from students.models import AttendanceAlert, StudentCase, StudentCaseNote


def _audit(*, actor, branch, action_type, target_label, details=""):
    SupportAuditLog.objects.create(
        actor=actor,
        branch=branch,
        action_type=action_type,
        target_label=target_label,
        details=details,
    )


@transaction.atomic
def resolve_attendance_alert(*, actor, alert_id):
    alert = AttendanceAlert.objects.select_for_update().select_related("branch", "student").get(id=alert_id)
    if alert.is_resolved:
        return {"message": "Alerte deja resolue.", "status": "done"}
    alert.is_resolved = True
    alert.save(update_fields=["is_resolved"])
    _audit(
        actor=actor,
        branch=alert.branch,
        action_type=SupportAuditLog.ACTION_TICKET_STATUS_CHANGED,
        target_label=f"Alerte assiduite #{alert.id}",
        details=f"Alerte resolue par le DG pour {alert.student}.",
    )
    return {"message": "Alerte resolue.", "status": "done", "refresh": "alerts"}


@transaction.atomic
def resolve_student_case(*, actor, case_id):
    case = StudentCase.objects.select_for_update().select_related("branch", "student").get(id=case_id)
    if case.status == StudentCase.STATUS_RESOLU:
        return {"message": "Cas deja resolu.", "status": "done"}
    case.resolve(actor)
    _audit(
        actor=actor,
        branch=case.branch,
        action_type=SupportAuditLog.ACTION_TICKET_STATUS_CHANGED,
        target_label=f"Cas etudiant #{case.id}",
        details=f"Cas resolu par le DG: {case.title}",
    )
    return {"message": "Cas etudiant resolu.", "status": "done", "refresh": "alerts"}


@transaction.atomic
def escalate_student_case(*, actor, case_id):
    case = StudentCase.objects.select_for_update().select_related("branch", "student").get(id=case_id)
    if case.status == StudentCase.STATUS_ESCALADE:
        return {"message": "Cas deja escalade.", "status": "done"}
    case.status = StudentCase.STATUS_ESCALADE
    case.save(update_fields=["status", "updated_at"])
    StudentCaseNote.objects.create(
        case=case,
        author=actor,
        content="Cas escalade depuis le dashboard DG.",
    )
    _audit(
        actor=actor,
        branch=case.branch,
        action_type=SupportAuditLog.ACTION_TICKET_STATUS_CHANGED,
        target_label=f"Cas etudiant #{case.id}",
        details=f"Cas escalade par le DG: {case.title}",
    )
    return {"message": "Cas escalade a la direction.", "status": "done", "refresh": "alerts"}


def create_finance_followup(*, actor, branch):
    title = f"Suivi finance DG - {branch.name}"
    open_tickets = list(
        SupportTicket.objects.filter(
            branch=branch,
            title=title,
            status__in=[SupportTicket.STATUS_OPEN, SupportTicket.STATUS_IN_PROGRESS],
        ).order_by("-created_at", "-id")
    )
    ticket = open_tickets[0] if open_tickets else None
    for duplicate in open_tickets[1:]:
        duplicate.status = SupportTicket.STATUS_REJECTED
        duplicate.resolution = "Doublon ferme automatiquement par l'action DG."
        duplicate.resolved_by = actor
        duplicate.save(update_fields=["status", "resolution", "resolved_by", "updated_at"])
    created = ticket is None
    if created:
        ticket = SupportTicket.objects.create(
            branch=branch,
            title=title,
            description="Demande DG: clarifier les paiements en attente et fournir une synthese de recouvrement.",
            category=SupportTicket.CATEGORY_OTHER,
            priority=SupportTicket.PRIORITY_HIGH,
            requester_user=actor,
            created_by=actor,
        )
    if created:
        _audit(
            actor=actor,
            branch=branch,
            action_type=SupportAuditLog.ACTION_TICKET_CREATED,
            target_label=f"Ticket #{ticket.id}",
            details="Ticket de suivi finance cree depuis le dashboard DG.",
        )
        return {"message": f"Ticket finance #{ticket.id} cree.", "status": "done", "refresh": "finance"}
    return {"message": f"Ticket finance #{ticket.id} deja ouvert.", "status": "done", "refresh": "finance"}
