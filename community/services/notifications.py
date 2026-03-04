import json
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from django.core.mail import send_mail
from django.conf import settings

from community.models import Notification


def create_notification(
    *,
    user,
    actor,
    topic=None,
    answer=None,
    notification_type,
    send_email=False
):
    """
    Crée notification + websocket + email éventuel
    """

    notification = Notification.objects.create(
        user=user,
        actor=actor,
        topic=topic,
        answer=answer,
        notification_type=notification_type
    )

    # =========================
    # WEBSOCKET
    # =========================

    channel_layer = get_channel_layer()

    async_to_sync(channel_layer.group_send)(
        f"user_{user.id}",
        {
            "type": "send_notification",
            "message": build_message(notification),
            "url": notification.get_url(),
        }
    )

    # =========================
    # EMAIL
    # =========================

    if send_email and user.email:

        send_mail(
            subject="Nouvelle activité sur ESFE",
            message=build_email(notification),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=True
        )

    return notification


def build_message(notification):

    actor = notification.actor.username

    if notification.notification_type == "new_answer":
        return f"{actor} a répondu à votre question"

    if notification.notification_type == "accepted_answer":
        return f"{actor} a accepté votre réponse"

    if notification.notification_type == "new_topic":
        return f"{actor} a posé une question dans votre domaine"

    return "Nouvelle notification"


def build_email(notification):

    message = build_message(notification)

    url = notification.get_url()

    return f"""
{message}

Consulter la discussion :
{url}
"""