"""
Signaux pour les inscriptions
- Notifications automatiques lors des changements de statut
- Historique des modifications
"""

from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

from .models import Inscription, StatusHistory
from core.models import Notification


# ==========================================================
# STATUT -> TYPE DE NOTIFICATION
# ==========================================================
STATUS_NOTIFICATION_MAP = {
    "created": "inscription_created",
    "active": "inscription_active",
    "suspended": "inscription_suspended",
    "expired": "inscription_expired",
    "transferred": "inscription_transferred",
    "completed": "inscription_completed",
}


# ==========================================================
# MESSAGES PAR DEFAUT POUR CHAQUE STATUT
# ==========================================================
STATUS_MESSAGES = {
    "created": "Votre inscription a ete creee avec succes. Veuillez proceder au paiement des frais d'inscription.",
    "active": "Votre inscription est desormais active. Bienvenue a l'Ecole Privee de Sante Felix Houphouet Boigny !",
    "suspended": "Votre inscription a ete suspendue. Veuillez contacter l'administration pour plus d'informations.",
    "expired": "Votre inscription a expire. Veuillez contacter l'administration si vous souhaitez la reactiver.",
    "transferred": "Votre inscription a ete transferee vers un autre programme.",
    "completed": "Felicitations ! Votre inscription est marquee comme terminee.",
}


# ==========================================================
# TITRES PAR DEFAUT POUR CHAQUE STATUT
# ==========================================================
STATUS_TITLES = {
    "created": "Inscription creee",
    "active": "Inscription activee",
    "suspended": "Inscription suspendue",
    "expired": "Inscription expiree",
    "transferred": "Inscription transferee",
    "completed": "Inscription terminee",
}


# ==========================================================
# CREATION DE NOTIFICATION
# ==========================================================
def create_inscription_notification(inscription, previous_status, new_status):

    try:
        candidature = inscription.candidature
        recipient_email = candidature.email
        recipient_name = f"{candidature.last_name} {candidature.first_name}"
    except Exception:
        recipient_email = "unknown@esfe-mali.org"
        recipient_name = "Etudiant"
        candidature = None

    notification_type = STATUS_NOTIFICATION_MAP.get(new_status)

    if not notification_type:
        return None

    title = STATUS_TITLES.get(new_status, f"Statut inscription: {new_status}")

    message = STATUS_MESSAGES.get(
        new_status,
        f"Votre statut d'inscription est maintenant: {new_status}"
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
# SIGNAL PRE SAVE
# DETECTER CHANGEMENT STATUT
# ==========================================================
@receiver(pre_save, sender=Inscription)
def inscription_status_change(sender, instance, **kwargs):

    if not instance.pk:
        instance._previous_status = None
        return

    try:
        old_instance = Inscription.objects.get(pk=instance.pk)
        instance._previous_status = old_instance.status
    except Inscription.DoesNotExist:
        instance._previous_status = None


# ==========================================================
# SIGNAL POST SAVE
# CREATION HISTORIQUE + NOTIFICATION
# ==========================================================
@receiver(post_save, sender=Inscription)
def inscription_saved(sender, instance, created, **kwargs):

    previous_status = getattr(instance, "_previous_status", None)
    new_status = instance.status

    # =====================================
    # NOUVELLE INSCRIPTION
    # =====================================
    if created:

        create_inscription_notification(instance, None, "created")

        StatusHistory.objects.create(
            inscription=instance,
            previous_status="",
            new_status="created",
            comment="Inscription creee",
        )

        return

    # =====================================
    # CHANGEMENT DE STATUT
    # =====================================
    if previous_status and previous_status != new_status:

        create_inscription_notification(instance, previous_status, new_status)

        StatusHistory.objects.create(
            inscription=instance,
            previous_status=previous_status,
            new_status=new_status,
            comment=f"Statut change de '{previous_status}' vers '{new_status}'",
        )