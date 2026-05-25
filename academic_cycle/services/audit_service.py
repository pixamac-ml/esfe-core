from django.forms.models import model_to_dict

from academic_cycle.models import AcademicAuditLog


def serialize_instance(instance, fields=None):
    if instance is None:
        return None
    try:
        return model_to_dict(instance, fields=fields)
    except Exception:
        return {"repr": str(instance)}


def log_action(
    actor,
    action,
    obj,
    old_values=None,
    new_values=None,
    reason="",
    branch=None,
    academic_year=None,
    student=None,
    request=None,
):
    ip_address = None
    user_agent = ""
    if request is not None:
        ip_address = request.META.get("HTTP_X_FORWARDED_FOR", request.META.get("REMOTE_ADDR", "")).split(",")[0] or None
        user_agent = request.META.get("HTTP_USER_AGENT", "")[:255]

    return AcademicAuditLog.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        branch=branch,
        academic_year=academic_year,
        student=student,
        action=action,
        object_type=f"{obj._meta.app_label}.{obj._meta.model_name}",
        object_id=str(obj.pk),
        old_values=old_values,
        new_values=new_values,
        reason=reason,
        ip_address=ip_address,
        user_agent=user_agent,
    )
