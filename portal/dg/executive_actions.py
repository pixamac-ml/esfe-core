from __future__ import annotations

from datetime import date

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from academic_cycle.constants import (
    BRANCH_CYCLE_ACTIVE,
    BRANCH_CYCLE_CLOSED,
    BRANCH_CYCLE_DRAFT,
    BRANCH_CYCLE_REGISTRATION_OPEN,
)
from accounts.models import BranchMonthlyClosure
from academics.models import AcademicClass, AcademicDiplomaAward
from branches.models import Branch
from students.models import StudentYearDecision

User = get_user_model()


@transaction.atomic
def nominate_branch_manager(*, actor: User, branch_id: int, user_id: int) -> dict:
    """DG nomme un gestionnaire pour une annexe."""
    branch = Branch.objects.select_for_update().get(pk=branch_id, is_active=True)
    manager = User.objects.select_for_update().get(pk=user_id, is_active=True)
    branch.manager = manager
    branch.save(update_fields=["manager"])
    return {
        "ok": True,
        "message": f"{manager.get_full_name()} nommé gestionnaire de {branch.name}.",
    }


@transaction.atomic
def publish_class_diplomas(*, actor: User, class_id: int) -> dict:
    """DG délivre tous les diplômes prêts d'une classe (ready -> delivered)."""
    awards = AcademicDiplomaAward.objects.select_for_update().filter(
        academic_class_id=class_id,
        status=AcademicDiplomaAward.STATUS_READY,
    )
    count = awards.count()
    now = timezone.now()
    today = date.today()
    awards.update(
        status=AcademicDiplomaAward.STATUS_DELIVERED,
        delivered_by=actor,
        delivered_at=now,
        awarded_at=today,
    )
    return {
        "ok": True,
        "message": f"{count} diplôme(s) délivré(s) pour cette classe.",
    }


@transaction.atomic
def deliver_diploma(*, actor: User, award_id: int) -> dict:
    """DG délivre un diplôme (ready -> delivered)."""
    award = AcademicDiplomaAward.objects.select_for_update().get(
        pk=award_id,
        status=AcademicDiplomaAward.STATUS_READY,
    )
    award.status = AcademicDiplomaAward.STATUS_DELIVERED
    award.delivered_by = actor
    award.delivered_at = timezone.now()
    award.awarded_at = date.today()
    award.save(update_fields=["status", "delivered_by", "delivered_at", "awarded_at"])
    return {
        "ok": True,
        "message": f"Diplôme délivré pour {award.student}.",
    }


@transaction.atomic
def validate_closure(*, actor: User, closure_id: int) -> dict:
    """DG valide une clôture mensuelle (draft -> validated)."""
    closure = BranchMonthlyClosure.objects.select_for_update().get(
        pk=closure_id,
        status=BranchMonthlyClosure.STATUS_DRAFT,
    )
    closure.status = BranchMonthlyClosure.STATUS_VALIDATED
    closure.validated_by = actor
    closure.validated_at = timezone.now()
    closure.save(update_fields=["status", "validated_by", "validated_at"])
    return {
        "ok": True,
        "message": f"Clôture de {closure.branch} ({closure.period_month:%Y-%m}) validée.",
    }


@transaction.atomic
def arbitrate_decision(*, actor: User, decision_id: int, approve: bool, reason: str = "") -> dict:
    """DG arbitre une décision d'orientation bloquée après validation académique+finance."""
    decision = StudentYearDecision.objects.select_for_update().select_related("student", "source_class").get(
        pk=decision_id,
        workflow_status=StudentYearDecision.WORKFLOW_FINANCE_VALIDATED,
    )
    if approve:
        decision.workflow_status = StudentYearDecision.WORKFLOW_APPLIED
        decision.applied_by = actor
        decision.applied_at = timezone.now()
        decision.note = (decision.note + "\n---\n" + reason).strip() if reason else decision.note
        decision.save(update_fields=["workflow_status", "applied_by", "applied_at", "note"])
        msg = f"Décision approuvée pour {decision.student}."
    else:
        decision.workflow_status = StudentYearDecision.WORKFLOW_REJECTED
        decision.rejected_by = actor
        decision.rejected_at = timezone.now()
        decision.rejection_reason = reason or "Rejetée par la Direction Générale."
        decision.save(update_fields=["workflow_status", "rejected_by", "rejected_at", "rejection_reason"])
        msg = f"Décision rejetée pour {decision.student}."
    return {"ok": True, "message": msg}


@transaction.atomic
def transition_branch_cycle(*, actor: User, cycle_id: int, target_status: str) -> dict:
    """DG fait transiter un cycle académique d'annexe (draft->registration_open->active->closed)."""
    from academic_cycle.models import BranchAcademicCycle

    cycle = BranchAcademicCycle.objects.select_for_update().select_related("branch", "academic_year").get(pk=cycle_id)
    allowed = {
        BRANCH_CYCLE_DRAFT: [BRANCH_CYCLE_REGISTRATION_OPEN],
        BRANCH_CYCLE_REGISTRATION_OPEN: [BRANCH_CYCLE_ACTIVE],
        BRANCH_CYCLE_ACTIVE: [BRANCH_CYCLE_CLOSED],
    }
    transitions = allowed.get(cycle.status, [])
    if target_status not in transitions:
        return {
            "ok": False,
            "message": f"Transition {cycle.status} -> {target_status} non autorisée.",
        }
    cycle.status = target_status
    if target_status == BRANCH_CYCLE_REGISTRATION_OPEN:
        cycle.registration_open_at = timezone.now()
    elif target_status == BRANCH_CYCLE_ACTIVE:
        cycle.activated_by = actor
        cycle.activated_at = timezone.now()
    elif target_status == BRANCH_CYCLE_CLOSED:
        cycle.closed_by = actor
        cycle.closed_at = timezone.now()
    cycle.save()
    label = dict(cycle._meta.get_field("status").flatchoices).get(target_status, target_status)
    return {
        "ok": True,
        "message": f"Cycle {cycle.branch}/{cycle.academic_year} passé à « {label} ».",
    }
