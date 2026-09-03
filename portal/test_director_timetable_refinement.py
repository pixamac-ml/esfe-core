from datetime import date, datetime, time

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from academics.models import AcademicClass, AcademicScheduleEvent, AcademicYear, EC, Semester, UE, WeeklyScheduleSlot
from academics.services.schedule_service import create_schedule_event
from portal.services.director.timetable_service import build_weekly_timetable_grid
from branches.models import Branch
from formations.models import Cycle, Diploma, Filiere, Programme


class DirectorTimetableRefinementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.branch = Branch.objects.create(
            name="Annexe Emploi du temps", code="AED", slug="annexe-emploi-du-temps"
        )
        cls.other_branch = Branch.objects.create(
            name="Annexe Confidentielle", code="ACO", slug="annexe-confidentielle-edt"
        )
        cycle = Cycle.objects.create(
            name="Licence EDT", theme="primary", min_duration_years=1, max_duration_years=5
        )
        diploma = Diploma.objects.create(name="Diplôme EDT", level="superieur")
        filiere = Filiere.objects.create(name="Filière EDT")
        programme = Programme.objects.create(
            title="Gestion des entreprises",
            filiere=filiere,
            cycle=cycle,
            diploma_awarded=diploma,
            duration_years=3,
            short_description="Programme pour les tests d'emploi du temps.",
            description="Programme complet pour les tests d'emploi du temps.",
        )
        cls.academic_year = AcademicYear.objects.create(
            name="2026-2027",
            start_date=date(2026, 10, 1),
            end_date=date(2027, 7, 31),
            is_active=True,
        )
        cls.academic_class = AcademicClass.objects.create(
            name="L1 Gestion EDT",
            programme=programme,
            branch=cls.branch,
            academic_year=cls.academic_year,
            level="L1",
            study_level="LICENCE",
        )
        cls.other_class = AcademicClass.objects.create(
            name="Classe Hors Annexe EDT",
            programme=programme,
            branch=cls.other_branch,
            academic_year=cls.academic_year,
            level="L2",
            study_level="LICENCE",
        )
        semester = Semester.objects.create(academic_class=cls.academic_class, number=1)
        other_semester = Semester.objects.create(academic_class=cls.other_class, number=1)
        ue = UE.objects.create(semester=semester, code="UE-EDT", title="Fondamentaux")
        other_ue = UE.objects.create(
            semester=other_semester, code="UE-SECRET", title="Hors annexe"
        )
        cls.ec = EC.objects.create(
            ue=ue, title="Comptabilité générale", credit_required="3.00", coefficient="2.00"
        )
        cls.other_ec = EC.objects.create(
            ue=other_ue, title="Matière confidentielle", credit_required="2.00", coefficient="1.00"
        )

        User = get_user_model()
        cls.director = User.objects.create_user(
            username="director_timetable",
            email="director-timetable@test.test",
            password="director-password",
            is_staff=True,
        )
        cls.director.profile.position = "director_of_studies"
        cls.director.profile.role = "executive"
        cls.director.profile.branch = cls.branch
        cls.director.profile.save(update_fields=["position", "role", "branch", "updated_at"])

        cls.teacher = User.objects.create_user(
            username="teacher_timetable",
            first_name="Aminata",
            last_name="Traoré",
            password="teacher-password",
        )
        cls.teacher.profile.position = "teacher"
        cls.teacher.profile.branch = cls.branch
        cls.teacher.profile.save(update_fields=["position", "branch", "updated_at"])

        cls.other_teacher = User.objects.create_user(
            username="other_teacher_timetable",
            first_name="Enseignant",
            last_name="Hors Annexe",
            password="teacher-password",
        )
        cls.other_teacher.profile.position = "teacher"
        cls.other_teacher.profile.branch = cls.other_branch
        cls.other_teacher.profile.save(update_fields=["position", "branch", "updated_at"])

    def setUp(self):
        self.client.force_login(self.director)

    def _create_slot(self, **overrides):
        values = {
            "academic_class": self.academic_class,
            "ec": self.ec,
            "teacher": self.teacher,
            "branch": self.branch,
            "academic_year": self.academic_year,
            "weekday": 0,
            "start_time": time(8, 0),
            "end_time": time(10, 0),
            "room": "Salle A12",
            "created_by": self.director,
        }
        values.update(overrides)
        return WeeklyScheduleSlot.objects.create(**values)

    def test_workspace_exposes_three_timetable_subviews_without_cross_branch_data(self):
        response = self.client.get(
            reverse("accounts_portal:director_workspace"),
            {"section": "planification"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Emploi du temps")
        self.assertContains(response, "Vue d&#x27;ensemble")
        self.assertContains(response, "Construire")
        self.assertContains(response, "Aperçu et impression")
        self.assertContains(response, self.academic_class.name)
        self.assertNotContains(response, self.other_class.name)

    def test_builder_requires_a_scoped_class_and_renders_week_grid(self):
        response = self.client.get(
            reverse("accounts_portal:director_timetable_subcontent"),
            {
                "view": "builder",
                "class_id": self.academic_class.pk,
                "week_start": "2026-11-18",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.academic_class.name)
        self.assertContains(response, "Lundi")
        self.assertContains(response, "Samedi")
        self.assertContains(response, "08:00")
        self.assertContains(response, 'data-timetable-week-start="2026-11-16"')
        self.assertContains(response, "Du 16/11/2026 au 21/11/2026")
        self.assertContains(response, "week_start=2026-11-09")
        self.assertContains(response, "week_start=2026-11-23")
        self.assertIn("section=planification", response.headers["HX-Push-Url"])

        forbidden_selection = self.client.get(
            reverse("accounts_portal:director_timetable_subcontent"),
            {"view": "builder", "class_id": self.other_class.pk},
        )
        self.assertNotContains(forbidden_selection, self.other_class.name)
        self.assertContains(forbidden_selection, "Sélectionnez une classe")

    def test_slot_drawer_only_lists_subjects_and_teachers_from_the_branch(self):
        response = self.client.get(
            reverse("accounts_portal:director_timetable_slot_drawer"),
            {
                "class_id": self.academic_class.pk,
                "weekday": "2",
                "start_time": "10:15",
                "end_time": "12:15",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.ec.title)
        self.assertContains(response, self.teacher.get_full_name())
        self.assertContains(response, 'value="10:15"')
        self.assertNotContains(response, self.other_ec.title)
        self.assertNotContains(response, self.other_teacher.get_full_name())

    def test_invalid_slot_preserves_values_and_rejects_cross_branch_teacher(self):
        response = self.client.post(
            reverse("accounts_portal:director_timetable_action"),
            {
                "action": "save",
                "class_id": self.academic_class.pk,
                "weekday": "1",
                "start_time": "11:00",
                "end_time": "09:00",
                "ec_id": self.ec.pk,
                "teacher_id": self.other_teacher.pk,
                "room": "Salle saisie à conserver",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Salle saisie à conserver")
        self.assertContains(response, "Cet enseignant n&#x27;appartient pas à votre annexe")
        self.assertContains(response, "postérieure")
        self.assertFalse(WeeklyScheduleSlot.objects.exists())
        self.assertNotIn("HX-Retarget", response.headers)

    def test_create_conflict_and_delete_use_the_canonical_weekly_service(self):
        payload = {
            "action": "save",
            "class_id": self.academic_class.pk,
            "weekday": "0",
            "start_time": "08:00",
            "end_time": "10:00",
            "ec_id": self.ec.pk,
            "teacher_id": self.teacher.pk,
            "room": "Salle A12",
            "week_start": "2026-11-16",
        }
        created = self.client.post(
            reverse("accounts_portal:director_timetable_action"), payload
        )

        self.assertEqual(created.status_code, 200)
        slot = WeeklyScheduleSlot.objects.get()
        self.assertEqual(slot.branch, self.branch)
        self.assertEqual(created.headers["HX-Retarget"], "#director-timetable-subcontent")
        self.assertEqual(created.headers["HX-Trigger"], "director-drawer-close")
        self.assertIn("week_start=2026-11-16", created.headers["HX-Push-Url"])

        conflict_payload = payload | {"start_time": "09:00", "end_time": "11:00"}
        conflict = self.client.post(
            reverse("accounts_portal:director_timetable_action"), conflict_payload
        )
        self.assertEqual(conflict.status_code, 200)
        self.assertContains(conflict, "Classe deja occupee")
        self.assertEqual(WeeklyScheduleSlot.objects.filter(is_active=True).count(), 1)

        deleted = self.client.post(
            reverse("accounts_portal:director_timetable_action"),
            {"action": "delete", "class_id": self.academic_class.pk, "slot_id": slot.pk},
        )
        self.assertEqual(deleted.status_code, 200)
        slot.refresh_from_db()
        self.assertFalse(slot.is_active)
        self.assertContains(deleted, "retiré de la grille")

    def test_weekly_print_is_landscape_and_branch_scoped(self):
        self._create_slot()
        response = self.client.get(
            reverse("accounts_portal:schedule_class_print", args=[self.academic_class.pk]),
            {"source": "weekly", "week_start": "2026-11-18"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A4 landscape")
        self.assertContains(response, self.ec.title)
        self.assertContains(response, "Salle A12")
        self.assertContains(response, "Du 16/11/2026 au 21/11/2026")
        self.assertContains(response, "Lundi<br>16/11", html=True)
        self.assertContains(response, "Document de référence pour l'affichage interne")

        outside = self.client.get(
            reverse("accounts_portal:schedule_class_print", args=[self.other_class.pk]),
            {"source": "weekly"},
        )
        self.assertEqual(outside.status_code, 403)

    def test_dated_week_print_uses_the_selected_week_and_document_identity(self):
        create_schedule_event(
            user=self.director, title="Comptabilité - impression datée",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            status=AcademicScheduleEvent.STATUS_PLANNED,
            academic_class=self.academic_class, academic_year=self.academic_year,
            branch=self.branch, ec=self.ec, teacher=self.teacher,
            start_datetime=timezone.make_aware(datetime(2026, 11, 23, 8, 0)),
            end_datetime=timezone.make_aware(datetime(2026, 11, 23, 10, 0)), location="Salle A12", is_online=False,
        )
        response = self.client.get(
            reverse("accounts_portal:schedule_class_print", args=[self.academic_class.pk]),
            {"source": "week", "week_start": "2026-11-23"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Emploi du temps de la classe")
        self.assertContains(response, "Du 23/11/2026 au 28/11/2026")
        self.assertContains(response, f"EDT-{self.academic_class.pk}-20261123")
        self.assertContains(response, "Direction des études")

    def test_dated_week_grid_does_not_reuse_another_week(self):
        create_schedule_event(
            user=self.director, title="Comptabilité - semaine A",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            status=AcademicScheduleEvent.STATUS_PLANNED,
            academic_class=self.academic_class, academic_year=self.academic_year,
            branch=self.branch, ec=self.ec, teacher=self.teacher,
            start_datetime=timezone.make_aware(datetime(2026, 11, 23, 8, 0)),
            end_datetime=timezone.make_aware(datetime(2026, 11, 23, 10, 0)), location="Salle A12", is_online=False,
        )
        week_a = build_weekly_timetable_grid(self.academic_class, week_start=date(2026, 11, 23))
        week_before = build_weekly_timetable_grid(self.academic_class, week_start=date(2026, 11, 16))
        self.assertEqual(len(week_a["slots"]), 1)
        self.assertEqual(len(week_before["slots"]), 0)

    def test_navigation_between_two_weeks_loads_each_weeks_own_courses(self):
        first = create_schedule_event(
            user=self.director, title="Comptabilité - semaine 1",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            status=AcademicScheduleEvent.STATUS_PLANNED,
            academic_class=self.academic_class, academic_year=self.academic_year,
            branch=self.branch, ec=self.ec, teacher=self.teacher,
            start_datetime=timezone.make_aware(datetime(2026, 11, 16, 8, 0)),
            end_datetime=timezone.make_aware(datetime(2026, 11, 16, 10, 0)), location="Salle A12", is_online=False,
        )
        second = create_schedule_event(
            user=self.director, title="Comptabilité - semaine 2",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            status=AcademicScheduleEvent.STATUS_PLANNED,
            academic_class=self.academic_class, academic_year=self.academic_year,
            branch=self.branch, ec=self.ec, teacher=self.teacher,
            start_datetime=timezone.make_aware(datetime(2026, 11, 23, 10, 15)),
            end_datetime=timezone.make_aware(datetime(2026, 11, 23, 12, 15)), location="Salle B02", is_online=False,
        )
        week_one = build_weekly_timetable_grid(self.academic_class, week_start=date(2026, 11, 16))
        week_two = build_weekly_timetable_grid(self.academic_class, week_start=date(2026, 11, 23))
        self.assertEqual([item["id"] for item in week_one["slots"]], [first.id])
        self.assertEqual([item["id"] for item in week_two["slots"]], [second.id])

    def test_dated_event_update_and_delete_only_affect_selected_occurrence(self):
        event = AcademicScheduleEvent.objects.create(
            title="Comptabilité - semaine A", event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            status=AcademicScheduleEvent.STATUS_PLANNED, academic_class=self.academic_class,
            academic_year=self.academic_year, branch=self.branch, ec=self.ec, teacher=self.teacher,
            start_datetime=timezone.make_aware(datetime(2026, 11, 23, 8, 0)), end_datetime=timezone.make_aware(datetime(2026, 11, 23, 10, 0)),
            location="Salle A12", is_online=False, created_by=self.director, updated_by=self.director,
        )
        updated = self.client.post(reverse("accounts_portal:director_timetable_event_action"), {
            "action": "save", "class_id": self.academic_class.pk, "event_id": event.pk,
            "date": "2026-11-23", "start_time": "10:15", "end_time": "12:15",
            "ec_id": self.ec.pk, "teacher_id": self.teacher.pk, "room": "Salle B02", "week_start": "2026-11-23",
        })
        self.assertEqual(updated.status_code, 200)
        event.refresh_from_db()
        self.assertEqual(event.location, "Salle B02")
        deleted = self.client.post(reverse("accounts_portal:director_timetable_event_action"), {
            "action": "delete", "class_id": self.academic_class.pk, "event_id": event.pk, "week_start": "2026-11-23",
        })
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.headers["HX-Retarget"], "#director-timetable-subcontent")
        self.assertEqual(deleted.headers["HX-Trigger"], "director-drawer-close")
        event.refresh_from_db()
        self.assertEqual(event.status, AcademicScheduleEvent.STATUS_CANCELLED)
        refreshed_week = build_weekly_timetable_grid(self.academic_class, week_start=date(2026, 11, 23))
        self.assertEqual(refreshed_week["slots"], [])

    def test_week_grid_always_uses_dated_sessions_even_if_a_template_mode_is_requested(self):
        event = AcademicScheduleEvent.objects.create(
            title="Comptabilité - semaine A", event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            status=AcademicScheduleEvent.STATUS_PLANNED, academic_class=self.academic_class,
            academic_year=self.academic_year, branch=self.branch, ec=self.ec, teacher=self.teacher,
            start_datetime=timezone.make_aware(datetime(2026, 11, 23, 8, 0)), end_datetime=timezone.make_aware(datetime(2026, 11, 23, 10, 0)),
            location="Salle A12", is_online=False, created_by=self.director, updated_by=self.director,
        )
        week_response = self.client.get(reverse("accounts_portal:director_timetable_subcontent"), {
            "view": "builder", "mode": "week", "class_id": self.academic_class.pk, "week_start": "2026-11-23",
        }, HTTP_HX_REQUEST="true")
        self.assertContains(week_response, f"event_id={event.pk}")
        self.assertContains(week_response, reverse("accounts_portal:director_timetable_event_drawer"))
        self.assertContains(week_response, "Séances de la semaine sélectionnée")

        requested_template_response = self.client.get(reverse("accounts_portal:director_timetable_subcontent"), {
            "view": "builder", "mode": "template", "class_id": self.academic_class.pk, "week_start": "2026-11-23",
        }, HTTP_HX_REQUEST="true")
        self.assertContains(requested_template_response, "Séances de la semaine sélectionnée")
        self.assertNotContains(requested_template_response, "Modèle hebdomadaire récurrent")
        self.assertContains(requested_template_response, reverse("accounts_portal:director_timetable_event_drawer"))

    def test_director_grid_cannot_materialize_recurring_slots_into_other_weeks(self):
        self._create_slot()
        response = self.client.post(reverse("accounts_portal:director_timetable_action"), {
            "action": "materialize_month", "class_id": self.academic_class.pk,
            "week_start": "2026-11-23",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "génération automatique de semaines est désactivée")
        self.assertFalse(AcademicScheduleEvent.objects.filter(academic_class=self.academic_class).exists())
