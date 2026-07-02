from django.test import TestCase
from django.contrib.auth import get_user_model

from notifier.models import NotificationEvent, NotificationMessage
from notification_center.selectors import (
    get_user_messages,
    get_user_in_app_messages,
    get_user_unread_count,
    get_notification_center_queryset,
    get_notification_center_stats,
)

User = get_user_model()


class SelectorTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass123")
        self.event = NotificationEvent.objects.create(
            event_type="test_event",
            source_app="tests",
        )

    def _create_message(self, **kwargs):
        defaults = dict(
            event=self.event,
            recipient=self.user,
            title="Test",
            body="Body",
            notification_type="test",
            event_type="test_event",
            channel=NotificationMessage.CHANNEL_IN_APP,
        )
        defaults.update(kwargs)
        return NotificationMessage.objects.create(**defaults)

    def test_get_user_messages(self):
        self._create_message()
        self._create_message(channel=NotificationMessage.CHANNEL_EMAIL_TRANSACTIONAL)
        msgs = get_user_messages(self.user)
        self.assertEqual(msgs.count(), 2)

    def test_get_user_in_app_messages_excludes_delivery_channels(self):
        in_app = self._create_message(title="Inbox")
        self._create_message(title="Email", channel=NotificationMessage.CHANNEL_EMAIL_TRANSACTIONAL)
        self._create_message(title="Socket", channel=NotificationMessage.CHANNEL_WEBSOCKET)

        self.assertEqual(list(get_user_in_app_messages(self.user)), [in_app])

    def test_get_user_unread_count(self):
        self._create_message()
        self._create_message(read_at=None)
        self.assertEqual(get_user_unread_count(self.user), 2)
        msg = NotificationMessage.objects.first()
        msg.read_at = "2026-01-01T00:00:00Z"
        msg.save()
        self.assertEqual(get_user_unread_count(self.user), 1)

    def test_get_notification_center_stats(self):
        self._create_message()
        self._create_message(priority=NotificationMessage.PRIORITY_CRITICAL)
        stats = get_notification_center_stats(self.user)
        self.assertIn("total", stats)
        self.assertIn("unread", stats)
        self.assertIn("critical", stats)
