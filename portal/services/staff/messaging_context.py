"""Shared internal messaging workspace context.

Generalizes the Director of Studies messaging context (inbox / sent /
archived / trash, filters, threads, attachments) so every staff dashboard
reuses the same experience. The data layer stays in
``notification_center.services.internal_messaging``.
"""

from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Case, CharField, Count, F, Max, Q, When
from django.db.models.functions import Cast
from django.urls import reverse
from django.utils import timezone

from notification_center.presentation import get_safe_action_url
from notification_center.selectors import (
    get_notification_center_queryset,
    get_notification_center_stats,
    get_notification_filter_options,
    get_user_in_app_messages,
    get_user_unread_count,
)
from notifier.models import MessageAttachment, NotificationMessage
from notifier.services import NotificationBus


def _detail_url_for(notification_id, *, detail_url_name, dash=None):
    url = reverse(detail_url_name, args=[notification_id])
    if dash:
        url = f"{url}?dash={dash}"
    return url


def build_staff_messaging_items(
    request,
    notifications,
    *,
    detail_url_name,
    dash=None,
    attachment_batch_ids=None,
    recipient_counts=None,
):
    attachment_batch_ids = set(attachment_batch_ids or [])
    recipient_counts = recipient_counts or {}
    items = []
    for notification in notifications:
        created_at = (
            timezone.localtime(notification.created_at).strftime("%d/%m/%Y %H:%M")
            if notification.created_at
            else ""
        )
        if notification.event_type == "internal_message" and notification.actor_id == request.user.pk:
            source_label = f"À {notification.recipient.get_full_name() or notification.recipient.username}"
        elif notification.actor:
            source_label = f"De {notification.actor.get_full_name() or notification.actor.username}"
        else:
            source_label = notification.event_type or notification.legacy_source or "Système"
        items.append({
            "id": notification.id,
            "title": notification.title,
            "summary": notification.body[:140] if notification.body else "",
            "icon": "bell",
            "source": source_label,
            "time_ago": created_at,
            "is_read": notification.read_at is not None,
            "priority": notification.priority,
            "sender": (
                notification.actor.get_full_name() or notification.actor.username
                if notification.actor
                else "Système"
            ),
            "recipient": (
                notification.recipient.get_full_name() or notification.recipient.username
                if notification.recipient
                else "Destinataire externe"
            ),
            "action_url": get_safe_action_url(notification, request),
            "detail_url": _detail_url_for(notification.id, detail_url_name=detail_url_name, dash=dash),
            "hx_mark_read": "",
            "has_attachment": bool(
                notification.batch_id and notification.batch_id in attachment_batch_ids
            ),
            "recipient_count": recipient_counts.get(notification.pk, 1),
        })
    return items


def _logical_sent_groups(queryset):
    """Return one database row per logical send, including legacy rows."""
    return (
        queryset.annotate(
            _send_group=Case(
                When(batch_id__isnull=True, then=Cast(F("pk"), CharField())),
                default=Cast(F("batch_id"), CharField()),
                output_field=CharField(),
            )
        )
        .values("_send_group")
        .annotate(
            recipient_count=Count("pk"),
            latest_id=Max("pk"),
            latest_created_at=Max("created_at"),
        )
        .order_by("-latest_created_at", "-latest_id")
    )


def build_staff_messaging_context(request, *, detail_url_name, dash=None):
    box = (request.GET.get("box") or request.POST.get("box") or "inbox").strip().lower()
    if box not in {"inbox", "sent", "archived", "trash"}:
        box = "inbox"
    filters = {
        "channel": request.GET.get("channel") or "in_app",
        "status": request.GET.get("status") or "",
        "priority": request.GET.get("priority") or "",
        "source": request.GET.get("source") or "",
        "q": (request.GET.get("q") or "").strip(),
    }
    if box == "sent":
        queryset = NotificationMessage.objects.select_related(
            "actor", "recipient", "event"
        ).filter(
            actor=request.user,
            event_type="internal_message",
            channel=NotificationMessage.CHANNEL_IN_APP,
            deleted_at__isnull=True,
        )
        if filters["q"]:
            queryset = queryset.filter(
                Q(title__icontains=filters["q"])
                | Q(body__icontains=filters["q"])
                | Q(recipient__first_name__icontains=filters["q"])
                | Q(recipient__last_name__icontains=filters["q"])
                | Q(recipient__username__icontains=filters["q"])
            )
    elif box == "trash":
        queryset = NotificationMessage.objects.select_related(
            "actor", "recipient", "event"
        ).filter(
            recipient=request.user,
            channel=NotificationMessage.CHANNEL_IN_APP,
            deleted_at__isnull=False,
        )
        if filters["q"]:
            queryset = queryset.filter(
                Q(title__icontains=filters["q"]) | Q(body__icontains=filters["q"])
            )
    else:
        if box == "archived":
            filters["status"] = "archived"
        queryset = get_notification_center_queryset(request.user, filters)
    queryset = queryset.order_by("-pinned_at", "-created_at")
    recipient_counts = {}
    if box == "sent":
        # Delivery is stored per recipient so their own read/archive/delete
        # state stays isolated. Page logical sends (batches) for the sender.
        sent_groups = _logical_sent_groups(queryset)
        paginator = Paginator(sent_groups, 10)
    else:
        paginator = Paginator(queryset, 10)
    page = request.GET.get("page") or 1
    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages or 1)

    if box == "sent":
        sent_group_rows = list(page_obj.object_list)
        sent_ids = [row["latest_id"] for row in sent_group_rows]
        sent_by_id = {item.pk: item for item in queryset.filter(pk__in=sent_ids)}
        page_notifications = [
            sent_by_id[item_id] for item_id in sent_ids if item_id in sent_by_id
        ]
        recipient_counts = {
            row["latest_id"]: row["recipient_count"] for row in sent_group_rows
        }
        page_obj.object_list = page_notifications
    else:
        page_notifications = list(page_obj.object_list)

    selected_notification = None
    selected_id = (request.GET.get("notification_id") or "").strip()
    if selected_id.isdigit():
        selected_queryset = NotificationMessage.objects.select_related(
            "actor", "recipient", "event"
        ).filter(pk=int(selected_id))
        if box == "sent":
            selected_queryset = selected_queryset.filter(
                actor=request.user,
                event_type="internal_message",
                channel=NotificationMessage.CHANNEL_IN_APP,
            )
        elif box == "trash":
            selected_queryset = selected_queryset.filter(
                recipient=request.user, deleted_at__isnull=False
            )
        else:
            selected_queryset = selected_queryset.filter(recipient=request.user)
        selected_notification = selected_queryset.first()
    if selected_notification is None and page_obj.object_list:
        selected_notification = page_obj.object_list[0]
    if (
        box == "inbox"
        and selected_notification is not None
        and selected_notification.recipient_id == request.user.pk
        and selected_notification.channel == NotificationMessage.CHANNEL_IN_APP
        and selected_notification.read_at is None
    ):
        NotificationBus.mark_as_read(selected_notification)

    stats = get_notification_center_stats(request.user)
    sent_deliveries = NotificationMessage.objects.filter(
        actor=request.user,
        event_type="internal_message",
        channel=NotificationMessage.CHANNEL_IN_APP,
        deleted_at__isnull=True,
    )
    stats["sent"] = _logical_sent_groups(sent_deliveries).count()
    stats["trash"] = NotificationMessage.objects.filter(
        recipient=request.user,
        channel=NotificationMessage.CHANNEL_IN_APP,
        deleted_at__isnull=False,
    ).count()
    selected_attachments = MessageAttachment.objects.none()
    selected_thread = NotificationMessage.objects.none()
    selected_send_recipients = NotificationMessage.objects.none()
    if selected_notification is not None:
        if selected_notification.batch_id:
            selected_attachments = MessageAttachment.objects.filter(
                batch_id=selected_notification.batch_id
            )
        if selected_notification.thread_id:
            selected_thread = NotificationMessage.objects.select_related(
                "actor", "recipient"
            ).filter(
                Q(recipient=request.user) | Q(actor=request.user),
                thread_id=selected_notification.thread_id,
                channel=NotificationMessage.CHANNEL_IN_APP,
                deleted_at__isnull=True,
            ).order_by("created_at", "id")
        if (
            selected_notification.actor_id == request.user.pk
            and selected_notification.batch_id
        ):
            selected_send_recipients = NotificationMessage.objects.select_related(
                "recipient"
            ).filter(
                actor=request.user,
                batch_id=selected_notification.batch_id,
                event_type="internal_message",
                channel=NotificationMessage.CHANNEL_IN_APP,
            ).order_by("recipient__first_name", "recipient__last_name", "recipient__username")
    attachment_batch_ids = set(
        MessageAttachment.objects.filter(
            batch_id__in=[item.batch_id for item in page_notifications if item.batch_id]
        ).values_list("batch_id", flat=True)
    )
    return {
        "page_title": "Messagerie interne",
        "message_box": box,
        "filters": filters,
        "filters_options": get_notification_filter_options(request.user),
        "stats": stats,
        "unread_count": get_user_unread_count(request.user),
        "page_obj": page_obj,
        "notifications": build_staff_messaging_items(
            request,
            page_notifications,
            detail_url_name=detail_url_name,
            dash=dash,
            attachment_batch_ids=attachment_batch_ids,
            recipient_counts=recipient_counts,
        ),
        "selected_notification": selected_notification,
        "selected_attachments": selected_attachments,
        "selected_thread": selected_thread,
        "selected_send_recipients": selected_send_recipients,
    }


def build_staff_messaging_preview_context(request, *, detail_url_name, dash=None):
    notifications = list(get_user_in_app_messages(request.user, limit=6))
    return {
        "unread_count": get_user_unread_count(request.user),
        "notifications": build_staff_messaging_items(
            request, notifications, detail_url_name=detail_url_name, dash=dash
        ),
    }
