from types import SimpleNamespace
from unittest.mock import patch
import json
import uuid

from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from channels.layers import get_channel_layer
from django.test import SimpleTestCase

from accounts.authentication import AuthenticationDecision
from notifier.realtime.consumer import NotificationConsumer
from notifier.realtime.service import session_group_name


class NotificationWebSocketSecurityTests(SimpleTestCase):
    def _connect(self, user):
        async def scenario():
            communicator = WebsocketCommunicator(
                NotificationConsumer.as_asgi(),
                "/ws/notifications/",
            )
            communicator.scope["user"] = user
            connected, detail = await communicator.connect()
            if connected:
                await communicator.disconnect()
            return connected, detail

        return async_to_sync(scenario)()

    def test_anonymous_connection_is_rejected(self):
        connected, _ = self._connect(SimpleNamespace(is_anonymous=True))
        self.assertFalse(connected)

    @patch("notifier.realtime.consumer._authentication_decision")
    def test_suspended_or_blocked_account_is_rejected(self, evaluate):
        evaluate.return_value = AuthenticationDecision(False, "account_suspended", "Suspendu")
        user = SimpleNamespace(is_anonymous=False, id=42)

        connected, close_code = self._connect(user)

        self.assertFalse(connected)
        self.assertEqual(close_code, 4403)

    @patch("notifier.realtime.consumer._authentication_decision")
    def test_valid_public_or_system_account_is_accepted(self, evaluate):
        evaluate.return_value = AuthenticationDecision(True)
        user = SimpleNamespace(is_anonymous=False, id=43)

        connected, _ = self._connect(user)

        self.assertTrue(connected)

    @patch("notifier.realtime.consumer._authentication_decision")
    @patch("notifier.realtime.consumer._system_session_state")
    def test_system_session_without_security_state_is_rejected(self, session_state, evaluate):
        evaluate.return_value = AuthenticationDecision(True)
        session_state.return_value = (True, None)
        user = SimpleNamespace(is_anonymous=False, id=44)

        connected, close_code = self._connect(user)

        self.assertFalse(connected)
        self.assertEqual(close_code, 4401)

    @patch("notifier.realtime.consumer._authentication_decision")
    @patch("notifier.realtime.consumer._system_session_state")
    def test_expired_system_session_is_rejected(self, session_state, evaluate):
        evaluate.return_value = AuthenticationDecision(True)
        session_state.return_value = (True, {"reason": "IDLE_TIMEOUT", "remaining_seconds": 0})
        user = SimpleNamespace(is_anonymous=False, id=45)

        connected, close_code = self._connect(user)

        self.assertFalse(connected)
        self.assertEqual(close_code, 4401)

    @patch("notifier.realtime.consumer._authoritative_system_session_valid", return_value=True)
    @patch("notifier.realtime.consumer._authentication_decision")
    @patch("notifier.realtime.consumer._system_session_state")
    def test_active_system_socket_closes_on_opaque_session_revocation(self, session_state, evaluate, authoritative):
        evaluate.return_value = AuthenticationDecision(True)
        session_state.return_value = (
            True,
            {"reason": None, "remaining_seconds": 120, "expires_at": 9999999999},
        )
        identifier = uuid.uuid4()
        user = SimpleNamespace(is_anonymous=False, id=46)

        async def scenario():
            communicator = WebsocketCommunicator(NotificationConsumer.as_asgi(), "/ws/notifications/")
            communicator.scope["user"] = user
            communicator.scope["session"] = {"esfe_system_session_id": str(identifier)}
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await get_channel_layer().group_send(
                session_group_name(identifier),
                {"type": "session_revoked", "reason": "IDLE_TIMEOUT"},
            )
            payload = json.loads(await communicator.receive_from())
            self.assertEqual(payload["type"], "session.expired")
            await communicator.wait()

        async_to_sync(scenario)()

    @patch("notifier.realtime.consumer._authoritative_system_session_valid", return_value=True)
    @patch("notifier.realtime.consumer._authentication_decision")
    @patch("notifier.realtime.consumer._system_session_state")
    def test_websocket_heartbeat_does_not_mutate_activity(self, session_state, evaluate, authoritative):
        evaluate.return_value = AuthenticationDecision(True)
        session_state.return_value = (
            True,
            {"reason": None, "remaining_seconds": 120, "expires_at": 9999999999},
        )
        identifier = uuid.uuid4()
        scope_session = {
            "esfe_system_session_id": str(identifier),
            "esfe_last_meaningful_activity": 123.0,
        }
        user = SimpleNamespace(is_anonymous=False, id=47)

        async def scenario():
            communicator = WebsocketCommunicator(NotificationConsumer.as_asgi(), "/ws/notifications/")
            communicator.scope["user"] = user
            communicator.scope["session"] = scope_session
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.send_to(text_data="heartbeat")
            self.assertEqual(scope_session["esfe_last_meaningful_activity"], 123.0)
            await communicator.disconnect()

        async_to_sync(scenario)()
