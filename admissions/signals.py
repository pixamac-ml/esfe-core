# admissions/signals.py
"""
Signaux pour les notifications automatiques lors des changements de statut
"""

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model

from admissions.models import Candidature
from communication.models import CommunicationNotification
from communication.services import NotificationService
from core.models import StatusHistory

# ==========================================================
# MESSAGES PAR TYPE DE NOTIFICATION
# ==========================================================

NOTIFICATION_MESSAGES = {
    "candidature_submitted": {
        "title": "Candidature soumise avec succes",
        "message": "Votre candidature a ete soumise avec succes. Nous allons l'examiner dans les prochains jours."
    },
    "candidature_under_review": {
        "title": "Candidature en cours d'analyse",
        "message": "Votre candidature est actuellement en cours d'analyse par notre equipe pedagogique."
    },
    "candidature_to_complete": {
        "title": "Candidature a completer",
        "message": "Votre candidature necessite des documents complements. Veuillez televerser les documents manquants."
    },
    "candidature_accepted": {
        "title": "Felicitations ! Candidature acceptee",
        "message": "Votre candidature a ete acceptee. Vous pouvez desorm procede a votre inscription administrative."
    },
    "candidature_accepted_with_reserve": {
        "title": "Candidature acceptee sous reserve",
        "message": "Votre candidature a ete acceptee sous reserve. Veuillez completer les conditions indiquees."
    },
    "candidature_rejected": {
        "title": "Candidature refusee",
        "message": "Nous avons le regret de vous informer que votre candidature n'a pas ete retenue."
    },
    "document_missing": {
        "title": "Document manquant",
        "message": "Un document requis est manquant ou invalide dans votre dossier. Veuillez le televerser."
    },
}


def _get_candidate_user(email):
    return get_user_model().objects.filter(email__iexact=email).first()


def _queue_candidature_email(*, candidature_id, notification_id, notification_type):
    """Migration progressive: l'envoi transactionnel est pilote par communication/."""
    return None


# ==========================================================
# FONCTIONS DE CREATION DE NOTIFICATION
# ==========================================================

def create_status_notification(candidature, notification_type):
    """Cree une notification pour un candidat"""

    if notification_type not in NOTIFICATION_MESSAGES:
        return None

    data = NOTIFICATION_MESSAGES[notification_type]

    # CORRIGE: utiliser last_name et first_name au lieu de full_name
    recipient_name = f"{candidature.last_name} {candidature.first_name}"

    recipient_user = _get_candidate_user(candidature.email)
    channels = [CommunicationNotification.CHANNEL_EMAIL_TRANSACTIONAL]
    if recipient_user:
        channels = [
            CommunicationNotification.CHANNEL_IN_APP,
            CommunicationNotification.CHANNEL_WEBSOCKET,
            CommunicationNotification.CHANNEL_EMAIL_TRANSACTIONAL,
        ]
    event, created_notifications = NotificationService.notify_user(
        recipient=recipient_user,
        actor=None,
        event_type=notification_type,
        title=data["title"],
        body=data["message"],
        source_app="admissions",
        channels=tuple(channels),
        metadata={
            "recipient_email": candidature.email,
            "recipient_name": recipient_name,
            "url": "/candidature/",
            "html_template": "emails/notification_candidature.html",
            "context": {
                "recipient_name": recipient_name,
                "message": data["message"],
                "candidate_reference": getattr(candidature, "reference", ""),
                "programme_name": getattr(getattr(candidature, "programme", None), "title", ""),
                "dashboard_url": "/candidature/",
                "reference": getattr(candidature, "reference", ""),
            },
        },
    )

    _queue_candidature_email(
        candidature_id=candidature.pk,
        notification_id=created_notifications[0].pk if created_notifications else None,
        notification_type=notification_type,
    )

    return event


def create_status_history(candidature, old_status, new_status, changed_by=None, comment=""):
    """Cree un historique de changement de statut"""

    return StatusHistory.objects.create(
        candidature=candidature,
        old_status=old_status,
        new_status=new_status,
        changed_by=changed_by,
        comment=comment,
    )


# ==========================================================
# SIGNALS
# ==========================================================

@receiver(pre_save, sender=Candidature)
def candidature_status_change(sender, instance, **kwargs):
    """
    Detecte les changements de statut AVANT sauvegarde
    """
    if not instance.pk:
        # Nouvelle candidature - pas de changement de statut
        instance._old_status = None
        return

    try:
        old_candidature = Candidature.objects.get(pk=instance.pk)
        instance._old_status = old_candidature.status
    except Candidature.DoesNotExist:
        instance._old_status = None


@receiver(post_save, sender=Candidature)
def candidature_saved(sender, instance, created, **kwargs):
    """
    Cree les notifications et historiques apres sauvegarde
    """
    old_status = getattr(instance, '_old_status', None)

    # Si nouvelle candidature
    if created:
        create_status_notification(instance, "candidature_submitted")
        create_status_history(instance, "", instance.status, comment="Candidature soumise")
        return

    # Si changement de statut
    if old_status and old_status != instance.status:
        # Mapper le nouveau statut vers le type de notification
        status_to_notification_map = {
            "submitted": "candidature_submitted",
            "under_review": "candidature_under_review",
            "to_complete": "candidature_to_complete",
            "accepted": "candidature_accepted",
            "accepted_with_reserve": "candidature_accepted_with_reserve",
            "rejected": "candidature_rejected",
        }

        notification_type = status_to_notification_map.get(instance.status)

        if notification_type:
            create_status_notification(instance, notification_type)

        create_status_history(
            instance,
            old_status,
            instance.status,
            comment=f"Statut change de {old_status} a {instance.status}"
        )


# ==========================================================
# SIGNAL POUR DOCUMENTS MANQUANTS
# ==========================================================

@receiver(post_save, sender=Candidature)
def check_documents_after_status_change(sender, instance, created, **kwargs):
    """
    Verifie les documents apres un changement de statut vers 'under_review'
    """
    if created:
        return

    old_status = getattr(instance, '_old_status', None)

    # Si la candidature passe en cours d'analyse
    if old_status != "under_review" and instance.status == "under_review":

        # Verifier si tous les documents sont valides
        if not instance.all_documents_valid:
            # Creer une notification pour documents manquants
            missing_docs = []
            required_docs = instance.programme.required_documents.all()

            for req_doc in required_docs:
                doc = instance.documents.filter(document_type=req_doc.document).first()
                if not doc or not doc.is_valid:
                    missing_docs.append(req_doc.document.name)

            if missing_docs:
                # Modifier le message avec les documents manquants
                docs_list = ", ".join(missing_docs)
                message = f"Un document requis est manquant ou invalide: {docs_list}. Veuillez le televerser."

                # CORRIGE: utiliser last_name et first_name au lieu de full_name
                recipient_name = f"{instance.last_name} {instance.first_name}"

                recipient_user = _get_candidate_user(instance.email)
                channels = [CommunicationNotification.CHANNEL_EMAIL_TRANSACTIONAL]
                if recipient_user:
                    channels = [
                        CommunicationNotification.CHANNEL_IN_APP,
                        CommunicationNotification.CHANNEL_WEBSOCKET,
                        CommunicationNotification.CHANNEL_EMAIL_TRANSACTIONAL,
                    ]
                NotificationService.notify_user(
                    recipient=recipient_user,
                    actor=None,
                    event_type="document_missing",
                    title="Document manquant",
                    body=message,
                    source_app="admissions",
                    channels=tuple(channels),
                    metadata={
                        "recipient_email": instance.email,
                        "recipient_name": recipient_name,
                        "url": "/candidature/",
                        "html_template": "emails/notification_candidature.html",
                        "context": {
                            "recipient_name": recipient_name,
                            "message": message,
                            "candidate_reference": getattr(instance, "reference", ""),
                            "programme_name": getattr(getattr(instance, "programme", None), "title", ""),
                            "dashboard_url": "/candidature/",
                            "reference": getattr(instance, "reference", ""),
                        },
                    },
                )

                # Mettre a jour automatiquement le statut
                instance.status = "to_complete"
                instance.admin_comment = message
                update_fields = ["status", "admin_comment"]
                if hasattr(instance, "updated_at"):
                    update_fields.append("updated_at")
                instance.save(update_fields=update_fields)
