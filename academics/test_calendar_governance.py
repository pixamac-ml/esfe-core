from datetime import date, datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from academics.models import (
    AcademicCalendar,
    AcademicCalendarAdjustment,
    AcademicCalendarDisruption,
    AcademicCalendarEntry,
    AcademicYear,
)
from academics.services.calendar_service import (
    activate_calendar_disruption,
    create_calendar,
    create_calendar_adjustment,
    create_calendar_entry,
    create_calendar_revision,
    get_effective_calendar_schedule,
    publish_calendar,
    publish_calendar_adjustment,
    reject_calendar,
    report_calendar_disruption,
    submit_calendar,
    submit_calendar_adjustment,
    validate_calendar,
    validate_calendar_adjustment,
)
from branches.models import Branch


class AcademicCalendarGovernanceTests(TestCase):
    def setUp(self):
        self.actor = get_user_model().objects.create_superuser(
            username="calendar_governance", email="governance@example.com", password="pass"
        )
        self.branch = Branch.objects.create(name="Gouvernance", code="GOV", slug="gouvernance")
        self.year = AcademicYear.objects.create(
            name="2055-2056", start_date=date(2055, 9, 1), end_date=date(2056, 7, 31)
        )

    def aware(self, month, day, hour=8):
        year = 2055 if month >= 9 else 2056
        return timezone.make_aware(datetime(year, month, day, hour))

    def calendar_with_entry(self):
        calendar = create_calendar(actor=self.actor, branch=self.branch, academic_year=self.year)
        create_calendar_entry(
            actor=self.actor,
            calendar=calendar,
            title="Rentree academique",
            event_type=AcademicCalendarEntry.EVENT_ACADEMIC_START,
            start_datetime=self.aware(9, 1),
            end_datetime=self.aware(9, 1, 18),
            target_scope=AcademicCalendarEntry.SCOPE_BRANCH,
            is_blocking=False,
        )
        entry = create_calendar_entry(
            actor=self.actor,
            calendar=calendar,
            title="Session normale S1",
            event_type=AcademicCalendarEntry.EVENT_EXAM_SESSION,
            start_datetime=self.aware(1, 15),
            end_datetime=self.aware(1, 20),
            target_scope=AcademicCalendarEntry.SCOPE_BRANCH,
            is_blocking=True,
        )
        create_calendar_entry(
            actor=self.actor,
            calendar=calendar,
            title="Cloture academique",
            event_type=AcademicCalendarEntry.EVENT_ACADEMIC_END,
            start_datetime=self.aware(7, 30),
            end_datetime=self.aware(7, 30, 18),
            target_scope=AcademicCalendarEntry.SCOPE_BRANCH,
            is_blocking=False,
        )
        return calendar, entry

    def publish(self, calendar):
        submit_calendar(calendar, actor=self.actor)
        validate_calendar(calendar, actor=self.actor)
        publish_calendar(calendar, actor=self.actor)
        calendar.refresh_from_db()
        return calendar

    def test_submission_rejection_and_resubmission_are_traced(self):
        calendar, _ = self.calendar_with_entry()

        submit_calendar(calendar, actor=self.actor)
        self.assertEqual(calendar.status, AcademicCalendar.STATUS_SUBMITTED)
        self.assertEqual(calendar.submitted_by, self.actor)

        reject_calendar(calendar, actor=self.actor, reason="Ajouter la date de cloture.")
        self.assertEqual(calendar.status, AcademicCalendar.STATUS_REJECTED)
        self.assertEqual(calendar.rejection_reason, "Ajouter la date de cloture.")

        submit_calendar(calendar, actor=self.actor)
        self.assertEqual(calendar.status, AcademicCalendar.STATUS_SUBMITTED)
        self.assertEqual(calendar.rejection_reason, "")

    def test_revision_clones_entries_and_supersedes_previous_publication(self):
        first, entry = self.calendar_with_entry()
        self.publish(first)

        revision = create_calendar_revision(first, actor=self.actor)
        self.assertEqual(revision.version, 2)
        self.assertEqual(revision.revision_of, first)
        copied = revision.entries.get()
        self.assertEqual(copied.title, entry.title)
        self.assertEqual(copied.status, AcademicCalendarEntry.STATUS_DRAFT)

        self.publish(revision)
        first.refresh_from_db()
        revision.refresh_from_db()
        self.assertEqual(first.status, AcademicCalendar.STATUS_SUPERSEDED)
        self.assertEqual(revision.status, AcademicCalendar.STATUS_PUBLISHED)

    def test_disruption_and_adjustment_preserve_original_event_dates(self):
        calendar, entry = self.calendar_with_entry()
        self.publish(calendar)

        disruption = report_calendar_disruption(
            actor=self.actor,
            calendar=calendar,
            title="Suspension locale",
            incident_type=AcademicCalendarDisruption.TYPE_SECURITY,
            reason="Mesure de securite temporaire.",
            starts_at=self.aware(1, 14),
            target_scope=AcademicCalendarEntry.SCOPE_BRANCH,
            in_person_impact=AcademicCalendarDisruption.IMPACT_SUSPENDED,
            online_impact=AcademicCalendarDisruption.IMPACT_MAINTAINED,
            assessment_impact=AcademicCalendarDisruption.IMPACT_POSTPONED,
        )
        activate_calendar_disruption(disruption, actor=self.actor)

        adjustment = create_calendar_adjustment(
            actor=self.actor,
            calendar=calendar,
            calendar_entry=entry,
            disruption=disruption,
            action=AcademicCalendarAdjustment.ACTION_RESCHEDULE,
            reason="Report de la session apres reprise.",
            effective_start_datetime=self.aware(1, 22),
            effective_end_datetime=self.aware(1, 27),
        )
        submit_calendar_adjustment(adjustment, actor=self.actor)
        validate_calendar_adjustment(adjustment, actor=self.actor)
        publish_calendar_adjustment(adjustment, actor=self.actor)

        entry.refresh_from_db()
        effective = next(
            item for item in get_effective_calendar_schedule(calendar)
            if item["entry"].id == entry.id
        )
        self.assertEqual(entry.start_datetime, self.aware(1, 15))
        self.assertEqual(entry.end_datetime, self.aware(1, 20))
        self.assertEqual(effective["start_datetime"], self.aware(1, 22))
        self.assertEqual(effective["end_datetime"], self.aware(1, 27))
