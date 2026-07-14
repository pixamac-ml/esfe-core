"""API commune de pilotage UX des sessions SYSTEM."""

from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from accounts.access_context import get_request_access_context
from accounts.session_policy import SESSION_ID_KEY, record_meaningful_activity, session_deadline_state


def _public_denied():
    return JsonResponse({"error": "system_account_required"}, status=403)


def _payload(state, request):
    return {
        "active": True,
        "remaining_seconds": state["remaining_seconds"],
        "idle_remaining_seconds": state["idle_remaining_seconds"],
        "absolute_remaining_seconds": state["absolute_remaining_seconds"],
        "warning_seconds": state["warning_seconds"],
        "expires_at": state["expires_at"],
        "session_identifier": request.session.get(SESSION_ID_KEY),
        "activity_throttle_seconds": settings.SYSTEM_SESSION_ACTIVITY_THROTTLE_SECONDS,
    }


@login_required
@require_GET
def system_session_status(request):
    context = get_request_access_context(request)
    if context.context_type != "SYSTEM":
        return _public_denied()
    state = session_deadline_state(request.session, context.position)
    return JsonResponse(_payload(state, request))


@login_required
@require_POST
def system_session_activity(request):
    context = get_request_access_context(request)
    if context.context_type != "SYSTEM":
        return _public_denied()
    return JsonResponse(_payload(record_meaningful_activity(request), request))
