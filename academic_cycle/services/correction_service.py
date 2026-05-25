from django.core.exceptions import PermissionDenied
from django.utils import timezone

from academic_cycle.models import AcademicCorrectionRequest
from academic_cycle.permissions import can_handle_correction
from academic_cycle.services.audit_service import log_action, serialize_instance


def submit_correction_request(**kwargs):
    correction = AcademicCorrectionRequest.objects.create(**kwargs)
    log_action(
        kwargs.get("submitted_by"),
        "correction.submitted",
        correction,
        branch=correction.branch,
        academic_year=correction.academic_year,
        student=correction.student,
    )
    return correction


def assign_correction_request(correction, assignee, actor):
    if not can_handle_correction(actor, correction):
        raise PermissionDenied("Vous n'etes pas autorise a assigner cette correction.")
    correction.status = AcademicCorrectionRequest.STATUS_ASSIGNED
    correction.assigned_to = assignee
    correction.save(update_fields=["status", "assigned_to", "updated_at"])
    log_action(actor, "correction.assigned", correction, new_values={"assigned_to": assignee.pk}, branch=correction.branch, academic_year=correction.academic_year, student=correction.student)
    return correction


def resolve_correction_request(correction, actor, resolution_note):
    if not can_handle_correction(actor, correction):
        raise PermissionDenied("Vous n'etes pas autorise a resoudre cette correction.")
    correction.status = AcademicCorrectionRequest.STATUS_RESOLVED
    correction.resolved_by = actor
    correction.resolved_at = timezone.now()
    correction.resolution_note = resolution_note
    correction.save(update_fields=["status", "resolved_by", "resolved_at", "resolution_note", "updated_at"])
    log_action(actor, "correction.resolved", correction, new_values={"resolution_note": resolution_note}, branch=correction.branch, academic_year=correction.academic_year, student=correction.student)
    return correction


def apply_post_publication_correction(obj, updates, actor, reason, branch=None, academic_year=None, student=None):
    old_values = serialize_instance(obj, fields=list(updates.keys()))
    for field, value in updates.items():
        setattr(obj, field, value)
    obj.save(update_fields=list(updates.keys()))
    log_action(
        actor,
        "post_publication.corrected",
        obj,
        old_values=old_values,
        new_values=serialize_instance(obj, fields=list(updates.keys())),
        reason=reason,
        branch=branch,
        academic_year=academic_year,
        student=student,
    )
    return obj
