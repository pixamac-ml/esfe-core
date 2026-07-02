from django.test import TestCase

from notifier.models import NotificationMessage
from notifier.services import NotificationBus
from notifier.services.policy import resolve_channel_policy
from notifier.realtime.payloads import build_notification_payload
from django.contrib.auth import get_user_model
from django.core.management import call_command
from io import StringIO


class NotifierEmailTests(TestCase):
    def test_email_service_resolves_registry_template_and_fallback(self):
        _event, notifications = NotificationBus.send_email(
            subject="Paiement ESFE",
            recipient_email="etudiant@example.com",
            source_app="payments",
            event_type="first_payment_validated",
            context={
                "student_name": "Awa Traore",
                "payment_amount": 25000,
                "receipt_url": "/payments/receipt/RC-001/",
                "login_url": "/accounts/login/",
                "reference": "PAY-001",
            },
            dispatch_on_commit=False,
        )
        notification = notifications[0]
        self.assertEqual(notification.channel, NotificationMessage.CHANNEL_EMAIL_TRANSACTIONAL)
        self.assertEqual(notification.metadata["template_key"], "first_payment_validated")
        self.assertEqual(notification.metadata["html_template"], "emails/payments/first_payment_validated.html")
        self.assertEqual(notification.metadata["text_template"], "emails/payment_confirmation.txt")
        self.assertEqual(notification.metadata["context"]["student_name"], "Awa Traore")
        self.assertIn("Reference: PAY-001", notification.metadata["fallback_text"])

    def test_channel_policy_marks_first_payment_as_in_app_only(self):
        policy = resolve_channel_policy(
            "payment_validated",
            default_channels=(
                NotificationMessage.CHANNEL_IN_APP,
                NotificationMessage.CHANNEL_WEBSOCKET,
            ),
            default_priority=NotificationMessage.PRIORITY_NORMAL,
            metadata={},
        )
        self.assertEqual(policy["channels"], (NotificationMessage.CHANNEL_IN_APP,))
        self.assertEqual(policy["priority"], NotificationMessage.PRIORITY_HIGH)
        self.assertEqual(policy["metadata"]["channel_family"], "notification_in_app")
        self.assertEqual(policy["metadata"]["realtime_behavior"], "silent")

    def test_notify_applies_registered_policy_by_default(self):
        user = get_user_model().objects.create_user(username="policy-default")

        _event, messages = NotificationBus.notify(
            recipient=user,
            event_type="payment_validated",
            title="Paiement valide",
            dispatch_on_commit=False,
        )

        self.assertEqual(
            [message.channel for message in messages],
            [NotificationMessage.CHANNEL_IN_APP],
        )
        self.assertEqual(messages[0].priority, NotificationMessage.PRIORITY_HIGH)
        self.assertEqual(messages[0].metadata["realtime_behavior"], "silent")

    def test_notify_preserves_explicit_channel_override(self):
        user = get_user_model().objects.create_user(username="policy-override")

        _event, messages = NotificationBus.notify(
            recipient=user,
            event_type="payment_validated",
            title="Paiement valide",
            channels=(NotificationMessage.CHANNEL_WEBSOCKET,),
            dispatch_on_commit=False,
        )

        self.assertEqual(
            [message.channel for message in messages],
            [NotificationMessage.CHANNEL_WEBSOCKET],
        )


class RealtimePayloadTests(TestCase):
    def test_payload_contains_exact_in_app_unread_count(self):
        user = get_user_model().objects.create_user(username="realtime")
        NotificationBus.notify(
            recipient=user,
            event_type="test",
            title="Test",
            dispatch_on_commit=False,
        )
        websocket_message = NotificationMessage.objects.get(
            recipient=user,
            channel=NotificationMessage.CHANNEL_WEBSOCKET,
        )

        payload = build_notification_payload(websocket_message)

        self.assertEqual(payload["unread_count"], 1)


class LegacyImportCommandTests(TestCase):
    def test_command_is_safe_when_legacy_tables_are_absent(self):
        output = StringIO()

        call_command("migrate_communications", stdout=output)

        self.assertIn("nothing to import", output.getvalue())
