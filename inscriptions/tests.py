from django.contrib.auth import get_user_model
from django.test import TestCase

from notifier.models import NotificationMessage
from notifier.services.audience import resolve_candidate_user_by_email, restrict_candidate_channels


User = get_user_model()


class CandidateNotificationAudienceTests(TestCase):
    def _user(self, username, email, *, role="", position="", user_type="public"):
        user = User.objects.create_user(username=username, email=email, password="test-password")
        profile = user.profile
        profile.role = role
        profile.position = position
        profile.user_type = user_type
        profile.save(update_fields=["role", "position", "user_type", "updated_at"])
        return user

    def test_teacher_with_candidate_email_is_never_selected(self):
        self._user(
            "teacher_same_email",
            "candidate@example.com",
            role="teacher",
            position="teacher",
            user_type="staff",
        )

        self.assertIsNone(resolve_candidate_user_by_email("candidate@example.com"))

    def test_student_with_candidate_email_is_selected(self):
        student = self._user(
            "student_same_email",
            "student@example.com",
            role="student",
            position="student",
        )

        self.assertEqual(resolve_candidate_user_by_email("STUDENT@example.com"), student)

    def test_unprivileged_public_candidate_account_is_selected(self):
        candidate = self._user("candidate_account", "public@example.com")

        self.assertEqual(resolve_candidate_user_by_email("public@example.com"), candidate)

    def test_ambiguous_candidate_accounts_remain_email_only(self):
        self._user("candidate_one", "duplicate@example.com")
        self._user("candidate_two", "duplicate@example.com")

        self.assertIsNone(resolve_candidate_user_by_email("duplicate@example.com"))

    def test_unresolved_candidate_cannot_use_internal_channels(self):
        channels = restrict_candidate_channels(
            None,
            (
                NotificationMessage.CHANNEL_IN_APP,
                NotificationMessage.CHANNEL_WEBSOCKET,
                NotificationMessage.CHANNEL_EMAIL_TRANSACTIONAL,
            ),
        )

        self.assertEqual(channels, (NotificationMessage.CHANNEL_EMAIL_TRANSACTIONAL,))

# Create your tests here.
