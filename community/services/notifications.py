"""
Services de notifications centralises pour la communaute ESFE.

DEPRECATED:
- l'ancien runtime community est retire
- le pilotage passe par communication/
"""
from urllib.parse import urljoin

from django.conf import settings

from communication.models import CommunicationNotification
from communication.services import NotificationService
from communication.services.channel_policy import resolve_channel_policy


def create_notification(
    *,
    user,
    actor,
    topic=None,
    answer=None,
    notification_type,
    send_email=False,
    vote_count=1,
):
    metadata = _build_metadata(topic=topic, answer=answer, vote_count=vote_count)
    event_type = f"community_{notification_type}"
    title = _build_title(notification_type)
    body = build_message(notification_type=notification_type, actor=actor, vote_count=vote_count)

    if notification_type == "upvote":
        existing = _find_existing_notification(
            recipient=user,
            event_type=event_type,
            topic=topic,
            answer=answer,
            unread_only=True,
        )
        if existing:
            next_vote_count = int(existing.metadata.get("vote_count", 1) or 1) + vote_count
            existing.metadata = {
                **existing.metadata,
                "vote_count": next_vote_count,
            }
            existing.body = build_message(
                notification_type=notification_type,
                actor=actor,
                vote_count=next_vote_count,
            )
            existing.title = title
            existing.save(update_fields=["metadata", "body", "title", "updated_at"])
            return existing
    else:
        existing = _find_existing_notification(
            recipient=user,
            event_type=event_type,
            topic=topic,
            answer=answer,
            unread_only=False,
        )
        if existing:
            return None

    default_channels = [
        CommunicationNotification.CHANNEL_IN_APP,
        CommunicationNotification.CHANNEL_WEBSOCKET,
    ]
    if send_email and user.email:
        metadata = {
            **metadata,
            "recipient_email": user.email,
            "context": {
                "message": _build_email_content(
                    recipient=user,
                    notification_type=notification_type,
                    actor=actor,
                    vote_count=vote_count,
                    topic=topic,
                    answer=answer,
                ),
            },
        }
        default_channels.append(CommunicationNotification.CHANNEL_EMAIL_TRANSACTIONAL)

    policy = resolve_channel_policy(
        event_type,
        default_channels=default_channels,
        default_priority=CommunicationNotification.PRIORITY_NORMAL,
        metadata=metadata,
    )

    _event, created_notifications = NotificationService.notify_user(
        recipient=user,
        actor=actor,
        event_type=event_type,
        title=title,
        body=body,
        source_app="community",
        channels=policy["channels"],
        priority=policy["priority"],
        metadata=policy["metadata"],
        dispatch_on_commit=False,
    )
    return created_notifications[0] if created_notifications else None


def notify_new_topic(topic, author):
    subscribers = topic.category.subscribers.exclude(id=author.id)
    for subscriber in subscribers:
        create_notification(
            user=subscriber,
            actor=author,
            topic=topic,
            notification_type="new_topic",
            send_email=True,
        )


def notify_new_answer(topic, answer):
    author = answer.author
    if topic.author != author:
        create_notification(
            user=topic.author,
            actor=author,
            topic=topic,
            answer=answer,
            notification_type="new_answer",
            send_email=True,
        )


def notify_reply_to_reply(parent_answer, reply):
    if parent_answer.author == reply.author:
        return
    create_notification(
        user=parent_answer.author,
        actor=reply.author,
        topic=reply.topic,
        answer=reply,
        notification_type="reply_to_reply",
        send_email=True,
    )


def notify_upvote(answer, voter):
    if answer.author == voter:
        return
    create_notification(
        user=answer.author,
        actor=voter,
        topic=answer.topic,
        answer=answer,
        notification_type="upvote",
        vote_count=1,
        send_email=False,
    )


def notify_accepted_answer(topic, accepted_answer):
    create_notification(
        user=accepted_answer.author,
        actor=topic.author,
        topic=topic,
        answer=accepted_answer,
        notification_type="accepted_answer",
        send_email=True,
    )


def build_message(*, notification_type, actor, vote_count=1):
    actor_name = actor.get_full_name() or actor.username

    if notification_type == "new_topic":
        return f"{actor_name} a publie un nouveau sujet"
    if notification_type == "new_answer":
        return f"{actor_name} a repondu a votre sujet"
    if notification_type == "reply_to_reply":
        return f"{actor_name} a repondu a votre commentaire"
    if notification_type == "upvote":
        if vote_count == 1:
            return f"{actor_name} a vote sur votre contribution"
        return f"{actor_name} et {vote_count - 1} autres ont vote sur votre contribution"
    if notification_type == "accepted_answer":
        return f"{actor_name} a accepte votre reponse comme solution"
    return "Nouvelle notification"


def _build_title(notification_type):
    titles = {
        "new_topic": "Nouveau sujet dans votre domaine",
        "new_answer": "Nouvelle reponse a votre sujet",
        "reply_to_reply": "Nouvelle reponse a votre commentaire",
        "upvote": "Nouveau vote sur votre contribution",
        "accepted_answer": "Votre reponse a ete acceptee",
    }
    return titles.get(notification_type, "Nouvelle notification")


def _build_metadata(*, topic=None, answer=None, vote_count=1):
    url = "/"
    if answer and getattr(answer, "topic", None):
        url = f"{answer.topic.get_absolute_url()}#answer-{answer.id}"
    elif topic:
        url = topic.get_absolute_url()

    return {
        "url": url,
        "topic_id": getattr(topic, "id", None),
        "topic_title": getattr(topic, "title", ""),
        "answer_id": getattr(answer, "id", None),
        "vote_count": vote_count,
    }


def _build_email_content(*, recipient, notification_type, actor, vote_count=1, topic=None, answer=None):
    message = build_message(
        notification_type=notification_type,
        actor=actor,
        vote_count=vote_count,
    )
    url = _build_metadata(topic=topic, answer=answer, vote_count=vote_count)["url"]
    base_url = getattr(settings, "BASE_URL", "https://www.esfe-mali.org")
    full_url = urljoin(base_url.rstrip("/") + "/", str(url).lstrip("/"))
    return (
        f"Bonjour {recipient.get_full_name() or recipient.username},\n\n"
        f"{message}\n\n"
        f"Consulter la notification:\n{full_url}\n"
    )


def _find_existing_notification(*, recipient, event_type, topic=None, answer=None, unread_only=False):
    queryset = CommunicationNotification.objects.filter(
        recipient=recipient,
        event_type=event_type,
        channel=CommunicationNotification.CHANNEL_IN_APP,
        metadata__topic_id=getattr(topic, "id", None),
        metadata__answer_id=getattr(answer, "id", None),
    ).order_by("-created_at")
    if unread_only:
        queryset = queryset.filter(read_at__isnull=True)
    return queryset.first()
