"""Server-side roles and capabilities for the shared manager workspace."""

from __future__ import annotations

from dataclasses import dataclass
from functools import wraps

from django.conf import settings
from django.http import HttpResponse

from accounts.access import get_user_position
from accounts.dashboards.helpers import get_user_branch, is_manager
from accounts.dashboards.permissions import check_admissions_access, check_finance_access


MANAGER_SECTIONS = frozenset(
    {
        "overview",
        "candidatures",
        "inscriptions",
        "reenrollment",
        "paiements",
        "salaires",
        "honoraires",
        "depenses",
        "caisse",
        "rapport",
        "cloture",
        "boutique",
        "dons",
        "settings",
    }
)

MANAGER_CAPABILITIES = frozenset(
    {
        "view_manager_workspace",
        "manage_all_manager_modules",
        "view_payments",
        "validate_payment",
        "cancel_payment",
        "correct_payment",
        "manage_cash_sessions",
        "view_reenrollment_finance",
        "view_admissions",
        "manage_admissions",
        "delete_candidature",
        "view_inscriptions",
        "create_inscription",
        "apply_coupon",
    }
)

FINANCE_MANAGER_CAPABILITIES = frozenset(
    {
        "view_manager_workspace",
        "view_payments",
        "validate_payment",
        "cancel_payment",
        "correct_payment",
        "manage_cash_sessions",
        "view_reenrollment_finance",
    }
)

PAYMENT_AGENT_CAPABILITIES = frozenset(
    {
        "view_manager_workspace",
        "view_payments",
        "validate_payment",
        "cancel_payment",
        "manage_cash_sessions",
        "view_reenrollment_finance",
    }
)

ADMISSIONS_CAPABILITIES = frozenset(
    {
        "view_manager_workspace",
        "view_admissions",
        "manage_admissions",
        "delete_candidature",
        "view_inscriptions",
        "create_inscription",
    }
)


@dataclass(frozen=True, slots=True)
class ManagerWorkspaceAccess:
    position: str
    branch: object
    default_section: str
    allowed_sections: frozenset[str]
    capabilities: frozenset[str]

    def can(self, capability):
        return capability in self.capabilities

    def capabilities_context(self):
        known = (
            MANAGER_CAPABILITIES
            | FINANCE_MANAGER_CAPABILITIES
            | PAYMENT_AGENT_CAPABILITIES
            | ADMISSIONS_CAPABILITIES
        )
        return {f"can_{name}": name in self.capabilities for name in known}


def resolve_manager_workspace_access(user, *, request=None):
    """Resolve a branch-scoped access contract without trusting the template."""

    if not getattr(user, "is_authenticated", False):
        return None

    position = get_user_position(user)
    branch = get_user_branch(user)

    if settings.AUTH_POLICY_V2_ENABLED and request is not None:
        from accounts.access_context import get_request_access_context

        access_context = get_request_access_context(request)
        if not access_context.is_valid or access_context.context_type != "SYSTEM":
            return None
        position = access_context.position
        branch = access_context.branch

    if branch is None:
        return None

    manager_position = position in {"annex_manager", "branch_manager"}
    finance_position = position in {"finance_manager", "payment_agent"}
    admissions_position = position == "admissions"

    if manager_position or (
        not manager_position
        and not finance_position
        and not admissions_position
        and not settings.AUTH_POLICY_V2_ENABLED
        and is_manager(user)
    ):
        return ManagerWorkspaceAccess(
            position="annex_manager",
            branch=branch,
            default_section="overview",
            allowed_sections=MANAGER_SECTIONS,
            capabilities=MANAGER_CAPABILITIES,
        )

    if finance_position or (
        not manager_position
        and not finance_position
        and not admissions_position
        and not settings.AUTH_POLICY_V2_ENABLED
        and check_finance_access(user)
    ):
        normalized_position = position if position in {"finance_manager", "payment_agent"} else "finance_manager"
        capabilities = (
            PAYMENT_AGENT_CAPABILITIES
            if normalized_position == "payment_agent"
            else FINANCE_MANAGER_CAPABILITIES
        )
        return ManagerWorkspaceAccess(
            position=normalized_position,
            branch=branch,
            default_section="paiements",
            allowed_sections=frozenset({"paiements", "reenrollment", "settings"}),
            capabilities=capabilities,
        )

    if admissions_position or (
        not manager_position
        and not finance_position
        and not admissions_position
        and not settings.AUTH_POLICY_V2_ENABLED
        and check_admissions_access(user)
    ):
        return ManagerWorkspaceAccess(
            position="admissions",
            branch=branch,
            default_section="candidatures",
            allowed_sections=frozenset({"candidatures", "inscriptions", "settings"}),
            capabilities=ADMISSIONS_CAPABILITIES,
        )

    return None


def manager_workspace_required(capability="view_manager_workspace"):
    """Authorize one capability and attach the trusted branch to the request."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            access = resolve_manager_workspace_access(request.user, request=request)
            if access is None or not access.can(capability):
                return HttpResponse("Non autorise", status=403)
            request.branch = access.branch
            request.manager_workspace_access = access
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


manager_full_access_required = manager_workspace_required("manage_all_manager_modules")
