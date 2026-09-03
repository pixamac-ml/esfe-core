"""Generic staff workspace endpoints shared by every certified dashboard.

These views provide, for any staff user (gestionnaire, secretaire,
surveillant general, informaticien, enseignant, DG, marketing, superadmin):

* the integrated account drawer (profile / edit / security / preferences);
* the internal messaging workspace (inbox / sent / archived / trash,
  compose, reply, forward) on top of ``notification_center`` services;
* the personal read-only salary workspace on top of ``PayrollEntry``.

Each dashboard links these endpoints with ``?dash=<dashboard key>`` so the
HTMX targets (workspace, drawer, modal) resolve back to the caller's
certified shell. Data access stays scoped to ``request.user``.
"""

from __future__ import annotations

import json
from functools import wraps
from uuid import uuid4

from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.access import can_access
from accounts.dashboards.helpers import paginate_queryset
from accounts.forms import SystemProfileForm, UserPreferenceForm
from accounts.models import PayrollEntry, Profile, UserPreference
from notification_center.services.internal_messaging import (
    resolve_internal_message_recipients,
    send_internal_message,
)
from notifier.models import MessageAttachment, NotificationMessage
from notifier.services import NotificationBus
from portal.forms import DirectorInternalMessageForm
from portal.services.director import build_director_salary_context
from portal.services.staff import (
    build_staff_account_context,
    build_staff_messaging_context,
    build_staff_messaging_preview_context,
    resolve_staff_dashboard,
)


def _staff_user_allowed(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return can_access(user, "view_portal", "staff") or can_access(
        user, "view_portal", "teacher"
    )


def staff_common_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not _staff_user_allowed(request.user):
            from portal.views.views import _deny_portal_access

            return _deny_portal_access(request)
        return view_func(request, *args, **kwargs)

    return login_required(wrapper)


def _resolve_target(request):
    dash = (
        request.GET.get("dash") or request.POST.get("dash") or ""
    ).strip().lower()
    return resolve_staff_dashboard(dash)


def _bad_dash():
    return HttpResponseBadRequest("Dashboard staff inconnu.")


def _hx_toast(message, *, tone="success", extra=None):
    payload = {"ui:toast": {"message": message, "tone": tone}}
    if extra:
        payload.update(extra)
    return json.dumps(payload, ensure_ascii=True)


# ---------------------------------------------------------------------------
# Compte (profil / securite / preferences)
# ---------------------------------------------------------------------------


@staff_common_required
def staff_account_panel(request):
    view_name = (
        request.GET.get("view") or request.POST.get("view") or "profile"
    ).strip().lower()
    if view_name not in {"profile", "edit", "security", "preferences"}:
        return HttpResponseBadRequest("Vue de compte inconnue.")
    target = _resolve_target(request)
    if target is None:
        return _bad_dash()

    panel_url = reverse("accounts_portal:staff_account_panel")
    base_context = {
        "staff_dash": target.key,
        "panel_url": f"{panel_url}?dash={target.key}",
        "panel_edit_url": f"{panel_url}?dash={target.key}&view=edit",
        "panel_security_url": f"{panel_url}?dash={target.key}&view=security",
        "panel_preferences_url": f"{panel_url}?dash={target.key}&view=preferences",
        "drawer_content_target": target.drawer_content_target,
        "drawer_id": target.drawer_id,
    }
    profile_context = build_staff_account_context(
        request,
        panel_url_name="accounts_portal:staff_account_panel",
        drawer_content_target=target.drawer_content_target,
    )
    system_profile, _ = Profile.objects.get_or_create(user=request.user)
    preference, _ = UserPreference.objects.get_or_create(user=request.user)

    if request.method == "POST":
        if view_name == "edit":
            form = SystemProfileForm(
                request.POST, request.FILES, instance=system_profile, user=request.user
            )
            if form.is_valid():
                form.save()
                response = render(
                    request,
                    "portal/staff/shared/account/panel_profile.html",
                    {**base_context, **profile_context},
                )
                response["HX-Trigger"] = _hx_toast(
                    "Profil mis a jour.", extra={"account:profile-updated": True}
                )
                return response
            return render(
                request,
                "portal/staff/shared/account/panel_edit.html",
                {
                    **base_context,
                    "form": form,
                    "profile": system_profile,
                },
                status=400,
            )
        if view_name == "security":
            form = PasswordChangeForm(request.user, request.POST)
            if form.is_valid():
                from django.contrib.auth import update_session_auth_hash

                user = form.save()
                update_session_auth_hash(request, user)
                response = render(
                    request,
                    "portal/staff/shared/account/panel_security.html",
                    {
                        **base_context,
                        "password_form": PasswordChangeForm(request.user),
                        "email": request.user.email,
                    },
                )
                response["HX-Trigger"] = _hx_toast(
                    "Mot de passe mis a jour.", extra={"account:profile-updated": True}
                )
                return response
            return render(
                request,
                "portal/staff/shared/account/panel_security.html",
                {
                    **base_context,
                    "password_form": form,
                    "email": request.user.email,
                },
                status=400,
            )
        if view_name == "preferences":
            form = UserPreferenceForm(request.POST, instance=preference)
            if form.is_valid():
                form.save()
                response = render(
                    request,
                    "portal/staff/shared/account/panel_preferences.html",
                    {**base_context, "form": UserPreferenceForm(instance=preference)},
                )
                response["HX-Trigger"] = _hx_toast(
                    "Preferences mises a jour.",
                    extra={"account:profile-updated": True},
                )
                return response
            return render(
                request,
                "portal/staff/shared/account/panel_preferences.html",
                {**base_context, "form": form},
                status=400,
            )

    if view_name == "profile":
        return render(
            request,
            "portal/staff/shared/account/panel_profile.html",
            {**base_context, **profile_context},
        )
    if view_name == "edit":
        return render(
            request,
            "portal/staff/shared/account/panel_edit.html",
            {
                **base_context,
                "form": SystemProfileForm(instance=system_profile, user=request.user),
                "profile": system_profile,
            },
        )
    if view_name == "security":
        return render(
            request,
            "portal/staff/shared/account/panel_security.html",
            {
                **base_context,
                "password_form": PasswordChangeForm(request.user),
                "email": request.user.email,
            },
        )
    return render(
        request,
        "portal/staff/shared/account/panel_preferences.html",
        {**base_context, "form": UserPreferenceForm(instance=preference)},
    )


# ---------------------------------------------------------------------------
# Messagerie interne
# ---------------------------------------------------------------------------


def _messaging_common_context(request, target):
    return {
        "staff_dash": target.key,
        "staff_workspace_target": target.workspace_target,
        "staff_modal_target": target.modal_content_target,
        "staff_drawer_target": target.drawer_content_target,
    }


@staff_common_required
def staff_notifications_preview(request):
    target = _resolve_target(request)
    if target is None:
        return _bad_dash()
    context = build_staff_messaging_preview_context(
        request,
        detail_url_name="accounts_portal:staff_notification_detail",
        dash=target.key,
    )
    messaging_url = reverse("accounts_portal:staff_messaging")
    for notification in context["notifications"]:
        notification["detail_url"] = (
            f"{messaging_url}?dash={target.key}&notification_id={notification['id']}"
        )
    context.update(_messaging_common_context(request, target))
    return render(
        request, "portal/staff/shared/messaging/preview.html", context
    )


@staff_common_required
def staff_messaging_workspace(request):
    target = _resolve_target(request)
    if target is None:
        return _bad_dash()
    context = build_staff_messaging_context(
        request,
        detail_url_name="accounts_portal:staff_notification_detail",
        dash=target.key,
    )
    context.update(_messaging_common_context(request, target))
    response = render(
        request, "portal/staff/shared/messaging/workspace.html", context
    )
    response["HX-Push-Url"] = target.dashboard_url
    return response


@staff_common_required
def staff_notification_detail(request, pk):
    target = _resolve_target(request)
    if target is None:
        return _bad_dash()
    notification = get_object_or_404(
        NotificationMessage.objects.select_related("actor", "recipient", "event").filter(
            Q(recipient=request.user)
            | Q(
                actor=request.user,
                event_type="internal_message",
                channel=NotificationMessage.CHANNEL_IN_APP,
            )
        ),
        pk=pk,
    )
    if (
        notification.channel == NotificationMessage.CHANNEL_IN_APP
        and notification.recipient_id == request.user.pk
        and notification.read_at is None
    ):
        NotificationBus.mark_as_read(notification)
    selected_send_recipients = NotificationMessage.objects.none()
    if notification.actor_id == request.user.pk and notification.batch_id:
        selected_send_recipients = NotificationMessage.objects.select_related(
            "recipient"
        ).filter(
            actor=request.user,
            batch_id=notification.batch_id,
            event_type="internal_message",
            channel=NotificationMessage.CHANNEL_IN_APP,
        ).order_by("recipient__first_name", "recipient__last_name", "recipient__username")
    context = {
        **_messaging_common_context(request, target),
        "notification": notification,
        "message_box": (request.GET.get("box") or "inbox").strip().lower(),
        "selected_attachments": (
            MessageAttachment.objects.filter(batch_id=notification.batch_id)
            if notification.batch_id
            else MessageAttachment.objects.none()
        ),
        "selected_thread": (
            NotificationMessage.objects.select_related("actor", "recipient").filter(
                Q(recipient=request.user) | Q(actor=request.user),
                thread_id=notification.thread_id,
                channel=NotificationMessage.CHANNEL_IN_APP,
                deleted_at__isnull=True,
            ).order_by("created_at", "id")
            if notification.thread_id
            else NotificationMessage.objects.none()
        ),
        "selected_send_recipients": selected_send_recipients,
    }
    response = render(
        request, "portal/staff/shared/messaging/detail.html", context
    )
    response["HX-Trigger"] = "notification.read"
    return response


@staff_common_required
@require_POST
def staff_notification_action(request, pk):
    target = _resolve_target(request)
    if target is None:
        return _bad_dash()
    notification = get_object_or_404(
        NotificationMessage,
        pk=pk,
        recipient=request.user,
        channel=NotificationMessage.CHANNEL_IN_APP,
    )
    action = (request.POST.get("action") or "").strip().lower()
    if action == "archive":
        NotificationBus.archive(notification)
        message = "Message archive."
    elif action == "unarchive":
        NotificationBus.unarchive(notification)
        message = "Message replacé dans la boîte de réception."
    elif action == "read":
        NotificationBus.mark_as_read(notification)
        message = "Message marqué comme lu."
    elif action == "unread":
        notification.read_at = None
        notification.status = NotificationMessage.STATUS_DELIVERED
        notification.save(update_fields=["read_at", "status", "updated_at"])
        message = "Message marqué comme non lu."
    elif action == "pin":
        notification.pinned_at = timezone.now()
        notification.save(update_fields=["pinned_at", "updated_at"])
        message = "Message épinglé."
    elif action == "unpin":
        notification.pinned_at = None
        notification.save(update_fields=["pinned_at", "updated_at"])
        message = "Message désépinglé."
    elif action == "delete":
        notification.deleted_at = timezone.now()
        notification.save(update_fields=["deleted_at", "updated_at"])
        message = "Message placé dans la corbeille."
    elif action == "restore":
        notification.deleted_at = None
        notification.save(update_fields=["deleted_at", "updated_at"])
        message = "Message restauré."
    else:
        return HttpResponseBadRequest("Action inconnue.")
    context = build_staff_messaging_context(
        request,
        detail_url_name="accounts_portal:staff_notification_detail",
        dash=target.key,
    )
    context.update(_messaging_common_context(request, target))
    response = render(
        request, "portal/staff/shared/messaging/workspace.html", context
    )
    response["HX-Trigger"] = _hx_toast(
        message, extra={"notificationsChanged": True}
    )
    return response


@staff_common_required
@require_POST
def staff_mark_all_notifications_read(request):
    target = _resolve_target(request)
    if target is None:
        return _bad_dash()
    now = timezone.now()
    NotificationMessage.objects.filter(
        recipient=request.user,
        read_at__isnull=True,
        archived_at__isnull=True,
        deleted_at__isnull=True,
        channel=NotificationMessage.CHANNEL_IN_APP,
    ).update(read_at=now, status=NotificationMessage.STATUS_READ, updated_at=now)
    context = build_staff_messaging_context(
        request,
        detail_url_name="accounts_portal:staff_notification_detail",
        dash=target.key,
    )
    context.update(_messaging_common_context(request, target))
    response = render(
        request, "portal/staff/shared/messaging/workspace.html", context
    )
    response["HX-Trigger"] = _hx_toast(
        "Toutes les notifications ont ete marquees comme lues.",
        extra={"notificationsChanged": True},
    )
    return response


@staff_common_required
def staff_message_compose(request):
    target = _resolve_target(request)
    if target is None:
        return _bad_dash()
    workspace_mode = (
        request.GET.get("workspace") or request.POST.get("workspace") or ""
    ) == "1"
    submission_key = (
        request.GET.get("submission_key")
        or request.POST.get("submission_key")
        or uuid4().hex
    ).strip()
    if len(submission_key) > 64 or not submission_key.replace("-", "").isalnum():
        submission_key = uuid4().hex
    branch = getattr(getattr(request.user, "profile", None), "branch", None)
    initial = {}
    parent_message = None
    reply_to = (
        request.GET.get("reply_to") or request.POST.get("reply_to") or ""
    ).strip()
    if reply_to.isdigit():
        source = NotificationMessage.objects.select_related(
            "actor", "actor__profile"
        ).filter(
            pk=int(reply_to),
            recipient=request.user,
        )
        if branch is not None:
            source = source.filter(actor__profile__branch=branch)
        source = source.first()
        if source and source.actor_id != request.user.pk:
            parent_message = source
            initial = {
                "audience": "individual",
                "recipients": [source.actor_id],
                "title": f"Re: {source.title}"[:255],
            }
    forward_from = (
        request.GET.get("forward_from") or request.POST.get("forward_from") or ""
    ).strip()
    if forward_from.isdigit() and parent_message is None:
        source = (
            NotificationMessage.objects.select_related("actor", "recipient")
            .filter(
                Q(recipient=request.user) | Q(actor=request.user),
                pk=int(forward_from),
                event_type="internal_message",
                channel=NotificationMessage.CHANNEL_IN_APP,
            )
            .first()
        )
        if source:
            initial = {
                "audience": "individual",
                "title": f"Tr: {source.title}"[:255],
                "body": f"\n\n--- Message transféré ---\n{source.body}",
            }

    form = DirectorInternalMessageForm(
        request.POST or None,
        request.FILES or None,
        branch=branch,
        user=request.user,
        initial=initial,
    )
    # The native multiple-select remains in the form for Django validation;
    # the workspace composer drives it from its richer recipient cards.
    form.fields["recipients"].widget.attrs["x-ref"] = "recipients"
    if request.method == "POST" and form.is_valid():
        idempotency_key = f"staff-message-send:{request.user.pk}:{submission_key}"
        if not cache.add(idempotency_key, True, timeout=180):
            form.add_error(None, "Ce message est deja en cours d'envoi ou a deja ete envoye.")
        else:
            try:
                resolved = resolve_internal_message_recipients(
                    sender=request.user,
                    branch=branch,
                    direct_recipient_ids=[
                        recipient.pk for recipient in form.cleaned_data["recipients"]
                    ],
                    audience=form.cleaned_data["audience"],
                    class_ids=(
                        form.cleaned_data["target_classes"].values_list("id", flat=True)
                        if form.cleaned_data.get("target_classes") is not None
                        else []
                    ),
                    programme_ids=(
                        form.cleaned_data["target_programmes"].values_list("id", flat=True)
                        if form.cleaned_data.get("target_programmes") is not None
                        else []
                    ),
                    role_tokens=form.cleaned_data.get("target_roles", []),
                )
                result = send_internal_message(
                    sender=request.user,
                    branch=branch,
                    recipients=resolved,
                    title=form.cleaned_data["title"],
                    body=form.cleaned_data["body"],
                    priority=form.cleaned_data["priority"],
                    audience=form.cleaned_data["audience"],
                    attachment=form.cleaned_data.get("attachment"),
                    parent_message=parent_message,
                )
            except ValidationError as exc:
                cache.delete(idempotency_key)
                form.add_error(None, " ".join(exc.messages))
            else:
                original_get = request.GET
                params = request.GET.copy()
                params["box"] = "sent"
                request.GET = params
                try:
                    context = build_staff_messaging_context(
                        request,
                        detail_url_name="accounts_portal:staff_notification_detail",
                        dash=target.key,
                    )
                finally:
                    request.GET = original_get
                context.update(_messaging_common_context(request, target))
                response = render(
                    request, "portal/staff/shared/messaging/workspace.html", context
                )
                response["HX-Retarget"] = target.workspace_target
                response["HX-Push-Url"] = target.dashboard_url
                response["HX-Trigger"] = _hx_toast(
                    f"Message envoyé à {result['recipient_count']} destinataire(s).",
                    extra={
                        "certified-dashboard:close-modal": True,
                        "notificationsChanged": True,
                    },
                )
                return response
    composer_context = {
        **_messaging_common_context(request, target),
        "message_form": form,
        "composer_form": form,
        "message_recipients": _message_recipient_profiles(form),
        "submission_key": submission_key,
        "reply_to": reply_to,
        "forward_from": forward_from,
    }
    if workspace_mode:
        workspace_context = build_staff_messaging_context(
            request,
            detail_url_name="accounts_portal:staff_notification_detail",
            dash=target.key,
        )
        workspace_context.update(composer_context)
        return render(
            request,
            "portal/staff/shared/messaging/workspace.html",
            workspace_context,
        )
    return render(request, "portal/staff/shared/messaging/compose.html", composer_context)


def _message_recipient_profiles(form):
    """Presentation-only recipient data for the shared message composer.

    The form queryset remains the authority for recipient scope and validation.
    This small projection only lets the template render useful chat-style cards
    instead of exposing a bare multiple-select element.
    """
    selected_ids = {str(value) for value in form["recipients"].value() or []}
    recipients = []
    for user in form.fields["recipients"].queryset:
        profile = getattr(user, "profile", None)
        name = user.get_full_name() or user.username
        position = profile.get_position_display() if profile and profile.position else "Utilisateur"
        recipients.append(
            {
                "id": user.pk,
                "name": name,
                "username": user.username,
                "position": position,
                "initial": name[:1].upper(),
                "selected": str(user.pk) in selected_ids,
            }
        )
    return recipients


# ---------------------------------------------------------------------------
# Mon salaire (lecture seule, PayrollEntry de l'utilisateur connecte)
# ---------------------------------------------------------------------------


_SALARY_SUBVIEW_TEMPLATES = {
    "overview": "portal/staff/shared/salary/overview.html",
    "history": "portal/staff/shared/salary/history.html",
}


def _staff_salary_tabs(*, active, dash, period):
    fragment_url = reverse("accounts_portal:staff_salary_subcontent")
    tabs = []
    for item_id, label, icon in (
        ("overview", "Vue d'ensemble", "wallet"),
        ("history", "Historique", "history"),
    ):
        href = f"{fragment_url}?dash={dash}&view={item_id}&period={period}"
        tabs.append(
            {
                "id": item_id,
                "label": label,
                "icon": icon,
                "href": href,
                "hx_get": href,
                "hx_target": "#staff-salary-subcontent",
                "hx_swap": "innerHTML",
                "hx_push_url": href,
                "hx_indicator": "#staff-salary-loading",
                "hx_sync": "#staff-salary-subcontent:replace",
            }
        )
    return tabs


def _build_staff_salary_context(request, target):
    salary_context = build_director_salary_context(
        user=request.user,
        branch=None,
        period_month=request.GET.get("period") or request.POST.get("period"),
    )
    subview = (
        request.GET.get("view") or request.POST.get("view") or "overview"
    ).strip().lower()
    if subview not in _SALARY_SUBVIEW_TEMPLATES:
        subview = "overview"
    history_page = paginate_queryset(
        request,
        salary_context["salary_history_rows"],
        per_page=10,
        page_param="salary_page",
    )
    return {
        **salary_context,
        "salary_subview": subview,
        "salary_history_page": history_page,
        "salary_tabs": _staff_salary_tabs(
            active=subview,
            dash=target.key,
            period=salary_context["salary_period_value"],
        ),
        "salary_query_suffix": (
            f"dash={target.key}&view={subview}"
            f"&period={salary_context['salary_period_value']}"
        ),
        "staff_dash": target.key,
        "staff_salary_url": reverse("accounts_portal:staff_salary"),
        "staff_salary_subcontent_url": reverse(
            "accounts_portal:staff_salary_subcontent"
        ),
        "staff_dashboard_url": target.dashboard_url,
    }


@staff_common_required
def staff_salary_section(request):
    target = _resolve_target(request)
    if target is None:
        return _bad_dash()
    if not PayrollEntry.objects.filter(employee=request.user).exists():
        response = render(
            request,
            "portal/staff/shared/salary/none.html",
            {"staff_dash": target.key},
        )
        response["HX-Push-Url"] = target.dashboard_url
        return response
    context = _build_staff_salary_context(request, target)
    response = render(
        request, "portal/staff/shared/salary/section.html", context
    )
    response["HX-Push-Url"] = target.dashboard_url
    return response


@staff_common_required
def staff_salary_subcontent(request):
    target = _resolve_target(request)
    if target is None:
        return _bad_dash()
    raw_view = (request.GET.get("view") or "").strip().lower()
    subview = raw_view if raw_view in _SALARY_SUBVIEW_TEMPLATES else "overview"
    context = _build_staff_salary_context(request, target)
    response = render(request, _SALARY_SUBVIEW_TEMPLATES[subview], context)
    response["HX-Push-Url"] = target.dashboard_url
    return response
