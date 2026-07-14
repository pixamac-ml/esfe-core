import json
from datetime import date, datetime

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from academics.models import AcademicCalendar, AcademicCalendarEntry, AcademicYear
from academics.services.calendar_service import create_calendar, create_calendar_entry, publish_calendar, validate_calendar
from branches.models import Branch


class AcademicCalendarWorkflowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser("cal_workflow", "cal@example.com", "pass")
        self.branch = Branch.objects.create(name="Workflow", code="WFL", slug="workflow")
        self.year = AcademicYear.objects.create(name="2050-2051", start_date=date(2050, 9, 1), end_date=date(2051, 7, 31))
        self.client.force_login(self.user)

    def aware(self, month, day, hour=8):
        year = 2050 if month >= 9 else 2051
        return timezone.make_aware(datetime(year, month, day, hour))

    def entry_data(self, start=None, end=None, title="Rentree"):
        return {
            "title": title,
            "event_type": AcademicCalendarEntry.EVENT_ACADEMIC_START,
            "start_datetime": (start or self.aware(9, 1)).isoformat(),
            "end_datetime": (end or self.aware(9, 1, 10)).isoformat(),
            "target_scope": AcademicCalendarEntry.SCOPE_BRANCH,
            "is_blocking": False,
        }

    def test_json_crud_and_workflow(self):
        response = self.client.post(
            reverse("academics:calendar_list_create"),
            json.dumps({"branch_id": self.branch.pk, "academic_year_id": self.year.pk}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        calendar_id = response.json()["calendar"]["id"]
        entry_response = self.client.post(
            reverse("academics:calendar_entry_create", args=[calendar_id]),
            json.dumps(self.entry_data()), content_type="application/json",
        )
        self.assertEqual(entry_response.status_code, 201)
        self.assertEqual(self.client.post(reverse("academics:calendar_validate", args=[calendar_id])).status_code, 200)
        self.assertEqual(self.client.post(reverse("academics:calendar_publish", args=[calendar_id])).status_code, 200)
        self.assertEqual(self.client.post(reverse("academics:calendar_archive", args=[calendar_id])).status_code, 200)
        self.assertEqual(AcademicCalendar.objects.get(pk=calendar_id).status, AcademicCalendar.STATUS_ARCHIVED)

    def test_publish_rejects_overlapping_periods(self):
        calendar = create_calendar(actor=self.user, branch=self.branch, academic_year=self.year)
        base = {"event_type": AcademicCalendarEntry.EVENT_HOLIDAY, "target_scope": AcademicCalendarEntry.SCOPE_BRANCH}
        create_calendar_entry(actor=self.user, calendar=calendar, title="A", start_datetime=self.aware(12, 1), end_datetime=self.aware(12, 5), **base)
        create_calendar_entry(actor=self.user, calendar=calendar, title="B", start_datetime=self.aware(12, 4), end_datetime=self.aware(12, 8), **base)
        validate_calendar(calendar, actor=self.user)
        with self.assertRaises(ValidationError):
            publish_calendar(calendar, actor=self.user)

    def test_filters_by_branch_and_year(self):
        create_calendar(actor=self.user, branch=self.branch, academic_year=self.year)
        response = self.client.get(reverse("academics:calendar_list_create"), {"branch": self.branch.pk, "academic_year": self.year.pk})
        self.assertEqual(len(response.json()["calendars"]), 1)
