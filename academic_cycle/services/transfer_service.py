from django.utils import timezone

from academic_cycle.models import TransferRequest
from academic_cycle.services.audit_service import log_action


def create_transfer_request(student, data):
    request = TransferRequest.objects.create(student=student, **data)
    return request


def review_transfer_request(request, actor):
    request.status = TransferRequest.STATUS_UNDER_REVIEW
    request.reviewed_by = actor
    request.reviewed_at = timezone.now()
    request.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
    log_action(actor, "transfer.under_review", request, branch=request.source_branch, academic_year=request.source_academic_year, student=request.student)
    return request


def approve_transfer_request(request, actor):
    request.status = TransferRequest.STATUS_APPROVED
    request.reviewed_by = actor
    request.reviewed_at = timezone.now()
    request.decision_note = request.decision_note or "Transfert approuve."
    request.save(update_fields=["status", "reviewed_by", "reviewed_at", "decision_note", "updated_at"])
    log_action(actor, "transfer.approved", request, branch=request.source_branch, academic_year=request.source_academic_year, student=request.student)
    return request


def reject_transfer_request(request, actor, reason):
    request.status = TransferRequest.STATUS_REJECTED
    request.reviewed_by = actor
    request.reviewed_at = timezone.now()
    request.decision_note = reason
    request.save(update_fields=["status", "reviewed_by", "reviewed_at", "decision_note", "updated_at"])
    log_action(
        actor,
        "transfer.rejected",
        request,
        reason=reason,
        branch=request.source_branch,
        academic_year=request.source_academic_year,
        student=request.student,
    )
    return request
