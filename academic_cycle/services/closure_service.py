from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from academic_cycle import constants
from academic_cycle.permissions import can_close_branch_cycle
from academic_cycle.services.audit_service import log_action
from academic_cycle.services.readiness_service import generate_closure_report


def start_deliberation(branch_cycle, actor):
    if not can_close_branch_cycle(actor, branch_cycle):
        raise PermissionDenied("Vous n'etes pas autorise a demarrer la deliberation de cette annexe.")
    old_status = branch_cycle.status
    branch_cycle.status = constants.BRANCH_CYCLE_DELIBERATION
    branch_cycle.deliberation_started_at = timezone.now()
    branch_cycle.save(update_fields=["status", "deliberation_started_at", "updated_at"])
    log_action(
        actor,
        "branch_cycle.deliberation_started",
        branch_cycle,
        old_values={"status": old_status},
        new_values={"status": branch_cycle.status},
        branch=branch_cycle.branch,
        academic_year=branch_cycle.academic_year,
    )
    return branch_cycle


@transaction.atomic
def close_branch_cycle(branch_cycle, actor):
    if not can_close_branch_cycle(actor, branch_cycle):
        raise PermissionDenied("Vous n'etes pas autorise a cloturer cette annexe.")
    report = generate_closure_report(branch_cycle, actor=actor)
    if report.status != constants.CLOSURE_REPORT_VALID:
        raise ValidationError("La cloture est impossible: des classes ou controles sont incomplets.")
    old_status = branch_cycle.status
    branch_cycle.status = constants.BRANCH_CYCLE_CLOSED
    branch_cycle.closed_at = timezone.now()
    branch_cycle.closed_by = actor
    branch_cycle.save(update_fields=["status", "closed_at", "closed_by", "updated_at"])
    log_action(
        actor,
        "branch_cycle.closed",
        branch_cycle,
        old_values={"status": old_status},
        new_values={"status": branch_cycle.status, "report_id": report.pk},
        branch=branch_cycle.branch,
        academic_year=branch_cycle.academic_year,
    )
    return branch_cycle


def archive_branch_cycle(branch_cycle, actor):
    if not can_close_branch_cycle(actor, branch_cycle):
        raise PermissionDenied("Vous n'etes pas autorise a archiver cette annexe.")
    if branch_cycle.status != constants.BRANCH_CYCLE_CLOSED:
        raise ValidationError("Seul un cycle cloture peut etre archive.")
    old_status = branch_cycle.status
    branch_cycle.status = constants.BRANCH_CYCLE_ARCHIVED
    branch_cycle.archived_at = timezone.now()
    branch_cycle.archived_by = actor
    branch_cycle.save(update_fields=["status", "archived_at", "archived_by", "updated_at"])
    log_action(
        actor,
        "branch_cycle.archived",
        branch_cycle,
        old_values={"status": old_status},
        new_values={"status": branch_cycle.status},
        branch=branch_cycle.branch,
        academic_year=branch_cycle.academic_year,
    )
    return branch_cycle
