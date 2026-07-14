import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.template.loader import get_template
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.position_registry import POSITION_REGISTRY
from branches.models import Branch
from notification_center.presentation import get_safe_action_url
from notifier.models import NotificationEvent, NotificationMessage


User = get_user_model()


class PortalNotificationPhaseOneTests(TestCase):
    def setUp(self):
        self.branch_a = Branch.objects.create(name="Annexe notifications A", code="NTA", slug="notifications-a")
        self.branch_b = Branch.objects.create(name="Annexe notifications B", code="NTB", slug="notifications-b")
        self.event = NotificationEvent.objects.create(event_type="phase1", source_app="tests")

    def _system_user(self, username, position, branch=None):
        user = User.objects.create_user(username=username, password="testpass123")
        profile = user.profile
        profile.position = position
        profile.branch = branch
        profile.save(update_fields=["position", "branch", "updated_at"])
        return user

    def _message(self, user, title, *, metadata=None):
        return NotificationMessage.objects.create(
            event=self.event,
            recipient=user,
            title=title,
            body="Corps de la notification",
            notification_type="phase1",
            event_type="phase1",
            channel=NotificationMessage.CHANNEL_IN_APP,
            status=NotificationMessage.STATUS_DELIVERED,
            metadata=metadata or {},
        )

    def test_every_official_system_position_uses_portal_center_and_common_bell(self):
        for index, (position, definition) in enumerate(POSITION_REGISTRY.items()):
            with self.subTest(position=position):
                branch = self.branch_a if definition.branch_required else None
                user = self._system_user(f"phase1-position-{index}", position, branch)
                self.client.force_login(user)

                response = self.client.get(reverse("notification_center:notifications"))

                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, "notification_center/index_system.html")
                self.assertContains(response, "ESFE <span class=\"text-sky-300\">Portal</span>", html=True)
                self.assertContains(response, 'id="portal-notification-shell"')
                self.assertContains(response, "data-portal-notification-slot")
                self.client.logout()

    def test_public_account_does_not_receive_system_portal_component(self):
        user = User.objects.create_user(username="phase1-public", password="testpass123")
        self.client.force_login(user)

        response = self.client.get(reverse("notification_center:notifications"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "notification_center/index.html")
        self.assertNotContains(response, 'id="portal-notification-shell"')

    def test_widget_and_center_are_isolated_by_recipient_across_branches(self):
        user_a = self._system_user("phase1-branch-a", "student", self.branch_a)
        user_b = self._system_user("phase1-branch-b", "student", self.branch_b)
        self._message(user_a, "Visible annexe A")
        self._message(user_b, "Confidentiel annexe B")
        self.client.force_login(user_a)

        widget = self.client.get(reverse("notification_center:notifications_widget"))
        center = self.client.get(reverse("notification_center:notifications"))

        self.assertContains(widget, "Visible annexe A")
        self.assertNotContains(widget, "Confidentiel annexe B")
        self.assertContains(center, "Visible annexe A")
        self.assertNotContains(center, "Confidentiel annexe B")

    def test_archive_is_scoped_hidden_from_active_inbox_and_restorable(self):
        user = self._system_user("phase1-archive", "student", self.branch_a)
        other = self._system_user("phase1-archive-other", "student", self.branch_b)
        message = self._message(user, "Notification à archiver")
        self.client.force_login(other)
        denied = self.client.post(reverse("notification_center:archive_notification", args=[message.pk]))
        self.assertEqual(denied.status_code, 404)

        self.client.force_login(user)
        archived = self.client.post(reverse("notification_center:archive_notification", args=[message.pk]))
        self.assertRedirects(archived, reverse("notification_center:notifications"))
        message.refresh_from_db()
        self.assertIsNotNone(message.archived_at)
        self.assertIsNotNone(message.read_at)

        widget = self.client.get(reverse("notification_center:notifications_widget"))
        active_center = self.client.get(reverse("notification_center:notifications"))
        archive_center = self.client.get(reverse("notification_center:notifications"), {"status": "archived"})
        self.assertNotContains(widget, message.title)
        self.assertNotContains(active_center, message.title)
        self.assertContains(archive_center, message.title)

        restored = self.client.post(reverse("notification_center:unarchive_notification", args=[message.pk]))
        self.assertRedirects(restored, reverse("notification_center:notifications"))
        message.refresh_from_db()
        self.assertIsNone(message.archived_at)

    def test_archived_notification_cannot_be_marked_unread(self):
        user = self._system_user("phase1-archive-unread", "student", self.branch_a)
        message = self._message(user, "Archive non lue interdite")
        message.archived_at = timezone.now()
        message.save(update_fields=["archived_at", "updated_at"])
        self.client.force_login(user)

        response = self.client.post(reverse("notification_center:mark_notification_unread", args=[message.pk]))

        self.assertEqual(response.status_code, 404)

    def test_action_links_accept_internal_paths_and_reject_external_hosts(self):
        user = self._system_user("phase1-actions", "student", self.branch_a)
        internal = self._message(user, "Action interne", metadata={"action_url": "/payments/receipt/RC-1/"})
        external = self._message(user, "Action externe", metadata={"action_url": "https://evil.example/phishing"})
        self.client.force_login(user)

        response = self.client.get(reverse("notification_center:notifications"))

        self.assertContains(response, '/payments/receipt/RC-1/')
        self.assertNotContains(response, "evil.example")
        self.assertEqual(get_safe_action_url(internal, response.wsgi_request), "/payments/receipt/RC-1/")
        self.assertEqual(get_safe_action_url(external, response.wsgi_request), "")


class PortalDashboardTemplateContractTests(SimpleTestCase):
    """Prouve que chaque surface officielle hérite du socle qui monte la cloche."""

    DASHBOARD_TEMPLATES = {
        "STUDENT": "portal/student/dashboard.html",
        "TEACHER": "portal/teacher/v2/dashboard.html",
        "ANNEX_MANAGER": "accounts/dashboard/manager_dashboard.html",
        "SECRETARY": "secretary/dashboard.html",
        "ADMISSIONS_OFFICER": "portal/staff/admissions_dashboard.html",
        "ACADEMIC_SUPERVISOR": "portal/staff/supervisor_dashboard.html",
        "DIRECTOR_OF_STUDIES": "portal/staff/director_dashboard.html",
        "IT_SUPPORT": "portal/staff/informaticien_dashboard_v2.html",
        "MARKETING_MANAGER": "marketing/dashboard.html",
        "EXECUTIVE_DIRECTOR": "portal/dg/dashboard.html",
        "DEPUTY_EXECUTIVE_DIRECTOR": "portal/dg/dashboard.html",
        "SUPER_ADMIN": "superadmin/dashboard.html",
        "PAYMENT_AGENT": "portal/staff/finance_dashboard.html",
    }
    EXTENDS_RE = re.compile(r'{%\s*extends\s+["\']([^"\']+)["\']\s*%}')

    def _parent_template(self, template_name):
        origin = Path(get_template(template_name).origin.name)
        source = origin.read_text(encoding="utf-8")
        match = self.EXTENDS_RE.search(source)
        return match.group(1) if match else None

    def test_all_system_dashboards_inherit_the_common_base(self):
        for position, template_name in self.DASHBOARD_TEMPLATES.items():
            with self.subTest(position=position):
                current = template_name
                visited = set()
                while current and current != "base.html" and current not in visited:
                    visited.add(current)
                    current = self._parent_template(current)
                self.assertEqual(current, "base.html")

    def test_common_base_mounts_exactly_one_official_portal_component(self):
        base_source = (settings.BASE_DIR / "templates" / "base.html").read_text(encoding="utf-8")
        include = '{% include "notification_center/partials/portal_component.html" %}'
        self.assertEqual(base_source.count(include), 1)
