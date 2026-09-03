from datetime import date
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import PayrollEntry, Profile
from branches.models import Branch
from notifier.models import NotificationMessage


class StaffCommonEndpointsTests(TestCase):
    """Generic staff workspace endpoints (account / messaging / salary)."""

    @classmethod
    def setUpTestData(cls):
        cls.branch = Branch.objects.create(name="Annexe Staff", code="STF", slug="staff")
        cls.other_branch = Branch.objects.create(name="Annexe Autre", code="AUT", slug="autre")

        cls.manager = cls._staff_user("manager_common", cls.branch, "branch_manager")
        cls.secretary = cls._staff_user("secretary_common", cls.branch, "secretary")
        cls.teacher = cls._staff_user("teacher_common", cls.branch, "teacher")
        cls.outsider = cls._staff_user("outsider_common", cls.other_branch, "secretary")
        cls.student = get_user_model().objects.create_user(
            username="student_common", password="password"
        )
        cls.student.profile.position = "student"
        cls.student.profile.branch = cls.branch
        cls.student.profile.save(update_fields=["position", "branch"])

        cls.manager_payroll = PayrollEntry.objects.create(
            branch=cls.branch,
            employee=cls.manager,
            period_month=date(2032, 10, 1),
            base_salary=200000,
            status=PayrollEntry.STATUS_READY,
        )
        cls.outsider_payroll = PayrollEntry.objects.create(
            branch=cls.other_branch,
            employee=cls.outsider,
            period_month=date(2032, 10, 1),
            base_salary=999999,
            status=PayrollEntry.STATUS_PAID,
        )

    @classmethod
    def _staff_user(cls, username, branch, position):
        user = get_user_model().objects.create_user(
            username=username,
            first_name=username.title(),
            last_name="Test",
            email=f"{username}@example.test",
            password="password",
        )
        user.profile.branch = branch
        user.profile.position = position
        user.profile.user_type = "staff"
        user.profile.save(update_fields=["branch", "position", "user_type"])
        return user

    def test_account_panel_renders_in_drawer_fragment(self):
        self.client.force_login(self.manager)
        response = self.client.get(
            reverse("accounts_portal:staff_account_panel") + "?dash=manager&view=profile"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "manager_common".title(), status_code=200)

    def test_account_panel_rejects_unknown_dashboard(self):
        self.client.force_login(self.manager)
        response = self.client.get(
            reverse("accounts_portal:staff_account_panel") + "?dash=unknown&view=profile"
        )
        self.assertEqual(response.status_code, 400)

    def test_student_cannot_access_staff_endpoints(self):
        self.client.force_login(self.student)
        response = self.client.get(
            reverse("accounts_portal:staff_messaging") + "?dash=sg"
        )
        self.assertIn(response.status_code, {302, 403})

    def test_messaging_workspace_lists_inbox(self):
        NotificationMessage.objects.create(
            recipient=self.manager,
            actor=self.secretary,
            event_type="internal_message",
            title="Bonjour manager",
            body="Contenu du message interne.",
            channel=NotificationMessage.CHANNEL_IN_APP,
            status=NotificationMessage.STATUS_DELIVERED,
        )
        self.client.force_login(self.manager)
        response = self.client.get(
            reverse("accounts_portal:staff_messaging") + "?dash=manager"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bonjour manager")

    def test_notification_preview_loads_and_targets_shared_messaging(self):
        notification = NotificationMessage.objects.create(
            recipient=self.manager,
            actor=self.secretary,
            event_type="internal_message",
            title="Apercu commun",
            body="Le clic doit ouvrir la messagerie partagee.",
            channel=NotificationMessage.CHANNEL_IN_APP,
            status=NotificationMessage.STATUS_DELIVERED,
        )
        self.client.force_login(self.manager)
        response = self.client.get(
            reverse("accounts_portal:staff_notifications_preview") + "?dash=manager"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Apercu commun")
        self.assertContains(
            response,
            f"{reverse('accounts_portal:staff_messaging')}?dash=manager&amp;notification_id={notification.id}",
        )

    def test_workspace_composer_keeps_messaging_context(self):
        self.client.force_login(self.manager)
        response = self.client.get(
            reverse("accounts_portal:staff_message_compose")
            + "?dash=manager&workspace=1"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Choisissez les destinataires puis rédigez sans quitter votre boîte de réception.",
        )
        self.assertContains(response, "Réception")
        self.assertContains(response, "secretary_common")

    def test_compose_individual_message_creates_notification(self):
        self.client.force_login(self.secretary)
        response = self.client.post(
            reverse("accounts_portal:staff_message_compose"),
            {
                "dash": "sg",
                "audience": "individual",
                "recipients": [self.manager.pk],
                "title": "Relance documents",
                "body": "Merci de passer au secretariat.",
                "priority": NotificationMessage.PRIORITY_NORMAL,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            NotificationMessage.objects.filter(
                recipient=self.manager,
                actor=self.secretary,
                event_type="internal_message",
                title="Relance documents",
                channel=NotificationMessage.CHANNEL_IN_APP,
            ).exists()
        )

    def test_individual_only_sender_can_send_from_workspace_composer(self):
        self.client.force_login(self.teacher)
        response = self.client.post(
            reverse("accounts_portal:staff_message_compose"),
            {
                "dash": "teacher",
                "workspace": "1",
                "audience": "individual",
                "recipients": [self.manager.pk],
                "title": "Message individuel",
                "body": "Envoi autorisé sans champs collectifs.",
                "priority": NotificationMessage.PRIORITY_NORMAL,
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            NotificationMessage.objects.filter(
                recipient=self.manager,
                actor=self.teacher,
                title="Message individuel",
            ).exists()
        )

    def test_workspace_composer_ignores_duplicate_submission_key(self):
        self.client.force_login(self.manager)
        payload = {
            "dash": "manager",
            "workspace": "1",
            "submission_key": "duplicate-message-test-001",
            "audience": "individual",
            "recipients": [self.secretary.pk],
            "title": "Ne pas dupliquer",
            "body": "Une seule copie doit etre creee.",
            "priority": NotificationMessage.PRIORITY_NORMAL,
        }
        first = self.client.post(
            reverse("accounts_portal:staff_message_compose"), payload, HTTP_HX_REQUEST="true"
        )
        second = self.client.post(
            reverse("accounts_portal:staff_message_compose"), payload, HTTP_HX_REQUEST="true"
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(
            NotificationMessage.objects.filter(
                actor=self.manager,
                recipient=self.secretary,
                title="Ne pas dupliquer",
                channel=NotificationMessage.CHANNEL_IN_APP,
            ).count(),
            1,
        )

    def test_sent_messages_are_grouped_by_delivery_batch(self):
        batch_id = uuid4()
        for recipient in (self.secretary, self.teacher, self.outsider):
            NotificationMessage.objects.create(
                recipient=recipient,
                actor=self.manager,
                event_type="internal_message",
                title="Information groupee",
                body="Un seul envoi logique, plusieurs destinataires.",
                channel=NotificationMessage.CHANNEL_IN_APP,
                status=NotificationMessage.STATUS_DELIVERED,
                batch_id=batch_id,
            )
        self.client.force_login(self.manager)
        response = self.client.get(
            reverse("accounts_portal:staff_messaging") + "?dash=manager&box=sent"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].paginator.count, 1)
        self.assertEqual(len(response.context["notifications"]), 1)
        self.assertEqual(response.context["notifications"][0]["recipient_count"], 3)
        self.assertContains(response, "Envoyé à 3 destinataires")

    def test_collective_audience_rejected_for_unauthorized_sender(self):
        self.client.force_login(self.teacher)
        response = self.client.post(
            reverse("accounts_portal:staff_message_compose"),
            {
                "dash": "teacher",
                "audience": "staff",
                "title": "Message collectif interdit",
                "body": "Tentative d'envoi collectif.",
                "priority": NotificationMessage.PRIORITY_NORMAL,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            NotificationMessage.objects.filter(
                actor=self.teacher, event_type="internal_message"
            ).exists()
        )

    def test_salary_section_shows_only_own_entries(self):
        self.client.force_login(self.manager)
        response = self.client.get(
            reverse("accounts_portal:staff_salary") + "?dash=manager&period=2032-10"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "200")
        self.assertNotContains(response, "999")

    def test_salary_section_without_entries_renders_empty_state(self):
        self.client.force_login(self.teacher)
        response = self.client.get(
            reverse("accounts_portal:staff_salary") + "?dash=teacher"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Aucune fiche de paie")

    def test_salary_history_subview_is_isolated(self):
        self.client.force_login(self.manager)
        response = self.client.get(
            reverse("accounts_portal:staff_salary_subcontent")
            + "?dash=manager&view=history"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "200")
        self.assertNotContains(response, "999")
