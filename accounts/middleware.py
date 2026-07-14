import logging
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.functional import SimpleLazyObject

from accounts.access_context import get_request_access_context
from accounts.shadow_access import compare_access_classification
from accounts.session_policy import (
    SESSION_ID_KEY,
    close_session_record,
    initialize_system_session,
    record_meaningful_activity,
    session_deadline_state,
)
from accounts.models import AccountSecurityEvent, AccountSessionRecord


logger = logging.getLogger("accounts.access_shadow")


class AccessContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.access_context = SimpleLazyObject(
            lambda: get_request_access_context(request)
        )
        response = self.get_response(request)
        if (
            settings.AUTH_POLICY_V2_SHADOW_ENABLED
            and getattr(request.user, "is_authenticated", False)
        ):
            divergence = compare_access_classification(
                request.user,
                context=get_request_access_context(request),
            )
            if divergence:
                logger.warning("access_policy_shadow_divergence", extra=divergence)
        return response


class SystemSessionSecurityMiddleware:
    """Expiration autoritative des sessions SYSTEM, avant toute vue metier."""

    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def _is_htmx(request):
        return request.headers.get("HX-Request", "").lower() == "true"

    @staticmethod
    def _wants_json(request):
        return (
            "application/json" in request.headers.get("Accept", "")
            or request.headers.get("X-Requested-With") == "XMLHttpRequest"
            or request.content_type == "application/json"
        )

    @staticmethod
    def _login_url(request, reason):
        try:
            base = reverse(settings.LOGIN_URL)
        except Exception:
            base = reverse("accounts:login")
        next_path = request.get_full_path()
        if not next_path.startswith("/") or next_path.startswith("//"):
            next_path = "/portal/"
        return f"{base}?{urlencode({'next': next_path, 'session_expired': reason.lower()})}"

    def _expired_response(self, request, reason):
        identifier = request.session.get(SESSION_ID_KEY)
        event_type = (
            AccountSecurityEvent.ABSOLUTE_TIMEOUT
            if reason == AccountSecurityEvent.ABSOLUTE_TIMEOUT
            else AccountSecurityEvent.IDLE_TIMEOUT
        )
        end_reason = (
            AccountSessionRecord.END_ABSOLUTE_TIMEOUT
            if event_type == AccountSecurityEvent.ABSOLUTE_TIMEOUT
            else AccountSessionRecord.END_IDLE_TIMEOUT
        )
        expired_user = request.user
        close_session_record(
            user=expired_user,
            identifier=identifier,
            reason=end_reason,
            request=request,
            event_type=event_type,
        )
        from accounts.session_security import notify_websocket_revocation

        request._suppress_security_logout_signal = True
        logout(request)
        from django.db import transaction

        transaction.on_commit(
            lambda user=expired_user: notify_websocket_revocation(user, reason=end_reason, identifier=identifier)
        )
        login_url = self._login_url(request, event_type)
        messages.warning(request, "Votre session a expire. Reconnectez-vous pour continuer.")

        if self._is_htmx(request):
            response = HttpResponse(status=401)
            response["HX-Redirect"] = login_url
            response["X-ESFE-Session-Expired"] = event_type
            return response
        if self._wants_json(request):
            return JsonResponse(
                {
                    "error": "session_expired",
                    "reason": event_type,
                    "login_url": login_url,
                },
                status=401,
            )
        return redirect(login_url)

    def _unauthenticated_async_response(self, request):
        protected_prefixes = (
            "/portal/",
            "/accounts/dashboard/",
            "/accounts/htmx/",
            "/secretary/",
            "/superadmin/",
            "/marketing/",
        )
        if not request.path.startswith(protected_prefixes):
            return None
        login_url = self._login_url(request, "SESSION_REQUIRED")
        if self._is_htmx(request):
            response = HttpResponse(status=401)
            response["HX-Redirect"] = login_url
            response["X-ESFE-Session-Expired"] = "SESSION_REQUIRED"
            return response
        if self._wants_json(request):
            return JsonResponse(
                {"error": "session_expired", "reason": "SESSION_REQUIRED", "login_url": login_url},
                status=401,
            )
        return None

    def __call__(self, request):
        user = getattr(request, "user", None)
        context = getattr(request, "access_context", None)
        if not user or not user.is_authenticated:
            async_response = self._unauthenticated_async_response(request)
            if async_response is not None:
                return async_response
            return self.get_response(request)
        if not context or context.context_type != "SYSTEM":
            return self.get_response(request)

        initialize_system_session(request)
        state = session_deadline_state(request.session, context.position)
        if state is None:
            initialize_system_session(request)
            state = session_deadline_state(request.session, context.position)
        if state and state["reason"]:
            return self._expired_response(request, state["reason"])

        meaningful_header = request.headers.get("X-ESFE-Meaningful-Activity") == "1"
        automated_request = request.headers.get("X-ESFE-Automated-Request") == "1"
        meaningful_mutation = request.method in {"POST", "PUT", "PATCH", "DELETE"} and not automated_request
        if meaningful_mutation or meaningful_header:
            state = record_meaningful_activity(request)

        response = self.get_response(request)
        if state:
            response["X-ESFE-Session-Remaining"] = str(state["remaining_seconds"])
        return response


class MandatoryPasswordChangeMiddleware:
    """Empêche un mot de passe temporaire de donner accès au logiciel."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            state = getattr(user, "support_state", None)
            if state and state.must_change_password:
                allowed_paths = {
                    reverse("accounts:password_change"),
                    reverse("accounts:password_change_done"),
                    reverse("accounts_portal:system_change_password"),
                    reverse("accounts_portal:system_session_status"),
                    reverse("accounts_portal:system_session_activity"),
                    reverse("accounts:logout"),
                }
                if request.path not in allowed_paths:
                    return redirect("accounts:password_change")
        return self.get_response(request)
