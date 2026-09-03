"""Audit transactionnel des decisions executives DG.

Cette couche ne remplace aucun journal existant. Elle choisit le journal deja
adapte au domaine de l'action et doit etre appelee depuis une transaction
metier deja ouverte.
"""

from __future__ import annotations

import json

from academic_cycle.services.audit_service import log_action
from accounts.models import FinancialAuditLog
from portal.models import SupportAuditLog


def record_executive_action(
    *,
    actor,
    action,
    target,
    domain,
    branch=None,
    academic_year=None,
    old_state=None,
    new_state=None,
    reason="",
    target_user=None,
    target_label="",
):
    """Persist the audit entry matching the business domain of a DG action."""

    old_state = old_state or {}
    new_state = new_state or {}
    if reason:
        new_state = {**new_state, "reason": reason}
    if academic_year is not None:
        new_state = {**new_state, "academic_year": str(academic_year)}
    if domain == "finance":
        return FinancialAuditLog.objects.create(
            branch=branch,
            action_type=action,
            target_model=f"{target._meta.app_label}.{target._meta.model_name}",
            target_id=target.pk,
            previous_state=old_state,
            new_state=new_state,
            performed_by=actor,
        )
    if domain == "academic":
        return log_action(
            actor,
            action,
            target,
            old_values=old_state,
            new_values=new_state,
            reason=reason,
            branch=branch,
            academic_year=academic_year,
        )

    details = json.dumps(
        {
            "domain": domain,
            "old_state": old_state,
            "new_state": new_state,
            "reason": reason,
        },
        ensure_ascii=False,
        default=str,
    )
    return SupportAuditLog.objects.create(
        branch=branch,
        actor=actor,
        target_user=target_user,
        action_type=SupportAuditLog.ACTION_MANAGER_NOMINATED,
        target_label=target_label or str(target),
        details=details,
    )
