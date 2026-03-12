# admissions/signals.py
"""
Signaux pour les notifications automatiques lors des changements de statut
"""

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from admissions.models import Candidature
from core.models import Notification, StatusHistory

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

    notification = Notification.objects.create(
        recipient_email=candidature.email,
        recipient_name=recipient_name,
        notification_type=notification_type,
        title=data["title"],
        message=data["message"],
        related_candidature=candidature,
    )

    return notification


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

                Notification.objects.create(
                    recipient_email=instance.email,
                    recipient_name=recipient_name,
                    notification_type="document_missing",
                    title="Document manquant",
                    message=message,
                    related_candidature=instance,
                )

                # Mettre a jour automatiquement le statut
                instance.status = "to_complete"
                instance.save(update_fields=["status"])