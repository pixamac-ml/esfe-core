from datetime import date, datetime

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from academics.models import (
    AcademicCalendar,
    AcademicCalendarEntry,
    AcademicClass,
    AcademicYear,
    Semester,
)
from academics.selectors.calendar_selectors import (
    get_active_calendar,
    get_calendar_entries_by_academic_year,
    get_calendar_entries_by_period,
)
from academics.services.calendar_service import (
    create_calendar,
    create_calendar_entry,
    publish_calendar,
    validate_calendar,
)
from branches.models import Branch
from formations.models import Cycle, Diploma, Filiere, Programme


User = get_user_model()


class AcademicCalendarSprintOneTests(TestCase):
    def setUp(self):
        self.actor = User.objects.create_superuser(
            username="calendar_admin",
            email="calendar@example.com",
            password="pass1234",
        )
        self.branch = Branch.objects.create(
            name="Annexe Calendrier",
            code="CAL",
            slug="annexe-calendrier",
        )
        self.other_branch = Branch.objects.create(
            name="Autre Annexe Calendrier",
            code="CA2",
            slug="autre-annexe-calendrier",
        )
        self.academic_year = AcademicYear.objects.create(
            name="2040-2041",
            start_date=date(2040, 10, 1),
            end_date=date(2041, 7, 31),
            is_active=True,
        )
        cycle = Cycle.objects.create(
            name="Cycle Calendrier",
            theme="accent",
            min_duration_years=1,
            max_duration_years=3,
        )
        diploma = Diploma.objects.create(name="Diplome Calendrier", level="superieur")
        filiere = Filiere.objects.create(name="Filiere Calendrier")
        self.programme = Programme.objects.create(
            title="Programme Calendrier",
            filiere=filiere,
            cycle=cycle,
            diploma_awarded=diploma,
            duration_years=3,
            short_description="Calendrier",
            description="Programme de test du calendrier academique",
        )
        self.academic_class = AcademicClass.objects.create(
            programme=self.programme,
            branch=self.branch,
            academic_year=self.academic_year,
            level="L1-CAL",
            study_level="LICENCE",
        )
        self.semester = Semester.objects.create(
            academic_class=self.academic_class,
            number=1,
        )

    def aware(self, year, month, day, hour=0):
        return timezone.make_aware(datetime(year, month, day, hour, 0))

    def make_calendar(self, version=1):
        return create_calendar(
            actor=self.actor,
            branch=self.branch,
            academic_year=self.academic_year,
            version=version,
        )

    def make_entry(self, calendar, **overrides):
        data = {
            "title": "Rentree academique",
            "description": "Ouverture officielle de l'annee",
            "event_type": AcademicCalendarEntry.EVENT_ACADEMIC_START,
            "start_datetime": self.aware(2040, 10, 1, 8),
            "end_datetime": self.aware(2040, 10, 1, 10),
            "all_day": False,
            "target_scope": AcademicCalendarEntry.SCOPE_BRANCH,
            "color": "#2563eb",
            "icon": "calendar-days",
            "is_blocking": False,
            "status": AcademicCalendarEntry.STATUS_DRAFT,
        }
        data.update(overrides)
        return create_calendar_entry(actor=self.actor, calendar=calendar, **data)

    def test_calendar_creation(self):
        calendar = self.make_calendar()

        self.assertEqual(calendar.branch, self.branch)
        self.assertEqual(calendar.academic_year, self.academic_year)
        self.assertEqual(calendar.version, 1)
        self.assertEqual(calendar.status, AcademicCalendar.STATUS_DRAFT)
        self.assertEqual(calendar.created_by, self.actor)

    def test_calendar_entry_creation(self):
        calendar = self.make_calendar()
        entry = self.make_entry(
            calendar,
            title="Debut du semestre 1",
            event_type=AcademicCalendarEntry.EVENT_SEMESTER_START,
            target_scope=AcademicCalendarEntry.SCOPE_SEMESTER,
            semester=self.semester,
        )

        self.assertEqual(entry.calendar, calendar)
        self.assertEqual(entry.semester, self.semester)
        self.assertTrue(timezone.is_aware(entry.start_datetime))

    def test_entry_rejects_invalid_dates_and_dates_outside_academic_year(self):
        calendar = self.make_calendar()

        with self.assertRaises(ValidationError):
            self.make_entry(
                calendar,
                start_datetime=self.aware(2040, 10, 2, 10),
                end_datetime=self.aware(2040, 10, 2, 8),
            )

        with self.assertRaises(ValidationError):
            self.make_entry(
                calendar,
                start_datetime=self.aware(2041, 8, 1, 8),
                end_datetime=self.aware(2041, 8, 1, 10),
            )

        with self.assertRaises(ValidationError):
            self.make_entry(
                calendar,
                start_datetime=datetime(2040, 10, 2, 8, 0),
                end_datetime=datetime(2040, 10, 2, 10, 0),
            )

    def test_director_is_restricted_to_own_branch(self):
        director = User.objects.create_user(username="calendar_director", password="pass1234")
        director.profile.position = "director_of_studies"
        director.profile.branch = self.branch
        director.profile.save(update_fields=["position", "branch"])

        own_calendar = create_calendar(
            actor=director,
            branch=self.branch,
            academic_year=self.academic_year,
        )
        self.assertEqual(own_calendar.branch, self.branch)

        with self.assertRaises(PermissionDenied):
            create_calendar(
                actor=director,
                branch=self.other_branch,
                academic_year=self.academic_year,
            )

        other_class = AcademicClass.objects.create(
            programme=self.programme,
            branch=self.other_branch,
            academic_year=self.academic_year,
            level="L1-OTHER",
            study_level="LICENCE",
        )
        with self.assertRaises(ValidationError):
            self.make_entry(
                own_calendar,
                target_scope=AcademicCalendarEntry.SCOPE_CLASS,
                academic_class=other_class,
            )

    def test_only_one_published_calendar_per_branch_and_year(self):
        first = self.make_calendar(version=1)
        self.make_entry(first)
        validate_calendar(first, actor=self.actor)
        publish_calendar(first, actor=self.actor)

        duplicate = AcademicCalendar(
            branch=self.branch,
            academic_year=self.academic_year,
            version=2,
            status=AcademicCalendar.STATUS_PUBLISHED,
            created_by=self.actor,
            updated_by=self.actor,
            published_by=self.actor,
            published_at=timezone.now(),
        )
        with self.assertRaises(ValidationError):
            duplicate.save()

    def test_retrieves_active_calendar_and_entries_by_year(self):
        calendar = self.make_calendar()
        entry = self.make_entry(calendar)
        validate_calendar(calendar, actor=self.actor)
        publish_calendar(calendar, actor=self.actor)

        active = get_active_calendar(self.branch, self.academic_year)
        entries = get_calendar_entries_by_academic_year(self.academic_year)

        self.assertEqual(active, calendar)
        self.assertEqual(list(entries), [entry])

    def test_retrieves_entries_overlapping_period(self):
        calendar = self.make_calendar()
        matching = self.make_entry(
            calendar,
            start_datetime=self.aware(2040, 12, 20, 8),
            end_datetime=self.aware(2041, 1, 5, 18),
            event_type=AcademicCalendarEntry.EVENT_HOLIDAY,
            title="Vacances de fin d'annee",
            all_day=True,
            is_blocking=True,
        )
        self.make_entry(
            calendar,
            start_datetime=self.aware(2041, 4, 1, 8),
            end_datetime=self.aware(2041, 4, 1, 10),
            title="Reunion hors periode",
            event_type=AcademicCalendarEntry.EVENT_MEETING,
        )

        entries = get_calendar_entries_by_period(
            self.aware(2040, 12, 25),
            self.aware(2041, 1, 2),
        )

        self.assertEqual(list(entries), [matching])
