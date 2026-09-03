"""Parcours réel enseignant → surveillant pour un cahier de texte signé."""

import base64
import re
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Profile
from academics.models import (
    AcademicClass,
    AcademicScheduleEvent,
    AcademicYear,
    EC,
    LessonLog,
    Semester,
    UE,
)
from branches.models import Branch
from core.models import SignatureRequest
from formations.models import Cycle, Diploma, Filiere, Programme
from students.models import AttendanceRollSheet, TeacherAttendance


User = get_user_model()


class TeacherSupervisorSignatureWorkflowTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            name="Annexe workflow signature", code="WSG", slug="annexe-workflow-signature"
        )
        self.teacher = self._create_staff("workflow_teacher", "teacher", "teacher")
        self.supervisor = self._create_staff(
            "workflow_supervisor", "academic_supervisor", "executive"
        )
        cycle = Cycle.objects.create(
            name="Licence workflow", theme="accent", min_duration_years=1, max_duration_years=5
        )
        diploma = Diploma.objects.create(name="Diplôme workflow", level="superieur")
        filiere = Filiere.objects.create(name="Filière workflow")
        programme = Programme.objects.create(
            title="Programme workflow",
            filiere=filiere,
            cycle=cycle,
            diploma_awarded=diploma,
            duration_years=3,
            short_description="Programme de test",
            description="Programme de test signature",
        )
        today = timezone.localdate()
        academic_year = AcademicYear.objects.create(
            name=f"{today.year}-{str(today.year + 1)[-2:]}",
            start_date=today - timedelta(days=90),
            end_date=today + timedelta(days=275),
            is_active=True,
        )
        self.academic_class = AcademicClass.objects.create(
            name="L1 signature",
            programme=programme,
            branch=self.branch,
            academic_year=academic_year,
            level="L1",
            study_level="LICENCE",
        )
        semester = Semester.objects.create(
            academic_class=self.academic_class,
            number=1,
            total_required_credits=Decimal("3.00"),
        )
        ue = UE.objects.create(semester=semester, code="UE-SIG", title="UE Signature")
        self.ec = EC.objects.create(
            ue=ue, title="Mathématiques", credit_required=Decimal("3.00"), coefficient=Decimal("2.00")
        )
        start = timezone.now() - timedelta(hours=2)
        self.event = AcademicScheduleEvent.objects.create(
            title="Cours signé",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=academic_year,
            start_datetime=start,
            end_datetime=start + timedelta(hours=1),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle S1",
            created_by=self.teacher,
            updated_by=self.teacher,
        )

    def _create_staff(self, username, position, role):
        user = User.objects.create_user(username=username, password="test-password", is_staff=True)
        Profile.objects.filter(user=user).update(
            position=position, role=role, branch=self.branch, user_type="staff"
        )
        return user

    def test_teacher_signature_is_required_then_approved_by_supervisor(self):
        self.client.force_login(self.teacher)
        panel_url = reverse("accounts_portal:teacher_lesson_log_panel", args=[self.event.id])
        capture = self.client.post(
            panel_url,
            {"workflow_action": "sign_submit", "content": "Suites numériques et limites."},
        )
        self.assertEqual(capture.status_code, 200)
        token_match = re.search(rb"/teacher/signatures/([^/]+)/lesson-log/", capture.content)
        self.assertIsNotNone(token_match)

        token = token_match.group(1).decode()
        signed = self.client.post(
            reverse("accounts_portal:teacher_lesson_log_sign", args=[token]),
            {"signature_data": "data:image/png;base64," + base64.b64encode(b"ink").decode()},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(signed.status_code, 200)
        lesson_log = LessonLog.objects.get(schedule_event=self.event)
        signature_request = SignatureRequest.objects.get(object_id=lesson_log.id)
        self.assertEqual(lesson_log.status, LessonLog.STATUS_SUBMITTED)
        self.assertEqual(signature_request.status, SignatureRequest.STATUS_SIGNED)

        TeacherAttendance.objects.create(
            teacher=self.teacher,
            schedule_event=self.event,
            date=timezone.localdate(self.event.start_datetime),
            status=TeacherAttendance.STATUS_PRESENT,
            course_delivered=True,
            recorded_by=self.supervisor,
            branch=self.branch,
        )
        AttendanceRollSheet.objects.create(
            branch=self.branch,
            academic_class=self.academic_class,
            date=timezone.localdate(self.event.start_datetime),
            schedule_event=self.event,
            status=AttendanceRollSheet.STATUS_VALIDATED,
            validated_at=timezone.now(),
            validated_by=self.supervisor,
            updated_by=self.supervisor,
        )

        self.client.force_login(self.supervisor)
        approved = self.client.post(
            reverse("accounts_portal:supervisor_validate_lesson_log"),
            {
                "schedule_event_id": self.event.id,
                "lesson_log_id": lesson_log.id,
                "decision": "approve",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(approved.status_code, 200)
        lesson_log.refresh_from_db()
        signature_request.refresh_from_db()
        self.assertEqual(lesson_log.status, LessonLog.STATUS_DONE)
        self.assertEqual(lesson_log.validated_by, self.supervisor)
        self.assertEqual(signature_request.status, SignatureRequest.STATUS_APPROVED)

    def test_teacher_cannot_open_a_future_lesson_log(self):
        self.event.start_datetime = timezone.now() + timedelta(hours=1)
        self.event.end_datetime = self.event.start_datetime + timedelta(hours=1)
        self.event.save(update_fields=["start_datetime", "end_datetime", "updated_at"])
        self.client.force_login(self.teacher)

        response = self.client.post(
            reverse("accounts_portal:teacher_lesson_log_panel", args=[self.event.id]),
            {"workflow_action": "draft", "content": "Tentative anticipée"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(LessonLog.objects.filter(schedule_event=self.event).exists())
        self.assertContains(response, "à partir du début de la séance")
