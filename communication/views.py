from django.contrib.auth.decorators import login_required
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from communication.models import CommunicationNotification
from communication.selectors import get_user_notifications, get_user_unread_count
from communication.services import NotificationService


@login_required
def notifications(request):
    channel = request.GET.get("channel", "")
    queryset = get_user_notifications(request.user)
    if channel:
        queryset = queryset.filter(channel=channel)

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
        "current_channel": channel,
    }
    if request.headers.get("HX-Request"):
        return render(request, "communication/partials/notifications_list.html", context)
    return render(request, "communication/notifications.html", context)


@login_required
def notifications_partial(request):
    context = {
        "notifications": get_user_notifications(request.user, limit=7),
        "unread_count": get_user_unread_count(request.user),
    }
    return render(request, "communication/partials/notifications_dropdown.html", context)


@login_required
@require_POST
def mark_notification_read(request, pk):
    notification = get_object_or_404(
        CommunicationNotification,
        pk=pk,
        recipient=request.user,
    )
    NotificationService.mark_as_read(notification)
    if request.headers.get("HX-Request"):
        return render(
            request,
            "communication/partials/notification_item.html",
            {"notification": notification},
        )
    return HttpResponse(status=204)


@login_required
@require_POST
def mark_all_notifications_read(request):
    now = timezone.now()
    CommunicationNotification.objects.filter(
        recipient=request.user,
        read_at__isnull=True,
        channel=CommunicationNotification.CHANNEL_IN_APP,
    ).update(
        read_at=now,
        status=CommunicationNotification.STATUS_READ,
        updated_at=now,
    )
    if request.headers.get("HX-Request"):
        return HttpResponse("")
    return redirect("communication:notifications")
