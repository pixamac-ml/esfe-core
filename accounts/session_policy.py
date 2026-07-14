"""Politique centralisee d'expiration des sessions institutionnelles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import ipaddress
import uuid

from django.conf import settings
from django.utils import timezone

from accounts.access_context import build_access_context
from accounts.models import AccountSecurityEvent, AccountSessionRecord


SESSION_ID_KEY = "esfe_system_session_id"
SESSION_STARTED_KEY = "esfe_system_session_started_at"
SESSION_ACTIVITY_KEY = "esfe_last_meaningful_activity"


@dataclass(frozen=True)
class SessionPolicy:
    idle_seconds: int
    warning_seconds: int
    absolute_seconds: int


def policy_for_position(position: str | None) -> SessionPolicy:
    mapping = settings.SYSTEM_SESSION_IDLE_TIMEOUTS
    idle = int(mapping.get(position, settings.SYSTEM_SESSION_DEFAULT_IDLE_TIMEOUT))
    return SessionPolicy(
        idle_seconds=idle,
        warning_seconds=min(int(settings.SYSTEM_SESSION_WARNING_SECONDS), idle),
        absolute_seconds=int(settings.SYSTEM_SESSION_ABSOLUTE_TIMEOUT),
    )


def _timestamp(now=None) -> float:
    return (now or timezone.now()).timestamp()


def _safe_uuid(value):
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def request_ip(request):
    raw = request.META.get("REMOTE_ADDR", "")
    if settings.USE_X_FORWARDED_HOST:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            raw = forwarded.split(",", 1)[0].strip()
    try:
        return str(ipaddress.ip_address(raw))
    except ValueError:
        return None


def request_user_agent(request):
    return (request.META.get("HTTP_USER_AGENT") or "")[:300]


def _safe_metadata(value, *, key=""):
    forbidden = {"password", "pin", "token", "cookie", "authorization", "session_key", "secret"}
    if any(part in key.lower() for part in forbidden):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k)[:80]: _safe_metadata(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_metadata(item, key=key) for item in value[:50]]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:300]


def log_security_event(*, user, event_type, request=None, identifier=None, reason="", metadata=None, authentication_method="", actor=None):
    return AccountSecurityEvent.objects.create(
        user=user,
        actor=actor,
        session_identifier=_safe_uuid(identifier),
        event_type=event_type,
        reason=str(reason or "")[:80],
        authentication_method=str(authentication_method or "")[:32],
        ip_address=request_ip(request) if request else None,
        user_agent=request_user_agent(request) if request else "",
        metadata=_safe_metadata(metadata or {}),
    )


def initialize_system_session(request, *, user=None, log_login=False, authentication_method="password"):
    user = user or request.user
    context = build_access_context(user)
    if context.context_type != "SYSTEM":
        return None

    now = timezone.now()
    policy = policy_for_position(context.position)
    identifier = _safe_uuid(request.session.get(SESSION_ID_KEY))
    if identifier is None:
        identifier = uuid.uuid4()
        request.session[SESSION_ID_KEY] = str(identifier)
        request.session[SESSION_STARTED_KEY] = _timestamp(now)
        request.session[SESSION_ACTIVITY_KEY] = _timestamp(now)
        AccountSessionRecord.objects.create(
            identifier=identifier,
            user=user,
            position=context.position or "",
            started_at=now,
            last_activity_at=now,
            absolute_expires_at=now + timedelta(seconds=policy.absolute_seconds),
            ip_address=request_ip(request),
            user_agent=request_user_agent(request),
        )
        log_login = True

    if log_login and not AccountSecurityEvent.objects.filter(
        session_identifier=identifier,
        event_type=AccountSecurityEvent.LOGIN_SUCCESS,
    ).exists():
        log_security_event(
            user=user,
            event_type=AccountSecurityEvent.LOGIN_SUCCESS,
            request=request,
            identifier=identifier,
            authentication_method=authentication_method,
        )
    return identifier


def session_deadline_state(session, position, *, now=None):
    now_ts = _timestamp(now)
    policy = policy_for_position(position)
    try:
        started = float(session[SESSION_STARTED_KEY])
        activity = float(session[SESSION_ACTIVITY_KEY])
    except (KeyError, TypeError, ValueError):
        return None
    idle_remaining = policy.idle_seconds - (now_ts - activity)
    absolute_remaining = policy.absolute_seconds - (now_ts - started)
    remaining = min(idle_remaining, absolute_remaining)
    reason = None
    if absolute_remaining <= 0:
        reason = AccountSecurityEvent.ABSOLUTE_TIMEOUT
    elif idle_remaining <= 0:
        reason = AccountSecurityEvent.IDLE_TIMEOUT
    return {
        "remaining_seconds": max(0, int(remaining)),
        "idle_remaining_seconds": max(0, int(idle_remaining)),
        "absolute_remaining_seconds": max(0, int(absolute_remaining)),
        "expires_at": now_ts + max(0, remaining),
        "warning_seconds": policy.warning_seconds,
        "reason": reason,
    }


def record_meaningful_activity(request, *, now=None):
    now = now or timezone.now()
    request.session[SESSION_ACTIVITY_KEY] = _timestamp(now)
    identifier = _safe_uuid(request.session.get(SESSION_ID_KEY))
    if identifier:
        AccountSessionRecord.objects.filter(
            identifier=identifier,
            user=request.user,
            ended_at__isnull=True,
        ).update(last_activity_at=now)
    state = session_deadline_state(request.session, build_access_context(request.user).position, now=now)
    from accounts.session_security import notify_websocket_activity

    notify_websocket_activity(
        request.user,
        identifier=request.session.get(SESSION_ID_KEY),
        expires_at=state["expires_at"],
    )
    return state


def close_session_record(*, user, identifier, reason, request=None, event_type=None):
    identifier = _safe_uuid(identifier)
    now = timezone.now()
    transitioned = False
    if identifier:
        transitioned = bool(AccountSessionRecord.objects.filter(
            identifier=identifier,
            user=user,
            ended_at__isnull=True,
        ).update(ended_at=now, end_reason=reason))
    if event_type and (identifier is None or transitioned):
        log_security_event(
            user=user,
            event_type=event_type,
            request=request,
            identifier=identifier,
            reason=reason,
        )


def websocket_session_is_expired(session, user, *, now=None):
    context = build_access_context(user)
    if context.context_type != "SYSTEM":
        return False
    state = session_deadline_state(session, context.position, now=now)
    return state is None or bool(state["reason"])
