from datetime import date, datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from accounts.models import Profile
from academics.models import AcademicClass, AcademicYear, EC, Semester, UE
from academics.selectors.teacher_assignment_selectors import (
    get_ecs_without_teacher,
    get_expired_teacher_assignments,
    get_teacher_assignment_load,
    get_teacher_assignments_for_class,
    get_teacher_assignments_for_semester,
)
from academics.services.teacher_assignment_service import (
    archive_teacher_assignment,
    create_teacher_assignment,
    suspend_teacher_assignment,
    activate_teacher_assignment,
)
from branches.models import Branch
from formations.models import Cycle, Diploma, Filiere, Programme
from portal.models import DirectorTeacherAssignment


User = get_user_model()


class TeacherAssignmentServiceTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(name="Annexe Affectation", code="AFF", slug="annexe-affectation")
        self.other_branch = Branch.objects.create(name="Annexe Autre Affectation", code="AF2", slug="annexe-autre-affectation")
        cycle = Cycle.objects.create(name="Licence Affectation", theme="accent", min_duration_years=1, max_duration_years=3)
        diploma = Diploma.objects.create(name="Diplome Affectation", level="superieur")
        filiere = Filiere.objects.create(name="Filiere Affectation")
        self.programme = Programme.objects.create(
            title="Programme Affectation",
            filiere=filiere,
            cycle=cycle,
            diploma_awarded=diploma,
            duration_years=3,
            short_description="Affectation",
            description="Affectation",
        )
        self.academic_year = AcademicYear.objects.create(
            name="2043-2044",
            start_date=date(2043, 10, 1),
            end_date=date(2044, 7, 31),
            is_active=True,
        )
        self.academic_class = AcademicClass.objects.create(
            programme=self.programme,
            branch=self.branch,
            academic_year=self.academic_year,
            level="L1",
            study_level="LICENCE",
            validation_threshold=Decimal("10.00"),
            is_active=True,
        )
        self.other_class = AcademicClass.objects.create(
            programme=self.programme,
            branch=self.other_branch,
            academic_year=self.academic_year,
            level="L1",
            study_level="LICENCE",
            validation_threshold=Decimal("10.00"),
            is_active=True,
        )
        self.semester = Semester.objects.create(
            academic_class=self.academic_class,
            number=1,
            total_required_credits=Decimal("3.00"),
        )
        self.other_semester = Semester.objects.create(
            academic_class=self.other_class,
            number=1,
            total_required_credits=Decimal("3.00"),
        )
        self.ue = UE.objects.create(semester=self.semester, code="AF101", title="Fondamentaux")
        self.other_ue = UE.objects.create(semester=self.other_semester, code="AF201", title="Fondamentaux 2")
        self.ec = EC.objects.create(ue=self.ue, title="Python", credit_required=Decimal("3.00"), coefficient=Decimal("2.00"))
        self.other_ec = EC.objects.create(ue=self.other_ue, title="Java", credit_required=Decimal("3.00"), coefficient=Decimal("2.00"))
        self.director = self._user("aff_director", "director_of_studies", self.branch)
        self.other_director = self._user("aff_other_director", "director_of_studies", self.other_branch)
        self.dg = self._user("aff_dg", "executive_director", None)
        self.teacher = self._user("aff_teacher", "teacher", self.branch)
        self.inactive_teacher = self._user("aff_inactive_teacher", "teacher", self.branch, employment_status="inactive")

    def _user(self, username, position, branch, *, employment_status="active"):
        user = User.objects.create_user(username=username, password="pass1234")
        profile, _ = Profile.objects.get_or_create(user=user)
        profile.position = position
        profile.branch = branch
        profile.employment_status = employment_status
        profile.save(update_fields=["position", "branch", "employment_status", "updated_at"])
        user.refresh_from_db()
        return user

    def test_create_class_assignment(self):
        result = create_teacher_assignment(
            actor=self.director,
            teacher=self.teacher,
            branch=self.branch,
            academic_class=self.academic_class,
            room_label="Salle 1",
            planned_hours="12",
            starts_on="2043-10-01",
            ends_on="2044-06-30",
        )

        self.assertTrue(result.created)
        self.assertEqual(result.assignment.scope_type, DirectorTeacherAssignment.SCOPE_CLASS)
        self.assertTrue(result.assignment.is_active)
        self.assertEqual(result.assignment.branch, self.branch)

    def test_create_semester_assignment(self):
        result = create_teacher_assignment(
            actor=self.director,
            teacher=self.teacher,
            branch=self.branch,
            semester=self.semester,
            room_label="Salle 2",
            planned_hours="10",
            starts_on="2043-10-01",
            ends_on="2044-06-30",
        )

        self.assertEqual(result.assignment.scope_type, DirectorTeacherAssignment.SCOPE_SEMESTER)
        self.assertEqual(result.assignment.semester, self.semester)
        self.assertEqual(result.assignment.academic_class, self.academic_class)

    def test_refuses_cross_branch_assignment(self):
        with self.assertRaises(PermissionDenied):
            create_teacher_assignment(
                actor=self.director,
                teacher=self.teacher,
                branch=self.other_branch,
                academic_class=self.other_class,
                room_label="Salle 3",
                planned_hours="10",
            )

    def test_refuses_inactive_teacher(self):
        with self.assertRaises(ValidationError):
            create_teacher_assignment(
                actor=self.director,
                teacher=self.inactive_teacher,
                branch=self.branch,
                academic_class=self.academic_class,
                room_label="Salle 4",
                planned_hours="10",
            )

    def test_refuses_duplicate_or_conflicting_periods(self):
        create_teacher_assignment(
            actor=self.director,
            teacher=self.teacher,
            branch=self.branch,
            academic_class=self.academic_class,
            room_label="Salle 5",
            planned_hours="10",
            starts_on="2043-10-01",
            ends_on="2044-01-31",
        )

        with self.assertRaises(ValidationError):
            create_teacher_assignment(
                actor=self.director,
                teacher=self.teacher,
                branch=self.branch,
                academic_class=self.academic_class,
                room_label="Salle 5",
                planned_hours="10",
                starts_on="2043-12-01",
                ends_on="2044-03-31",
            )

    def test_archive_and_status_transitions(self):
        result = create_teacher_assignment(
            actor=self.director,
            teacher=self.teacher,
            branch=self.branch,
            academic_class=self.academic_class,
            room_label="Salle 6",
            planned_hours="10",
        )
        assignment = result.assignment

        suspend_teacher_assignment(actor=self.director, assignment=assignment, branch=self.branch)
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, DirectorTeacherAssignment.STATUS_SUSPENDED)
        self.assertFalse(assignment.is_active)

        activate_teacher_assignment(actor=self.director, assignment=assignment, branch=self.branch)
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, DirectorTeacherAssignment.STATUS_ACTIVE)
        self.assertTrue(assignment.is_active)

        archive_teacher_assignment(actor=self.director, assignment=assignment, branch=self.branch)
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, DirectorTeacherAssignment.STATUS_ARCHIVED)
        self.assertFalse(assignment.is_active)
        self.assertIsNotNone(assignment.archived_at)

    def test_selectors_cover_assignments_and_load(self):
        class_assignment = create_teacher_assignment(
            actor=self.director,
            teacher=self.teacher,
            branch=self.branch,
            academic_class=self.academic_class,
            room_label="Salle 7",
            planned_hours="8",
            starts_on="2043-10-01",
            ends_on="2044-01-31",
        ).assignment
        semester_assignment = create_teacher_assignment(
            actor=self.director,
            teacher=self.teacher,
            branch=self.branch,
            semester=self.semester,
            room_label="Salle 8",
            planned_hours="6",
            starts_on="2044-02-01",
            ends_on="2044-06-30",
        ).assignment
        expired_assignment = create_teacher_assignment(
            actor=self.director,
            teacher=self.teacher,
            branch=self.branch,
            academic_class=self.academic_class,
            room_label="Salle 9",
            planned_hours="4",
            starts_on="2042-10-01",
            ends_on="2042-12-31",
        ).assignment
        expired_assignment.ends_on = date(2042, 12, 31)
        expired_assignment.save(update_fields=["ends_on", "updated_at"])

        self.assertGreaterEqual(get_teacher_assignment_load(branch=self.branch, teacher=self.teacher).first()["total_hours"], Decimal("14"))
        self.assertTrue(get_teacher_assignments_for_class(self.academic_class).exists())
        self.assertTrue(get_teacher_assignments_for_semester(self.semester).exists())
        self.assertTrue(get_expired_teacher_assignments(branch=self.branch, today=date(2044, 1, 1)).exists())
        self.assertEqual(len(get_ecs_without_teacher(branch=self.branch, academic_class=self.academic_class)), 0)
        self.assertTrue(class_assignment.is_active and semester_assignment.is_active)

    def test_selector_finds_ec_without_teacher(self):
        self.assertEqual([ec.id for ec in get_ecs_without_teacher(branch=self.branch, academic_class=self.academic_class)], [self.ec.id])
