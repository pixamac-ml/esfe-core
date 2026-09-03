from datetime import date, datetime

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from academics.models import AcademicCalendarEntry, AcademicClass, AcademicYear, EvaluationCampaign
from academics.services.calendar_service import create_calendar, create_calendar_entry, publish_calendar, submit_calendar, validate_calendar
from academics.services.evaluation_campaign_service import create_evaluation_campaign
from branches.models import Branch
from formations.models import Cycle, Diploma, Filiere, Programme


class EvaluationCampaignServiceTests(TestCase):
    def setUp(self):
        self.actor = get_user_model().objects.create_superuser("campaign_test", "campaign@test.local", "pass")
        self.branch = Branch.objects.create(name="Annexe Campagne", code="CAM", slug="annexe-campagne")
        self.year = AcademicYear.objects.create(name="2040-2041", start_date=date(2040, 10, 1), end_date=date(2041, 8, 31))
        programme = Programme.objects.create(
            title="Programme Campagne", filiere=Filiere.objects.create(name="Filiere Campagne"),
            cycle=Cycle.objects.create(name="Cycle Campagne", theme="primary", min_duration_years=1, max_duration_years=3),
            diploma_awarded=Diploma.objects.create(name="Diplome Campagne", level="superieur"), duration_years=3,
            short_description="Test campagne", description="Test de campagne d'évaluation.",
        )
        self.academic_class = AcademicClass.objects.create(name="L1 Campagne", programme=programme, branch=self.branch, academic_year=self.year, level="L1", study_level="LICENCE")
        self.calendar = create_calendar(actor=self.actor, branch=self.branch, academic_year=self.year)
        create_calendar_entry(
            actor=self.actor, calendar=self.calendar, title="Rentrée",
            event_type=AcademicCalendarEntry.EVENT_ACADEMIC_START,
            start_datetime=timezone.make_aware(datetime(2040, 10, 1, 8)),
            end_datetime=timezone.make_aware(datetime(2040, 10, 1, 18)),
            target_scope=AcademicCalendarEntry.SCOPE_BRANCH,
        )
        self.entry = create_calendar_entry(
            actor=self.actor, calendar=self.calendar, title="Session normale S1",
            event_type=AcademicCalendarEntry.EVENT_EXAM_SESSION,
            start_datetime=timezone.make_aware(datetime(2041, 1, 10, 8)),
            end_datetime=timezone.make_aware(datetime(2041, 1, 15, 18)),
            target_scope=AcademicCalendarEntry.SCOPE_BRANCH, is_blocking=True,
        )
        create_calendar_entry(
            actor=self.actor, calendar=self.calendar, title="Cloture",
            event_type=AcademicCalendarEntry.EVENT_ACADEMIC_END,
            start_datetime=timezone.make_aware(datetime(2041, 8, 31, 8)),
            end_datetime=timezone.make_aware(datetime(2041, 8, 31, 18)),
            target_scope=AcademicCalendarEntry.SCOPE_BRANCH,
        )

    def test_campaign_requires_published_calendar_and_scopes_branch_classes(self):
        with self.assertRaises(ValidationError):
            create_evaluation_campaign(actor=self.actor, calendar_entry=self.entry)

        submit_calendar(self.calendar, actor=self.actor)
        validate_calendar(self.calendar, actor=self.actor)
        publish_calendar(self.calendar, actor=self.actor)
        self.entry.refresh_from_db()

        campaign = create_evaluation_campaign(actor=self.actor, calendar_entry=self.entry)
        self.assertEqual(campaign.kind, EvaluationCampaign.KIND_NORMAL)
        self.assertEqual(campaign.calendar_entry, self.entry)
        self.assertTrue(campaign.scopes.filter(academic_class=self.academic_class, included=True).exists())
