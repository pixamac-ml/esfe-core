import hashlib
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from academic_cycle import constants
from academic_cycle.models import BranchAcademicCycle, GradeModificationRequest, StudentYearDecision
from academic_cycle.services.grade_modifications import GradeModificationError, confirm_grade_modification
from accounts.models import SensitiveActionRequest
from academics.models import (
    AcademicClass,
    AcademicDebt,
    AcademicEnrollment,
    AcademicYear,
    EC,
    ECGrade,
    Semester,
    UE,
)
from academics.services.annual_deliberation import (
    build_enrollment_annual_synthesis,
    finalise_class_deliberation,
    get_annual_semesters,
    prepare_class_annual_synthesis,
)
from academics.services.documents import generate_annual_bulletin
from academics.services.reporting import build_student_annual_report
from academics.services.year import DECISION_ADMISSIBLE, DECISION_VALIDE, compute_annual_decision
from branches.models import Branch
from formations.models import Cycle, Diploma, Filiere, Programme
from admissions.models import Candidature
from inscriptions.models import Inscription
from students.models import Student


User = get_user_model()


class AnnualDeliberationWorkflowTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            name="Annexe annuelle", code="ANNUEL", slug="annexe-annuelle"
        )
        cycle = Cycle.objects.create(
            name="Licence annuelle", theme="primary", min_duration_years=1, max_duration_years=3
        )
        diploma = Diploma.objects.create(name="Diplôme annuel", level="superieur")
        filiere = Filiere.objects.create(name="Filière annuelle")
        self.programme = Programme.objects.create(
            title="Programme annuel",
            filiere=filiere,
            cycle=cycle,
            diploma_awarded=diploma,
            duration_years=3,
            short_description="Tests annuels",
            description="Tests annuels",
        )
        self.year = AcademicYear.objects.create(
            name="2041-2042",
            start_date=date(2041, 10, 1),
            end_date=date(2042, 7, 31),
            is_active=True,
        )
        self.director = User.objects.create_user(
            username="director_annual", password="test-password", is_staff=True
        )
        profile = self.director.profile
        profile.position = "director_of_studies"
        profile.role = "executive"
        profile.branch = self.branch
        profile.save(update_fields=["position", "role", "branch", "updated_at"])

    def _build_class(self, *, level="L1", semester_numbers=(1, 2), second_score=Decimal("12.00")):
        academic_class = AcademicClass.objects.create(
            name=f"Classe {level}",
            programme=self.programme,
            branch=self.branch,
            academic_year=self.year,
            level=level,
            study_level="LICENCE",
            validation_threshold=Decimal("10.00"),
            admissibility_gap=Decimal("2.00"),
        )
        semesters = []
        ecs = []
        for index, number in enumerate(semester_numbers, start=1):
            semester = Semester.objects.create(
                academic_class=academic_class,
                number=number,
                total_required_credits=Decimal("3.00"),
            )
            ue = UE.objects.create(semester=semester, code=f"UE{number}", title=f"UE S{number}")
            ec = EC.objects.create(
                ue=ue,
                title=f"EC S{number}",
                coefficient=Decimal("2.00"),
                credit_required=Decimal("3.00"),
            )
            semesters.append(semester)
            ecs.append(ec)

        user = User.objects.create_user(username=f"student_{level}_{semester_numbers[0]}", password="test-password")
        candidature = Candidature.objects.create(
            programme=self.programme,
            branch=self.branch,
            academic_year=self.year.name,
            entry_year=1,
            first_name="Awa",
            last_name=f"{level} Test",
            birth_date=date(2000, 1, 1),
            birth_place="Bamako",
            gender="female",
            phone="70000000",
            email=f"student_{level}_{semester_numbers[0]}@example.test",
            status="accepted",
        )
        inscription = Inscription.objects.create(
            candidature=candidature,
            academic_class=academic_class,
            amount_due=100000,
            status=Inscription.STATUS_ACTIVE,
        )
        Student.objects.create(user=user, inscription=inscription, matricule=f"MAT-{level}-{semester_numbers[0]}")
        enrollment = AcademicEnrollment.objects.create(
            inscription=inscription,
            student=user,
            programme=self.programme,
            branch=self.branch,
            academic_year=self.year,
            academic_class=academic_class,
        )
        ECGrade.objects.create(enrollment=enrollment, ec=ecs[0], normal_score=Decimal("12.00"))
        ECGrade.objects.create(enrollment=enrollment, ec=ecs[1], normal_score=second_score)
        for semester in semesters:
            semester.status = Semester.STATUS_PUBLISHED
            semester.save(update_fields=["status"])
        cycle = BranchAcademicCycle.objects.create(
            branch=self.branch,
            academic_year=self.year,
            status=constants.BRANCH_CYCLE_DELIBERATION,
        )
        return academic_class, enrollment, semesters, ecs, cycle

    def test_l2_s3_s4_uses_the_configured_pair_not_s1_s2(self):
        academic_class, enrollment, semesters, _ecs, _cycle = self._build_class(
            level="L2", semester_numbers=(3, 4)
        )

        self.assertEqual([semester.number for semester in get_annual_semesters(academic_class)], [3, 4])
        self.assertEqual(compute_annual_decision(enrollment)["decision"], DECISION_VALIDE)

        prepared = prepare_class_annual_synthesis(academic_class=academic_class, actor=self.director)
        snapshot = prepared["prepared"][0].synthesis_snapshot
        self.assertEqual([item["number"] for item in snapshot["semesters"]], [3, 4])

    def test_l3_s5_s6_uses_the_configured_pair_not_previous_levels(self):
        academic_class, enrollment, _semesters, _ecs, _cycle = self._build_class(
            level="L3", semester_numbers=(5, 6)
        )

        self.assertEqual([semester.number for semester in get_annual_semesters(academic_class)], [5, 6])
        self.assertEqual(compute_annual_decision(enrollment)["decision"], DECISION_VALIDE)

        prepared = prepare_class_annual_synthesis(academic_class=academic_class, actor=self.director)
        self.assertEqual(
            [item["number"] for item in prepared["prepared"][0].synthesis_snapshot["semesters"]],
            [5, 6],
        )

    def test_synthesis_refuses_an_incompatible_three_semester_configuration(self):
        academic_class, _enrollment, _semesters, _ecs, _cycle = self._build_class()
        Semester.objects.create(
            academic_class=academic_class,
            number=3,
            total_required_credits=Decimal("3.00"),
            status=Semester.STATUS_PUBLISHED,
        )

        with self.assertRaisesMessage(ValidationError, "exactement deux semestres"):
            prepare_class_annual_synthesis(academic_class=academic_class, actor=self.director)

    def test_finalisation_requires_preparation_and_is_idempotent(self):
        academic_class, enrollment, _semesters, _ecs, cycle = self._build_class()

        with self.assertRaisesMessage(ValidationError, "Préparez et contrôlez"):
            finalise_class_deliberation(
                academic_class=academic_class, actor=self.director, branch_cycle=cycle
            )

        prepared = prepare_class_annual_synthesis(academic_class=academic_class, actor=self.director)
        decision = prepared["prepared"][0]
        self.assertFalse(decision.is_final)
        self.assertEqual(decision.source_enrollment, enrollment)

        finalised = finalise_class_deliberation(
            academic_class=academic_class, actor=self.director, branch_cycle=cycle
        )
        self.assertFalse(finalised["idempotent"])
        decision.refresh_from_db()
        self.assertTrue(decision.is_final)
        self.assertEqual(decision.decision, constants.DECISION_PROMOTED)

        second_call = finalise_class_deliberation(
            academic_class=academic_class, actor=self.director, branch_cycle=cycle
        )
        self.assertTrue(second_call["idempotent"])
        self.assertEqual(
            StudentYearDecision.objects.filter(student=decision.student, academic_year=self.year).count(), 1
        )

    def test_preparation_does_not_overwrite_another_class_decision_for_the_same_year(self):
        academic_class, enrollment, _semesters, _ecs, _cycle = self._build_class()
        other_class = AcademicClass.objects.create(
            name="Autre classe annuelle",
            programme=self.programme,
            branch=self.branch,
            academic_year=self.year,
            level="L1-B",
            study_level="LICENCE",
        )
        existing = StudentYearDecision.objects.create(
            student=enrollment.student.student_profile,
            academic_year=self.year,
            branch=self.branch,
            current_class=other_class,
            decision=constants.DECISION_REPEATED,
        )

        with self.assertRaisesMessage(ValidationError, "autre décision annuelle existe"):
            prepare_class_annual_synthesis(academic_class=academic_class, actor=self.director)

        existing.refresh_from_db()
        self.assertEqual(existing.current_class_id, other_class.id)

    def test_pav_debts_are_created_only_when_collective_decision_is_final(self):
        academic_class, enrollment, _semesters, _ecs, cycle = self._build_class(
            second_score=Decimal("9.50")
        )

        prepared = prepare_class_annual_synthesis(academic_class=academic_class, actor=self.director)
        decision = prepared["prepared"][0]
        self.assertEqual(decision.synthesis_snapshot["academic_decision"], DECISION_ADMISSIBLE)
        self.assertFalse(AcademicDebt.objects.filter(enrollment=enrollment).exists())

        finalise_class_deliberation(
            academic_class=academic_class, actor=self.director, branch_cycle=cycle
        )
        self.assertEqual(
            AcademicDebt.objects.filter(enrollment=enrollment, status=AcademicDebt.STATUS_PENDING).count(),
            1,
        )

    def test_annual_bulletin_requires_the_official_deliberation(self):
        academic_class, enrollment, _semesters, _ecs, cycle = self._build_class()

        with self.assertRaisesMessage(ValidationError, "délibération annuelle validée"):
            generate_annual_bulletin(enrollment=enrollment, actor=self.director, publish=False)

        prepare_class_annual_synthesis(academic_class=academic_class, actor=self.director)
        finalise_class_deliberation(
            academic_class=academic_class, actor=self.director, branch_cycle=cycle
        )
        bulletin = generate_annual_bulletin(enrollment=enrollment, actor=self.director, publish=False)

        self.assertEqual(bulletin.decision, DECISION_VALIDE)
        self.assertEqual([item["number"] for item in bulletin.snapshot["semesters"]], [1, 2])

    def test_finalisation_refuses_a_proposal_made_stale_by_a_grade_correction(self):
        academic_class, enrollment, _semesters, ecs, cycle = self._build_class()
        prepare_class_annual_synthesis(academic_class=academic_class, actor=self.director)

        # A post-lock correction is possible only through the authorised OTP
        # path in production.  This direct update models its resulting data
        # change and proves that the previously reviewed proposal is rejected.
        ECGrade.objects.filter(enrollment=enrollment, ec=ecs[1]).update(
            normal_score=Decimal("8.00"),
            final_score=Decimal("8.00"),
            note=Decimal("8.00"),
        )

        with self.assertRaisesMessage(ValidationError, "notes ont changé"):
            finalise_class_deliberation(
                academic_class=academic_class, actor=self.director, branch_cycle=cycle
            )
        self.assertFalse(StudentYearDecision.objects.get(student__user=enrollment.student).is_final)

    def test_historical_annual_report_uses_final_snapshot_not_current_grade_state(self):
        academic_class, enrollment, _semesters, ecs, cycle = self._build_class()
        prepare_class_annual_synthesis(academic_class=academic_class, actor=self.director)
        finalise_class_deliberation(
            academic_class=academic_class, actor=self.director, branch_cycle=cycle
        )

        enrollment.status = AcademicEnrollment.STATUS_COMPLETED
        enrollment.save(update_fields=["status"])
        ECGrade.objects.filter(enrollment=enrollment, ec=ecs[0]).update(
            normal_score=Decimal("1.00"),
            final_score=Decimal("1.00"),
            note=Decimal("1.00"),
        )

        report = build_student_annual_report(
            enrollment.student.student_profile.id,
            academic_year_id=self.year.id,
        )
        self.assertEqual(report["academic_class"], academic_class)
        self.assertEqual(report["decision"], DECISION_VALIDE)
        self.assertEqual(report["semesters"][0]["average"], "12,00")

    def test_pending_semester_publication_otp_is_reused_on_repeat_submission(self):
        _academic_class, _enrollment, semesters, _ecs, _cycle = self._build_class()
        semester = semesters[0]
        semester.status = Semester.STATUS_FINALIZED
        semester.save(update_fields=["status"])

        executive = User.objects.create_user(
            username="executive_annual", password="test-password", is_staff=True
        )
        profile = executive.profile
        profile.position = "executive_director"
        profile.role = "executive"
        profile.branch = self.branch
        profile.save(update_fields=["position", "role", "branch", "updated_at"])

        self.client.force_login(self.director)
        url = reverse("accounts_portal:director_results_action")
        first_response = self.client.post(url, {"action": "publish", "semester_id": semester.id})
        second_response = self.client.post(url, {"action": "publish", "semester_id": semester.id})

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(
            SensitiveActionRequest.objects.filter(
                branch=self.branch,
                action_type=SensitiveActionRequest.ACTION_SEMESTER_PUBLISH,
                target_model="Semester",
                target_id=semester.id,
                status=SensitiveActionRequest.STATUS_PENDING,
            ).count(),
            1,
        )

    def test_requester_cannot_approve_own_grade_correction(self):
        _academic_class, _enrollment, _semesters, ecs, _cycle = self._build_class()
        grade = ECGrade.objects.get(ec=ecs[0])
        request_obj = GradeModificationRequest.objects.create(
            branch=self.branch,
            ec_grade=grade,
            session_type=GradeModificationRequest.SESSION_NORMAL,
            previous_score=grade.normal_score,
            requested_score=Decimal("15.00"),
            requested_by=self.director,
            otp_code_hash=hashlib.sha256(b"123456").hexdigest(),
            expires_at=timezone.now() + timezone.timedelta(minutes=5),
        )

        with self.assertRaisesMessage(GradeModificationError, "ne peut pas approuver sa propre"):
            confirm_grade_modification(
                request_id=request_obj.id,
                code="123456",
                approver=self.director,
                apply_callback=lambda _request: self.fail("La correction ne doit pas etre appliquee."),
            )

        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, GradeModificationRequest.STATUS_PENDING)
        grade.refresh_from_db()
        self.assertEqual(grade.normal_score, Decimal("12.00"))

    def test_prepared_annual_synthesis_reuses_prefetched_grades(self):
        academic_class, enrollment, _semesters, _ecs, _cycle = self._build_class()
        configured_semesters = get_annual_semesters(academic_class)
        grades_by_ec_id = {
            grade.ec_id: grade
            for grade in ECGrade.objects.filter(enrollment=enrollment).select_related("ec")
        }

        with CaptureQueriesContext(connection) as queries:
            synthesis = build_enrollment_annual_synthesis(
                enrollment,
                semesters=configured_semesters,
                grades_by_ec_id=grades_by_ec_id,
            )

        self.assertEqual(synthesis["academic_decision"], DECISION_VALIDE)
        self.assertFalse(
            any("academics_ecgrade" in query["sql"].lower() for query in queries.captured_queries),
            "La synthese preparee ne doit pas refaire une requete de notes par UE.",
        )
