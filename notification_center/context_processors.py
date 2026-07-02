from notification_center.selectors import get_user_unread_count


def notification_widget(request):
    user = getattr(request, "user", None)
    if not getattr(user, "is_authenticated", False):
        return {"notification_unread_count": 0}
    return {"notification_unread_count": get_user_unread_count(user)}
