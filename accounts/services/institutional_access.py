"""Synchronisation sûre entre position institutionnelle et groupes Django.

La position est l'identité métier. Les groupes sont des supports techniques de
permissions et ne doivent jamais devenir une seconde source de vérité.
"""

from django.contrib.auth.models import Group

from accounts.position_registry import (
    POSITION_REGISTRY,
    get_position_definition,
    normalize_position,
)


# Anciennes appellations qui ont pu donner des accès dans la première version
# du projet. Elles sont retirées lors de la synchronisation afin qu'un compte
# ne cumule pas des droits contradictoires avec sa position courante.
LEGACY_ACCESS_GROUPS = frozenset(
    {
        "admissions_managers",
        "finance_agents",
        "finance",
        "gestionnaire",
        "manager",
        "executive",
        "secretaries",
        "marketing",
        "branch_manager",
        "deputy_director",
    }
)

CANONICAL_GROUP_NAMES = frozenset(
    definition.default_group for definition in POSITION_REGISTRY.values()
)
MANAGED_ACCESS_GROUPS = CANONICAL_GROUP_NAMES | LEGACY_ACCESS_GROUPS

# `role` reste lu par quelques parcours historiques. Il est dérivé, jamais
# choisi indépendamment lorsqu'une position est connue.
COMPATIBILITY_ROLE_BY_POSITION = {
    "student": "student",
    "teacher": "teacher",
    "finance_manager": "finance",
    "payment_agent": "finance",
    "admissions": "admissions",
    "director_of_studies": "executive",
    "executive_director": "executive",
    "deputy_executive_director": "executive",
    "super_admin": "superadmin",
}


def compatibility_role_for_position(position):
    """Return the legacy-compatible role derived from an official position."""

    return COMPATIBILITY_ROLE_BY_POSITION.get(normalize_position(position), "")


def ensure_canonical_groups():
    """Create every official group idempotently and return them by name."""

    groups = {}
    for group_name in sorted(CANONICAL_GROUP_NAMES):
        groups[group_name], _created = Group.objects.get_or_create(name=group_name)
    return groups


def synchronize_user_position_groups(user, *, position=None):
    """Apply the one-position/one-canonical-group contract to a user.

    Only recognised access groups are changed. Any unrelated group (for
    example Support or Responsable Qualité) remains untouched until a future
    business decision explicitly covers it.
    """

    resolved_position = normalize_position(
        position if position is not None else getattr(getattr(user, "profile", None), "position", "")
    )
    definition = get_position_definition(resolved_position)
    expected_group_name = definition.default_group if definition else None

    ensure_canonical_groups()
    current_access_groups = Group.objects.filter(
        user=user,
        name__in=MANAGED_ACCESS_GROUPS,
    )
    if current_access_groups.exists():
        user.groups.remove(*current_access_groups)

    if expected_group_name:
        user.groups.add(Group.objects.get(name=expected_group_name))

    return expected_group_name
