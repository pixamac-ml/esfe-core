"""
Querysets centralisés pour les dashboards staff.

Objectifs :
- filtrage automatique par annexe
- optimisation ORM
- sécurité multi-annexe
- base commune pour tous les dashboards
"""

from admissions.models import Candidature
from inscriptions.models import Inscription
from payments.models import Payment

from .helpers import get_user_branch
from .permissions import is_global_viewer


# ==========================================================
# BASE QUERYSET
# ==========================================================

def get_base_queryset(user, model_type):
    """
    Retourne un queryset sécurisé filtré par annexe.

    Paramètres
    ----------
    user : User
        Utilisateur connecté

    model_type : str
        Type de modèle :
        - "candidature"
        - "inscription"
        - "payment"
    """

    branch = get_user_branch(user)
    is_global = is_global_viewer(user)

    # ==========================================================
    # CANDIDATURES
    # ==========================================================

    if model_type == "candidature":

        qs = (
            Candidature.objects
            .filter(is_deleted=False)
            .select_related(
                "programme",
                "branch"
            )
        )

        if not is_global:

            if not branch:
                return qs.none()

            qs = qs.filter(branch=branch)

        return qs


    # ==========================================================
    # INSCRIPTIONS
    # ==========================================================

    if model_type == "inscription":

        qs = (
            Inscription.objects
            .filter(
                is_archived=False,
                candidature__is_deleted=False,
            )
            .select_related(
                "candidature",
                "candidature__programme",
                "candidature__branch"
            )
        )

        if not is_global:

            if not branch:
                return qs.none()

            qs = qs.filter(
                candidature__branch=branch
            )

        return qs


    # ==========================================================
    # PAIEMENTS
    # ==========================================================

    if model_type == "payment":

        qs = (
            Payment.objects
            .filter(
                inscription__is_archived=False,
                inscription__candidature__is_deleted=False,
            )
            .select_related(
                "inscription",
                "inscription__candidature",
                "inscription__candidature__programme",
                "inscription__candidature__branch",
                "agent",
            )
        )

        if not is_global:

            if not branch:
                return qs.none()

            qs = qs.filter(
                inscription__candidature__branch=branch
            )

        return qs


    # ==========================================================
    # ERREUR
    # ==========================================================

    raise ValueError(
        f"Model type inconnu : {model_type}"
    )