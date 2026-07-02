from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from branches.models import Branch
from .models import Appointment, DocumentReceipt, RegistryEntry, SecretaryTask, VisitorLog
from .services import (
    archive_document,
    archive_registry_entry,
    complete_appointment,
    complete_task,
    close_visit,
    create_appointment,
    create_registry_entry,
    create_task,
    mark_registry_processed,
    move_registry_entry_status,
    register_document,
    register_visitor,
    start_registry_entry_processing,
    update_appointment,
    update_document,
    update_registry_entry,
    update_task,
    update_visitor,
)

User = get_user_model()


class SecretaryTestMixin:
    """Reusable test setup for secretary tests."""

    def setUp(self):
        self.branch = Branch.objects.create(
            name="Annexe Test",
            code="TST",
            slug="annexe-test",
        )
        self.other_branch = Branch.objects.create(
            name="Autre Annexe",
            code="AUT",
            slug="autre-annexe",
        )
        self.secretary = User.objects.create_user(
            username="secretary_user",
            email="secretary@example.com",
            password="pass1234",
            is_staff=True,
        )
        self.secretary.profile.position = "secretary"
        self.secretary.profile.branch = self.branch
        self.secretary.profile.save(update_fields=["position", "branch", "updated_at"])

        self.other_secretary = User.objects.create_user(
            username="other_secretary",
            email="other@example.com",
            password="pass1234",
            is_staff=True,
        )
        self.other_secretary.profile.position = "secretary"
        self.other_secretary.profile.branch = self.other_branch
        self.other_secretary.profile.save(update_fields=["position", "branch", "updated_at"])

        self.regular_user = User.objects.create_user(
            username="regular_user",
            email="regular@example.com",
            password="pass1234",
        )

        self.factory = RequestFactory()


# =================== MODEL TESTS ===================

class RegistryEntryModelTests(SecretaryTestMixin, TestCase):
    def test_create_minimal(self):
        entry = RegistryEntry.objects.create(
            entry_type=RegistryEntry.TYPE_PARENT_VISIT,
            created_by=self.secretary,
        )
        self.assertIsNotNone(entry.pk)
        self.assertTrue(entry.is_active)
        self.assertFalse(entry.is_archived)
        self.assertEqual(entry.status, RegistryEntry.STATUS_PENDING)

    def test_auto_title_from_entry_type(self):
        entry = RegistryEntry.objects.create(
            entry_type=RegistryEntry.TYPE_PARENT_VISIT,
            created_by=self.secretary,
        )
        self.assertIn("Visite parent", entry.title)

    def test_archive_sets_inactive(self):
        entry = RegistryEntry.objects.create(
            entry_type=RegistryEntry.TYPE_SCHOOL_PAYMENT,
            created_by=self.secretary,
        )
        entry.is_archived = True
        entry.save()
        self.assertFalse(entry.is_active)
        self.assertEqual(entry.status, RegistryEntry.STATUS_ARCHIVED)

    def test_str_is_title(self):
        entry = RegistryEntry.objects.create(
            title="Test entry",
            entry_type=RegistryEntry.TYPE_PARENT_VISIT,
            created_by=self.secretary,
        )
        self.assertEqual(str(entry), "Test entry")


class AppointmentModelTests(SecretaryTestMixin, TestCase):
    def test_create_minimal(self):
        apt = Appointment.objects.create(
            title="Reunion",
            person_name="M. Diallo",
            scheduled_at=timezone.now() + timedelta(hours=2),
            created_by=self.secretary,
        )
        self.assertIsNotNone(apt.pk)
        self.assertEqual(apt.status, Appointment.STATUS_PENDING)

    def test_past_scheduled_at_raises_validation(self):
        with self.assertRaises(ValidationError):
            apt = Appointment(
                title="Passe",
                person_name="M. Traore",
                scheduled_at=timezone.now() - timedelta(hours=2),
                created_by=self.secretary,
            )
            apt.full_clean()

    def test_str(self):
        apt = Appointment.objects.create(
            title="Reunion",
            person_name="M. Diallo",
            scheduled_at=timezone.now() + timedelta(hours=2),
            created_by=self.secretary,
        )
        self.assertIn("Reunion", str(apt))
        self.assertIn("Diallo", str(apt))


class VisitorLogModelTests(SecretaryTestMixin, TestCase):
    def test_create_minimal(self):
        visitor = VisitorLog.objects.create(
            full_name="M. Konate",
            arrived_at=timezone.now(),
            created_by=self.secretary,
        )
        self.assertIsNotNone(visitor.pk)
        self.assertEqual(visitor.status, VisitorLog.STATUS_IN_PROGRESS)

    def test_departed_before_arrived_raises_error(self):
        with self.assertRaises(ValidationError):
            visitor = VisitorLog(
                full_name="Test",
                arrived_at=timezone.now(),
                departed_at=timezone.now() - timedelta(hours=1),
                created_by=self.secretary,
            )
            visitor.full_clean()

    def test_str(self):
        visitor = VisitorLog.objects.create(
            full_name="M. Konate",
            arrived_at=timezone.now(),
            created_by=self.secretary,
        )
        self.assertEqual(str(visitor), "M. Konate")


class DocumentReceiptModelTests(SecretaryTestMixin, TestCase):
    def test_create_minimal(self):
        doc = DocumentReceipt.objects.create(
            title="Bulletin",
            submitted_by_name="M. Sacko",
            received_by=self.secretary,
        )
        self.assertIsNotNone(doc.pk)

    def test_str(self):
        doc = DocumentReceipt.objects.create(
            title="Bulletin",
            submitted_by_name="M. Sacko",
            received_by=self.secretary,
        )
        self.assertEqual(str(doc), "Bulletin")


class SecretaryTaskModelTests(SecretaryTestMixin, TestCase):
    def test_create_minimal(self):
        task = SecretaryTask.objects.create(title="Verifier dossier")
        self.assertIsNotNone(task.pk)
        self.assertEqual(task.status, SecretaryTask.STATUS_PENDING)

    def test_str(self):
        task = SecretaryTask.objects.create(title="Verifier dossier")
        self.assertEqual(str(task), "Verifier dossier")


# =================== SERVICE TESTS ===================

class RegistryEntryServiceTests(SecretaryTestMixin, TestCase):
    def test_create_registry_entry(self):
        entry = create_registry_entry(
            created_by=self.secretary,
            entry_type=RegistryEntry.TYPE_PARENT_VISIT,
        )
        self.assertIsNotNone(entry.pk)
        self.assertIsNotNone(entry.registry_number)
        self.assertTrue(entry.registry_number.startswith("ESFE-TST"))

    def test_update_registry_entry(self):
        entry = create_registry_entry(
            created_by=self.secretary,
            entry_type=RegistryEntry.TYPE_PARENT_VISIT,
        )
        updated = update_registry_entry(entry, visitor_name="M. Nouveau")
        self.assertEqual(updated.visitor_name, "M. Nouveau")
        self.assertEqual(len(updated.history), 2)  # creation + update

    def test_start_registry_entry_processing(self):
        entry = create_registry_entry(
            created_by=self.secretary,
            entry_type=RegistryEntry.TYPE_PARENT_VISIT,
        )
        started = start_registry_entry_processing(entry)
        self.assertEqual(started.status, RegistryEntry.STATUS_IN_PROGRESS)

    def test_mark_registry_processed(self):
        entry = create_registry_entry(
            created_by=self.secretary,
            entry_type=RegistryEntry.TYPE_PARENT_VISIT,
        )
        processed = mark_registry_processed(entry)
        self.assertEqual(processed.status, RegistryEntry.STATUS_COMPLETED)
        self.assertIsNotNone(processed.closed_at)

    def test_archive_registry_entry_raises_on_archived(self):
        entry = create_registry_entry(
            created_by=self.secretary,
            entry_type=RegistryEntry.TYPE_PARENT_VISIT,
        )
        archive_registry_entry(entry)
        with self.assertRaises(ValidationError):
            archive_registry_entry(entry)

    def test_start_archived_raises(self):
        entry = create_registry_entry(
            created_by=self.secretary,
            entry_type=RegistryEntry.TYPE_PARENT_VISIT,
        )
        archive_registry_entry(entry)
        with self.assertRaises(ValidationError):
            start_registry_entry_processing(entry)

    def test_update_registry_entry_valid_status_transition_records_history(self):
        entry = create_registry_entry(
            created_by=self.secretary,
            entry_type=RegistryEntry.TYPE_PARENT_VISIT,
        )
        updated = update_registry_entry(entry, status=RegistryEntry.STATUS_IN_PROGRESS)
        self.assertEqual(updated.status, RegistryEntry.STATUS_IN_PROGRESS)
        status_event, update_event = updated.history[-2], updated.history[-1]
        self.assertEqual(status_event["action"], "changement_statut")
        self.assertEqual(status_event["details"]["from"], RegistryEntry.STATUS_PENDING)
        self.assertEqual(status_event["details"]["to"], RegistryEntry.STATUS_IN_PROGRESS)
        self.assertEqual(update_event["action"], "mise_a_jour")

    def test_update_registry_entry_invalid_status_transition_raises(self):
        entry = create_registry_entry(
            created_by=self.secretary,
            entry_type=RegistryEntry.TYPE_PARENT_VISIT,
        )
        archive_registry_entry(entry)
        with self.assertRaises(ValidationError):
            update_registry_entry(entry, status=RegistryEntry.STATUS_PENDING)

    def test_move_registry_entry_status_valid_transition(self):
        entry = create_registry_entry(
            created_by=self.secretary,
            entry_type=RegistryEntry.TYPE_PARENT_VISIT,
        )
        moved = move_registry_entry_status(entry, RegistryEntry.STATUS_IN_PROGRESS)
        self.assertEqual(moved.status, RegistryEntry.STATUS_IN_PROGRESS)
        status_event = moved.history[-1]
        self.assertEqual(status_event["action"], "changement_statut")
        self.assertEqual(status_event["details"]["from"], RegistryEntry.STATUS_PENDING)
        self.assertEqual(status_event["details"]["to"], RegistryEntry.STATUS_IN_PROGRESS)

    def test_move_registry_entry_status_preserves_routing_fields(self):
        entry = create_registry_entry(
            created_by=self.secretary,
            entry_type=RegistryEntry.TYPE_SCHOOL_PAYMENT,
        )
        target_service = entry.target_service
        priority = entry.priority
        moved = move_registry_entry_status(entry, RegistryEntry.STATUS_TRANSFERRED)
        self.assertEqual(moved.target_service, target_service)
        self.assertEqual(moved.priority, priority)

    def test_move_registry_entry_status_invalid_transition_raises(self):
        entry = create_registry_entry(
            created_by=self.secretary,
            entry_type=RegistryEntry.TYPE_PARENT_VISIT,
        )
        mark_registry_processed(entry)
        with self.assertRaises(ValidationError):
            move_registry_entry_status(entry, RegistryEntry.STATUS_PENDING)

    def test_move_registry_entry_status_archived_raises(self):
        entry = create_registry_entry(
            created_by=self.secretary,
            entry_type=RegistryEntry.TYPE_PARENT_VISIT,
        )
        archive_registry_entry(entry)
        with self.assertRaises(ValidationError):
            move_registry_entry_status(entry, RegistryEntry.STATUS_IN_PROGRESS)

    def test_move_registry_entry_status_same_status_is_noop(self):
        entry = create_registry_entry(
            created_by=self.secretary,
            entry_type=RegistryEntry.TYPE_PARENT_VISIT,
        )
        history_length = len(entry.history)
        moved = move_registry_entry_status(entry, RegistryEntry.STATUS_PENDING)
        self.assertEqual(len(moved.history), history_length)


class AppointmentServiceTests(SecretaryTestMixin, TestCase):
    def test_create_appointment(self):
        apt = create_appointment(
            created_by=self.secretary,
            title="Test",
            person_name="M. X",
            scheduled_at=timezone.now() + timedelta(hours=3),
        )
        self.assertIsNotNone(apt.pk)

    def test_update_appointment(self):
        apt = create_appointment(
            created_by=self.secretary,
            title="Original",
            person_name="M. X",
            scheduled_at=timezone.now() + timedelta(hours=3),
        )
        updated = update_appointment(apt, title="Modifie")
        self.assertEqual(updated.title, "Modifie")

    def test_update_appointment_past_scheduled_at_raises(self):
        apt = create_appointment(
            created_by=self.secretary,
            title="Test",
            person_name="M. X",
            scheduled_at=timezone.now() + timedelta(hours=3),
        )
        with self.assertRaises(ValidationError):
            update_appointment(apt, scheduled_at=timezone.now() - timedelta(hours=1))

    def test_complete_appointment(self):
        apt = create_appointment(
            created_by=self.secretary,
            title="Test",
            person_name="M. X",
            scheduled_at=timezone.now() + timedelta(hours=3),
        )
        completed = complete_appointment(apt)
        self.assertEqual(completed.status, Appointment.STATUS_COMPLETED)

    def test_complete_already_completed_raises(self):
        apt = create_appointment(
            created_by=self.secretary,
            title="Test",
            person_name="M. X",
            scheduled_at=timezone.now() + timedelta(hours=3),
        )
        complete_appointment(apt)
        with self.assertRaises(ValidationError):
            complete_appointment(apt)


class VisitorServiceTests(SecretaryTestMixin, TestCase):
    def test_register_visitor(self):
        visitor = register_visitor(
            created_by=self.secretary,
            full_name="M. Diallo",
            arrived_at=timezone.now(),
        )
        self.assertIsNotNone(visitor.pk)
        self.assertEqual(visitor.status, VisitorLog.STATUS_IN_PROGRESS)

    def test_update_visitor(self):
        visitor = register_visitor(
            created_by=self.secretary,
            full_name="Original",
            arrived_at=timezone.now(),
        )
        updated = update_visitor(visitor, full_name="Modifie")
        self.assertEqual(updated.full_name, "Modifie")

    def test_close_visit(self):
        visitor = register_visitor(
            created_by=self.secretary,
            full_name="M. Diallo",
            arrived_at=timezone.now(),
        )
        closed = close_visit(visitor)
        self.assertEqual(closed.status, VisitorLog.STATUS_COMPLETED)
        self.assertIsNotNone(closed.departed_at)

    def test_close_already_closed_raises(self):
        visitor = register_visitor(
            created_by=self.secretary,
            full_name="M. Diallo",
            arrived_at=timezone.now(),
        )
        close_visit(visitor)
        with self.assertRaises(ValidationError):
            close_visit(visitor)


class DocumentServiceTests(SecretaryTestMixin, TestCase):
    def test_register_document(self):
        doc = register_document(
            received_by=self.secretary,
            title="Bulletin",
            submitted_by_name="M. Sacko",
        )
        self.assertIsNotNone(doc.pk)

    def test_update_document(self):
        doc = register_document(
            received_by=self.secretary,
            title="Original",
            submitted_by_name="M. Sacko",
        )
        updated = update_document(doc, title="Modifie")
        self.assertEqual(updated.title, "Modifie")

    def test_archive_document(self):
        doc = register_document(
            received_by=self.secretary,
            title="Bulletin",
            submitted_by_name="M. Sacko",
        )
        archived = archive_document(doc)
        self.assertTrue(archived.is_archived)
        self.assertFalse(archived.is_active)

    def test_archive_already_archived_raises(self):
        doc = register_document(
            received_by=self.secretary,
            title="Bulletin",
            submitted_by_name="M. Sacko",
        )
        archive_document(doc)
        with self.assertRaises(ValidationError):
            archive_document(doc)


class TaskServiceTests(SecretaryTestMixin, TestCase):
    def test_create_task(self):
        task = create_task(created_by=self.secretary, title="Test task")
        self.assertIsNotNone(task.pk)

    def test_update_task(self):
        task = create_task(created_by=self.secretary, title="Original")
        updated = update_task(task, title="Modifie")
        self.assertEqual(updated.title, "Modifie")

    def test_complete_task(self):
        task = create_task(created_by=self.secretary, title="Test")
        completed = complete_task(task)
        self.assertEqual(completed.status, SecretaryTask.STATUS_COMPLETED)

    def test_complete_already_completed_raises(self):
        task = create_task(created_by=self.secretary, title="Test")
        complete_task(task)
        with self.assertRaises(ValidationError):
            complete_task(task)


# =================== VIEW TESTS (EDIT) ===================

class RegistryEditViewTests(SecretaryTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.entry = RegistryEntry.objects.create(
            title="Original",
            entry_type=RegistryEntry.TYPE_PARENT_VISIT,
            created_by=self.secretary,
            branch=self.branch,
        )
        self.url = reverse("secretary:registry_update", args=[self.entry.pk])

    def test_get_returns_200_for_secretary(self):
        self.client.force_login(self.secretary)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_get_returns_form_in_modal_for_htmx(self):
        self.client.force_login(self.secretary)
        response = self.client.get(self.url, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Modifier")

    def test_post_updates_entry(self):
        self.client.force_login(self.secretary)
        response = self.client.post(self.url, {
            "title": "Modifie",
            "entry_type": RegistryEntry.TYPE_PARENT_VISIT,
            "visitor_name": "Nouveau visiteur",
            "status": RegistryEntry.STATUS_PENDING,
            "priority": RegistryEntry.PRIORITY_NORMAL,
        })
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.title, "Modifie")
        self.assertEqual(self.entry.visitor_name, "Nouveau visiteur")

    def test_redirects_to_list_after_post(self):
        self.client.force_login(self.secretary)
        response = self.client.post(self.url, {
            "title": "Modifie",
            "entry_type": RegistryEntry.TYPE_PARENT_VISIT,
            "visitor_name": "Nouveau",
            "status": RegistryEntry.STATUS_PENDING,
            "priority": RegistryEntry.PRIORITY_NORMAL,
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("secretary:registry_list"))

    def test_regular_user_cannot_access(self):
        self.client.force_login(self.regular_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_other_branch_secretary_cannot_access(self):
        self.client.force_login(self.other_secretary)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)


class RegistryDetailViewTests(SecretaryTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.entry = create_registry_entry(
            created_by=self.secretary,
            entry_type=RegistryEntry.TYPE_PARENT_VISIT,
        )
        update_registry_entry(self.entry, status=RegistryEntry.STATUS_IN_PROGRESS)
        self.entry.refresh_from_db()
        self.url = reverse("secretary:registry_detail", args=[self.entry.pk])

    def test_get_returns_200_for_secretary(self):
        self.client.force_login(self.secretary)
        response = self.client.get(self.url, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Historique")

    def test_history_timeline_renders_events(self):
        self.client.force_login(self.secretary)
        response = self.client.get(self.url, HTTP_HX_REQUEST="true")
        self.assertContains(response, "circle-plus")
        self.assertContains(response, "arrow-right-left")

    def test_regular_user_cannot_access(self):
        self.client.force_login(self.regular_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_other_branch_secretary_cannot_access(self):
        self.client.force_login(self.other_secretary)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)


class AppointmentEditViewTests(SecretaryTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.apt = Appointment.objects.create(
            title="Original",
            person_name="M. X",
            scheduled_at=timezone.now() + timedelta(hours=3),
            created_by=self.secretary,
        )
        self.url = reverse("secretary:appointment_update", args=[self.apt.pk])

    def test_get_returns_200(self):
        self.client.force_login(self.secretary)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_post_updates(self):
        self.client.force_login(self.secretary)
        self.client.post(self.url, {
            "title": "Modifie",
            "person_name": "M. X",
            "scheduled_at": (timezone.now() + timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M"),
            "status": Appointment.STATUS_PENDING,
        })
        self.apt.refresh_from_db()
        self.assertEqual(self.apt.title, "Modifie")

    def test_regular_user_gets_403(self):
        self.client.force_login(self.regular_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)


class VisitorEditViewTests(SecretaryTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.visitor = VisitorLog.objects.create(
            full_name="Original",
            arrived_at=timezone.now(),
            created_by=self.secretary,
        )
        self.url = reverse("secretary:visitor_update", args=[self.visitor.pk])

    def test_get_returns_200(self):
        self.client.force_login(self.secretary)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_post_updates(self):
        self.client.force_login(self.secretary)
        self.client.post(self.url, {
            "full_name": "Modifie",
            "arrived_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
            "status": VisitorLog.STATUS_IN_PROGRESS,
        })
        self.visitor.refresh_from_db()
        self.assertEqual(self.visitor.full_name, "Modifie")

    def test_regular_user_gets_403(self):
        self.client.force_login(self.regular_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)


class DocumentEditViewTests(SecretaryTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.doc = DocumentReceipt.objects.create(
            title="Original",
            submitted_by_name="M. Sacko",
            received_by=self.secretary,
        )
        self.url = reverse("secretary:document_receipt_update", args=[self.doc.pk])

    def test_get_returns_200(self):
        self.client.force_login(self.secretary)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_post_updates(self):
        self.client.force_login(self.secretary)
        self.client.post(self.url, {
            "title": "Modifie",
            "submitted_by_name": "M. Sacko",
            "status": DocumentReceipt.STATUS_PENDING,
        })
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.title, "Modifie")

    def test_regular_user_gets_403(self):
        self.client.force_login(self.regular_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)


class TaskEditViewTests(SecretaryTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.task = SecretaryTask.objects.create(
            title="Original",
            created_by=self.secretary,
        )
        self.url = reverse("secretary:task_update", args=[self.task.pk])

    def test_get_returns_200(self):
        self.client.force_login(self.secretary)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_post_updates(self):
        self.client.force_login(self.secretary)
        self.client.post(self.url, {
            "title": "Modifie",
            "status": SecretaryTask.STATUS_PENDING,
            "priority": SecretaryTask.PRIORITY_MEDIUM,
        })
        self.task.refresh_from_db()
        self.assertEqual(self.task.title, "Modifie")

    def test_regular_user_gets_403(self):
        self.client.force_login(self.regular_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)


# =================== PERMISSION TESTS ===================

class PermissionTests(SecretaryTestMixin, TestCase):
    def test_is_secretary_returns_true_for_secretary_profile(self):
        from .permissions import is_secretary
        self.assertTrue(is_secretary(self.secretary))

    def test_is_secretary_returns_false_for_regular_user(self):
        from .permissions import is_secretary
        self.assertFalse(is_secretary(self.regular_user))

    def test_is_secretary_returns_true_for_superuser(self):
        from .permissions import is_secretary
        admin = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="admin1234",
        )
        self.assertTrue(is_secretary(admin))

    def test_is_secretary_returns_true_for_secretary_group(self):
        from .permissions import is_secretary
        from django.contrib.auth.models import Group
        group = Group.objects.create(name="secretary")
        user = User.objects.create_user(username="group_user", password="pass")
        user.groups.add(group)
        self.assertTrue(is_secretary(user))

    def test_ensure_secretary_access_raises_for_unauthorized(self):
        from .permissions import ensure_secretary_access
        from django.core.exceptions import PermissionDenied
        with self.assertRaises(PermissionDenied):
            ensure_secretary_access(self.regular_user)

    def test_ensure_secretary_access_passes_for_authorized(self):
        from .permissions import ensure_secretary_access
        try:
            ensure_secretary_access(self.secretary)
        except PermissionDenied:
            self.fail("ensure_secretary_access raised PermissionDenied for secretary")


# =================== SCOPE / FILTER TESTS ===================

class ScopeTests(SecretaryTestMixin, TestCase):
    def test_registry_scoped_to_branch(self):
        entry = RegistryEntry.objects.create(
            title="Visible",
            entry_type=RegistryEntry.TYPE_PARENT_VISIT,
            created_by=self.secretary,
            branch=self.branch,
        )
        RegistryEntry.objects.create(
            title="Cachee",
            entry_type=RegistryEntry.TYPE_PARENT_VISIT,
            created_by=self.other_secretary,
            branch=self.other_branch,
        )
        qs = RegistryEntry.objects.filter(branch=self.branch)
        self.assertIn(entry, qs)
        self.assertEqual(qs.count(), 1)

    def test_appointment_scoped_via_created_by_branch(self):
        apt = Appointment.objects.create(
            title="Visible",
            person_name="M. X",
            scheduled_at=timezone.now() + timedelta(hours=3),
            created_by=self.secretary,
        )
        Appointment.objects.create(
            title="Cache",
            person_name="M. Y",
            scheduled_at=timezone.now() + timedelta(hours=3),
            created_by=self.other_secretary,
        )
        from .selectors import get_appointments_queryset
        qs = get_appointments_queryset(user=self.secretary)
        self.assertIn(apt, qs)
        self.assertEqual(qs.count(), 1)

    def test_visitor_scoped_via_created_by_branch(self):
        v = VisitorLog.objects.create(
            full_name="Visible",
            arrived_at=timezone.now(),
            created_by=self.secretary,
        )
        VisitorLog.objects.create(
            full_name="Cache",
            arrived_at=timezone.now(),
            created_by=self.other_secretary,
        )
        from .selectors import get_visits_queryset
        qs = get_visits_queryset(user=self.secretary)
        self.assertIn(v, qs)
        self.assertEqual(qs.count(), 1)

    def test_document_scoped_via_received_by_branch(self):
        doc = DocumentReceipt.objects.create(
            title="Visible",
            submitted_by_name="M. Sacko",
            received_by=self.secretary,
        )
        DocumentReceipt.objects.create(
            title="Cache",
            submitted_by_name="M. Sacko",
            received_by=self.other_secretary,
        )
        from .selectors import get_documents_queryset
        qs = get_documents_queryset(user=self.secretary)
        self.assertIn(doc, qs)
        self.assertEqual(qs.count(), 1)

    def test_task_scoped_via_created_by_branch(self):
        task = SecretaryTask.objects.create(
            title="Visible",
            created_by=self.secretary,
        )
        SecretaryTask.objects.create(
            title="Cache",
            created_by=self.other_secretary,
        )
        from .selectors import get_tasks_queryset
        qs = get_tasks_queryset(user=self.secretary)
        self.assertIn(task, qs)
        self.assertEqual(qs.count(), 1)


# =================== KANBAN VIEW TESTS ===================

class RegistryKanbanViewTests(SecretaryTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.entry = create_registry_entry(
            created_by=self.secretary,
            entry_type=RegistryEntry.TYPE_PARENT_VISIT,
        )
        RegistryEntry.objects.create(
            title="Autre annexe",
            entry_type=RegistryEntry.TYPE_PARENT_VISIT,
            created_by=self.other_secretary,
            branch=self.other_branch,
        )
        self.url = reverse("secretary:registry_kanban")

    def test_get_returns_200_for_secretary(self):
        self.client.force_login(self.secretary)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "En attente")
        self.assertContains(response, "En cours")
        self.assertContains(response, "Transfere")
        self.assertContains(response, "Traite")

    def test_entry_appears_in_pending_column(self):
        self.client.force_login(self.secretary)
        response = self.client.get(self.url)
        self.assertContains(response, self.entry.registry_number)

    def test_other_branch_entry_not_visible(self):
        self.client.force_login(self.secretary)
        response = self.client.get(self.url)
        self.assertNotContains(response, "Autre annexe")

    def test_priority_filter_excludes_non_matching_entries(self):
        self.client.force_login(self.secretary)
        response = self.client.get(self.url, {"priority": RegistryEntry.PRIORITY_HIGH})
        self.assertNotContains(response, self.entry.registry_number)

    def test_regular_user_cannot_access(self):
        self.client.force_login(self.regular_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)


class RegistryKanbanMoveViewTests(SecretaryTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.entry = create_registry_entry(
            created_by=self.secretary,
            entry_type=RegistryEntry.TYPE_PARENT_VISIT,
        )

    def _url(self, entry, new_status):
        return reverse("secretary:registry_kanban_move", args=[entry.pk, new_status])

    def test_valid_transition_updates_status_and_history(self):
        self.client.force_login(self.secretary)
        response = self.client.post(self._url(self.entry, RegistryEntry.STATUS_IN_PROGRESS), HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.status, RegistryEntry.STATUS_IN_PROGRESS)
        status_event = self.entry.history[-1]
        self.assertEqual(status_event["action"], "changement_statut")
        self.assertEqual(status_event["details"]["to"], RegistryEntry.STATUS_IN_PROGRESS)

    def test_invalid_transition_keeps_previous_status(self):
        update_registry_entry(self.entry, status=RegistryEntry.STATUS_COMPLETED)
        self.entry.refresh_from_db()
        self.client.force_login(self.secretary)
        response = self.client.post(self._url(self.entry, RegistryEntry.STATUS_PENDING), HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.status, RegistryEntry.STATUS_COMPLETED)

    def test_response_renders_kanban_board_with_trigger_header(self):
        self.client.force_login(self.secretary)
        response = self.client.post(self._url(self.entry, RegistryEntry.STATUS_IN_PROGRESS), HTTP_HX_REQUEST="true")
        self.assertContains(response, "sg-kanban-board")
        self.assertIn("HX-Trigger", response.headers)

    def test_get_not_allowed(self):
        self.client.force_login(self.secretary)
        response = self.client.get(self._url(self.entry, RegistryEntry.STATUS_IN_PROGRESS))
        self.assertEqual(response.status_code, 405)

    def test_regular_user_cannot_access(self):
        self.client.force_login(self.regular_user)
        response = self.client.post(self._url(self.entry, RegistryEntry.STATUS_IN_PROGRESS))
        self.assertEqual(response.status_code, 403)

    def test_other_branch_secretary_gets_404(self):
        self.client.force_login(self.other_secretary)
        response = self.client.post(self._url(self.entry, RegistryEntry.STATUS_IN_PROGRESS))
        self.assertEqual(response.status_code, 404)


# =================== COMMAND PALETTE TESTS ===================

class CommandPaletteViewTests(SecretaryTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("secretary:htmx_command_palette")

    def test_empty_query_returns_actions_without_students_section(self):
        self.client.force_login(self.secretary)
        response = self.client.get(self.url, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nouvelle entree registre")
        self.assertNotContains(response, "Etudiants")

    def test_query_matches_action_by_keyword(self):
        self.client.force_login(self.secretary)
        response = self.client.get(self.url, {"q": "kanban"}, HTTP_HX_REQUEST="true")
        self.assertContains(response, "Vue Kanban du registre")
        self.assertNotContains(response, "Nouvelle tache")

    def test_query_with_no_matches_shows_empty_state(self):
        self.client.force_login(self.secretary)
        response = self.client.get(self.url, {"q": "zzzzzzz"}, HTTP_HX_REQUEST="true")
        self.assertContains(response, "Aucun resultat")

    def test_regular_user_cannot_access(self):
        self.client.force_login(self.regular_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)
