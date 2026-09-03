from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from academics.models import AcademicClass, AcademicEnrollment, AcademicYear
from accounts.models import PayrollEntry
from admissions.models import Candidature
from branches.models import Branch
from formations.models import Cycle, Diploma, Filiere, Programme
from inscriptions.models import Inscription
from notifier.models import NotificationMessage
from portal.models import AcademicEnrollmentMovement, InternalTransfer, OutgoingTransfer, TransferHistory, TransferRequest, TransferSchool
from students.models import Student


class DirectorOperationsHubsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.branch = Branch.objects.create(name="Annexe Centre", code="CTR", slug="centre")
        cls.other_branch = Branch.objects.create(name="Annexe Nord", code="NRD", slug="nord")
        cycle = Cycle.objects.create(name="Cycle Operations", min_duration_years=1, max_duration_years=4)
        diploma = Diploma.objects.create(name="Diplome Operations", level="superieur")
        filiere = Filiere.objects.create(name="Filiere Operations")
        programme_values = {
            "filiere": filiere,
            "cycle": cycle,
            "diploma_awarded": diploma,
            "duration_years": 3,
            "short_description": "Programme de test",
            "description": "Programme de test des modules du DE.",
        }
        cls.programme = Programme.objects.create(title="Gestion des operations", **programme_values)
        cls.target_programme = Programme.objects.create(title="Administration des entreprises", **programme_values)
        cls.year = AcademicYear.objects.create(
            name="2032-2033", start_date=date(2032, 10, 1), end_date=date(2033, 7, 31), is_active=True
        )
        cls.source_class = cls._academic_class("L1 Centre", cls.programme, cls.branch, "L1")
        cls.target_class = cls._academic_class("L1 Centre B", cls.programme, cls.branch, "L1")
        cls.reclassification_class = cls._academic_class("L1 Administration", cls.target_programme, cls.branch, "L1")
        cls.other_class = cls._academic_class("L1 Nord", cls.programme, cls.other_branch, "L1")

        User = get_user_model()
        cls.director = cls._user("director_hubs", cls.branch, "director_of_studies", "Mariam", "Traore")
        cls.recipient = cls._user("secretary_hubs", cls.branch, "secretary", "Awa", "Keita")
        cls.outsider = cls._user("outsider_hubs", cls.other_branch, "secretary", "Fanta", "Coulibaly")
        cls.student_user = User.objects.create_user(
            username="student_hubs", first_name="Sira", last_name="Diallo", password="password"
        )
        candidature = Candidature.objects.create(
            programme=cls.programme,
            branch=cls.branch,
            academic_year=cls.year.name,
            entry_year=1,
            first_name="Sira",
            last_name="Diallo",
            birth_date=date(2003, 2, 1),
            birth_place="Bamako",
            gender="female",
            phone="70000001",
            email="sira.hubs@example.test",
            status="accepted",
        )
        inscription = Inscription.objects.create(
            candidature=candidature,
            academic_class=cls.source_class,
            amount_due=100000,
            status=Inscription.STATUS_ACTIVE,
        )
        Student.objects.create(
            user=cls.student_user, inscription=inscription, matricule="HUB-001", is_active=True
        )
        cls.enrollment = AcademicEnrollment.objects.create(
            inscription=inscription,
            student=cls.student_user,
            programme=cls.programme,
            branch=cls.branch,
            academic_year=cls.year,
            academic_class=cls.source_class,
        )
        cls.payroll = PayrollEntry.objects.create(
            branch=cls.branch,
            employee=cls.director,
            period_month=date(2032, 10, 1),
            base_salary=150000,
            status=PayrollEntry.STATUS_READY,
        )

    @classmethod
    def _academic_class(cls, name, programme, branch, level):
        return AcademicClass.objects.create(
            name=name,
            programme=programme,
            branch=branch,
            academic_year=cls.year,
            level=level,
            study_level="LICENCE",
        )

    @classmethod
    def _user(cls, username, branch, position, first_name, last_name):
        user = get_user_model().objects.create_user(
            username=username,
            first_name=first_name,
            last_name=last_name,
            email=f"{username}@example.test",
            password="password",
        )
        user.profile.branch = branch
        user.profile.position = position
        user.profile.role = "executive" if position == "director_of_studies" else ""
        user.profile.save(update_fields=["branch", "position", "role", "updated_at"])
        return user

    def setUp(self):
        self.client.force_login(self.director)

    def _create_transfer(self, transfer_type, **extra):
        values = {
            "branch": self.branch,
            "enrollment": self.enrollment,
            "transfer_type": transfer_type,
            "source_class": self.source_class,
            "reason": "Decision pedagogique documentee.",
            "created_by": self.director,
        }
        values.update(extra)
        transfer = TransferRequest.objects.create(**values)
        if transfer_type == TransferRequest.TYPE_INTERNAL:
            target = extra["target_class"]
            InternalTransfer.objects.create(
                transfer_request=transfer,
                target_programme=target.programme,
                target_class=target,
                source_level=self.source_class.level,
                target_level=target.level,
            )
        elif transfer_type == TransferRequest.TYPE_OUTGOING:
            school = TransferSchool.objects.create(
                branch=self.branch, name=extra["target_school_name"], created_by=self.director
            )
            OutgoingTransfer.objects.create(
                transfer_request=transfer,
                destination_school=school,
                academic_check_completed=True,
                administrative_check_completed=True,
                financial_check_completed=True,
            )
        return transfer

    def test_sidebar_exposes_operations_sections_and_personal_salary(self):
        response = self.client.get(reverse("accounts_portal:portal_dashboard"))
        self.assertContains(response, 'data-nav-key="transferts"')
        self.assertContains(response, 'data-nav-key="messagerie"')
        self.assertContains(response, 'data-nav-key="salaire"')
        self.assertNotContains(response, 'data-nav-key="finance"')

    def test_internal_transfer_keeps_level_and_records_new_placement(self):
        transfer = self._create_transfer(
            TransferRequest.TYPE_INTERNAL, target_class=self.target_class
        )
        response = self.client.post(
            reverse("accounts_portal:director_transfer_review"),
            {"transfer_id": transfer.pk, "action": "approve"},
        )
        self.assertEqual(response.status_code, 200)
        transfer.refresh_from_db()
        self.enrollment.refresh_from_db()
        self.assertEqual(transfer.status, TransferRequest.STATUS_COMPLETED)
        self.assertEqual(self.enrollment.academic_class, self.target_class)
        self.assertEqual(self.enrollment.programme, self.programme)
        self.assertEqual(transfer.internal_details.source_level, transfer.internal_details.target_level)
        self.assertTrue(TransferHistory.objects.filter(
            transfer_request=transfer, action="academic_placement_created"
        ).exists())
        movement = AcademicEnrollmentMovement.objects.get(transfer_request=transfer)
        self.assertEqual(movement.source_class, self.source_class)
        self.assertEqual(movement.target_class, self.target_class)
        self.assertEqual(movement.enrollment, self.enrollment)

    def test_internal_transfer_rejects_programme_change(self):
        response = self.client.post(
            reverse("accounts_portal:director_transfer_create"),
            {
                "enrollment_id": self.enrollment.pk,
                "transfer_type": TransferRequest.TYPE_INTERNAL,
                "target_class_id": self.reclassification_class.pk,
                "reason": "Changement de filière non autorisé ici",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(TransferRequest.objects.filter(target_class=self.reclassification_class).exists())

    def test_outgoing_transfer_archives_only_after_handover(self):
        transfer = self._create_transfer(
            TransferRequest.TYPE_OUTGOING, target_school_name="Institut partenaire"
        )
        self.client.post(
            reverse("accounts_portal:director_transfer_review"),
            {
                "transfer_id": transfer.pk,
                "action": "approve",
                "academic_check_completed": "on",
                "administrative_check_completed": "on",
                "financial_check_completed": "on",
            },
        )
        transfer.refresh_from_db()
        self.enrollment.refresh_from_db()
        self.assertEqual(transfer.status, TransferRequest.STATUS_APPROVED)
        self.assertTrue(self.enrollment.is_active)
        self.client.post(
            reverse("accounts_portal:director_transfer_review"),
            {"transfer_id": transfer.pk, "action": "handover"},
        )
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.status, AcademicEnrollment.STATUS_TRANSFERRED)
        self.assertTrue(self.enrollment.is_archived)
        self.assertTrue(AcademicEnrollment.objects.filter(pk=self.enrollment.pk).exists())

    def test_transfer_form_rejects_cross_branch_destination(self):
        response = self.client.post(
            reverse("accounts_portal:director_transfer_create"),
            {
                "enrollment_id": self.enrollment.pk,
                "transfer_type": TransferRequest.TYPE_INTERNAL,
                "target_class_id": self.other_class.pk,
                "reason": "Destination interdite",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(TransferRequest.objects.filter(target_class=self.other_class).exists())

    def test_internal_message_is_branch_scoped_and_visible_in_sent_box(self):
        response = self.client.post(
            reverse("accounts_portal:director_internal_message_compose"),
            {
                "audience": "individual",
                "recipients": [self.recipient.pk],
                "title": "Reunion pedagogique",
                "body": "Merci de preparer les dossiers.",
                "priority": NotificationMessage.PRIORITY_HIGH,
            },
        )
        self.assertEqual(response.status_code, 200)
        message = NotificationMessage.objects.get(
            actor=self.director,
            recipient=self.recipient,
            event_type="internal_message",
            channel=NotificationMessage.CHANNEL_IN_APP,
        )
        self.assertEqual(message.metadata["branch_id"], self.branch.pk)
        self.assertIsNotNone(message.batch_id)
        self.assertIsNotNone(message.thread_id)

        invalid = self.client.post(
            reverse("accounts_portal:director_internal_message_compose"),
            {
                "audience": "individual",
                "recipients": [self.outsider.pk],
                "title": "Hors annexe",
                "body": "Ce message doit etre refuse.",
                "priority": NotificationMessage.PRIORITY_NORMAL,
            },
        )
        self.assertEqual(invalid.status_code, 200)
        self.assertFalse(NotificationMessage.objects.filter(title="Hors annexe").exists())

    def test_collective_message_targets_only_students_in_selected_branch_class(self):
        response = self.client.post(
            reverse("accounts_portal:director_internal_message_compose"),
            {
                "audience": "classes",
                "target_classes": [self.source_class.pk],
                "title": "Information de classe",
                "body": "Le cours commence a huit heures.",
                "priority": NotificationMessage.PRIORITY_NORMAL,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(NotificationMessage.objects.filter(
            recipient=self.student_user,
            event_type="internal_message",
            channel=NotificationMessage.CHANNEL_IN_APP,
            title="Information de classe",
        ).exists())
        self.assertFalse(NotificationMessage.objects.filter(
            recipient=self.outsider,
            title="Information de classe",
        ).exists())

    def test_incoming_transfer_creates_submitted_application_not_enrollment(self):
        response = self.client.post(
            reverse("accounts_portal:director_transfer_create"),
            {
                "transfer_type": TransferRequest.TYPE_INCOMING,
                "target_class_id": self.target_class.pk,
                "origin_school_name": "Lycee partenaire",
                "school_city": "Segou",
                "first_name": "Fatou",
                "last_name": "Sangare",
                "birth_date": "2004-04-12",
                "birth_place": "Segou",
                "gender": "female",
                "phone": "70000002",
                "email": "fatou.transfer@example.test",
                "country": "Mali",
                "reason": "Demande d'equivalence.",
            },
        )
        self.assertEqual(response.status_code, 200)
        transfer = TransferRequest.objects.get(transfer_type=TransferRequest.TYPE_INCOMING)
        self.assertIsNone(transfer.enrollment)
        self.client.post(
            reverse("accounts_portal:director_transfer_review"),
            {"transfer_id": transfer.pk, "action": "approve", "decision_note": "Recevable"},
        )
        transfer.refresh_from_db()
        candidature = transfer.incoming_details.candidature
        self.assertEqual(transfer.status, TransferRequest.STATUS_COMPLETED)
        self.assertEqual(candidature.status, "submitted")
        self.assertFalse(hasattr(candidature, "inscription"))

    def test_salary_workspace_exposes_only_authenticated_employee(self):
        other_payroll = PayrollEntry.objects.create(
            branch=self.other_branch,
            employee=self.outsider,
            period_month=date(2032, 10, 1),
            base_salary=99000,
        )
        workspace = self.client.get(
            reverse("accounts_portal:director_workspace"),
            {"section": "salaire", "view": "overview", "period": "2032-10"},
        )
        self.assertContains(workspace, "Salaire brut")
        self.assertContains(workspace, "SAL-203210")
        self.assertNotContains(workspace, self.outsider.get_full_name())
        self.assertNotContains(workspace, "Honoraires enseignants")
        self.assertNotContains(workspace, "Caisse et depenses")
        own_pdf = self.client.get(reverse("accounts:payslip_download", args=[self.payroll.pk]))
        other_pdf = self.client.get(reverse("accounts:payslip_download", args=[other_payroll.pk]))
        self.assertEqual(own_pdf.status_code, 200)
        self.assertEqual(other_pdf.status_code, 404)
