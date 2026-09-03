from datetime import date, datetime, timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from academics.models import (
    AcademicCalendar,
    AcademicCalendarEntry,
    AcademicClass,
    AcademicScheduleChangeLog,
    AcademicScheduleEvent,
    AcademicYear,
    EC,
    Semester,
    UE,
)
from academics.services.calendar_service import create_calendar, create_calendar_entry, publish_calendar, submit_calendar, validate_calendar
from academics.services.evaluation_campaign_service import create_evaluation_campaign
from academic_cycle.models import AcademicAuditLog
from branches.models import Branch
from formations.models import Cycle, Diploma, Filiere, Programme


class DirectorEvaluationWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.branch = Branch.objects.create(
            name="Annexe Evaluations", code="AEV", slug="annexe-evaluations"
        )
        cls.other_branch = Branch.objects.create(
            name="Annexe Exterieure", code="AEX", slug="annexe-exterieure"
        )
        cycle = Cycle.objects.create(
            name="Licence Evaluations",
            theme="primary",
            min_duration_years=1,
            max_duration_years=5,
        )
        diploma = Diploma.objects.create(name="Diplome Evaluations", level="superieur")
        filiere = Filiere.objects.create(name="Filiere Evaluations")
        programme = Programme.objects.create(
            title="Programme Evaluations",
            filiere=filiere,
            cycle=cycle,
            diploma_awarded=diploma,
            duration_years=3,
            short_description="Workflow des evaluations",
            description="Donnees de test du Directeur des Etudes.",
        )
        cls.academic_year = AcademicYear.objects.create(
            name="2026-2027",
            start_date=date(2026, 10, 1),
            end_date=date(2027, 7, 31),
            is_active=True,
        )
        cls.academic_class = AcademicClass.objects.create(
            name="Classe Evaluation A",
            programme=programme,
            branch=cls.branch,
            academic_year=cls.academic_year,
            level="L1",
            study_level="LICENCE",
        )
        cls.other_class = AcademicClass.objects.create(
            name="Classe Evaluation Hors Annexe",
            programme=programme,
            branch=cls.other_branch,
            academic_year=cls.academic_year,
            level="L2",
            study_level="LICENCE",
        )
        cls.semester = Semester.objects.create(
            academic_class=cls.academic_class, number=1
        )
        cls.other_semester = Semester.objects.create(
            academic_class=cls.other_class, number=1
        )
        cls.ue = UE.objects.create(
            semester=cls.semester, code="UE-EVAL", title="Unite Evaluation"
        )
        cls.other_ue = UE.objects.create(
            semester=cls.other_semester,
            code="UE-HORS",
            title="Unite Hors Annexe",
        )
        cls.ec = EC.objects.create(
            ue=cls.ue,
            title="Matiere Evaluation",
            credit_required="3.00",
            coefficient="2.00",
        )
        cls.other_ec = EC.objects.create(
            ue=cls.other_ue,
            title="Matiere Interdite",
            credit_required="3.00",
            coefficient="2.00",
        )
        cls.director = cls._create_user(
            "workflow_director", "director_of_studies", cls.branch
        )
        cls.teacher = cls._create_user("workflow_teacher", "teacher", cls.branch)
        cls.other_teacher = cls._create_user(
            "workflow_other_teacher", "teacher", cls.other_branch
        )
        calendar = create_calendar(actor=cls.director, branch=cls.branch, academic_year=cls.academic_year)
        create_calendar_entry(
            actor=cls.director, calendar=calendar, title="Rentrée", event_type=AcademicCalendarEntry.EVENT_ACADEMIC_START,
            start_datetime=timezone.make_aware(datetime(2026, 10, 1, 8)), end_datetime=timezone.make_aware(datetime(2026, 10, 1, 18)),
            target_scope=AcademicCalendarEntry.SCOPE_BRANCH,
        )
        cls.campaign_entry = create_calendar_entry(
            actor=cls.director, calendar=calendar, title="Session normale S1", event_type=AcademicCalendarEntry.EVENT_EXAM_SESSION,
            start_datetime=timezone.make_aware(datetime(2026, 11, 1, 8)), end_datetime=timezone.make_aware(datetime(2026, 12, 15, 18)),
            target_scope=AcademicCalendarEntry.SCOPE_BRANCH, is_blocking=True,
        )
        create_calendar_entry(
            actor=cls.director, calendar=calendar, title="Clôture", event_type=AcademicCalendarEntry.EVENT_ACADEMIC_END,
            start_datetime=timezone.make_aware(datetime(2027, 7, 31, 8)), end_datetime=timezone.make_aware(datetime(2027, 7, 31, 18)),
            target_scope=AcademicCalendarEntry.SCOPE_BRANCH,
        )
        submit_calendar(calendar, actor=cls.director)
        validate_calendar(calendar, actor=cls.director)
        publish_calendar(calendar, actor=cls.director)
        cls.campaign_entry.refresh_from_db()
        cls.campaign = create_evaluation_campaign(actor=cls.director, calendar_entry=cls.campaign_entry)

    @classmethod
    def _create_user(cls, username, position, branch):
        user = get_user_model().objects.create_user(
            username=username,
            email=f"{username}@test.test",
            password="director-workflow-password",
            is_staff=True,
        )
        profile = user.profile
        profile.position = position
        profile.role = "teacher" if position == "teacher" else "executive"
        profile.branch = branch
        profile.save(update_fields=["position", "role", "branch", "updated_at"])
        return user

    def setUp(self):
        self.client.force_login(self.director)

    def _evaluation_payload(self, **overrides):
        payload = {
            "action": "create",
            "campaign": str(self.campaign.id),
            "title": "Controle continu de droit",
            "event_type": AcademicScheduleEvent.EVENT_TYPE_EXAM,
            "class_id": str(self.academic_class.id),
            "ec": str(self.ec.id),
            "teacher": str(self.teacher.id),
            "start_datetime": "2026-11-10T08:00",
            "end_datetime": "2026-11-10T10:00",
            "location": "Salle 12",
            "description": "Chapitres 1 a 3",
        }
        payload.update(overrides)
        return payload

    def _create_event(self, *, title="Evaluation existante", day=12, branch=None):
        target_branch = branch or self.branch
        academic_class = self.academic_class if target_branch == self.branch else self.other_class
        ec = self.ec if target_branch == self.branch else self.other_ec
        teacher = self.teacher if target_branch == self.branch else self.other_teacher
        return AcademicScheduleEvent.objects.create(
            title=title,
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_EXAM,
            academic_class=academic_class,
            ec=ec,
            teacher=teacher,
            branch=target_branch,
            academic_year=self.academic_year,
            start_datetime=timezone.make_aware(datetime(2026, 11, day, 8, 0)),
            end_datetime=timezone.make_aware(datetime(2026, 11, day, 10, 0)),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle test",
            created_by=self.director,
            updated_by=self.director,
        )

    def test_create_evaluation_uses_scoped_form_and_schedule_service(self):
        response = self.client.post(
            reverse("accounts_portal:director_evaluation_action"),
            self._evaluation_payload(),
        )

        self.assertEqual(response.status_code, 200)
        event = AcademicScheduleEvent.objects.get(title="Controle continu de droit")
        self.assertEqual(event.branch, self.branch)
        self.assertEqual(event.academic_class, self.academic_class)
        self.assertEqual(event.teacher, self.teacher)
        self.assertEqual(event.academic_year, self.academic_class.academic_year)
        self.assertTrue(
            AcademicScheduleChangeLog.objects.filter(
                event=event, action_type=AcademicScheduleChangeLog.ACTION_CREATED
            ).exists()
        )
        self.assertContains(response, "a été planifiée")
        self.assertIn("section=evaluations_calendar", response.headers["HX-Push-Url"])

    def test_attendance_sheet_is_built_from_the_planned_evaluation(self):
        self.client.post(
            reverse("accounts_portal:director_evaluation_action"),
            self._evaluation_payload(),
        )
        event = AcademicScheduleEvent.objects.get(title="Controle continu de droit")

        response = self.client.get(
            reverse("accounts_portal:director_evaluation_attendance_sheet", args=[event.id]),
            {"format": "print"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fiche de présence")
        self.assertContains(response, self.academic_class.name)
        self.assertContains(response, self.ec.title)

    def test_campaign_rejects_duplicate_class_ec_evaluation(self):
        url = reverse("accounts_portal:director_evaluation_action")
        first = self.client.post(url, self._evaluation_payload())
        self.assertEqual(first.status_code, 200)
        second = self.client.post(url, self._evaluation_payload(title="Deuxieme epreuve"))
        self.assertEqual(second.status_code, 200)
        self.assertContains(second, "Une epreuve est deja planifiee")
        self.assertEqual(
            AcademicScheduleEvent.objects.filter(
                evaluation_campaign=self.campaign,
                academic_class=self.academic_class,
                ec=self.ec,
                is_active=True,
            ).count(),
            1,
        )

    def test_campaign_rejects_ec_not_in_campaign_requirements(self):
        other_ec = EC.objects.create(
            ue=self.ue,
            title="EC non prepare",
            credit_required="2.00",
            coefficient="1.00",
        )
        response = self.client.post(
            reverse("accounts_portal:director_evaluation_action"),
            self._evaluation_payload(ec=str(other_ec.id)),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ne fait pas partie de la preparation")
        self.assertFalse(AcademicScheduleEvent.objects.filter(ec=other_ec).exists())

    def test_create_evaluation_rejects_cross_branch_relations(self):
        response = self.client.post(
            reverse("accounts_portal:director_evaluation_action"),
            self._evaluation_payload(
                class_id=str(self.other_class.id),
                ec=str(self.other_ec.id),
                teacher=str(self.other_teacher.id),
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(AcademicScheduleEvent.objects.count(), 0)
        self.assertContains(response, "Sélectionnez un choix valide", count=3)
        self.assertContains(response, "Controle continu de droit")

    def test_invalid_dates_keep_bound_values_and_field_error(self):
        response = self.client.post(
            reverse("accounts_portal:director_evaluation_action"),
            self._evaluation_payload(end_datetime="2026-11-10T07:30"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "La fin doit être postérieure au début")
        self.assertContains(response, "Controle continu de droit")
        self.assertEqual(AcademicScheduleEvent.objects.count(), 0)

    def test_ec_options_are_limited_to_the_selected_branch_class(self):
        response = self.client.get(
            reverse("accounts_portal:director_evaluation_ec_options"),
            {"class_id": self.academic_class.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.ec.title)
        self.assertNotContains(response, self.other_ec.title)

    def test_cancel_evaluation_requires_reason_and_records_change(self):
        event = self._create_event()
        url = reverse("accounts_portal:director_evaluation_action")

        response = self.client.post(
            url, {"action": "cancel", "event_id": event.id, "reason": ""}
        )
        event.refresh_from_db()
        self.assertEqual(event.status, AcademicScheduleEvent.STATUS_PLANNED)
        self.assertContains(response, "motif d&#x27;annulation est obligatoire")

        response = self.client.post(
            url,
            {
                "action": "cancel",
                "event_id": event.id,
                "reason": "Indisponibilite de la salle",
            },
        )
        event.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(event.status, AcademicScheduleEvent.STATUS_CANCELLED)
        change = event.change_logs.get(
            action_type=AcademicScheduleChangeLog.ACTION_CANCELLED
        )
        self.assertEqual(change.reason, "Indisponibilite de la salle")

    def test_scheduled_list_is_paginated_and_never_leaks_other_branch(self):
        for index in range(11):
            self._create_event(title=f"Evaluation annexe {index:02d}", day=12 + index)
        self._create_event(
            title="Evaluation confidentielle autre annexe",
            day=25,
            branch=self.other_branch,
        )

        url = reverse("accounts_portal:director_exam_sessions_subcontent")
        first_page = self.client.get(url, {"view": "scheduled"})
        second_page = self.client.get(url, {"view": "scheduled", "events_page": 2})

        self.assertEqual(first_page.status_code, 200)
        self.assertContains(first_page, "Page 1/2")
        self.assertContains(first_page, "events_page=2")
        self.assertNotContains(first_page, "Evaluation confidentielle autre annexe")
        self.assertContains(second_page, "Page 2/2")
        self.assertNotContains(second_page, "Evaluation confidentielle autre annexe")

    def test_create_exam_session_creates_draft_calendar_entry_for_branch(self):
        response = self.client.post(
            reverse("accounts_portal:director_exam_session_action"),
            {
                "action": "create",
                "title": "Examens du premier semestre",
                "event_type": AcademicCalendarEntry.EVENT_EXAM_SESSION,
                "start_date": "2026-12-01",
                "end_date": "2026-12-05",
                "description": "Session officielle de l'annexe",
            },
        )

        self.assertEqual(response.status_code, 200)
        calendar = AcademicCalendar.objects.get(branch=self.branch, status=AcademicCalendar.STATUS_DRAFT)
        entry = calendar.entries.get(title="Examens du premier semestre")
        self.assertEqual(calendar.status, AcademicCalendar.STATUS_DRAFT)
        self.assertEqual(entry.status, AcademicCalendarEntry.STATUS_DRAFT)
        self.assertEqual(entry.target_scope, AcademicCalendarEntry.SCOPE_BRANCH)
        self.assertTrue(entry.is_blocking)
        self.assertContains(response, "a été créée en brouillon")

    def test_session_workspace_starts_from_an_official_period(self):
        response = self.client.get(
            reverse("accounts_portal:director_exam_sessions_subcontent"),
            {"view": "sessions"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Choisir la période officielle")
        self.assertContains(response, 'name="action" value="create_campaign"')
        self.assertNotContains(response, 'name="start_date"')

    def test_campaign_workflow_subviews_keep_the_selected_campaign(self):
        url = reverse("accounts_portal:director_exam_sessions_subcontent")
        for view, expected in (
            ("subjects", "Sujets à recevoir"),
            ("supervision", "Surveillance et présences"),
            ("copies", "Suivi des copies"),
        ):
            response = self.client.get(url, {"view": view, "campaign_id": self.campaign.id})
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, expected)
            self.assertIn(f"campaign_id={self.campaign.id}", response.headers["HX-Push-Url"])

    def test_campaign_subject_search_accepts_ec_title_and_ue_code(self):
        url = reverse("accounts_portal:director_exam_sessions_subcontent")
        by_title = self.client.get(
            url,
            {"view": "campaign", "campaign_id": self.campaign.id, "requirement_q": "Matiere"},
        )
        by_code = self.client.get(
            url,
            {"view": "campaign", "campaign_id": self.campaign.id, "requirement_q": "UE-EVAL"},
        )
        self.assertEqual(by_title.status_code, 200)
        self.assertEqual(by_code.status_code, 200)
        self.assertContains(by_title, self.ec.title)
        self.assertContains(by_code, self.ec.title)

    def test_subject_upload_marks_the_requirement_received_and_keeps_file(self):
        requirement = self.campaign.requirements.get(
            academic_class=self.academic_class,
            ec=self.ec,
        )
        response = self.client.post(
            reverse("accounts_portal:director_exam_session_action"),
            {
                "action": "record_subject",
                "return_view": "subjects",
                "campaign_id": self.campaign.id,
                "requirement_id": requirement.id,
                "subject_status": "expected",
                "subject_file": SimpleUploadedFile("sujet-test.pdf", b"contenu du sujet", content_type="application/pdf"),
            },
        )
        requirement.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sujet de")
        self.assertEqual(requirement.subject_status, "received")
        self.assertTrue(requirement.subject_file.name.endswith(".pdf"))

    def test_cancel_exam_session_requires_reason_and_is_audited(self):
        self.client.post(
            reverse("accounts_portal:director_exam_session_action"),
            {
                "action": "create",
                "title": "Session a annuler",
                "event_type": AcademicCalendarEntry.EVENT_RETAKE_SESSION,
                "start_date": "2027-02-01",
                "end_date": "2027-02-03",
                "description": "Session de rattrapage",
            },
        )
        entry = AcademicCalendarEntry.objects.get(title="Session a annuler")
        url = reverse("accounts_portal:director_exam_session_action")

        response = self.client.post(
            url, {"action": "cancel", "entry_id": entry.id, "reason": ""}
        )
        entry.refresh_from_db()
        self.assertEqual(entry.status, AcademicCalendarEntry.STATUS_DRAFT)
        self.assertContains(response, "motif d&#x27;annulation est obligatoire")

        response = self.client.post(
            url,
            {
                "action": "cancel",
                "entry_id": entry.id,
                "reason": "Reorganisation du calendrier academique",
            },
        )
        entry.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(entry.status, AcademicCalendarEntry.STATUS_CANCELLED)
        audit = AcademicAuditLog.objects.get(
            action="exam_session.cancelled", object_id=str(entry.id)
        )
        self.assertEqual(audit.branch, self.branch)
        self.assertEqual(audit.reason, "Reorganisation du calendrier academique")

    def test_sessions_endpoint_requires_director_position(self):
        self.client.force_login(self.teacher)
        response = self.client.get(
            reverse("accounts_portal:director_exam_sessions_subcontent"),
            {"view": "overview"},
        )
        self.assertEqual(response.status_code, 403)
