"""
Services de notifications enrichis pour la communauté ESFE
Gère les notifications multi-canal : DB + WebSocket + Email
"""
import json

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from django.core.mail import send_mail
from django.conf import settings
from django.db.models import Count

from community.models import Notification


def create_notification(
        *,
        user,
        actor,
        topic=None,
        answer=None,
        notification_type,
        send_email=False,
        vote_count=1
):
    """
    Crée une notification avec regroupement intelligent des votes.

    Args:
        user: Utilisateur cible de la notification
        actor: Utilisateur qui déclenche la notification
        topic: Sujet concerné (optionnel)
        answer: Réponse concernée (optionnel)
        notification_type: Type de notification
        send_email: Envoyer un email (défaut: False)
        vote_count: Nombre de votes (pour le regroupement)
    """

    # =========================
    # GESTION DES DOUBLONS
    # =========================

    # Pour les upvotes, on regroupe ou on met à jour
    if notification_type == "upvote":
        existing = Notification.objects.filter(
            user=user,
            topic=topic,
            answer=answer,
            notification_type="upvote",
            is_read=False
        ).first()

        if existing:
            # Mettre à jour le compteur de votes
            existing.vote_count += vote_count
            existing.save(update_fields=["vote_count", "updated_at"])

            # Envoyer via WebSocket pour la mise à jour temps réel
            _send_websocket_notification(user, existing)

            return existing

    # Pour les autres types, vérifier l'unicité
    else:
        existing = Notification.objects.filter(
            user=user,
            topic=topic,
            answer=answer,
            notification_type=notification_type
        ).exists()

        if existing:
            return None  # Ne pas créer de doublon

    # =========================
    # CRÉATION DE LA NOTIFICATION
    # =========================

    notification = Notification.objects.create(
        user=user,
        actor=actor,
        topic=topic,
        answer=answer,
        notification_type=notification_type,
        vote_count=vote_count if notification_type == "upvote" else 1
    )

    # =========================
    # WEBSOCKET (TEMPS RÉEL)
    # =========================
    _send_websocket_notification(user, notification)

    # =========================
    # EMAIL (OPTIONNEL)
    # =========================
    if send_email and user.email and not notification.email_sent:
        try:
            send_mail(
                subject=_build_email_subject(notification),
                message=_build_email_content(notification),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=True
            )
            notification.email_sent = True
            notification.save(update_fields=["email_sent"])
        except Exception:
            pass

    return notification


def _send_websocket_notification(user, notification):
    """Envoie la notification via WebSocket"""
    try:
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"user_{user.id}",
                {
                    "type": "send_notification",
                    "message": build_message(notification),
                    "url": notification.get_target_url,
                    "notification_type": notification.notification_type,
                    "vote_count": notification.vote_count,
                }
            )
    except Exception:
        pass  # Ne jamais bloquer la requête


def notify_new_topic(topic, author):
    """
    Notifie tous les abonnés de la catégorie lors d'un nouveau sujet.
    """
    from community.models import Category

    category = topic.category

    # Récupérer les abonnés (sauf l'auteur)
    subscribers = category.subscribers.exclude(id=author.id)

    for subscriber in subscribers:
        create_notification(
            user=subscriber,
            actor=author,
            topic=topic,
            notification_type="new_topic",
            send_email=True
        )


def notify_new_answer(topic, answer):
    """
    Notifie l'auteur du sujet et les répondants précédents.
    """
    author = answer.author

    # 1.Notifier l'auteur du sujet (si ce n'est pas lui qui répond)
    if topic.author != author:
        create_notification(
            user=topic.author,
            actor=author,
            topic=topic,
            answer=answer,
            notification_type="new_answer",
            send_email=True
        )

    # 2.Notifier les personnes qui ont répondu (sauf l'auteur et l'auteur du sujet)
    previous_responders = (
        answer.topic.answers.filter(is_deleted=False)
        .exclude(author=author)
        .exclude(author=topic.author)
        .values_list("author_id", flat=True)
        .distinct()
    )

    for responder_id in previous_responders:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        responder = User.objects.get(id=responder_id)

        create_notification(
            user=responder,
            actor=author,
            topic=topic,
            answer=answer,
            notification_type="new_answer",
            send_email=False
        )


def notify_reply_to_reply(parent_answer, reply):
    """
    Notifie l'auteur de la réponse parentale quand quelqu'un répond à sa réponse.
    """
    # Ne pas se notifier soi-même
    if parent_answer.author == reply.author:
        return

    create_notification(
        user=parent_answer.author,
        actor=reply.author,
        topic=reply.topic,
        answer=reply,
        notification_type="reply_to_reply",
        send_email=True
    )


def notify_upvote(answer, voter):
    """
    Notifie l'auteur d'une réponse lors d'un nouveau vote.
    Utilise le regroupement pour éviter les spams de notifications.
    """
    # Ne pas se notifier soi-même
    if answer.author == voter:
        return

    create_notification(
        user=answer.author,
        actor=voter,
        topic=answer.topic,
        answer=answer,
        notification_type="upvote",
        vote_count=1,
        send_email=False
    )


def notify_accepted_answer(topic, accepted_answer):
    """
    Notifie l'auteur de la réponse acceptée.
    """
    create_notification(
        user=accepted_answer.author,
        actor=topic.author,
        topic=topic,
        answer=accepted_answer,
        notification_type="accepted_answer",
        send_email=True
    )


# =====================================
# CONSTRUCTION DES MESSAGES
# =====================================

def build_message(notification):
    """Construit le message selon le type de notification"""

    actor_name = notification.actor.get_full_name() or notification.actor.username

    if notification.notification_type == "new_topic":
        return f"{actor_name} a publié un nouveau sujet"

    if notification.notification_type == "new_answer":
        return f"{actor_name} a répondu à votre sujet"

    if notification.notification_type == "reply_to_reply":
        return f"{actor_name} a répondu à votre commentaire"

    if notification.notification_type == "upvote":
        count = notification.vote_count
        if count == 1:
            return f"{actor_name} a voted sur votre contribution"
        return f"{actor_name} et {count - 1} autres ont voted sur votre contribution"

    if notification.notification_type == "accepted_answer":
        return f"{actor_name} a accepté votre réponse comme solution"

    return "Nouvelle notification"


def _build_email_subject(notification):
    """Construit l'objet de l'email"""
    if notification.notification_type == "new_topic":
        return "📝 Nouveau sujet dans votre domaine"
    if notification.notification_type == "new_answer":
        return "💬 Nouvelle réponse à votre sujet"
    if notification.notification_type == "reply_to_reply":
        return "↩️ Nouvelle réponse à votre commentaire"
    if notification.notification_type == "accepted_answer":
        return "✅ Votre réponse a été acceptée !"
    return "🔔 Nouvelle notification ESFE"


def _build_email_content(notification):
    """Construit le contenu de l'email"""
    message = build_message(notification)
    url = notification.get_target_url

    base_url = getattr(settings, "BASE_URL", "https://esfe.fr")
    full_url = f"{base_url}{url}"

    return f"""
Bonjour {notification.user.get_full_name() or notification.user.username},

{message}

📌 {notification.topic.title if notification.topic else 'Voir les détails'}

👁️ Consulter la notification:
{full_url}

---
Cet email a été envoyé par ESFE - École de Santé
    """