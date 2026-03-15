"""
Gestion centralisée des permissions pour les dashboards staff.

Objectifs :
- sécuriser les accès
- éviter les erreurs si profile absent
- centraliser la logique métier
"""

from .helpers import user_has_group


# ==========================================================
# OUTILS
# ==========================================================

def get_user_role(user):
    """
    Retourne le rôle du profil utilisateur si disponible.
    """

    if hasattr(user, "profile"):
        return getattr(user.profile, "role", None)

    return None


# ==========================================================
# GLOBAL VIEWER
# ==========================================================

def is_global_viewer(user):
    """
    Utilisateurs pouvant voir toutes les annexes.
    """

    if not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    role = get_user_role(user)

    if role == "executive":
        return True

    if user_has_group(user, "executive_director"):
        return True

    return False


# ==========================================================
# DASHBOARD ADMISSIONS
# ==========================================================

def check_admissions_access(user):
    """
    Vérifie accès dashboard admissions.
    """

    if not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    role = get_user_role(user)

    if role == "admissions":
        return True

    if user_has_group(user, "admissions_managers"):
        return True

    if is_global_viewer(user):
        return True

    return False


# ==========================================================
# DASHBOARD FINANCE
# ==========================================================

def check_finance_access(user):
    """
    Vérifie accès dashboard finance.
    """

    if not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    role = get_user_role(user)

    if role == "finance":
        return True

    if user_has_group(user, "finance_agents"):
        return True

    if is_global_viewer(user):
        return True

    return False


# ==========================================================
# DASHBOARD EXECUTIVE
# ==========================================================

def check_executive_access(user):
    """
    Vérifie accès dashboard direction.
    """

    if not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    role = get_user_role(user)

    if role == "executive":
        return True

    if user_has_group(user, "executive_director"):
        return True

    return False