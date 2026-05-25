from django.db import transaction
from django.utils import timezone

from academic_cycle import constants
from academic_cycle.models import AcademicReEnrollment, StudentYearDecision
from academic_cycle.services.audit_service import log_action


def prepare_reenrollment_for_student(student, decision, target_year):
    target_class = decision.target_class
    if not target_class and decision.decision == constants.DECISION_REPEATED:
        target_class = decision.current_class
    reenrollment, _ = AcademicReEnrollment.objects.update_or_create(
        student=student,
        target_academic_year=target_year,
        defaults={
            "source_academic_year": decision.academic_year,
            "source_class": decision.current_class,
            "target_class": target_class,
            "branch": decision.branch,
            "status": AcademicReEnrollment.STATUS_PREPARED,
            "prepared_by_system": True,
        },
    )
    return reenrollment


def prepare_reenrollments_for_branch(branch_cycle, target_year):
    prepared = []
    decisions = StudentYearDecision.objects.filter(
        branch=branch_cycle.branch,
        academic_year=branch_cycle.academic_year,
        decision__in=["promoted", "promoted_with_academic_debt", "repeated"],
    ).select_related("student", "current_class", "target_class", "branch")
    for decision in decisions:
        prepared.append(prepare_reenrollment_for_student(decision.student, decision, target_year))
    return prepared


def start_reenrollment(reenrollment, actor):
    reenrollment.status = AcademicReEnrollment.STATUS_STARTED
    reenrollment.started_at = timezone.now()
    reenrollment.save(update_fields=["status", "started_at", "updated_at"])
    log_action(actor, "reenrollment.started", reenrollment, branch=reenrollment.branch, academic_year=reenrollment.target_academic_year, student=reenrollment.student)
    return reenrollment


def submit_reenrollment(reenrollment, data, actor):
    reenrollment.status = AcademicReEnrollment.STATUS_PENDING_PAYMENT
    reenrollment.submitted_at = timezone.now()
    reenrollment.save(update_fields=["status", "submitted_at", "updated_at"])
    log_action(
        actor,
        "reenrollment.submitted",
        reenrollment,
        new_values={"data": data},
        branch=reenrollment.branch,
        academic_year=reenrollment.target_academic_year,
        student=reenrollment.student,
    )
    return reenrollment


def mark_payment_validated(reenrollment, payment):
    reenrollment.status = AcademicReEnrollment.STATUS_PAYMENT_VALIDATED
    reenrollment.payment_validated_at = timezone.now()
    reenrollment.save(update_fields=["status", "payment_validated_at", "updated_at"])
    return reenrollment


@transaction.atomic
def activate_reenrollment(reenrollment, actor):
    reenrollment.status = AcademicReEnrollment.STATUS_ACTIVATED
    reenrollment.activated_at = timezone.now()
    reenrollment.save(update_fields=["status", "activated_at", "updated_at"])
    log_action(
        actor,
        "reenrollment.activated",
        reenrollment,
        branch=reenrollment.branch,
        academic_year=reenrollment.target_academic_year,
        student=reenrollment.student,
    )
    return reenrollment
