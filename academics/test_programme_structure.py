from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from accounts.models import Profile
from academics.models import AcademicClass, AcademicYear, EC, Semester, UE
from academics.selectors.programme_structure_selectors import (
    get_semester_completeness_state,
    get_total_credits_by_semester,
)
from academics.services.programme_structure_service import (
    archive_ec,
    create_ec,
    create_ue,
    update_ec,
)
from branches.models import Branch
from formations.models import Cycle, Diploma, Filiere, Programme
from portal.models import DirectorTeacherAssignment


User = get_user_model()


class ProgrammeStructureServiceTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(name="Annexe Structure", code="STR", slug="annexe-structure")
        self.other_branch = Branch.objects.create(name="Annexe Autre Structure", code="STO", slug="annexe-autre-structure")
        cycle = Cycle.objects.create(name="Licence Structure", theme="accent", min_duration_years=1, max_duration_years=3)
        diploma = Diploma.objects.create(name="Diplome Structure", level="superieur")
        filiere = Filiere.objects.create(name="Filiere Structure")
        self.programme = Programme.objects.create(
            title="Programme Structure",
            filiere=filiere,
            cycle=cycle,
            diploma_awarded=diploma,
            duration_years=3,
            short_description="Structure",
            description="Structure",
        )
        self.academic_year = AcademicYear.objects.create(
            name="2040-2041",
            start_date=date(2040, 10, 1),
            end_date=date(2041, 7, 31),
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
        self.other_class_same_branch = AcademicClass.objects.create(
            programme=self.programme,
            branch=self.branch,
            academic_year=self.academic_year,
            level="L2",
            study_level="LICENCE",
            validation_threshold=Decimal("10.00"),
            is_active=True,
        )
        self.other_branch_class = AcademicClass.objects.create(
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
        self.other_semester_same_branch = Semester.objects.create(
            academic_class=self.other_class_same_branch,
            number=1,
            total_required_credits=Decimal("3.00"),
        )
        self.other_branch_semester = Semester.objects.create(
            academic_class=self.other_branch_class,
            number=1,
            total_required_credits=Decimal("3.00"),
        )
        self.director = self._user("director_structure", "director_of_studies", self.branch)
        self.other_director = self._user("other_director_structure", "director_of_studies", self.other_branch)
        self.dg = self._user("dg_structure", "executive_director", None)
        self.teacher = self._user("teacher_structure", "teacher", self.branch)

    def _user(self, username, position, branch):
        user = User.objects.create_user(username=username, password="pass1234")
        profile, _ = Profile.objects.get_or_create(user=user)
        profile.position = position
        profile.branch = branch
        profile.save(update_fields=["position", "branch", "updated_at"])
        user.refresh_from_db()
        return user

    def test_create_valid_ue(self):
        ue = create_ue(actor=self.director, semester=self.semester, code="ue101", title="Fondamentaux")

        self.assertEqual(ue.code, "UE101")
        self.assertEqual(ue.semester, self.semester)
        self.assertEqual(ue.structure_status, UE.STRUCTURE_DRAFT)

    def test_create_valid_ec(self):
        ue = create_ue(actor=self.director, semester=self.semester, code="UE102", title="Bases")

        ec = create_ec(
            actor=self.director,
            ue=ue,
            title="Algorithmique",
            credit_required=Decimal("3.00"),
            coefficient=Decimal("2.00"),
        )

        self.assertEqual(ec.ue, ue)
        self.assertEqual(ec.structure_status, EC.STRUCTURE_COMPLETE)
        ue.refresh_from_db()
        self.assertEqual(ue.structure_status, UE.STRUCTURE_COMPLETE)

    def test_reject_ec_moved_to_ue_from_another_class(self):
        ue = create_ue(actor=self.director, semester=self.semester, code="UE103", title="Classe A")
        other_ue = create_ue(actor=self.director, semester=self.other_semester_same_branch, code="UE203", title="Classe B")
        ec = create_ec(actor=self.director, ue=ue, title="Python", credit_required="3", coefficient="2")

        with self.assertRaises(ValidationError):
            update_ec(actor=self.director, ec=ec, ue=other_ue)

    def test_reject_invalid_credit_and_coefficient(self):
        ue = create_ue(actor=self.director, semester=self.semester, code="UE104", title="Validation")

        with self.assertRaises(ValidationError):
            create_ec(actor=self.director, ue=ue, title="Credit invalide", credit_required="0", coefficient="2")
        with self.assertRaises(ValidationError):
            create_ec(actor=self.director, ue=ue, title="Coef invalide", credit_required="2", coefficient="0")

    def test_reject_cross_branch_director_mutation(self):
        with self.assertRaises(PermissionDenied):
            create_ue(actor=self.director, semester=self.other_branch_semester, code="UE-X", title="Hors annexe")

        ue = create_ue(actor=self.dg, semester=self.other_branch_semester, code="UE-DG", title="Global autorise")
        self.assertEqual(ue.semester, self.other_branch_semester)

    def test_refuse_archive_used_ec(self):
        ue = create_ue(actor=self.director, semester=self.semester, code="UE105", title="Affectations")
        ec = create_ec(actor=self.director, ue=ue, title="Base de donnees", credit_required="3", coefficient="2")
        DirectorTeacherAssignment.objects.create(
            branch=self.branch,
            teacher=self.teacher,
            academic_class=self.academic_class,
            ec=ec,
            room_label="Salle A",
            planned_hours=Decimal("12.00"),
            created_by=self.director,
        )

        with self.assertRaises(ValidationError):
            archive_ec(actor=self.director, ec=ec)

    def test_semester_completeness_and_total_credits(self):
        ue = create_ue(actor=self.director, semester=self.semester, code="UE106", title="Completude")
        ec = create_ec(actor=self.director, ue=ue, title="Reseaux", credit_required="3", coefficient="2")
        DirectorTeacherAssignment.objects.create(
            branch=self.branch,
            teacher=self.teacher,
            academic_class=self.academic_class,
            ec=ec,
            room_label="Salle B",
            planned_hours=Decimal("12.00"),
            created_by=self.director,
        )

        self.assertEqual(get_total_credits_by_semester(self.semester), Decimal("3.00"))
        state = get_semester_completeness_state(self.semester)
        self.assertTrue(state["is_complete"])
        self.assertEqual(state["blocking_reasons"], [])

    def test_reject_semester_credit_overflow(self):
        ue = create_ue(actor=self.director, semester=self.semester, code="UE107", title="Overflow")
        create_ec(actor=self.director, ue=ue, title="EC 1", credit_required="2", coefficient="1")

        with self.assertRaises(ValidationError):
            create_ec(actor=self.director, ue=ue, title="EC 2", credit_required="2", coefficient="1")
