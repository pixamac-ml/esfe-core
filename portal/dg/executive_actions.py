from __future__ import annotations

from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from academic_cycle.constants import (
    BRANCH_CYCLE_ACTIVE,
    BRANCH_CYCLE_CLOSED,
    BRANCH_CYCLE_DRAFT,
    BRANCH_CYCLE_REGISTRATION_OPEN,
)
from accounts.models import BranchMonthlyClosure, Profile
from accounts.position_registry import ANNEX_MANAGER, normalize_position
from academics.models import AcademicClass, AcademicDiplomaAward
from branches.models import Branch
from .audit_service import record_executive_action


def _assert_scope(*, branch_id, academic_year_id, scope_branch_ids, academic_year):
    if scope_branch_ids is not None and branch_id not in scope_branch_ids:
        raise ValidationError("La cible est hors de l'annexe active du contexte DG.")
    if academic_year is not None and academic_year_id is not None and academic_year_id != academic_year.id:
        raise ValidationError("La cible est hors de l'année académique active du contexte DG.")


@transaction.atomic
def nominate_branch_manager(*, actor, branch_id, user_id, scope_branch_ids=None, reason=""):
    branch = Branch.objects.select_for_update().get(pk=branch_id, is_active=True)
    _assert_scope(branch_id=branch.id, academic_year_id=None, scope_branch_ids=scope_branch_ids, academic_year=None)
    candidate = (
        Profile.objects.select_for_update().select_related("user", "branch")
        .filter(user_id=user_id, user__is_active=True, user_type="staff").first()
    )
    if candidate is None:
        raise ValidationError("Le candidat gestionnaire est introuvable ou inactif.")
    if normalize_position(candidate.position) != ANNEX_MANAGER:
        raise ValidationError("Le candidat doit avoir la fonction « Gestionnaire annexe ».")
    if candidate.branch_id not in {None, branch.id}:
        raise ValidationError("Le candidat est affecté à une autre annexe.")
    if branch.manager_id == candidate.user_id:
        return {"ok": True, "message": "Ce gestionnaire est déjà nommé pour cette annexe.", "idempotent": True}
    old_manager_id = branch.manager_id
    branch.manager = candidate.user
    branch.save(update_fields=["manager"])
    if candidate.branch_id is None:
        candidate.branch = branch
        candidate.save(update_fields=["branch", "updated_at"])
    record_executive_action(
        actor=actor, action="manager_nominated", target=branch, domain="support", branch=branch,
        old_state={"manager_id": old_manager_id}, new_state={"manager_id": candidate.user_id},
        reason=reason, target_user=candidate.user, target_label=branch.name,
    )
    return {"ok": True, "message": f"{candidate.user.get_full_name() or candidate.user.username} nommé gestionnaire de {branch.name}."}


@transaction.atomic
def publish_class_diplomas(*, actor, class_id, scope_branch_ids=None, academic_year=None, reason=""):
    academic_class = AcademicClass.objects.select_for_update().select_related("branch", "academic_year").get(pk=class_id, is_active=True)
    _assert_scope(
        branch_id=academic_class.branch_id, academic_year_id=academic_class.academic_year_id,
        scope_branch_ids=scope_branch_ids, academic_year=academic_year,
    )
    awards = AcademicDiplomaAward.objects.select_for_update().filter(
        academic_class=academic_class, status=AcademicDiplomaAward.STATUS_READY,
    )
    count = awards.count()
    if count == 0:
        return {"ok": True, "message": "Aucun diplôme prêt à délivrer pour cette classe.", "idempotent": True}
    awards.update(status=AcademicDiplomaAward.STATUS_DELIVERED, delivered_by=actor, delivered_at=timezone.now(), awarded_at=date.today())
    record_executive_action(
        actor=actor, action="diplomas_delivered", target=academic_class, domain="academic",
        branch=academic_class.branch, academic_year=academic_class.academic_year,
        old_state={"ready_awards": count}, new_state={"delivered_awards": count}, reason=reason,
    )
    return {"ok": True, "message": f"{count} diplôme(s) délivré(s) pour cette classe."}


@transaction.atomic
def deliver_diploma(*, actor, award_id, scope_branch_ids=None, academic_year=None, reason=""):
    award = (
        AcademicDiplomaAward.objects.select_for_update().select_related("student", "branch", "academic_year")
        .get(pk=award_id, status=AcademicDiplomaAward.STATUS_READY)
    )
    _assert_scope(
        branch_id=award.branch_id, academic_year_id=award.academic_year_id,
        scope_branch_ids=scope_branch_ids, academic_year=academic_year,
    )
    award.status = AcademicDiplomaAward.STATUS_DELIVERED
    award.delivered_by = actor
    award.delivered_at = timezone.now()
    award.awarded_at = date.today()
    award.save(update_fields=["status", "delivered_by", "delivered_at", "awarded_at"])
    record_executive_action(
        actor=actor, action="diploma_delivered", target=award, domain="academic", branch=award.branch,
        academic_year=award.academic_year, old_state={"status": AcademicDiplomaAward.STATUS_READY},
        new_state={"status": award.status, "delivered_by_id": actor.id}, reason=reason,
    )
    return {"ok": True, "message": f"Diplôme délivré pour {award.student}."}


@transaction.atomic
def validate_closure(*, actor, closure_id, scope_branch_ids=None, academic_year=None, reason=""):
    closure = (
        BranchMonthlyClosure.objects.select_for_update().select_related("branch")
        .get(pk=closure_id, status=BranchMonthlyClosure.STATUS_DRAFT)
    )
    _assert_scope(branch_id=closure.branch_id, academic_year_id=None, scope_branch_ids=scope_branch_ids, academic_year=None)
    if academic_year is not None and not academic_year.start_date <= closure.period_month <= academic_year.end_date:
        raise ValidationError("La clôture est hors de l'année académique active du contexte DG.")
    closure.status = BranchMonthlyClosure.STATUS_VALIDATED
    closure.validated_by = actor
    closure.validated_at = timezone.now()
    closure.save(update_fields=["status", "validated_by", "validated_at"])
    record_executive_action(
        actor=actor, action="monthly_closure_validated", target=closure, domain="finance", branch=closure.branch,
        old_state={"status": BranchMonthlyClosure.STATUS_DRAFT},
        new_state={"status": closure.status, "validated_by_id": actor.id}, reason=reason,
    )
    return {"ok": True, "message": f"Clôture de {closure.branch} ({closure.period_month:%Y-%m}) validée."}


@transaction.atomic
def transition_branch_cycle(*, actor, cycle_id, target_status, scope_branch_ids=None, academic_year=None, reason=""):
    from academic_cycle.models import BranchAcademicCycle

    cycle = BranchAcademicCycle.objects.select_for_update().select_related("branch", "academic_year").get(pk=cycle_id)
    _assert_scope(
        branch_id=cycle.branch_id, academic_year_id=cycle.academic_year_id,
        scope_branch_ids=scope_branch_ids, academic_year=academic_year,
    )
    allowed = {
        BRANCH_CYCLE_DRAFT: [BRANCH_CYCLE_REGISTRATION_OPEN],
        BRANCH_CYCLE_REGISTRATION_OPEN: [BRANCH_CYCLE_ACTIVE],
        BRANCH_CYCLE_ACTIVE: [BRANCH_CYCLE_CLOSED],
    }
    if target_status not in allowed.get(cycle.status, []):
        raise ValidationError(f"Transition {cycle.status} -> {target_status} non autorisée.")
    old_status = cycle.status
    cycle.status = target_status
    if target_status == BRANCH_CYCLE_REGISTRATION_OPEN:
        cycle.registration_open_at = timezone.now()
    elif target_status == BRANCH_CYCLE_ACTIVE:
        cycle.activated_by, cycle.activated_at = actor, timezone.now()
    elif target_status == BRANCH_CYCLE_CLOSED:
        cycle.closed_by, cycle.closed_at = actor, timezone.now()
    cycle.save()
    record_executive_action(
        actor=actor, action="branch_cycle_transitioned", target=cycle, domain="academic", branch=cycle.branch,
        academic_year=cycle.academic_year, old_state={"status": old_status}, new_state={"status": target_status}, reason=reason,
    )
    label = dict(cycle._meta.get_field("status").flatchoices).get(target_status, target_status)
    return {"ok": True, "message": f"Cycle {cycle.branch}/{cycle.academic_year} passé à « {label} »."}
