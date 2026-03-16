"""
Helpers centralisés pour les dashboards staff.

Objectifs :
- utilitaires sécurisés
- gestion annexe utilisateur
- pagination standard
- outils robustes pour requêtes GET
- logique rôles staff
"""

from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

from payments.models import PaymentAgent
from branches.models import Branch


# ==========================================================
# GROUPES UTILISATEUR
# ==========================================================

def user_has_group(user, group_name):
    """
    Vérifie si l'utilisateur appartient à un groupe.
    """

    if not user or not user.is_authenticated:
        return False

    return user.groups.filter(name=group_name).exists()


def is_manager(user):
    """
    Vérifie si l'utilisateur est gestionnaire.
    """

    return user_has_group(user, "gestionnaire")


def is_admissions(user):
    """
    Vérifie si l'utilisateur appartient au staff admissions.
    """

    return user_has_group(user, "admissions")


def is_finance(user):
    """
    Vérifie si l'utilisateur appartient au staff finance.
    """

    return user_has_group(user, "finance")


def is_executive(user):
    """
    Vérifie si l'utilisateur appartient à la direction.
    """

    return user_has_group(user, "executive") or user.is_superuser


# ==========================================================
# ANNEXE UTILISATEUR
# ==========================================================

def get_user_branch(user):
    """
    Détermine l'annexe associée à l'utilisateur.

    Priorité :

    1. superuser -> accès global
    2. profile.branch
    3. PaymentAgent.branch
    4. Branch.manager
    """

    if not user or not user.is_authenticated:
        return None

    # super admin = accès global
    if user.is_superuser:
        return None

    # profil utilisateur
    if hasattr(user, "profile"):

        profile_branch = getattr(user.profile, "branch", None)

        if profile_branch:
            return profile_branch

    # agent de paiement
    try:

        agent = (
            PaymentAgent.objects
            .select_related("branch")
            .get(user=user)
        )

        if agent.branch:
            return agent.branch

    except PaymentAgent.DoesNotExist:
        pass

    # responsable annexe
    managed_branch = (
        Branch.objects
        .filter(manager=user)
        .first()
    )

    return managed_branch


# ==========================================================
# VUE GLOBALE
# ==========================================================

def is_global_viewer(user):
    """
    Détermine si l'utilisateur peut voir toutes les annexes.
    """

    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    return user_has_group(user, "executive")


# ==========================================================
# ANNEXE OBLIGATOIRE (gestionnaire)
# ==========================================================

def ensure_manager_branch(user):
    """
    Vérifie qu'un gestionnaire possède une annexe.
    """

    if not is_manager(user):
        return None

    branch = get_user_branch(user)

    if not branch:
        raise ValueError(
            "Le gestionnaire doit être assigné à une annexe."
        )

    return branch


# ==========================================================
# PAGINATION STANDARD
# ==========================================================

def paginate_queryset(request, queryset, per_page=25):
    """
    Pagination sécurisée pour dashboards.
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
# GET PARAM SÉCURISÉ
# ==========================================================

def safe_int(value, default=0):
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

def safe_str(value, default=""):
    """
    Nettoie une valeur GET string.
    """

    if not value:
        return default

    return str(value).strip()


# ==========================================================
# SAFE BOOLEAN
# ==========================================================

def safe_bool(value):
    """
    Convertit un paramètre GET en booléen.
    """

    if isinstance(value, bool):
        return value

    if not value:
        return False

    return str(value).lower() in ["1", "true", "yes", "on"]