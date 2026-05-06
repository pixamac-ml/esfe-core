from communication.models import CommunicationNotification


def get_user_notifications(user, *, limit=None, channel=None):
    queryset = CommunicationNotification.objects.filter(recipient=user).select_related("actor", "event")
    if channel:
        queryset = queryset.filter(channel=channel)
    queryset = queryset.order_by("-created_at")
    if limit:
        return queryset[:limit]
    return queryset


def get_user_unread_count(user):
    return CommunicationNotification.objects.filter(
        recipient=user,
        read_at__isnull=True,
        channel=CommunicationNotification.CHANNEL_IN_APP,
    ).count()
