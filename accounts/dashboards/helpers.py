"""
Helpers centralises pour les dashboards staff.

Objectifs :
- utilitaires securises
- gestion annexe utilisateur
- pagination standard
- outils robustes pour requetes GET
- logique roles staff
"""

from typing import Any

from django.contrib.auth.models import AbstractBaseUser
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import QuerySet
from django.http import HttpRequest

from accounts.access import (
    get_user_annexe,
    get_user_groups,
    get_user_scope,
)
from branches.models import Branch


# ==========================================================
# GROUPES UTILISATEUR
# ==========================================================

def user_has_group(user: AbstractBaseUser, group_name: str) -> bool:
    """
    Verifie si l'utilisateur appartient a un groupe.
    """
    return group_name in get_user_groups(user)


def is_manager(user: AbstractBaseUser) -> bool:
    """
    Verifie si l'utilisateur est gestionnaire.
    """
    return user_has_group(user, "gestionnaire")


def is_admissions(user: AbstractBaseUser) -> bool:
    """
    Verifie si l'utilisateur appartient au staff admissions.
    """
    return user_has_group(user, "admissions")


def is_finance(user: AbstractBaseUser) -> bool:
    """
    Verifie si l'utilisateur appartient au staff finance.
    """
    return user_has_group(user, "finance")


def is_executive(user: AbstractBaseUser) -> bool:
    """
    Verifie si l'utilisateur appartient a la direction.
    """
    return user_has_group(user, "executive") or user.is_superuser


# ==========================================================
# ANNEXE UTILISATEUR
# ==========================================================

def get_user_branch(user: AbstractBaseUser) -> Branch | None:
    """
    Determine l'annexe associee a l'utilisateur.

    Priorite :

    1. superuser -> acces global
    2. profile.branch
    3. PaymentAgent.branch
    4. Branch.manager
    """
    return get_user_annexe(user)


# ==========================================================
# VUE GLOBALE
# ==========================================================

def is_global_viewer(user: AbstractBaseUser) -> bool:
    """
    Determine si l'utilisateur peut voir toutes les annexes.
    """
    if not user or not user.is_authenticated:
        return False
    return bool(get_user_scope(user)["is_global"])


# ==========================================================
# ANNEXE OBLIGATOIRE (gestionnaire)
# ==========================================================

def ensure_manager_branch(user: AbstractBaseUser) -> Branch | None:
    """
    Verifie qu'un gestionnaire possede une annexe.
    """
    if not is_manager(user):
        return None

    branch = get_user_branch(user)

    if not branch:
        raise ValueError(
            "Le gestionnaire doit etre assigne a une annexe."
        )

    return branch


# ==========================================================
# PAGINATION STANDARD
# ==========================================================

def paginate_queryset(request: HttpRequest, queryset: QuerySet, per_page: int = 25) -> Any:
    """
    Pagination securisee pour dashboards.
    """
    paginator = Paginator(queryset, per_page)

    page_number = request.GET.get("page")

    try:
        page_obj = paginator.page(page_number)

    except PageNotAnInteger:
        page_obj = paginator.page(1)

    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    return page_obj


# ==========================================================
# GET PARAM SECURISE
# ==========================================================

def safe_int(value: Any, default: int = 0) -> int:
    """
    Convertit une valeur GET en int sans crash.
    """
    try:
        return int(value)

    except (ValueError, TypeError):
        return default


# ==========================================================
# SAFE GET STRING
# ==========================================================

def safe_str(value: Any, default: str = "") -> str:
    """
    Nettoie une valeur GET string.
    """
    if not value:
        return default

    return str(value).strip()


# ==========================================================
# SAFE BOOLEAN
# ==========================================================

def safe_bool(value: Any) -> bool:
    """
    Convertit un parametre GET en booleen.
    """
    if isinstance(value, bool):
        return value

    if not value:
        return False

    return str(value).lower() in ["1", "true", "yes", "on"]
