from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from notifier.models import NotificationEvent, NotificationMessage

User = get_user_model()


class NotificationCenterViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser",
            password="testpass123",
        )
        self.other_user = User.objects.create_user(username="other", password="testpass123")
        self.event = NotificationEvent.objects.create(event_type="test", source_app="tests")

    def _message(self, *, recipient=None, channel=NotificationMessage.CHANNEL_IN_APP, title="Test"):
        return NotificationMessage.objects.create(
            event=self.event,
            recipient=recipient or self.user,
            title=title,
            body="Body",
            notification_type="test",
            event_type="test",
            channel=channel,
            status=NotificationMessage.STATUS_DELIVERED,
        )

    def test_login_required(self):
        urls = [
            "notification_center:notifications",
            "notification_center:notifications_widget",
            "notification_center:notifications_partial",
        ]
        for name in urls:
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302, f"{name} should require login")

    def test_notifications_view(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("notification_center:notifications"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "notification_center/index.html")

    def test_dropdown_only_contains_in_app_messages(self):
        self._message(title="Visible")
        self._message(channel=NotificationMessage.CHANNEL_EMAIL_TRANSACTIONAL, title="Email hidden")
        self._message(channel=NotificationMessage.CHANNEL_WEBSOCKET, title="Socket hidden")
        self.client.force_login(self.user)

        response = self.client.get(reverse("notification_center:notifications_partial"))

        self.assertContains(response, "Visible")
        self.assertNotContains(response, "Email hidden")
        self.assertNotContains(response, "Socket hidden")

    def test_read_endpoint_rejects_non_in_app_and_other_users(self):
        email = self._message(channel=NotificationMessage.CHANNEL_EMAIL_TRANSACTIONAL)
        foreign = self._message(recipient=self.other_user)
        self.client.force_login(self.user)

        self.assertEqual(
            self.client.post(reverse("notification_center:mark_notification_read", args=[email.pk])).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(reverse("notification_center:mark_notification_read", args=[foreign.pk])).status_code,
            404,
        )

    def test_read_endpoint_marks_in_app_message(self):
        message = self._message()
        self.client.force_login(self.user)

        response = self.client.post(reverse("notification_center:mark_notification_read", args=[message.pk]))

        self.assertEqual(response.status_code, 204)
        message.refresh_from_db()
        self.assertIsNotNone(message.read_at)
        self.assertEqual(message.status, NotificationMessage.STATUS_READ)

    def test_email_detail_does_not_change_delivery_status(self):
        message = self._message(channel=NotificationMessage.CHANNEL_EMAIL_TRANSACTIONAL)
        self.client.force_login(self.user)

        response = self.client.get(reverse("notification_center:notification_detail", args=[message.pk]))

        self.assertEqual(response.status_code, 200)
        message.refresh_from_db()
        self.assertIsNone(message.read_at)
        self.assertEqual(message.status, NotificationMessage.STATUS_DELIVERED)
