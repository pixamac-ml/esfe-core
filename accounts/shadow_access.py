"""Comparaison sans effet de bord entre la compatibilité et Policy V2."""

from accounts.access import get_user_position
from accounts.access_context import build_access_context
from accounts.position_registry import normalize_position


def compare_access_classification(user, *, context=None):
    """Retourne une divergence sérialisable, sans donnée personnelle."""
    context = context or build_access_context(user)
    old_position = normalize_position(get_user_position(user)) or None
    new_position = context.position
    old_is_system = old_position is not None
    new_is_system = context.context_type == "SYSTEM"

    if old_position == new_position and old_is_system == new_is_system:
        return None
    return {
        "user_id": user.pk,
        "old_position": old_position,
        "new_position": new_position,
        "old_is_system": old_is_system,
        "new_is_system": new_is_system,
        "reason_code": context.reason_code,
    }
