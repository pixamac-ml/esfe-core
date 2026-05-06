from communication.selectors import get_user_unread_count


def build_notification_payload(notification):
    unread_count = None
    if notification.recipient_id:
        unread_count = get_user_unread_count(notification.recipient)
    return {
        "type": "communication.notification",
        "id": notification.id,
        "title": notification.title,
        "body": notification.body,
        "event_type": notification.event_type,
        "notification_type": notification.notification_type,
        "channel": notification.channel,
        "priority": notification.priority,
        "status": notification.status,
        "created_at": notification.created_at.isoformat(),
        "metadata": notification.metadata,
        "unread_count": unread_count,
    }
