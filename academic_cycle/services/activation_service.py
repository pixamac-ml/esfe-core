from django.core.exceptions import ValidationError
from django.utils import timezone

from academic_cycle import constants
from academic_cycle.models import BranchAcademicCycle
from academic_cycle.services.audit_service import log_action
from academic_cycle.services.dashboard_access_service import compute_student_access_policy
from academic_cycle.services.reenrollment_service import prepare_reenrollments_for_branch


def open_registration_for_year(branch, target_year, actor):
    cycle, _ = BranchAcademicCycle.objects.get_or_create(branch=branch, academic_year=target_year)
    old_status = cycle.status
    cycle.status = constants.BRANCH_CYCLE_REGISTRATION_OPEN
    cycle.registration_open_at = timezone.now()
    cycle.save(update_fields=["status", "registration_open_at", "updated_at"])
    log_action(actor, "branch_cycle.registration_opened", cycle, old_values={"status": old_status}, new_values={"status": cycle.status}, branch=branch, academic_year=target_year)
    return cycle


def activate_academic_year_for_branch(branch, target_year, actor):
    cycle, _ = BranchAcademicCycle.objects.get_or_create(branch=branch, academic_year=target_year)
    old_status = cycle.status
    cycle.status = constants.BRANCH_CYCLE_ACTIVE
    cycle.activated_at = timezone.now()
    cycle.activated_by = actor
    cycle.save(update_fields=["status", "activated_at", "activated_by", "updated_at"])
    log_action(actor, "branch_cycle.activated", cycle, old_values={"status": old_status}, new_values={"status": cycle.status}, branch=branch, academic_year=target_year)
    return cycle


def migrate_branch_dashboards(branch_cycle, target_year, actor):
    if branch_cycle.status not in {constants.BRANCH_CYCLE_CLOSED, constants.BRANCH_CYCLE_ARCHIVED}:
        raise ValidationError("L'ancienne annee doit etre cloturee pour migrer les dashboards.")
    reenrollments = prepare_reenrollments_for_branch(branch_cycle, target_year)
    policies = [compute_student_access_policy(reenrollment.student, target_year) for reenrollment in reenrollments]
    log_action(
        actor,
        "branch_dashboards.migrated",
        branch_cycle,
        new_values={"reenrollments": len(reenrollments), "policies": len(policies)},
        branch=branch_cycle.branch,
        academic_year=target_year,
    )
    return {"reenrollments": reenrollments, "policies": policies}
