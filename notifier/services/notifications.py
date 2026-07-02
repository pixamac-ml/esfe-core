from django.utils import timezone

from notifier.models import NotificationMessage
from notifier.services.json_utils import make_json_safe


def create_message(
    *,
    event,
    recipient=None,
    actor=None,
    title="",
    body="",
    notification_type="system",
    event_type="system",
    channel=NotificationMessage.CHANNEL_IN_APP,
    priority=NotificationMessage.PRIORITY_NORMAL,
    metadata=None,
    legacy_source="",
    legacy_object_id="",
    status=NotificationMessage.STATUS_PENDING,
):
    return NotificationMessage.objects.create(
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


def mark_message_read(message):
    if message.read_at:
        return message
    message.read_at = timezone.now()
    message.status = NotificationMessage.STATUS_READ
    message.save(update_fields=["read_at", "status", "updated_at"])
    return message
