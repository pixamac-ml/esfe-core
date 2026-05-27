from communication.selectors import get_user_notifications, get_user_unread_count


def notification_widget(request):
    user = getattr(request, "user", None)
    if not getattr(user, "is_authenticated", False):
        return {
            "communication_unread_count": 0,
            "communication_recent_notifications": [],
        }
    return {
        "communication_unread_count": get_user_unread_count(user),
        "communication_recent_notifications": get_user_notifications(user, limit=6),
    }
