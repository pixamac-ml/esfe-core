"""Gestion centralisée des sessions lors des changements de sécurité."""

from django.contrib.sessions.models import Session
from django.db import transaction
from django.utils import timezone


def notify_websocket_revocation(user, *, reason="SESSION_REVOKED", identifier=None):
    """Ferme les sockets deja actifs via leur groupe utilisateur."""
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        from notifier.realtime.service import session_group_name, user_group_name

        layer = get_channel_layer()
        if layer:
            async_to_sync(layer.group_send)(
                session_group_name(identifier) if identifier else user_group_name(user.pk),
                {"type": "session_revoked", "reason": reason},
            )
    except Exception:
        # La revocation de la session HTTP ne depend jamais de Channels.
        pass


def notify_websocket_activity(user, *, identifier, expires_at):
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        from notifier.realtime.service import session_group_name

        layer = get_channel_layer()
        if layer:
            async_to_sync(layer.group_send)(
                session_group_name(identifier),
                {"type": "session_activity", "expires_at": float(expires_at)},
            )
    except Exception:
        pass


def revoke_user_sessions(user, *, exclude_session_key=None, reason="ADMIN_REVOKED", global_scope=False):
    """Révoque les sessions Django appartenant à ``user``."""
    sessions = Session.objects.filter(expire_date__gte=timezone.now())
    if exclude_session_key:
        sessions = sessions.exclude(session_key=exclude_session_key)

    revoked = 0
    for session in sessions.iterator():
        decoded = session.get_decoded()
        if str(decoded.get("_auth_user_id")) == str(user.pk):
            from accounts.models import AccountSecurityEvent, AccountSessionRecord
            from accounts.session_policy import close_session_record

            event_type = None
            if reason == AccountSessionRecord.END_ADMIN_REVOKED:
                event_type = AccountSecurityEvent.ADMIN_REVOKED
            close_session_record(
                user=user,
                identifier=decoded.get("esfe_system_session_id"),
                reason=reason,
                event_type=event_type,
            )
            identifier = decoded.get("esfe_system_session_id")
            session.delete()
            transaction.on_commit(
                lambda user=user, reason=reason, identifier=identifier: notify_websocket_revocation(
                    user,
                    reason=reason,
                    identifier=identifier,
                )
            )
            revoked += 1
    if global_scope:
        transaction.on_commit(lambda: notify_websocket_revocation(user, reason=reason))
    return revoked


def mark_temporary_password(user, *, updated_by=None):
    """Force le renouvellement du mot de passe et invalide les accès existants."""
    from portal.services.it_support_service import get_account_support_state

    state = get_account_support_state(user)
    state.must_change_password = True
    state.updated_by = updated_by
    state.save(update_fields=["must_change_password", "updated_by", "updated_at"])
    from accounts.models import AccountSecurityEvent, AccountSessionRecord
    from accounts.session_policy import log_security_event

    log_security_event(
        user=user,
        actor=updated_by,
        event_type=AccountSecurityEvent.PASSWORD_CHANGED,
        reason=AccountSessionRecord.END_PASSWORD_CHANGED,
        authentication_method="administrative_reset",
    )
    revoke_user_sessions(
        user,
        reason=AccountSessionRecord.END_PASSWORD_CHANGED,
        global_scope=True,
    )
    return state
