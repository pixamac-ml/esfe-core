from django.utils import timezone

from communication.models import CommunicationNotification
from communication.services.json_utils import make_json_safe


def create_notification(
    *,
    event,
    recipient=None,
    actor=None,
    title="",
    body="",
    notification_type="system",
    event_type="system",
    channel=CommunicationNotification.CHANNEL_IN_APP,
    priority=CommunicationNotification.PRIORITY_NORMAL,
    metadata=None,
    legacy_source="",
    legacy_object_id="",
    status=CommunicationNotification.STATUS_PENDING,
):
    return CommunicationNotification.objects.create(
        event=event,
        recipient=recipient,
        actor=actor,
        title=title,
        body=body,
        notification_type=notification_type,
        event_type=event_type,
        channel=channel,
        priority=priority,
        metadata=make_json_safe(metadata or {}),
        legacy_source=legacy_source,
        legacy_object_id=str(legacy_object_id or ""),
        status=status,
    )


def mark_notification_read(notification):
    if notification.read_at:
        return notification
    notification.read_at = timezone.now()
    notification.status = CommunicationNotification.STATUS_READ
    notification.save(update_fields=["read_at", "status", "updated_at"])
    return notification
