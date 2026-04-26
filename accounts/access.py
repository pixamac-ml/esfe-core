"""Couche centrale de compatibilite pour les acces ESFE."""

from __future__ import annotations

import logging

from branches.models import Branch
from payments.models import PaymentAgent

logger = logging.getLogger(__name__)


PROFILE_ROLE_TO_CANONICAL = {
    "student": "student",
    "teacher": "teacher",
    "admissions": "staff_admin",
    "finance": "staff_admin",
    "executive": "directeur_etudes",
    "superadmin": "super_admin",
}

POSITION_TO_CANONICAL = {
    "student": "student",
    "teacher": "teacher",
    "finance_manager": "staff_admin",
    "payment_agent": "staff_admin",
    "secretary": "staff_admin",
    "admissions": "staff_admin",
    "director_of_studies": "directeur_etudes",
    "executive_director": "directeur_etudes",
    "branch_manager": "staff_admin",
    "academic_supervisor": "staff_admin",
    "super_admin": "super_admin",
}

GROUP_COMPAT_CLUSTERS = (
    ("admissions_managers", "admissions"),
    ("finance_agents", "finance"),
    ("executive_director", "executive"),
    ("gestionnaire", "manager"),
)

GROUP_TO_CANONICAL = {
    "admissions_managers": "staff_admin",
    "admissions": "staff_admin",
    "finance_agents": "staff_admin",
    "finance": "staff_admin",
    "gestionnaire": "staff_admin",
    "manager": "staff_admin",
    "executive_director": "directeur_etudes",
    "executive": "directeur_etudes",
}

ACCESS_RULES = {
    ("view_dashboard", "admissions"): {
        "groups": {"admissions_managers", "admissions"},
        "profile_roles": {"admissions"},
        "positions": {"admissions", "secretary"},
        "canonical_roles": set(),
        "allow_global": True,
    },
    ("view_dashboard", "finance"): {
        "groups": {"finance_agents", "finance"},
        "profile_roles": {"finance"},
        "positions": {"finance_manager", "payment_agent"},
        "canonical_roles": set(),
        "allow_global": True,
    },
    ("view_dashboard", "executive"): {
        "groups": {"executive_director", "executive"},
        "profile_roles": {"executive", "superadmin"},
        "positions": {"director_of_studies", "executive_director", "super_admin"},
        "canonical_roles": {"directeur_etudes", "super_admin"},
        "allow_global": True,
    },
    ("view_dashboard", "manager"): {
        "groups": {"gestionnaire", "manager"},
        "profile_roles": set(),
        "positions": {"branch_manager"},
        "canonical_roles": set(),
        "allow_global": False,
    },
    ("view_portal", "student"): {
        "groups": set(),
        "profile_roles": {"student"},
        "positions": {"student"},
        "canonical_roles": {"student"},
        "allow_global": False,
    },
    ("view_portal", "teacher"): {
        "groups": set(),
        "profile_roles": {"teacher"},
        "positions": {"teacher"},
        "canonical_roles": {"teacher"},
        "allow_global": False,
    },
    ("view_portal", "staff"): {
        "groups": {
            "admissions_managers",
            "admissions",
            "finance_agents",
            "finance",
            "gestionnaire",
            "manager",
            "executive_director",
            "executive",
            "secretary",
            "secretaries",
        },
        "profile_roles": {"admissions", "finance", "executive", "superadmin"},
        "positions": {
            "finance_manager",
            "payment_agent",
            "secretary",
            "admissions",
            "director_of_studies",
            "executive_director",
            "branch_manager",
            "academic_supervisor",
            "super_admin",
        },
        "canonical_roles": {"staff_admin", "directeur_etudes", "super_admin"},
        "allow_global": True,
    },
    ("view_portal", "dashboard"): {
        "groups": set(),
        "profile_roles": {"superadmin"},
        "positions": {"super_admin"},
        "canonical_roles": {"super_admin"},
        "allow_global": False,
    },
}


def _is_authenticated(user):
    return bool(user and getattr(user, "is_authenticated", False))


def _normalize_token(value):
    if value is None:
        return None
    return str(value).strip().lower() or None


def _get_profile(user):
    if not _is_authenticated(user):
        return None

    try:
        return user.profile
    except Exception:
        return None


def _get_raw_group_names(user):
    if not _is_authenticated(user):
        return set()

    return {
        _normalize_token(name)
        for name in user.groups.values_list("name", flat=True)
        if _normalize_token(name)
    }


def _is_global_user(user, *, profile_role=None, groups=None, canonical_role=None):
    if not _is_authenticated(user):
        return False

    profile_role = profile_role if profile_role is not None else get_user_profile_role(user)
    groups = set(groups) if groups is not None else set(get_user_groups(user))
    canonical_role = canonical_role if canonical_role is not None else get_user_role(user)

    return bool(
        user.is_superuser
        or profile_role in {"executive", "superadmin"}
        or "executive_director" in groups
        or canonical_role in {"directeur_etudes", "super_admin"}
    )


def get_user_profile_role(user):
    profile = _get_profile(user)
    role = _normalize_token(getattr(profile, "role", None))

    if _is_authenticated(user):
        logger.debug(
            "Profil role detecte pour %s: %s",
            getattr(user, "username", "anonymous"),
            role,
        )

    return role


def get_user_groups(user):
    groups = _get_raw_group_names(user)
    expanded_groups = set(groups)

    for cluster in GROUP_COMPAT_CLUSTERS:
        if groups.intersection(cluster):
            expanded_groups.update(cluster)

    if _is_authenticated(user) and getattr(user, "is_superuser", False):
        expanded_groups.add("superuser")

    ordered_groups = tuple(sorted(expanded_groups))

    if _is_authenticated(user):
        logger.debug(
            "Groupes detectes pour %s: %s",
            getattr(user, "username", "anonymous"),
            ", ".join(ordered_groups) or "aucun",
        )

    return ordered_groups


def get_user_position(user):
    if not _is_authenticated(user):
        return None

    profile = _get_profile(user)
    explicit_position = _normalize_token(getattr(profile, "position", None))
    if explicit_position:
        position = explicit_position
    elif user.is_superuser:
        position = "super_admin"
    elif Branch.objects.filter(manager=user).exists():
        position = "branch_manager"
    elif PaymentAgent.objects.filter(user=user).exists():
        position = "payment_agent"
    elif "executive_director" in get_user_groups(user):
        position = "executive_director"
    else:
        profile_role = get_user_profile_role(user)
        if profile_role == "finance":
            position = "finance_manager"
        elif profile_role == "admissions":
            position = "admissions"
        elif profile_role == "teacher":
            position = "teacher"
        elif profile_role == "student":
            position = "student"
        elif profile_role == "executive":
            position = "director_of_studies"
        elif profile_role == "superadmin":
            position = "super_admin"
        elif {"secretary", "secretaries"}.intersection(set(get_user_groups(user))):
            position = "secretary"
        else:
            position = None

    logger.debug(
        "Position detectee pour %s: %s",
        getattr(user, "username", "anonymous"),
        position,
    )

    return position


def get_user_role(user):
    if not _is_authenticated(user):
        return None

    profile_role = get_user_profile_role(user)
    groups = set(get_user_groups(user))
    position = get_user_position(user)

    role = None

    if user.is_superuser:
        role = "super_admin"
    elif profile_role in PROFILE_ROLE_TO_CANONICAL:
        role = PROFILE_ROLE_TO_CANONICAL[profile_role]
    elif position in POSITION_TO_CANONICAL:
        role = POSITION_TO_CANONICAL[position]
    else:
        for group_name in sorted(groups):
            if group_name in GROUP_TO_CANONICAL:
                role = GROUP_TO_CANONICAL[group_name]
                break

    if role is None and getattr(user, "is_staff", False) and groups:
        role = "staff_admin"

    logger.debug(
        "Role canonique detecte pour %s: %s (profile_role=%s, position=%s)",
        getattr(user, "username", "anonymous"),
        role,
        profile_role,
        position,
    )

    return role


def get_user_annexe(user):
    if not _is_authenticated(user):
        return None

    if user.is_superuser:
        logger.debug("Annexe detectee pour %s: aucune (superuser/global)", user.username)
        return None

    profile = _get_profile(user)
    profile_branch = getattr(profile, "branch", None)
    if profile_branch:
        logger.debug(
            "Annexe detectee pour %s via profile.branch: %s",
            user.username,
            profile_branch,
        )
        return profile_branch

    payment_agent = (
        PaymentAgent.objects
        .select_related("branch")
        .filter(user=user)
        .first()
    )
    if payment_agent and payment_agent.branch:
        logger.debug(
            "Annexe detectee pour %s via PaymentAgent.branch: %s",
            user.username,
            payment_agent.branch,
        )
        return payment_agent.branch

    managed_branch = Branch.objects.filter(manager=user).first()
    if managed_branch:
        logger.debug(
            "Annexe detectee pour %s via Branch.manager: %s",
            user.username,
            managed_branch,
        )
        return managed_branch

    logger.debug("Annexe detectee pour %s: aucune", user.username)
    return None


def get_user_scope(user):
    profile_role = get_user_profile_role(user)
    groups = get_user_groups(user)
    canonical_role = get_user_role(user)
    position = get_user_position(user)
    branch = get_user_annexe(user)
    is_global = _is_global_user(
        user,
        profile_role=profile_role,
        groups=groups,
        canonical_role=canonical_role,
    )

    scope = {
        "branch": branch,
        "annexe": branch,
        "is_global": is_global,
        "role": canonical_role,
        "profile_role": profile_role,
        "groups": groups,
        "position": position,
    }

    if _is_authenticated(user):
        logger.debug(
            "Scope detecte pour %s: role=%s, profile_role=%s, position=%s, is_global=%s, branch=%s",
            getattr(user, "username", "anonymous"),
            canonical_role,
            profile_role,
            position,
            is_global,
            branch,
        )

    return scope


def can_access(user, action, resource=None):
    action_key = _normalize_token(action)
    resource_key = _normalize_token(resource)

    if not _is_authenticated(user):
        logger.warning(
            "Acces refuse (non authentifie): action=%s, resource=%s",
            action_key,
            resource_key,
        )
        return False

    groups = set(get_user_groups(user))
    profile_role = get_user_profile_role(user)
    canonical_role = get_user_role(user)
    position = get_user_position(user)
    is_global = _is_global_user(
        user,
        profile_role=profile_role,
        groups=groups,
        canonical_role=canonical_role,
    )

    if user.is_superuser:
        logger.debug(
            "Acces accorde (superuser): user=%s, action=%s, resource=%s",
            user.username,
            action_key,
            resource_key,
        )
        return True

    rule = ACCESS_RULES.get((action_key, resource_key))
    if not rule:
        logger.warning(
            "Acces refuse (regle inconnue): user=%s, action=%s, resource=%s, role=%s, groups=%s",
            user.username,
            action_key,
            resource_key,
            canonical_role,
            sorted(groups),
        )
        return False

    has_access = bool(
        (rule["allow_global"] and is_global)
        or profile_role in rule["profile_roles"]
        or canonical_role in rule["canonical_roles"]
        or position in rule["positions"]
        or bool(groups.intersection(rule["groups"]))
    )

    log_method = logger.debug if has_access else logger.warning
    log_method(
        "Acces %s: user=%s, action=%s, resource=%s, role=%s, profile_role=%s, position=%s, groups=%s, is_global=%s",
        "accorde" if has_access else "refuse",
        user.username,
        action_key,
        resource_key,
        canonical_role,
        profile_role,
        position,
        sorted(groups),
        is_global,
    )

    return has_access
