import json
import asyncio
import time
import uuid

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

from .service import session_group_name, user_group_name


def _authentication_decision(user):
    # Import tardif : notifier est chargé pendant l'initialisation de payments.
    from accounts.authentication import AuthenticationGate

    return AuthenticationGate.evaluate(user)


def _system_session_state(user, session):
    from accounts.access_context import build_access_context
    from accounts.session_policy import session_deadline_state

    context = build_access_context(user)
    if context.context_type != "SYSTEM":
        return False, None
    return True, session_deadline_state(session, context.position)


def _authoritative_system_session_valid(user_id, identifier, session_key):
    from django.contrib.auth import get_user_model
    from django.contrib.sessions.models import Session
    from django.utils import timezone
    from accounts.models import AccountSessionRecord
    from accounts.session_policy import websocket_session_is_expired

    if not session_key or not AccountSessionRecord.objects.filter(
        identifier=identifier,
        user_id=user_id,
        ended_at__isnull=True,
    ).exists():
        return False
    row = Session.objects.filter(session_key=session_key, expire_date__gt=timezone.now()).first()
    if row is None:
        return False
    decoded = row.get_decoded()
    if str(decoded.get("esfe_system_session_id")) != str(identifier):
        return False
    user = get_user_model().objects.filter(pk=user_id, is_active=True).first()
    return bool(user and _authentication_decision(user).allowed and not websocket_session_is_expired(decoded, user))


class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope["user"]
        if user.is_anonymous:
            await self.close()
            return

        decision = await database_sync_to_async(_authentication_decision)(user)
        if not decision.allowed:
            await self.close(code=4403)
            return

        is_system, state = await database_sync_to_async(_system_session_state)(user, self.scope.get("session", {}))
        if is_system and (state is None or state["reason"] or state["remaining_seconds"] <= 0):
            await self.close(code=4401)
            return

        self.group_name = user_group_name(user.id)
        self.session_group_name = None
        if is_system:
            identifier = self.scope.get("session", {}).get("esfe_system_session_id")
            try:
                identifier = uuid.UUID(str(identifier))
            except (TypeError, ValueError, AttributeError):
                await self.close(code=4401)
                return
            self.session_group_name = session_group_name(identifier)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        if self.session_group_name:
            await self.channel_layer.group_add(self.session_group_name, self.channel_name)
            valid = await database_sync_to_async(_authoritative_system_session_valid)(
                user.id,
                identifier,
                getattr(self.scope.get("session"), "session_key", None),
            )
            if not valid:
                await self.channel_layer.group_discard(self.session_group_name, self.channel_name)
                await self.channel_layer.group_discard(self.group_name, self.channel_name)
                await self.close(code=4401)
                return
        await self.accept()
        self.expiry_task = None
        if state is not None:
            self.session_expires_at = state["expires_at"]
            self._schedule_expiry(state["remaining_seconds"])

    def _schedule_expiry(self, remaining_seconds):
        task = getattr(self, "expiry_task", None)
        if task:
            task.cancel()
        self.expiry_task = asyncio.create_task(self._expire_after(max(0, remaining_seconds)))

    async def _expire_after(self, remaining_seconds):
        try:
            await asyncio.sleep(remaining_seconds)
            await self.send(text_data=json.dumps({"type": "session.expired", "reason": "IDLE_TIMEOUT"}))
            await self.close(code=4401)
        except asyncio.CancelledError:
            return

    async def disconnect(self, close_code):
        user = self.scope["user"]
        if user.is_anonymous:
            return
        task = getattr(self, "expiry_task", None)
        if task:
            task.cancel()
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
        if getattr(self, "session_group_name", None):
            await self.channel_layer.group_discard(self.session_group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        decision = await database_sync_to_async(_authentication_decision)(self.scope["user"])
        if not decision.allowed:
            await self.close(code=4403)

    async def notification_message(self, event):
        await self.send(text_data=json.dumps(event["payload"]))

    async def session_revoked(self, event):
        await self.send(text_data=json.dumps({"type": "session.expired", "reason": event.get("reason")}))
        await self.close(code=4401)

    async def session_activity(self, event):
        expires_at = float(event.get("expires_at", 0))
        if expires_at < float(getattr(self, "session_expires_at", 0)):
            return
        self.session_expires_at = expires_at
        self._schedule_expiry(max(0, expires_at - time.time()))
