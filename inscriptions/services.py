# inscriptions/services.py

from django.db import transaction
from django.core.exceptions import ValidationError

from inscriptions.models import Inscription


# ==========================================================
# CREATION INSCRIPTION A PARTIR D'UNE CANDIDATURE
# ==========================================================

def create_inscription_from_candidature(*, candidature, amount_due):
    """
    Création officielle d’une inscription à partir d’une candidature.

    PRINCIPES :

    - La candidature doit être ACCEPTÉE
    - Une seule inscription possible par candidature
    - Le montant est COPIÉ et FIGÉ
    - Transaction atomique pour éviter les duplications
    """

    if not candidature:
        raise ValidationError("Candidature requise.")

    if candidature.status != "accepted":
        raise ValidationError(
            "Impossible de créer une inscription : candidature non acceptée."
        )

    if amount_due <= 0:
        raise ValidationError(
            "Le montant dû doit être supérieur à zéro."
        )

    with transaction.atomic():

        # verrouillage candidature
        candidature_locked = (
            type(candidature)
            .objects
            .select_for_update()
            .get(pk=candidature.pk)
        )

        # vérifier si une inscription existe déjà
        if hasattr(candidature_locked, "inscription"):
            return candidature_locked.inscription

        # création inscription
        inscription = Inscription.objects.create(
            candidature=candidature_locked,
            amount_due=amount_due,
            status=Inscription.STATUS_CREATED
        )

        return inscription