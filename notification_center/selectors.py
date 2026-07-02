from django.db.models import Count, Q

from notifier.models import NotificationMessage


def get_user_notifications(user, *, limit=None, channel=None):
    """Backward-compat alias — delegates to get_user_messages."""
    return get_user_messages(user, limit=limit, channel=channel)


def get_user_messages(user, *, limit=None, channel=None):
    queryset = NotificationMessage.objects.filter(recipient=user).select_related("actor", "event")
    if channel:
        queryset = queryset.filter(channel=channel)
    queryset = queryset.order_by("-created_at")
    if limit:
        return queryset[:limit]
    return queryset


def get_user_in_app_messages(user, *, limit=None, exclude_sources=None):
    """Return only messages intended for the persistent user-facing inbox."""
    queryset = get_user_messages(
        user,
        channel=NotificationMessage.CHANNEL_IN_APP,
    )
    if exclude_sources:
        queryset = queryset.exclude(event__source_app__in=exclude_sources)
    if limit:
        return queryset[:limit]
    return queryset


def get_user_unread_count(user, *, exclude_sources=None):
    queryset = NotificationMessage.objects.filter(
        recipient=user,
        read_at__isnull=True,
        channel=NotificationMessage.CHANNEL_IN_APP,
    )
    if exclude_sources:
        queryset = queryset.exclude(event__source_app__in=exclude_sources)
    return queryset.count()


def get_notification_center_queryset(user, filters=None):
    filters = filters or {}
    queryset = get_user_messages(user)
    channel = filters.get("channel") or NotificationMessage.CHANNEL_IN_APP
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
    base = NotificationMessage.objects.filter(recipient=user)
    in_app = base.filter(channel=NotificationMessage.CHANNEL_IN_APP)
    return {
        "total": in_app.count(),
        "unread": in_app.filter(read_at__isnull=True).count(),
        "critical": in_app.filter(priority=NotificationMessage.PRIORITY_CRITICAL, read_at__isnull=True).count(),
        "failed": base.filter(status=NotificationMessage.STATUS_FAILED).count(),
        "email": base.filter(
            channel__in=[
                NotificationMessage.CHANNEL_EMAIL_TRANSACTIONAL,
                NotificationMessage.CHANNEL_EMAIL_MARKETING,
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
    base = NotificationMessage.objects.filter(recipient=user)
    return {
        "channels": NotificationMessage.CHANNEL_CHOICES,
        "priorities": NotificationMessage.PRIORITY_CHOICES,
        "sources": (
            base.exclude(event__source_app="")
            .values_list("event__source_app", flat=True)
            .distinct()
            .order_by("event__source_app")
        ),
    }
