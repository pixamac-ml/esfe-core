from django.test import TestCase

from communication.models import CommunicationNotification
from communication.services import EmailService
from communication.services.channel_policy import resolve_channel_policy


class EmailTemplateIntegrationTests(TestCase):
    def test_email_service_resolves_registry_template_and_fallback(self):
        _event, notifications = EmailService.send_transactional(
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
        self.assertEqual(notification.channel, CommunicationNotification.CHANNEL_EMAIL_TRANSACTIONAL)
        self.assertEqual(notification.metadata["template_key"], "first_payment_validated")
        self.assertEqual(
            notification.metadata["html_template"],
            "emails/payments/first_payment_validated.html",
        )
        self.assertEqual(
            notification.metadata["text_template"],
            "emails/payment_confirmation.txt",
        )
        self.assertEqual(notification.metadata["context"]["student_name"], "Awa Traore")
        self.assertIn("Reference: PAY-001", notification.metadata["fallback_text"])

    def test_channel_policy_marks_first_payment_as_in_app_only(self):
        policy = resolve_channel_policy(
            "payment_validated",
            default_channels=(
                CommunicationNotification.CHANNEL_IN_APP,
                CommunicationNotification.CHANNEL_WEBSOCKET,
            ),
            default_priority=CommunicationNotification.PRIORITY_NORMAL,
            metadata={},
        )

        self.assertEqual(policy["channels"], (CommunicationNotification.CHANNEL_IN_APP,))
        self.assertEqual(policy["priority"], CommunicationNotification.PRIORITY_HIGH)
        self.assertEqual(policy["metadata"]["channel_family"], "notification_in_app")
        self.assertEqual(policy["metadata"]["realtime_behavior"], "silent")
