"""Wrappers de compatibilite vers la couche centrale d'acces."""

from accounts.access import (
    can_access,
    get_user_profile_role,
    get_user_scope,
)


# ==========================================================
# OUTILS
# ==========================================================

def get_user_role(user):
    """
    Retourne le rôle du profil utilisateur si disponible.
    """
    return get_user_profile_role(user)


# ==========================================================
# GLOBAL VIEWER
# ==========================================================

def is_global_viewer(user):
    """
    Utilisateurs pouvant voir toutes les annexes.
    """

    if not user or not user.is_authenticated:
        return False
    return bool(get_user_scope(user)["is_global"])


# ==========================================================
# DASHBOARD ADMISSIONS
# ==========================================================

def check_admissions_access(user):
    """
    Vérifie accès dashboard admissions.
    """

    return can_access(user, "view_dashboard", "admissions")


# ==========================================================
# DASHBOARD FINANCE
# ==========================================================

def check_finance_access(user):
    """
    Vérifie accès dashboard finance.
    """

    return can_access(user, "view_dashboard", "finance")


# ==========================================================
# DASHBOARD EXECUTIVE
# ==========================================================

def check_executive_access(user):
    """
    Vérifie accès dashboard direction.
    """

    return can_access(user, "view_dashboard", "executive")
