"""Contexte d'accès institutionnel calculé une seule fois par requête."""

from dataclasses import dataclass

from accounts.access import get_user_annexe
from accounts.position_registry import get_position_definition, normalize_position


@dataclass(frozen=True)
class AccessContext:
    user: object
    context_type: str
    position: str | None
    category: str | None
    scope: str | None
    branch: object | None
    account_state: str
    capabilities: frozenset[str]
    is_valid: bool
    reason_code: str


def build_access_context(user):
    if not getattr(user, "is_authenticated", False):
        return AccessContext(user, "ANONYMOUS", None, None, None, None, "anonymous", frozenset(), False, "anonymous")

    profile = getattr(user, "profile", None)
    institutional_profile = getattr(user, "institutional_profile", None)
    # Policy V2 ne déduit jamais une position depuis un groupe, ``role``,
    # ``is_staff`` ou un objet métier historique. Une position SYSTEM doit être
    # une affectation institutionnelle explicite.
    raw_position = getattr(institutional_profile, "position", None)
    if institutional_profile is None:
        raw_position = getattr(profile, "position", None)
    position = normalize_position(raw_position) or None
    definition = get_position_definition(position)
    context_type = "SYSTEM" if definition else "PUBLIC"
    if definition and institutional_profile is not None:
        branch = institutional_profile.branch
    else:
        branch = get_user_annexe(user) if definition else None

    support_state = getattr(user, "support_state", None)
    if not user.is_active:
        account_state = "inactive"
    elif support_state and support_state.is_suspended:
        account_state = "suspended"
    elif support_state and support_state.is_blocked:
        account_state = "blocked"
    elif support_state and support_state.must_change_password:
        account_state = "password_change_required"
    else:
        account_state = "active"

    reason_code = "allowed"
    is_valid = account_state in {"active", "password_change_required"}
    if definition and definition.branch_required and branch is None:
        is_valid = False
        reason_code = "branch_required"
    elif not definition:
        reason_code = "public_context"
    elif not is_valid:
        reason_code = f"account_{account_state}"

    return AccessContext(
        user=user,
        context_type=context_type,
        position=position,
        category=definition.category if definition else None,
        scope=definition.scope if definition else None,
        branch=branch,
        account_state=account_state,
        capabilities=frozenset(user.get_all_permissions()),
        is_valid=is_valid,
        reason_code=reason_code,
    )


def get_request_access_context(request):
    if not hasattr(request, "_esfe_access_context"):
        request._esfe_access_context = build_access_context(request.user)
    return request._esfe_access_context
