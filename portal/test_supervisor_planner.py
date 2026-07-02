"""Tests cibles pour le planning du Surveillant General (drawers + modales).

Couvre :
- Affichage du workspace planning (vue lecture seule)
- Affichage du workspace grille hebdomadaire (avec toolbar + 3 cartes)
- Rendu du formulaire drawer (creation / edition d'un creneau)
- Rendu du formulaire drawer (creation rapide d'un cours)
- Generation de la semaine (creneaux recurrents -> cours dates)
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, cast

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from academics.models import (
    AcademicClass,
    AcademicScheduleEvent,
    AcademicYear,
    EC,
    Semester,
    UE,
    WeeklyScheduleSlot,
)
from branches.models import Branch
from formations.models import Cycle, Diploma, Filiere, Programme
from notifier.models import NotificationMessage
from students.models import TeacherCase


User = get_user_model()
USER_MANAGER = cast(Any, User._default_manager)


def _create_branch(code="TST", name="Annexe Test"):
    return Branch.objects.create(name=name, code=code, slug=f"annexe-{code.lower()}")


def _create_programme():
    cycle = Cycle.objects.create(name="Licence", min_duration_years=3, max_duration_years=4)
    diploma = Diploma.objects.create(name="Licence Pro", level="superieur")
    filiere = Filiere.objects.create(name="Informatique")
    return Programme.objects.create(
        title="LP Informatique",
        filiere=filiere,
        cycle=cycle,
        diploma_awarded=diploma,
        duration_years=3,
        short_description="Formation en informatique",
        description="Formation en informatique de niveau licence",
    )


def _create_supervisor(branch, username="sup_planner"):
    user = USER_MANAGER.create_user(
        username=username,
        email=f"{username}@test.com",
        password="pass1234",
        is_staff=True,
    )
    profile = user.profile
    profile.position = "academic_supervisor"
    profile.branch = branch
    profile.save(update_fields=["position", "branch", "updated_at"])
    return user


def _create_class_bundle(programme, branch, level="L1"):
    academic_year = AcademicYear.objects.create(
        name=f"25-26-{level}",
        start_date=date(2025, 10, 1),
        end_date=date(2026, 7, 31),
        is_active=True,
    )
    academic_class = AcademicClass.objects.create(
        programme=programme,
        branch=branch,
        academic_year=academic_year,
        level=level,
        study_level="LICENCE",
        is_active=True,
    )
    semester = Semester.objects.create(academic_class=academic_class, number=1)
    ue = UE.objects.create(semester=semester, code=f"UE-{level}", title=f"UE {level}")
    ec = EC.objects.create(ue=ue, title=f"EC {level}", credit_required=Decimal("3"), coefficient=Decimal("2"))
    return academic_year, academic_class, ec


def _create_teacher(branch, username="teacher_planner"):
    user = USER_MANAGER.create_user(
        username=username,
        email=f"{username}@test.com",
        password="pass1234",
    )
    profile = user.profile
    profile.position = "teacher"
    profile.branch = branch
    profile.save(update_fields=["position", "branch", "updated_at"])
    return user


class SupervisorPlannerViewTests(TestCase):
    """Le supervillant peut ouvrir les vues planning (lecture + edit) sans crash."""

    def setUp(self):
        self.branch = _create_branch()
        self.programme = _create_programme()
        self.year, self.cls, self.ec = _create_class_bundle(self.programme, self.branch)
        self.supervisor = _create_supervisor(self.branch)
        self.client.force_login(self.supervisor)

    def test_planner_view_workspace_renders_with_class(self):
        url = reverse("accounts_portal:supervisor_planner_view_workspace")
        response = self.client.get(url, {"class_id": self.cls.id})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Emploi du temps de")
        self.assertContains(response, "Ajouter un cours")
        self.assertContains(response, "Imprimer")

    def test_planner_view_workspace_has_no_preview_or_publish_buttons(self):
        url = reverse("accounts_portal:supervisor_planner_view_workspace")
        response = self.client.get(url, {"class_id": self.cls.id})
        body = response.content.decode()
        self.assertNotIn("Previsualiser", body)
        self.assertNotIn("Publier", body)

    def test_weekly_slots_workspace_renders_three_action_cards(self):
        url = reverse("accounts_portal:supervisor_weekly_slots_workspace", args=[self.cls.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("Nouveau créneau", body)
        self.assertIn("Générer la semaine", body)
        self.assertIn("Générer le mois", body)

    def test_weekly_slots_workspace_renders_inline_form_is_gone(self):
        url = reverse("accounts_portal:supervisor_weekly_slots_workspace", args=[self.cls.id])
        response = self.client.get(url)
        body = response.content.decode()
        self.assertNotIn('name="action" value="create"', body)
        self.assertNotIn('name="action" value="update"', body)


class SupervisorDrawerFormTests(TestCase):
    """Les formulaires charges en drawer (GET) rendent un partial autonome."""

    def setUp(self):
        self.branch = _create_branch(code="DRW", name="Annexe Drawer")
        self.programme = _create_programme()
        self.year, self.cls, self.ec = _create_class_bundle(self.programme, self.branch, "L2")
        self.teacher = _create_teacher(self.branch)
        self.supervisor = _create_supervisor(self.branch, "sup_drawer")
        self.client.force_login(self.supervisor)

    def test_weekly_slot_form_renders_for_create(self):
        url = reverse("accounts_portal:supervisor_weekly_slot_form", args=[self.cls.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nouveau creneau")
        self.assertContains(response, 'name="weekday"')
        self.assertContains(response, 'name="start_time"')
        self.assertContains(response, 'name="end_time"')
        self.assertContains(response, 'name="ec_id"')
        self.assertContains(response, 'name="teacher_id"')
        self.assertContains(response, 'name="room"')

    def test_weekly_slot_form_renders_for_edit(self):
        slot = WeeklyScheduleSlot.objects.create(
            academic_class=self.cls,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.year,
            weekday=0,
            start_time=time(8, 0),
            end_time=time(10, 0),
            room="A101",
        )
        url = reverse("accounts_portal:supervisor_weekly_slot_form", args=[self.cls.id])
        response = self.client.get(url, {"slot_id": slot.id})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Modifier le creneau")
        self.assertContains(response, 'name="action" value="update"')

    def test_quick_course_form_renders_for_class(self):
        url = reverse("accounts_portal:supervisor_quick_course_create")
        response = self.client.get(url, {"class_id": self.cls.id})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nouveau cours")
        self.assertContains(response, 'name="date"')
        self.assertContains(response, 'name="start_time"')
        self.assertContains(response, 'name="end_time"')
        self.assertContains(response, 'name="ec_id"')
        self.assertContains(response, 'name="teacher_id"')

    def test_quick_course_form_without_class_renders_empty(self):
        url = reverse("accounts_portal:supervisor_quick_course_create")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Aucune classe selectionnee")


class SupervisorMaterializeTests(TestCase):
    """La generation de la semaine a partir des creneaux recurrents fonctionne."""

    def setUp(self):
        self.branch = _create_branch(code="GEN", name="Annexe Generate")
        self.programme = _create_programme()
        self.year, self.cls, self.ec = _create_class_bundle(self.programme, self.branch, "L3")
        self.teacher = _create_teacher(self.branch)
        self.supervisor = _create_supervisor(self.branch, "sup_generate")
        self.client.force_login(self.supervisor)
        WeeklyScheduleSlot.objects.create(
            academic_class=self.cls,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.year,
            weekday=0,
            start_time=time(8, 0),
            end_time=time(10, 0),
            room="A102",
        )

    def test_week_materialize_creates_schedule_event(self):
        url = reverse("accounts_portal:supervisor_week_materialize", args=[self.cls.id])
        today = timezone.localdate()
        week_start = today - timedelta(days=today.weekday())
        response = self.client.post(url, {"week_start": week_start.isoformat()})
        self.assertEqual(response.status_code, 200)
        created = AcademicScheduleEvent.objects.filter(
            academic_class=self.cls,
            branch=self.branch,
            ec=self.ec,
        )
        self.assertGreaterEqual(created.count(), 1)
        self.assertContains(response, "Semaine")

    def test_month_materialize_creates_schedule_events(self):
        url = reverse("accounts_portal:supervisor_month_materialize", args=[self.cls.id])
        today = timezone.localdate()
        week_start = today - timedelta(days=today.weekday())
        response = self.client.post(url, {"week_start": week_start.isoformat()})
        self.assertEqual(response.status_code, 200)
        created = AcademicScheduleEvent.objects.filter(
            academic_class=self.cls,
            branch=self.branch,
        )
        self.assertGreaterEqual(created.count(), 1)


class SupervisorDgRequirementsTests(TestCase):
    def setUp(self):
        self.branch = _create_branch(code="DGR", name="Annexe DG Requirements")
        self.other_branch = _create_branch(code="DGO", name="Annexe DG Other")
        self.supervisor = _create_supervisor(self.branch, "sup_dg_requirements")
        self.teacher = _create_teacher(self.branch, "teacher_dg_requirements")
        self.other_teacher = _create_teacher(self.other_branch, "teacher_other_branch")
        self.director = USER_MANAGER.create_user(
            username="director_dg_requirements",
            email="director_dg_requirements@test.com",
            password="pass1234",
        )
        self.director.profile.position = "director_of_studies"
        self.director.profile.branch = self.branch
        self.director.profile.save(update_fields=["position", "branch", "updated_at"])
        self.client.force_login(self.supervisor)

    def test_teacher_regularity_sheet_is_printable_and_branch_scoped(self):
        response = self.client.get(
            reverse("accounts_portal:supervisor_teacher_regularity_print", args=[self.teacher.id])
        )
        foreign_response = self.client.get(
            reverse("accounts_portal:supervisor_teacher_regularity_print", args=[self.other_teacher.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fiche individuelle de régularité")
        self.assertContains(response, self.teacher.username)
        self.assertEqual(foreign_response.status_code, 404)

    def test_teacher_case_can_be_transmitted_to_branch_director(self):
        case = TeacherCase.objects.create(
            teacher=self.teacher,
            branch=self.branch,
            case_type=TeacherCase.TYPE_INCIDENT,
            title="Incident à transmettre",
            opened_by=self.supervisor,
        )

        response = self.client.post(
            reverse("accounts_portal:supervisor_case_escalate", args=["teacher", case.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(case.notes.filter(content="Cas transmis à la Direction des études.").exists())
        self.assertTrue(
            NotificationMessage.objects.filter(
                recipient=self.director,
                event_type="disciplinary_case_escalated",
                channel=NotificationMessage.CHANNEL_IN_APP,
            ).exists()
        )

    def test_invalid_case_kind_is_rejected(self):
        response = self.client.get(
            reverse("accounts_portal:supervisor_case_detail", args=["invalid", 1])
        )
        self.assertEqual(response.status_code, 400)
