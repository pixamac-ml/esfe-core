from django.db.models import Count, Q

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


def get_notification_center_queryset(user, filters=None):
    filters = filters or {}
    queryset = get_user_notifications(user)
    channel = filters.get("channel") or CommunicationNotification.CHANNEL_IN_APP
    status = filters.get("status") or ""
    priority = filters.get("priority") or ""
    source = filters.get("source") or ""
    q = filters.get("q") or ""

    if channel != "all":
        queryset = queryset.filter(channel=channel)
    if status == "unread":
        queryset = queryset.filter(read_at__isnull=True)
    elif status == "read":
        queryset = queryset.filter(read_at__isnull=False)
    elif status:
        queryset = queryset.filter(status=status)
    if priority:
        queryset = queryset.filter(priority=priority)
    if source:
        queryset = queryset.filter(Q(event__source_app=source) | Q(legacy_source=source))
    if q:
        queryset = queryset.filter(
            Q(title__icontains=q)
            | Q(body__icontains=q)
            | Q(event_type__icontains=q)
            | Q(notification_type__icontains=q)
            | Q(legacy_source__icontains=q)
        )
    return queryset


def get_notification_center_stats(user):
    base = CommunicationNotification.objects.filter(recipient=user)
    in_app = base.filter(channel=CommunicationNotification.CHANNEL_IN_APP)
    return {
        "total": in_app.count(),
        "unread": in_app.filter(read_at__isnull=True).count(),
        "critical": in_app.filter(priority=CommunicationNotification.PRIORITY_CRITICAL, read_at__isnull=True).count(),
        "failed": base.filter(status=CommunicationNotification.STATUS_FAILED).count(),
        "email": base.filter(
            channel__in=[
                CommunicationNotification.CHANNEL_EMAIL_TRANSACTIONAL,
                CommunicationNotification.CHANNEL_EMAIL_MARKETING,
            ]
        ).count(),
        "by_source": (
            base.exclude(event__source_app="")
            .values("event__source_app")
            .annotate(total=Count("id"))
            .order_by("-total")[:8]
        ),
    }


def get_notification_filter_options(user):
    base = CommunicationNotification.objects.filter(recipient=user)
    return {
        "channels": CommunicationNotification.CHANNEL_CHOICES,
        "priorities": CommunicationNotification.PRIORITY_CHOICES,
        "sources": (
            base.exclude(event__source_app="")
            .values_list("event__source_app", flat=True)
            .distinct()
            .order_by("event__source_app")
        ),
    }
