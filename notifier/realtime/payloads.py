from notifier.models import NotificationMessage


def build_notification_payload(message):
    payload = {
        "type": "notifier.notification",
        "id": message.id,
        "title": message.title,
        "body": message.body,
        "event_type": message.event_type,
        "notification_type": message.notification_type,
        "channel": message.channel,
        "priority": message.priority,
        "status": message.status,
        "created_at": message.created_at.isoformat(),
        "metadata": message.metadata,
    }
    if message.recipient_id:
        payload["unread_count"] = NotificationMessage.objects.filter(
            recipient_id=message.recipient_id,
            channel=NotificationMessage.CHANNEL_IN_APP,
            read_at__isnull=True,
        ).count()
    return payload
