"""
Signaux pour les inscriptions

Fonctions :
- Détection changement de statut
- Création automatique de l'historique
- Notifications automatiques aux candidats
"""

from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.db import transaction

from .models import Inscription, StatusHistory
from core.models import Notification


# ==========================================================
# STATUT -> TYPE DE NOTIFICATION
# ==========================================================

STATUS_NOTIFICATION_MAP = {
    "created": "inscription_created",
    "awaiting_payment": "inscription_payment_pending",
    "partial_paid": "inscription_partial_payment",
    "active": "inscription_active",
    "suspended": "inscription_suspended",
    "expired": "inscription_expired",
    "completed": "inscription_completed",
}


# ==========================================================
# MESSAGES PAR STATUT
# ==========================================================

STATUS_MESSAGES = {

    "created":
        "Votre inscription a été créée avec succès. "
        "Veuillez procéder au paiement des frais d'inscription.",

    "awaiting_payment":
        "Votre inscription est en attente de paiement. "
        "Veuillez finaliser votre inscription.",

    "partial_paid":
        "Un paiement partiel a été enregistré. "
        "Veuillez compléter votre paiement.",

    "active":
        "Votre inscription est désormais active. "
        "Bienvenue à l'École de Santé Félix Houphouët-Boigny.",

    "suspended":
        "Votre inscription a été suspendue. "
        "Veuillez contacter l'administration.",

    "expired":
        "Votre inscription a expiré. "
        "Contactez l'administration si vous souhaitez la réactiver.",

    "completed":
        "Votre inscription est terminée. Félicitations.",
}


# ==========================================================
# TITRES PAR STATUT
# ==========================================================

STATUS_TITLES = {

    "created": "Inscription créée",
    "awaiting_payment": "Paiement attendu",
    "partial_paid": "Paiement partiel",
    "active": "Inscription activée",
    "suspended": "Inscription suspendue",
    "expired": "Inscription expirée",
    "completed": "Inscription terminée",
}


# ==========================================================
# CREATION NOTIFICATION
# ==========================================================

def create_inscription_notification(inscription, previous_status, new_status):
    """
    Création d'une notification liée à un changement de statut.
    """

    candidature = getattr(inscription, "candidature", None)

    if not candidature:
        return None

    recipient_email = getattr(candidature, "email", None)
    recipient_name = f"{candidature.last_name} {candidature.first_name}"

    notification_type = STATUS_NOTIFICATION_MAP.get(new_status)

    if not notification_type:
        return None

    title = STATUS_TITLES.get(new_status, f"Statut inscription : {new_status}")

    message = STATUS_MESSAGES.get(
        new_status,
        f"Votre statut d'inscription est maintenant : {new_status}"
    )

    return Notification.objects.create(
        recipient_email=recipient_email,
        recipient_name=recipient_name,
        notification_type=notification_type,
        title=title,
        message=message,
        related_inscription=inscription,
        related_candidature=candidature,
    )


# ==========================================================
# PRE SAVE
# DETECTER CHANGEMENT STATUT
# ==========================================================

@receiver(pre_save, sender=Inscription)
def inscription_status_change(sender, instance, **kwargs):

    if not instance.pk:
        instance._previous_status = None
        return

    try:
        old = Inscription.objects.only("status").get(pk=instance.pk)
        instance._previous_status = old.status
    except Inscription.DoesNotExist:
        instance._previous_status = None


# ==========================================================
# POST SAVE
# HISTORIQUE + NOTIFICATION
# ==========================================================

@receiver(post_save, sender=Inscription)
def inscription_saved(sender, instance, created, **kwargs):

    previous_status = getattr(instance, "_previous_status", None)
    new_status = instance.status

    # ==========================================
    # CREATION
    # ==========================================

    if created:

        with transaction.atomic():

            StatusHistory.objects.create(
                inscription=instance,
                previous_status="",
                new_status="created",
                comment="Inscription créée automatiquement"
            )

            create_inscription_notification(instance, None, "created")

        return

    # ==========================================
    # CHANGEMENT STATUT
    # ==========================================

    if previous_status and previous_status != new_status:

        with transaction.atomic():

            StatusHistory.objects.create(
                inscription=instance,
                previous_status=previous_status,
                new_status=new_status,
                comment=f"Statut changé de '{previous_status}' vers '{new_status}'"
            )

            # ne pas notifier si inscription archivée
            if not instance.is_archived:
                create_inscription_notification(
                    instance,
                    previous_status,
                    new_status
                )