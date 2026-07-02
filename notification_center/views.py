from django.contrib.auth.decorators import login_required
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from notifier.models import NotificationMessage
from notifier.services import NotificationBus
from notification_center.selectors import (
    get_notification_center_queryset,
    get_notification_center_stats,
    get_notification_filter_options,
    get_user_in_app_messages,
    get_user_unread_count,
)


@login_required
def notifications(request):
    selected_notification = None
    selected_notification_id = request.GET.get("notification_id")
    if selected_notification_id:
        selected_notification = get_object_or_404(
            NotificationMessage.objects.select_related("actor", "event").prefetch_related("delivery_attempts"),
            pk=selected_notification_id,
            recipient=request.user,
        )
        if (
            selected_notification.channel == NotificationMessage.CHANNEL_IN_APP
            and selected_notification.read_at is None
        ):
            NotificationBus.mark_as_read(selected_notification)

    filters = {
        "channel": request.GET.get("channel") or getattr(selected_notification, "channel", NotificationMessage.CHANNEL_IN_APP),
        "status": request.GET.get("status", ""),
        "priority": request.GET.get("priority", ""),
        "source": request.GET.get("source", ""),
        "q": request.GET.get("q", "").strip(),
    }
    queryset = get_notification_center_queryset(request.user, filters)

    paginator = Paginator(queryset, 20)
    page = request.GET.get("page", 1)
    try:
        notifications_page = paginator.page(page)
    except PageNotAnInteger:
        notifications_page = paginator.page(1)
    except EmptyPage:
        notifications_page = paginator.page(paginator.num_pages)

    context = {
        "notifications": notifications_page,
        "page_obj": notifications_page,
        "unread_count": get_user_unread_count(request.user),
        "filters": filters,
        "stats": get_notification_center_stats(request.user),
        "selected_notification": selected_notification,
        **get_notification_filter_options(request.user),
    }
    if request.headers.get("HX-Request"):
        return render(request, "notification_center/partials/list.html", context)
    return render(request, "notification_center/index.html", context)


@login_required
def notification_detail(request, pk):
    notification = get_object_or_404(
        NotificationMessage.objects.select_related("actor", "event").prefetch_related("delivery_attempts"),
        pk=pk,
        recipient=request.user,
    )
    if (
        notification.channel == NotificationMessage.CHANNEL_IN_APP
        and notification.read_at is None
    ):
        NotificationBus.mark_as_read(notification)
    return render(request, "notification_center/partials/detail.html", {"notification": notification})


@login_required
def notifications_partial(request):
    context = {
        "notifications": get_user_in_app_messages(request.user, limit=7),
        "unread_count": get_user_unread_count(request.user),
    }
    return render(request, "notification_center/partials/dropdown.html", context)


@login_required
def notifications_widget(request):
    context = {
        "recent_notifications": get_user_in_app_messages(request.user, limit=6),
        "notification_unread_count": get_user_unread_count(request.user),
    }
    return render(request, "notification_center/partials/widget.html", context)


@login_required
@require_POST
def mark_notification_read(request, pk):
    notification = get_object_or_404(
        NotificationMessage,
        pk=pk,
        recipient=request.user,
        channel=NotificationMessage.CHANNEL_IN_APP,
    )
    NotificationBus.mark_as_read(notification)
    if request.headers.get("HX-Request"):
        return render(
            request,
            "notification_center/partials/item.html",
            {"notification": notification},
        )
    return HttpResponse(status=204)


@login_required
@require_POST
def mark_notification_unread(request, pk):
    notification = get_object_or_404(
        NotificationMessage,
        pk=pk,
        recipient=request.user,
        channel=NotificationMessage.CHANNEL_IN_APP,
    )
    notification.read_at = None
    notification.status = NotificationMessage.STATUS_DELIVERED
    notification.save(update_fields=["read_at", "status", "updated_at"])
    if request.headers.get("HX-Request"):
        return render(
            request,
            "notification_center/partials/item.html",
            {"notification": notification},
        )
    return HttpResponse(status=204)


@login_required
@require_POST
def mark_all_notifications_read(request):
    now = timezone.now()
    NotificationMessage.objects.filter(
        recipient=request.user,
        read_at__isnull=True,
        channel=NotificationMessage.CHANNEL_IN_APP,
    ).update(
        read_at=now,
        status=NotificationMessage.STATUS_READ,
        updated_at=now,
    )
    if request.headers.get("HX-Request"):
        context = {
            "recent_notifications": get_user_in_app_messages(request.user, limit=6),
            "notification_unread_count": get_user_unread_count(request.user),
        }
        return render(request, "notification_center/partials/widget.html", context)
    return redirect("notification_center:notifications")
