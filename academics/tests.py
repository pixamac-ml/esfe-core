from datetime import date, datetime, time, timedelta
from decimal import Decimal
from io import BytesIO
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from academic_cycle import constants as academic_cycle_constants
from academic_cycle.models import BranchAcademicCycle
from academics.models import (
    AcademicClass,
    AcademicBulletin,
    AcademicDebt,
    AcademicEnrollment,
    AcademicScheduleChangeLog,
    AcademicScheduleEvent,
    AcademicYear,
    EC,
    ECGrade,
    LessonLog,
    Semester,
    UE,
    WeeklyScheduleSlot,
)
from academics.services.grading import calculate_ec_grade
from academics.imports.import_service import import_grades
from academics.imports.template_service import generate_notes_workbook
from academics.services.documents import (
    build_bulletin_context,
    generate_annual_bulletin,
    generate_semester_bulletin,
)
from academics.services.annual_deliberation import (
    finalise_class_deliberation,
    prepare_class_annual_synthesis,
)
from academics.services.semester import compute_semester_result
from academics.services.ue import compute_ue_result
from academics.services.year import compute_annual_decision, compute_annual_result
from portal.services.notes_workflow import (
    ACTION_PUBLISH_NORMAL,
    get_retake_candidates,
    get_notes_state,
)
from academics.services.lesson_log_service import (
    create_lesson_log,
    get_class_lesson_logs,
    get_daily_lesson_status,
    get_teacher_lesson_logs,
    update_lesson_log,
)
from academics.services.academic_context_resolver import resolve_academic_context
from academics.services.schedule_service import (
    cancel_schedule_event,
    complete_schedule_event,
    create_schedule_event,
    get_branch_activity_summary,
    get_schedule_alerts,
    get_schedule_conflicts,
    get_schedule_quality_score,
    get_student_week_schedule,
    get_teacher_next_events,
    get_weekly_schedule_stats,
    postpone_schedule_event,
    suggest_available_slots,
)
from accounts.models import TeacherHonorariumEntry
from admissions.models import Candidature
from branches.models import Branch
from formations.models import Cycle, Diploma, Filiere, Programme
from inscriptions.models import Inscription
from notifier.models import NotificationMessage
from portal.student.widgets.academics import get_academics_widget
from students.models import Student, TeacherAttendance


User = get_user_model()


class AcademicResultCalculationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="result_student", password="pass1234")
        self.branch = Branch.objects.create(name="Annexe Resultats", code="RES", slug="annexe-resultats")
        cycle = Cycle.objects.create(name="Licence Resultats", theme="accent", min_duration_years=1, max_duration_years=3)
        diploma = Diploma.objects.create(name="Diplome Resultats", level="superieur")
        filiere = Filiere.objects.create(name="Filiere Resultats")
        self.programme = Programme.objects.create(
            title="Programme Resultats",
            filiere=filiere,
            cycle=cycle,
            diploma_awarded=diploma,
            duration_years=3,
            short_description="Resultats",
            description="Resultats",
        )
        self.academic_year = AcademicYear.objects.create(
            name="2035-2036",
            start_date=date(2035, 10, 1),
            end_date=date(2036, 7, 31),
            is_active=True,
        )
        self.academic_class = AcademicClass.objects.create(
            programme=self.programme,
            branch=self.branch,
            academic_year=self.academic_year,
            level="L1",
            study_level="LICENCE",
            validation_threshold=Decimal("10.00"),
            admissibility_gap=Decimal("0.50"),
            is_active=True,
        )
        self.semester = Semester.objects.create(
            academic_class=self.academic_class,
            number=1,
            total_required_credits=Decimal("6.00"),
        )
        ue = UE.objects.create(semester=self.semester, code="RES101", title="Calcul")
        self.ec_one = EC.objects.create(ue=ue, title="Matiere A", credit_required=Decimal("3.00"), coefficient=Decimal("2.00"))
        self.ec_two = EC.objects.create(ue=ue, title="Matiere B", credit_required=Decimal("3.00"), coefficient=Decimal("2.00"))
        candidature = Candidature.objects.create(
            programme=self.programme,
            branch=self.branch,
            academic_year=self.academic_year.name,
            entry_year=1,
            first_name="Awa",
            last_name="Resultat",
            birth_date=date(2001, 1, 1),
            birth_place="Bamako",
            gender="female",
            phone="71000000",
            email="awa.resultat@example.com",
            status="accepted",
        )
        inscription = Inscription.objects.create(
            candidature=candidature,
            academic_class=self.academic_class,
            amount_due=100000,
            status=Inscription.STATUS_ACTIVE,
        )
        Student.objects.create(user=self.user, inscription=inscription, matricule="MAT-RES-001", is_active=True)
        self.enrollment = AcademicEnrollment.objects.create(
            inscription=inscription,
            student=self.user,
            programme=self.programme,
            branch=self.branch,
            academic_year=self.academic_year,
            academic_class=self.academic_class,
        )

        self.it_user = User.objects.create_user(username="it_notes", password="pass1234", is_staff=True)
        self.it_user.profile.position = "it_support"
        self.it_user.profile.role = "staff"
        self.it_user.profile.branch = self.branch
        self.it_user.profile.save(update_fields=["position", "role", "branch", "updated_at"])

    def _official_workbook(self, *, session_type, scores_by_cell):
        output = generate_notes_workbook(
            self.academic_class,
            self.semester,
            session_type=session_type,
            scores_by_cell=scores_by_cell,
        )
        return SimpleUploadedFile(
            f"notes-{session_type}.xlsx",
            output.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def test_ec_below_threshold_gets_no_credit(self):
        result = calculate_ec_grade(
            note=Decimal("8.00"),
            coefficient=Decimal("3.00"),
            credit_required=Decimal("3.00"),
            threshold=Decimal("10.00"),
        )

        self.assertEqual(result["credit_obtained"], Decimal("0.00"))
        self.assertFalse(result["is_validated"])

    def test_semester_result_blocks_average_when_grade_missing(self):
        ECGrade.objects.create(enrollment=self.enrollment, ec=self.ec_one, normal_score=Decimal("14.00"))

        result = compute_semester_result(self.semester, self.enrollment)

        self.assertIsNone(result["average"])
        self.assertFalse(result["is_complete"])
        self.assertEqual(result["missing_grades"], 1)
        self.assertEqual(result["status"], "incomplete")

    def test_ue_shows_weighted_provisional_average_when_grade_missing(self):
        ECGrade.objects.create(enrollment=self.enrollment, ec=self.ec_one, normal_score=Decimal("14.00"))

        result = compute_ue_result(self.ec_one.ue, self.enrollment)

        self.assertEqual(result["average"], Decimal("14.00"))
        self.assertEqual(result["entered_coefficients"], Decimal("2.00"))
        self.assertEqual(result["missing_grades"], 1)
        self.assertTrue(result["is_provisional"])
        self.assertFalse(result["is_validated"])

    def test_semester_requires_all_credits_not_only_average(self):
        ECGrade.objects.create(enrollment=self.enrollment, ec=self.ec_one, normal_score=Decimal("20.00"))
        ECGrade.objects.create(enrollment=self.enrollment, ec=self.ec_two, normal_score=Decimal("8.00"))

        result = compute_semester_result(self.semester, self.enrollment)

        self.assertEqual(result["average"], Decimal("14.00"))
        self.assertEqual(result["credit_obtained"], Decimal("3.00"))
        self.assertFalse(result["is_validated"])
        self.assertEqual(result["status"], "failed")

    def test_retake_uses_best_score_and_restores_credit(self):
        ECGrade.objects.create(enrollment=self.enrollment, ec=self.ec_one, normal_score=Decimal("20.00"))
        ECGrade.objects.create(
            enrollment=self.enrollment,
            ec=self.ec_two,
            normal_score=Decimal("8.00"),
            retake_score=Decimal("12.00"),
        )

        result = compute_semester_result(self.semester, self.enrollment)

        self.assertEqual(result["credit_obtained"], Decimal("6.00"))
        self.assertTrue(result["is_validated"])

    def test_retake_requires_a_normal_score(self):
        self.semester.status = Semester.STATUS_RETAKE_ENTRY
        self.semester.save(update_fields=["status"])

        with self.assertRaises(ValidationError):
            ECGrade.objects.create(
                enrollment=self.enrollment,
                ec=self.ec_one,
                retake_score=Decimal("12.00"),
            )

    def test_model_rejects_an_out_of_range_source_score(self):
        with self.assertRaises(ValidationError):
            ECGrade.objects.create(
                enrollment=self.enrollment,
                ec=self.ec_one,
                normal_score=Decimal("20.01"),
            )

    def test_import_normal_then_retake_preserves_normal_score_and_opens_retake_modal(self):
        self.semester.status = Semester.STATUS_NORMAL_ENTRY
        self.semester.save(update_fields=["status"])
        normal_file = self._official_workbook(
            session_type="normal",
            scores_by_cell={
                (self.enrollment.id, self.ec_one.id): "14.00",
                (self.enrollment.id, self.ec_two.id): "8.00",
            },
        )
        normal_result = import_grades(
            normal_file,
            academic_class=self.academic_class,
            semester=self.semester,
            session_type="normal",
        )
        self.assertEqual(normal_result.updated, 2)

        from portal.services.notes_workflow import apply_notes_workflow_action

        apply_notes_workflow_action(
            actor=self.it_user,
            academic_class=self.academic_class,
            semester=self.semester,
            action=ACTION_PUBLISH_NORMAL,
        )
        self.semester.refresh_from_db()
        self.assertEqual(self.semester.status, Semester.STATUS_NORMAL_LOCKED)
        self.assertTrue(get_notes_state(academic_class=self.academic_class, semester=self.semester).retake_ready)

        self.client.force_login(self.it_user)
        modal_response = self.client.get(
            reverse("accounts_portal:it_notes_retake_modal"),
            {"class_id": self.academic_class.id, "semester_id": self.semester.id},
        )
        self.assertEqual(modal_response.status_code, 200)
        self.assertContains(modal_response, "Verification avant activation")

        activate_response = self.client.post(
            reverse("accounts_portal:it_notes_workflow_action"),
            {
                "class_id": self.academic_class.id,
                "semester_id": self.semester.id,
                "action": "activer_rattrapage",
                "from_modal": "retake",
            },
        )
        self.assertEqual(activate_response.status_code, 200)
        self.semester.refresh_from_db()
        self.assertEqual(self.semester.status, Semester.STATUS_RETAKE_ENTRY)

        retake_file = self._official_workbook(
            session_type="retake",
            scores_by_cell={(self.enrollment.id, self.ec_two.id): "12.00"},
        )
        retake_result = import_grades(
            retake_file,
            academic_class=self.academic_class,
            semester=self.semester,
            session_type="retake",
        )
        self.assertEqual(retake_result.updated, 1)
        grade = ECGrade.objects.get(enrollment=self.enrollment, ec=self.ec_two)
        self.assertEqual(grade.normal_score, Decimal("8.00"))
        self.assertEqual(grade.retake_score, Decimal("12.00"))
        self.assertEqual(grade.final_score, Decimal("12.00"))
        self.assertTrue(compute_semester_result(self.semester, self.enrollment)["is_validated"])
        self.assertEqual(
            get_retake_candidates(academic_class=self.academic_class, semester=self.semester),
            [],
        )

    def test_import_retake_rejects_a_previously_passing_ec(self):
        # Defensive case for legacy data: an old retake value must never make
        # an EC that passed normally eligible for a new retake import.
        ECGrade.objects.create(
            enrollment=self.enrollment,
            ec=self.ec_one,
            normal_score=Decimal("14.00"),
            retake_score=Decimal("12.00"),
        )
        self.semester.status = Semester.STATUS_RETAKE_ENTRY
        self.semester.save(update_fields=["status"])

        result = import_grades(
            self._official_workbook(
                session_type="retake",
                scores_by_cell={(self.enrollment.id, self.ec_one.id): "10.00"},
            ),
            academic_class=self.academic_class,
            semester=self.semester,
            session_type="retake",
        )

        self.assertEqual(result.updated, 0)
        self.assertEqual(result.skipped_invalid_scores, 1)
        self.assertEqual(result.student_issues[0]["reason"], "retake_not_allowed")
        grade = ECGrade.objects.get(enrollment=self.enrollment, ec=self.ec_one)
        self.assertEqual(grade.normal_score, Decimal("14.00"))
        self.assertEqual(grade.retake_score, Decimal("12.00"))

    def test_annual_result_reports_incomplete_until_all_semesters_ready(self):
        result = compute_annual_result(self.enrollment)

        self.assertFalse(result["is_complete"])
        self.assertEqual(result["status"], "incomplete")
        self.assertGreater(result["missing_grades"], 0)

    def test_annual_decision_promotes_with_debt_when_one_semester_is_close_to_threshold(self):
        second_semester = Semester.objects.create(
            academic_class=self.academic_class,
            number=2,
            total_required_credits=Decimal("6.00"),
        )
        ue = UE.objects.create(semester=second_semester, code="RES201", title="Compensation")
        ec_three = EC.objects.create(ue=ue, title="Matiere C", credit_required=Decimal("3.00"), coefficient=Decimal("3.00"))
        ec_four = EC.objects.create(ue=ue, title="Matiere D", credit_required=Decimal("3.00"), coefficient=Decimal("3.00"))
        ECGrade.objects.create(enrollment=self.enrollment, ec=self.ec_one, normal_score=Decimal("10.00"))
        ECGrade.objects.create(enrollment=self.enrollment, ec=self.ec_two, normal_score=Decimal("10.00"))
        ECGrade.objects.create(enrollment=self.enrollment, ec=ec_three, normal_score=Decimal("9.50"))
        ECGrade.objects.create(enrollment=self.enrollment, ec=ec_four, normal_score=Decimal("9.50"))

        decision = compute_annual_decision(self.enrollment)

        self.assertEqual(decision["decision"], "ADMISSIBLE")
        self.assertEqual(decision["rule_code"], "admissible_gap")
        self.assertTrue(decision["requires_academic_debt"])
        self.assertEqual(len(decision["debt_subjects"]), 2)
        self.assertFalse(AcademicDebt.objects.filter(enrollment=self.enrollment).exists())

    def test_import_is_rejected_outside_the_active_grade_session(self):
        self.semester.status = Semester.STATUS_PUBLISHED
        self.semester.save(update_fields=["status"])

        with self.assertRaises(ValidationError):
            import_grades(
                BytesIO(b"not-read-because-session-is-locked"),
                academic_class=self.academic_class,
                semester=self.semester,
            )

    def test_published_grade_is_locked(self):
        grade = ECGrade.objects.create(
            enrollment=self.enrollment,
            ec=self.ec_one,
            normal_score=Decimal("14.00"),
        )
        self.semester.status = Semester.STATUS_PUBLISHED
        self.semester.save(update_fields=["status"])

        grade.normal_score = Decimal("5.00")
        with self.assertRaises(ValidationError):
            grade.save()

    def test_annual_bulletin_requires_both_semesters(self):
        ECGrade.objects.create(enrollment=self.enrollment, ec=self.ec_one, normal_score=Decimal("14.00"))
        ECGrade.objects.create(enrollment=self.enrollment, ec=self.ec_two, normal_score=Decimal("12.00"))
        self.semester.status = Semester.STATUS_PUBLISHED
        self.semester.save(update_fields=["status"])

        with self.assertRaisesMessage(ValidationError, "exactement deux semestres"):
            generate_annual_bulletin(enrollment=self.enrollment, publish=True)

    @override_settings(
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.memory.InMemoryStorage"},
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
        }
    )
    def test_published_bulletin_keeps_snapshot_and_pdf_immutable(self):
        ECGrade.objects.create(enrollment=self.enrollment, ec=self.ec_one, normal_score=Decimal("14.00"))
        ECGrade.objects.create(enrollment=self.enrollment, ec=self.ec_two, normal_score=Decimal("10.00"))
        self.semester.status = Semester.STATUS_PUBLISHED
        self.semester.save(update_fields=["status"])

        bulletin = generate_semester_bulletin(
            enrollment=self.enrollment,
            semester=self.semester,
            publish=True,
        )

        self.assertEqual(bulletin.status, AcademicBulletin.STATUS_PUBLISHED)
        self.assertEqual(bulletin.snapshot["version"], 2)
        self.assertTrue(bulletin.pdf_file.name)
        with bulletin.pdf_file.open("rb") as pdf_file:
            self.assertTrue(pdf_file.read(4).startswith(b"%PDF"))

        ECGrade.objects.filter(enrollment=self.enrollment, ec=self.ec_one).update(
            normal_score=Decimal("1.00"),
            final_score=Decimal("1.00"),
            note=Decimal("1.00"),
        )
        context = build_bulletin_context(bulletin)
        self.assertEqual(context["semester_result"]["average"], Decimal("12.00"))

        bulletin.decision = "ALTERE"
        with self.assertRaisesMessage(ValidationError, "definitif"):
            bulletin.save()

    def test_student_widget_hides_grades_until_publication(self):
        ECGrade.objects.create(enrollment=self.enrollment, ec=self.ec_one, normal_score=Decimal("14.00"))

        hidden_widget = get_academics_widget(self.user)
        self.assertEqual(hidden_widget["average"], "Non disponible")

        self.semester.status = Semester.STATUS_PUBLISHED
        self.semester.save(update_fields=["status"])
        published_widget = get_academics_widget(self.user)
        self.assertEqual(published_widget["average"], "14.00/20")

    def test_generated_bulletin_is_not_exposed_as_official(self):
        ECGrade.objects.create(enrollment=self.enrollment, ec=self.ec_one, normal_score=Decimal("14.00"))
        ECGrade.objects.create(enrollment=self.enrollment, ec=self.ec_two, normal_score=Decimal("10.00"))
        self.semester.status = Semester.STATUS_PUBLISHED
        self.semester.save(update_fields=["status"])
        bulletin = generate_semester_bulletin(
            enrollment=self.enrollment,
            semester=self.semester,
            publish=False,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("academics:bulletin_detail", args=[bulletin.pk]))

        self.assertEqual(response.status_code, 404)

    @override_settings(
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.memory.InMemoryStorage"},
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
        }
    )
    def test_annual_publication_creates_debts_and_persists_pdf(self):
        second_semester = Semester.objects.create(
            academic_class=self.academic_class,
            number=2,
            total_required_credits=Decimal("6.00"),
        )
        second_ue = UE.objects.create(semester=second_semester, code="RES203", title="Dette")
        ec_three = EC.objects.create(
            ue=second_ue,
            title="Matiere C",
            credit_required=Decimal("3.00"),
            coefficient=Decimal("3.00"),
        )
        ec_four = EC.objects.create(
            ue=second_ue,
            title="Matiere D",
            credit_required=Decimal("3.00"),
            coefficient=Decimal("3.00"),
        )
        ECGrade.objects.create(enrollment=self.enrollment, ec=self.ec_one, normal_score=Decimal("10.00"))
        ECGrade.objects.create(enrollment=self.enrollment, ec=self.ec_two, normal_score=Decimal("10.00"))
        ECGrade.objects.create(enrollment=self.enrollment, ec=ec_three, normal_score=Decimal("9.50"))
        ECGrade.objects.create(enrollment=self.enrollment, ec=ec_four, normal_score=Decimal("9.50"))
        self.semester.status = Semester.STATUS_PUBLISHED
        self.semester.save(update_fields=["status"])
        second_semester.status = Semester.STATUS_PUBLISHED
        second_semester.save(update_fields=["status"])

        cycle = BranchAcademicCycle.objects.create(
            branch=self.branch,
            academic_year=self.academic_year,
            status=academic_cycle_constants.BRANCH_CYCLE_DELIBERATION,
        )
        prepare_class_annual_synthesis(academic_class=self.academic_class, actor=None)
        finalise_class_deliberation(
            academic_class=self.academic_class,
            actor=None,
            branch_cycle=cycle,
        )

        bulletin = generate_annual_bulletin(enrollment=self.enrollment, publish=True)

        self.assertEqual(bulletin.decision, "ADMISSIBLE")
        self.assertTrue(bulletin.pdf_file.name)
        self.assertEqual(
            AcademicDebt.objects.filter(
                enrollment=self.enrollment,
                status=AcademicDebt.STATUS_PENDING,
            ).count(),
            2,
        )

    def test_annual_decision_repeats_when_semester_gap_is_too_large(self):
        second_semester = Semester.objects.create(
            academic_class=self.academic_class,
            number=2,
            total_required_credits=Decimal("6.00"),
        )
        ue = UE.objects.create(semester=second_semester, code="RES202", title="Gap")
        ec_three = EC.objects.create(ue=ue, title="Matiere C", credit_required=Decimal("3.00"), coefficient=Decimal("3.00"))
        ec_four = EC.objects.create(ue=ue, title="Matiere D", credit_required=Decimal("3.00"), coefficient=Decimal("3.00"))
        ECGrade.objects.create(enrollment=self.enrollment, ec=self.ec_one, normal_score=Decimal("10.00"))
        ECGrade.objects.create(enrollment=self.enrollment, ec=self.ec_two, normal_score=Decimal("10.00"))
        ECGrade.objects.create(enrollment=self.enrollment, ec=ec_three, normal_score=Decimal("9.40"))
        ECGrade.objects.create(enrollment=self.enrollment, ec=ec_four, normal_score=Decimal("9.40"))

        decision = compute_annual_decision(self.enrollment)

        self.assertEqual(decision["decision"], "NON_ADMIS")
        self.assertEqual(decision["rule_code"], "gap_too_large")


class AcademicContextResolverTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(name="ESFE Resolver", code="RSV", slug="esfe-resolver")
        self.licence_cycle = Cycle.objects.create(
            name="Licence Resolver",
            min_duration_years=3,
            max_duration_years=3,
        )
        self.master_cycle = Cycle.objects.create(
            name="Master Resolver",
            min_duration_years=2,
            max_duration_years=2,
        )
        self.diploma = Diploma.objects.create(name="Diplome Resolver", level="superieur")
        self.filiere = Filiere.objects.create(name="Filiere Resolver")
        self.licence_programme = Programme.objects.create(
            title="Programme Licence Resolver",
            filiere=self.filiere,
            cycle=self.licence_cycle,
            diploma_awarded=self.diploma,
            duration_years=3,
            short_description="Licence",
            description="Licence",
        )
        self.master_programme = Programme.objects.create(
            title="Programme Master Resolver",
            filiere=self.filiere,
            cycle=self.master_cycle,
            diploma_awarded=self.diploma,
            duration_years=2,
            short_description="Master",
            description="Master",
        )
        self.academic_year = AcademicYear.objects.create(
            name="2030-2031",
            start_date=date(2030, 10, 1),
            end_date=date(2031, 7, 31),
            is_active=True,
        )

    def test_resolve_academic_context_uses_cycle_specific_master_mapping(self):
        academic_class = AcademicClass.objects.create(
            programme=self.master_programme,
            branch=self.branch,
            academic_year=self.academic_year,
            level="M1",
            study_level="MASTER",
            is_active=True,
        )
        candidature = Candidature.objects.create(
            programme=self.master_programme,
            branch=self.branch,
            academic_year="2030-2031",
            entry_year=1,
            first_name="Aminata",
            last_name="Resolver",
            birth_date=date(2000, 1, 1),
            birth_place="Bamako",
            gender="female",
            phone="70030000",
            email="aminata.resolver@example.com",
            status="accepted",
        )

        result = resolve_academic_context(candidature=candidature)

        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["resolved_level"], "M1")
        self.assertEqual(result["academic_class"], academic_class)

    def test_resolve_academic_context_normalizes_legacy_year_format(self):
        academic_class = AcademicClass.objects.create(
            programme=self.licence_programme,
            branch=self.branch,
            academic_year=self.academic_year,
            level="L1",
            study_level="LICENCE",
            is_active=True,
        )
        candidature = Candidature.objects.create(
            programme=self.licence_programme,
            branch=self.branch,
            academic_year="2030 / 2031",
            entry_year=1,
            first_name="Moussa",
            last_name="Normalizer",
            birth_date=date(2001, 1, 1),
            birth_place="Kayes",
            gender="male",
            phone="70030001",
            email="moussa.normalizer@example.com",
            status="accepted",
        )

        result = resolve_academic_context(candidature=candidature)

        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["academic_year"], self.academic_year)
        self.assertEqual(result["academic_class"], academic_class)

    def test_resolve_academic_context_returns_missing_class_status(self):
        candidature = Candidature.objects.create(
            programme=self.licence_programme,
            branch=self.branch,
            academic_year="2030-2031",
            entry_year=1,
            first_name="Fatou",
            last_name="MissingClass",
            birth_date=date(2001, 2, 1),
            birth_place="Sikasso",
            gender="female",
            phone="70030002",
            email="fatou.missing@example.com",
            status="accepted",
        )

        result = resolve_academic_context(candidature=candidature)

        self.assertEqual(result["status"], "manual_required_missing_class")
        self.assertEqual(result["reason"], "academic_class_not_found")
        self.assertEqual(result["resolved_level"], "L1")

    def test_resolve_academic_context_returns_ambiguous_level_when_master_entry_year_invalid(self):
        candidature = Candidature.objects.create(
            programme=self.master_programme,
            branch=self.branch,
            academic_year="2030-2031",
            entry_year=3,
            first_name="Binta",
            last_name="Ambiguous",
            birth_date=date(2001, 3, 1),
            birth_place="Segou",
            gender="female",
            phone="70030003",
            email="binta.ambiguous@example.com",
            status="accepted",
        )

        result = resolve_academic_context(candidature=candidature)

        self.assertEqual(result["status"], "manual_required_ambiguous_level")
        self.assertEqual(result["reason"], "unsupported_master_entry_year")

    @patch("academics.services.academic_context_resolver.AcademicClass.objects.filter")
    def test_resolve_academic_context_returns_ambiguous_level_when_multiple_classes_match(self, mock_filter):
        mock_queryset = Mock()
        mock_queryset.count.return_value = 2
        mock_queryset.first.return_value = None
        mock_filter.return_value = mock_queryset

        candidature = Candidature.objects.create(
            programme=self.licence_programme,
            branch=self.branch,
            academic_year="2030-2031",
            entry_year=1,
            first_name="Ibrahima",
            last_name="Duplicate",
            birth_date=date(2001, 4, 1),
            birth_place="Gao",
            gender="male",
            phone="70030004",
            email="ibrahima.duplicate@example.com",
            status="accepted",
        )

        result = resolve_academic_context(candidature=candidature)

        self.assertEqual(result["status"], "manual_required_ambiguous_level")
        self.assertEqual(result["reason"], "multiple_academic_classes")

    def test_resolve_academic_context_does_not_fallback_to_active_year_when_label_is_unknown(self):
        candidature = Candidature.objects.create(
            programme=self.licence_programme,
            branch=self.branch,
            academic_year="2034-2035",
            entry_year=1,
            first_name="Sans",
            last_name="Fallback",
            birth_date=date(2001, 4, 2),
            birth_place="Gao",
            gender="male",
            phone="70030005",
            email="sans.fallback@example.com",
            status="accepted",
        )

        result = resolve_academic_context(candidature=candidature)

        self.assertEqual(result["status"], "manual_required_missing_year")
        self.assertEqual(result["reason"], "academic_year_not_found")


class AcademicScheduleServiceTests(TestCase):
    def setUp(self):
        self.director = User.objects.create_user(username="director", password="x")
        self.teacher = User.objects.create_user(username="teacher_1", password="x", first_name="Ada", last_name="Lovelace")
        self.teacher_two = User.objects.create_user(username="teacher_2", password="x", first_name="Alan", last_name="Turing")
        self.student_user = User.objects.create_user(username="student_1", password="x")

        self.branch = Branch.objects.create(name="ESFE Bamako", code="BKO", slug="esfe-bamako")
        cycle = Cycle.objects.create(
            name="Licence",
            min_duration_years=3,
            max_duration_years=3,
        )
        diploma = Diploma.objects.create(name="Licence", level="superieur")
        filiere = Filiere.objects.create(name="Sciences")
        self.programme = Programme.objects.create(
            title="Informatique de gestion",
            filiere=filiere,
            cycle=cycle,
            diploma_awarded=diploma,
            duration_years=3,
            short_description="Programme test",
            description="Programme de test",
        )
        self.academic_year = AcademicYear.objects.create(
            name="2026-2027",
            start_date=date(2026, 10, 1),
            end_date=date(2027, 7, 31),
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
        semester = Semester.objects.create(
            academic_class=self.academic_class,
            number=1,
            total_required_credits=Decimal("30.00"),
        )
        ue = UE.objects.create(semester=semester, code="INF101", title="Fondamentaux")
        self.ec = EC.objects.create(
            ue=ue,
            title="Algorithmique",
            credit_required=Decimal("3.00"),
            coefficient=Decimal("3.00"),
        )
        self.ec_two = EC.objects.create(
            ue=ue,
            title="Base de donnees",
            credit_required=Decimal("3.00"),
            coefficient=Decimal("3.00"),
        )

        candidature = Candidature.objects.create(
            programme=self.programme,
            branch=self.branch,
            academic_year=self.academic_year.name,
            first_name="Jane",
            last_name="Doe",
            birth_date=date(2004, 1, 2),
            birth_place="Bamako",
            gender="female",
            phone="70000000",
            email="jane@example.com",
            status="accepted",
        )
        inscription = Inscription.objects.create(
            candidature=candidature,
            amount_due=100000,
            status=Inscription.STATUS_PARTIAL,
        )
        self.student = Student.objects.create(
            user=self.student_user,
            inscription=inscription,
            matricule="MAT-0001",
            is_active=True,
        )
        self.enrollment = AcademicEnrollment.objects.create(
            inscription=inscription,
            student=self.student_user,
            programme=self.programme,
            branch=self.branch,
            academic_year=self.academic_year,
            academic_class=self.academic_class,
            is_active=True,
        )
        self.week_start = date(2026, 10, 5)

    def _aware_dt(self, day_offset, hour, minute=0):
        return timezone.make_aware(datetime.combine(self.week_start + timedelta(days=day_offset), datetime.min.time().replace(hour=hour, minute=minute)))

    def test_create_schedule_event_valid(self):
        event = create_schedule_event(
            user=self.director,
            title="Cours Algorithmique",
            description="Introduction",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=self._aware_dt(0, 8),
            end_datetime=self._aware_dt(0, 10),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle A1",
            is_online=False,
            meeting_link="",
            is_active=True,
        )

        self.assertEqual(event.academic_class, self.academic_class)
        self.assertEqual(event.teacher, self.teacher)
        self.assertEqual(event.change_logs.count(), 1)
        self.assertEqual(event.change_logs.first().action_type, AcademicScheduleChangeLog.ACTION_CREATED)

    def test_refuse_class_conflict(self):
        create_schedule_event(
            user=self.director,
            title="Cours 1",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=self._aware_dt(0, 8),
            end_datetime=self._aware_dt(0, 10),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle A1",
            is_online=False,
            meeting_link="",
            is_active=True,
        )

        with self.assertRaises(ValidationError):
            create_schedule_event(
                user=self.director,
                title="Cours 2",
                description="",
                event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
                academic_class=self.academic_class,
                ec=self.ec_two,
                teacher=self.teacher_two,
                branch=self.branch,
                academic_year=self.academic_year,
                start_datetime=self._aware_dt(0, 9),
                end_datetime=self._aware_dt(0, 11),
                status=AcademicScheduleEvent.STATUS_PLANNED,
                location="Salle B2",
                is_online=False,
                meeting_link="",
                is_active=True,
            )

    def test_refuse_teacher_conflict(self):
        other_class = AcademicClass.objects.create(
            programme=self.programme,
            branch=self.branch,
            academic_year=self.academic_year,
            level="L2",
            study_level="LICENCE",
            validation_threshold=Decimal("10.00"),
            is_active=True,
        )
        semester = Semester.objects.create(
            academic_class=other_class,
            number=1,
            total_required_credits=Decimal("30.00"),
        )
        ue = UE.objects.create(semester=semester, code="INF201", title="Suite")
        ec_other = EC.objects.create(
            ue=ue,
            title="Reseaux",
            credit_required=Decimal("3.00"),
            coefficient=Decimal("3.00"),
        )

        create_schedule_event(
            user=self.director,
            title="Cours 1",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=self._aware_dt(1, 10),
            end_datetime=self._aware_dt(1, 12),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle A1",
            is_online=False,
            meeting_link="",
            is_active=True,
        )

        with self.assertRaises(ValidationError):
            create_schedule_event(
                user=self.director,
                title="Cours 2",
                description="",
                event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
                academic_class=other_class,
                ec=ec_other,
                teacher=self.teacher,
                branch=self.branch,
                academic_year=self.academic_year,
                start_datetime=self._aware_dt(1, 11),
                end_datetime=self._aware_dt(1, 13),
                status=AcademicScheduleEvent.STATUS_PLANNED,
                location="Salle C1",
                is_online=False,
                meeting_link="",
                is_active=True,
            )

    def test_get_schedule_conflicts_returns_structured_payload(self):
        existing = create_schedule_event(
            user=self.director,
            title="Cours structure",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=self._aware_dt(0, 8),
            end_datetime=self._aware_dt(0, 10),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle A1",
            is_online=False,
            meeting_link="",
            is_active=True,
        )

        conflicts = get_schedule_conflicts(
            academic_class=self.academic_class,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            ec=self.ec,
            location="Salle A1",
            start_datetime=self._aware_dt(0, 9),
            end_datetime=self._aware_dt(0, 11),
        )

        self.assertTrue(conflicts["has_conflict"])
        self.assertTrue(conflicts["class_conflicts"])
        self.assertTrue(conflicts["teacher_conflicts"])
        self.assertTrue(conflicts["location_conflicts"])
        self.assertTrue(conflicts["ec_conflicts"])
        self.assertEqual(conflicts["class_conflicts"][0].id, existing.id)
        self.assertIn("class_conflict", {item["type"] for item in conflicts["conflicts"]})
        self.assertIn("teacher_conflict", {item["type"] for item in conflicts["conflicts"]})

    def test_postpone_schedule_event_creates_log(self):
        event = create_schedule_event(
            user=self.director,
            title="Cours reporte",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=self._aware_dt(2, 8),
            end_datetime=self._aware_dt(2, 10),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle A1",
            is_online=False,
            meeting_link="",
            is_active=True,
        )

        postpone_schedule_event(
            event,
            self._aware_dt(3, 14),
            self._aware_dt(3, 16),
            "Decalage pour indisponibilite",
            self.director,
        )

        self.assertEqual(event.change_logs.count(), 2)
        log = event.change_logs.order_by("-changed_at").first()
        self.assertEqual(log.action_type, AcademicScheduleChangeLog.ACTION_POSTPONED)
        self.assertEqual(log.reason, "Decalage pour indisponibilite")
        self.assertEqual(log.old_start_datetime, self._aware_dt(2, 8))
        self.assertEqual(log.new_start_datetime, self._aware_dt(3, 14))

    def test_cancel_schedule_event_creates_log(self):
        event = create_schedule_event(
            user=self.director,
            title="Cours annule",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=self._aware_dt(4, 14),
            end_datetime=self._aware_dt(4, 16),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle A1",
            is_online=False,
            meeting_link="",
            is_active=True,
        )

        cancel_schedule_event(event, "Jour ferie", self.director)

        event.refresh_from_db()
        self.assertEqual(event.status, AcademicScheduleEvent.STATUS_CANCELLED)
        log = event.change_logs.order_by("-changed_at").first()
        self.assertEqual(log.action_type, AcademicScheduleChangeLog.ACTION_CANCELLED)
        self.assertEqual(log.reason, "Jour ferie")

    def test_postpone_and_cancel_require_reason(self):
        event = create_schedule_event(
            user=self.director,
            title="Cours valide",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=self._aware_dt(1, 14),
            end_datetime=self._aware_dt(1, 16),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle A1",
            is_online=False,
            meeting_link="",
            is_active=True,
        )

        with self.assertRaises(ValidationError):
            postpone_schedule_event(event, self._aware_dt(2, 14), self._aware_dt(2, 16), "", self.director)
        with self.assertRaises(ValidationError):
            cancel_schedule_event(event, "   ", self.director)

    def test_suggest_available_slots_returns_free_standard_slots(self):
        create_schedule_event(
            user=self.director,
            title="Cours occupe",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=self._aware_dt(0, 8),
            end_datetime=self._aware_dt(0, 10),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle A1",
            is_online=False,
            meeting_link="",
            is_active=True,
        )

        suggestions = suggest_available_slots(
            academic_class=self.academic_class,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            duration_minutes=120,
            week_start=self.week_start,
        )

        self.assertTrue(suggestions)
        self.assertNotEqual(suggestions[0]["start"], self._aware_dt(0, 8))
        self.assertGreaterEqual(suggestions[0]["score"], 40)
        self.assertEqual(suggestions[0]["end"] - suggestions[0]["start"], timedelta(minutes=120))

    def test_get_weekly_schedule_stats_returns_enriched_counts(self):
        event_planned = create_schedule_event(
            user=self.director,
            title="Cours 1",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=self._aware_dt(0, 8),
            end_datetime=self._aware_dt(0, 10),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle A1",
            is_online=False,
            meeting_link="",
            is_active=True,
        )
        event_cancelled = create_schedule_event(
            user=self.director,
            title="Cours 2",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec_two,
            teacher=self.teacher_two,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=self._aware_dt(1, 10),
            end_datetime=self._aware_dt(1, 12),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle B1",
            is_online=False,
            meeting_link="",
            is_active=True,
        )
        cancel_schedule_event(event_cancelled, "Indisponible", self.director)
        complete_schedule_event(
            event_planned,
            self.director,
            notes="Termine",
            started_at=self._aware_dt(0, 8),
            ended_at=self._aware_dt(0, 10),
        )

        stats = get_weekly_schedule_stats(self.branch, self.week_start)

        self.assertEqual(stats["total_events"], 2)
        self.assertEqual(stats["completed_count"], 1)
        self.assertEqual(stats["cancelled_count"], 1)
        self.assertIn("Ada Lovelace", stats["teacher_load"])
        self.assertIn(self.academic_class.display_name, stats["class_load"])
        self.assertEqual(stats["completion_rate"], 50.0)
        self.assertEqual(stats["cancellation_rate"], 50.0)

    def test_quality_score_alerts_and_branch_summary(self):
        postponed = create_schedule_event(
            user=self.director,
            title="Cours reporte",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=self._aware_dt(2, 8),
            end_datetime=self._aware_dt(2, 10),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="",
            is_online=False,
            meeting_link="",
            is_active=True,
        )
        postpone_schedule_event(
            postponed,
            self._aware_dt(3, 14),
            self._aware_dt(3, 16),
            "Report maintenu",
            self.director,
        )

        alerts = get_schedule_alerts(self.branch, self.week_start)
        quality = get_schedule_quality_score(self.branch, self.week_start)
        summary = get_branch_activity_summary(self.branch, self.week_start)

        self.assertTrue(any(alert["type"] == "missing_location" for alert in alerts))
        self.assertIn("score", quality)
        self.assertIn("status", quality)
        self.assertEqual(summary["alert_count"], len(summary["alerts"]))
        self.assertIn("stats", summary)

    def test_complete_schedule_event_creates_execution_log(self):
        event = create_schedule_event(
            user=self.director,
            title="Cours execution",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=self._aware_dt(4, 8),
            end_datetime=self._aware_dt(4, 10),
            status=AcademicScheduleEvent.STATUS_ONGOING,
            location="Salle A1",
            is_online=False,
            meeting_link="",
            is_active=True,
        )

        execution_log = complete_schedule_event(
            event,
            self.director,
            notes="Cours bien termine",
            started_at=self._aware_dt(4, 8),
            ended_at=self._aware_dt(4, 9, 45),
        )

        event.refresh_from_db()
        self.assertEqual(event.status, AcademicScheduleEvent.STATUS_COMPLETED)
        self.assertTrue(execution_log.is_completed)
        self.assertEqual(execution_log.started_at, self._aware_dt(4, 8))
        self.assertEqual(execution_log.ended_at, self._aware_dt(4, 9, 45))

    def test_get_teacher_next_events_returns_future_items(self):
        create_schedule_event(
            user=self.director,
            title="Cours suivant",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=timezone.now() + timedelta(days=1),
            end_datetime=timezone.now() + timedelta(days=1, hours=2),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle A1",
            is_online=False,
            meeting_link="",
            is_active=True,
        )

        events = get_teacher_next_events(self.teacher)

        self.assertTrue(events)
        self.assertEqual(events[0]["teacher_name"], "Ada Lovelace")

    def test_get_student_week_schedule_returns_weekly_grid(self):
        create_schedule_event(
            user=self.director,
            title="Cours dashboard",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=self._aware_dt(0, 8),
            end_datetime=self._aware_dt(0, 10),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle A1",
            is_online=False,
            meeting_link="",
            is_active=True,
        )

        schedule = get_student_week_schedule(self.student, self.week_start)

        self.assertEqual(schedule["week_start"], self.week_start)
        self.assertTrue(schedule["events"])
        self.assertEqual(schedule["events"][0]["title"], "Algorithmique")
        self.assertTrue(any(cell["events"] for slot in schedule["slots"] for cell in slot["cells"]))
        self.assertIn("summary", schedule)
        self.assertIn("empty_days", schedule)

    def test_get_student_week_schedule_handles_empty_week(self):
        schedule = get_student_week_schedule(self.student, self.week_start)

        self.assertEqual(schedule["events"], [])
        self.assertEqual(len(schedule["slots"]), 4)
        self.assertEqual(len(schedule["empty_days"]), 6)
        self.assertFalse(schedule["has_extra_slots"])

    def test_get_student_week_schedule_falls_back_to_weekly_slots(self):
        WeeklyScheduleSlot.objects.create(
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            weekday=0,
            start_time=time(8, 0),
            end_time=time(10, 0),
            room="Salle grille",
            is_active=True,
        )

        schedule = get_student_week_schedule(self.student, self.week_start)

        self.assertTrue(schedule["is_weekly_template"])
        self.assertEqual(schedule["summary"]["planned"], 1)
        self.assertEqual(schedule["events"][0]["title"], "Algorithmique")
        self.assertEqual(schedule["events"][0]["source"], "weekly_slot")
        self.assertEqual(schedule["slots"][0]["cells"][0]["events"][0]["location"], "Salle grille")

    def test_get_student_week_schedule_merges_unmaterialized_weekly_slots(self):
        create_schedule_event(
            user=self.director,
            title="Cours deja date",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=self._aware_dt(0, 8),
            end_datetime=self._aware_dt(0, 10),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle A1",
            is_online=False,
            meeting_link="",
            is_active=True,
        )
        WeeklyScheduleSlot.objects.create(
            academic_class=self.academic_class,
            ec=self.ec_two,
            teacher=self.teacher_two,
            branch=self.branch,
            academic_year=self.academic_year,
            weekday=1,
            start_time=time(10, 0),
            end_time=time(12, 0),
            room="Salle grille",
            is_active=True,
        )

        schedule = get_student_week_schedule(self.student, self.week_start)

        self.assertTrue(schedule["has_weekly_template_fallback"])
        self.assertEqual(schedule["summary"]["planned"], 2)
        self.assertEqual({event.get("source") for event in schedule["events"]}, {None, "weekly_slot"})
        self.assertTrue(schedule["slots"][1]["cells"][1]["events"])

    def test_get_student_week_schedule_displays_sunday_slots_when_used(self):
        WeeklyScheduleSlot.objects.create(
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            weekday=6,
            start_time=time(8, 0),
            end_time=time(10, 0),
            room="Salle dimanche",
            is_active=True,
        )

        schedule = get_student_week_schedule(self.student, self.week_start)

        self.assertEqual(len(schedule["days"]), 7)
        self.assertEqual(schedule["days"][6]["label"], "Dim")
        self.assertEqual(schedule["slots"][0]["cells"][6]["events"][0]["location"], "Salle dimanche")

    def test_get_student_week_schedule_exposes_non_standard_slots(self):
        create_schedule_event(
            user=self.director,
            title="Cours hors grille",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=self._aware_dt(2, 11),
            end_datetime=self._aware_dt(2, 13),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle A1",
            is_online=False,
            meeting_link="",
            is_active=True,
        )

        schedule = get_student_week_schedule(self.student, self.week_start)

        self.assertTrue(schedule["has_extra_slots"])
        self.assertEqual(schedule["extra_slots"][0]["label"], "11:00")
        self.assertEqual(schedule["extra_slots"][0]["cells"][2]["events"][0]["title"], "Algorithmique")

    def test_get_student_week_schedule_keeps_cancelled_and_planned_same_slot(self):
        cancelled_event = create_schedule_event(
            user=self.director,
            title="Cours annule cellule",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=self._aware_dt(0, 8),
            end_datetime=self._aware_dt(0, 10),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle A1",
            is_online=False,
            meeting_link="",
            is_active=True,
        )
        cancel_schedule_event(cancelled_event, "Annulation test", self.director)
        create_schedule_event(
            user=self.director,
            title="Cours maintenu cellule",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec_two,
            teacher=self.teacher_two,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=self._aware_dt(0, 8),
            end_datetime=self._aware_dt(0, 10),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle B1",
            is_online=False,
            meeting_link="",
            is_active=True,
        )

        schedule = get_student_week_schedule(self.student, self.week_start)

        monday_first_cell = schedule["slots"][0]["cells"][0]
        self.assertEqual(len(monday_first_cell["events"]), 2)
        self.assertEqual({event["status"] for event in monday_first_cell["events"]}, {"cancelled", "planned"})

    def test_get_student_week_schedule_marks_completed_events(self):
        event = create_schedule_event(
            user=self.director,
            title="Cours termine affichage",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=self._aware_dt(4, 16),
            end_datetime=self._aware_dt(4, 18),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle A1",
            is_online=False,
            meeting_link="",
            is_active=True,
        )
        complete_schedule_event(
            event,
            self.director,
            notes="Fin de cours",
            started_at=self._aware_dt(4, 16),
            ended_at=self._aware_dt(4, 18),
        )

        schedule = get_student_week_schedule(self.student, self.week_start)
        completed = next(item for item in schedule["events"] if item["id"] == event.id)

        self.assertTrue(completed["is_completed"])
        self.assertEqual(completed["status_label"], "Termine")
        self.assertEqual(schedule["summary"]["completed"], 1)


class LessonLogServiceTests(TestCase):
    def setUp(self):
        self.supervisor = User.objects.create_user(username="supervisor_log", password="x")
        self.teacher = User.objects.create_user(username="teacher_log", password="x", first_name="Grace", last_name="Hopper")

        self.branch = Branch.objects.create(name="ESFE Kayes", code="KYS", slug="esfe-kayes")
        cycle = Cycle.objects.create(name="Licence Log", min_duration_years=3, max_duration_years=3)
        diploma = Diploma.objects.create(name="Licence Log", level="superieur")
        filiere = Filiere.objects.create(name="Gestion")
        self.programme = Programme.objects.create(
            title="Gestion des organisations",
            filiere=filiere,
            cycle=cycle,
            diploma_awarded=diploma,
            duration_years=3,
            short_description="Programme log",
            description="Programme log",
        )
        self.academic_year = AcademicYear.objects.create(
            name="2027-2028",
            start_date=date(2027, 10, 1),
            end_date=date(2028, 7, 31),
            is_active=True,
        )
        self.academic_class = AcademicClass.objects.create(
            programme=self.programme,
            branch=self.branch,
            academic_year=self.academic_year,
            level="L2",
            study_level="LICENCE",
            validation_threshold=Decimal("10.00"),
            is_active=True,
        )
        semester = Semester.objects.create(
            academic_class=self.academic_class,
            number=1,
            total_required_credits=Decimal("30.00"),
        )
        ue = UE.objects.create(semester=semester, code="GST201", title="Pilotage")
        self.ec = EC.objects.create(
            ue=ue,
            title="Management",
            credit_required=Decimal("3.00"),
            coefficient=Decimal("3.00"),
        )
        self.lesson_date = date(2027, 10, 5)
        self.schedule_event = create_schedule_event(
            user=self.supervisor,
            title="Cours Management",
            description="Seance 1",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=timezone.make_aware(datetime.combine(self.lesson_date, datetime.min.time().replace(hour=8))),
            end_datetime=timezone.make_aware(datetime.combine(self.lesson_date, datetime.min.time().replace(hour=10))),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle M1",
            is_online=False,
            meeting_link="",
            is_active=True,
        )

    def test_create_lesson_log_creates_expected_record(self):
        lesson_log = create_lesson_log(
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            schedule_event=self.schedule_event,
            date=self.lesson_date,
            start_time=time(8, 0),
            end_time=time(10, 0),
            status=LessonLog.STATUS_DONE,
            branch=self.branch,
            created_by=self.supervisor,
            content="Introduction au management",
            homework="Lire le chapitre 1",
        )

        self.assertEqual(LessonLog.objects.count(), 1)
        self.assertEqual(lesson_log.schedule_event, self.schedule_event)
        self.assertEqual(lesson_log.status, LessonLog.STATUS_DONE)

    def test_update_lesson_log_updates_content_and_validation(self):
        lesson_log = create_lesson_log(
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            schedule_event=self.schedule_event,
            date=self.lesson_date,
            start_time=time(8, 0),
            end_time=time(10, 0),
            status=LessonLog.STATUS_PLANNED,
            branch=self.branch,
            created_by=self.supervisor,
        )

        updated = update_lesson_log(
            lesson_log,
            updated_by=self.supervisor,
            validated_by=self.supervisor,
            status=LessonLog.STATUS_DONE,
            content="Cours dispense",
            homework="Exercice 1",
        )

        self.assertEqual(updated.status, LessonLog.STATUS_DONE)
        self.assertEqual(updated.validated_by, self.supervisor)
        self.assertEqual(updated.content, "Cours dispense")

    def test_get_daily_lesson_status_flags_missing_logs_and_teacher_absence(self):
        TeacherAttendance.objects.create(
            teacher=self.teacher,
            schedule_event=self.schedule_event,
            date=self.lesson_date,
            status=TeacherAttendance.STATUS_ABSENT,
            recorded_by=self.supervisor,
            branch=self.branch,
        )

        daily_status = get_daily_lesson_status(self.branch, self.lesson_date)

        self.assertEqual(daily_status["scheduled_courses"], 1)
        self.assertEqual(daily_status["missing_lesson_logs_count"], 1)
        self.assertEqual(daily_status["critical_count"], 1)
        self.assertEqual(daily_status["critical_items"][0]["status"], "teacher_absent_with_planned_lesson")

    def test_create_lesson_log_for_absent_teacher_forces_absent_teacher_status(self):
        TeacherAttendance.objects.create(
            teacher=self.teacher,
            schedule_event=self.schedule_event,
            date=self.lesson_date,
            status=TeacherAttendance.STATUS_ABSENT,
            recorded_by=self.supervisor,
            branch=self.branch,
        )

        lesson_log = create_lesson_log(
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            schedule_event=self.schedule_event,
            date=self.lesson_date,
            start_time=time(8, 0),
            end_time=time(10, 0),
            status=LessonLog.STATUS_DONE,
            branch=self.branch,
            created_by=self.supervisor,
            content="Cours non tenu",
        )

        self.assertEqual(lesson_log.status, LessonLog.STATUS_ABSENT_TEACHER)

    def test_get_class_and_teacher_lesson_logs_return_created_items(self):
        lesson_log = create_lesson_log(
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            schedule_event=self.schedule_event,
            date=self.lesson_date,
            start_time=time(8, 0),
            end_time=time(10, 0),
            status=LessonLog.STATUS_DONE,
            branch=self.branch,
            created_by=self.supervisor,
            content="Cours dispense",
        )

        class_logs = get_class_lesson_logs(self.academic_class)
        teacher_logs = get_teacher_lesson_logs(self.teacher, branch=self.branch)

        self.assertEqual(class_logs[0].id, lesson_log.id)
        self.assertEqual(teacher_logs[0].id, lesson_log.id)


class LessonLogApiTests(TestCase):
    def setUp(self):
        self.supervisor = User.objects.create_user(username="lesson_api", password="pass1234")
        self.supervisor.profile.position = "academic_supervisor"
        self.supervisor.profile.user_type = "staff"
        self.branch = Branch.objects.create(name="ESFE Sikasso", code="SKO", slug="esfe-sikasso")
        self.other_branch = Branch.objects.create(name="ESFE Gao", code="GAO", slug="esfe-gao")
        self.supervisor.profile.branch = self.branch
        self.supervisor.profile.save(update_fields=["position", "user_type", "branch", "updated_at"])

        self.teacher = User.objects.create_user(username="teacher_api_log", password="x", first_name="Marie", last_name="Curie")
        self.teacher_other = User.objects.create_user(username="teacher_api_log_other", password="x")

        cycle = Cycle.objects.create(name="Licence API Log", min_duration_years=3, max_duration_years=3)
        diploma = Diploma.objects.create(name="Licence API Log", level="superieur")
        filiere = Filiere.objects.create(name="Informatique API Log")
        self.programme = Programme.objects.create(
            title="Developpement logiciel",
            filiere=filiere,
            cycle=cycle,
            diploma_awarded=diploma,
            duration_years=3,
            short_description="Prog API log",
            description="Prog API log",
        )
        self.academic_year = AcademicYear.objects.create(
            name="2029-2030",
            start_date=date(2029, 10, 1),
            end_date=date(2030, 7, 31),
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
        semester = Semester.objects.create(academic_class=self.academic_class, number=1, total_required_credits=Decimal("30.00"))
        other_semester = Semester.objects.create(academic_class=self.other_class, number=1, total_required_credits=Decimal("30.00"))
        ue = UE.objects.create(semester=semester, code="LOG101", title="Log")
        other_ue = UE.objects.create(semester=other_semester, code="LOG201", title="Log2")
        self.ec = EC.objects.create(ue=ue, title="Python", credit_required=Decimal("3.00"), coefficient=Decimal("3.00"))
        self.other_ec = EC.objects.create(ue=other_ue, title="Java", credit_required=Decimal("3.00"), coefficient=Decimal("3.00"))
        self.event = AcademicScheduleEvent.objects.create(
            title="Cours Python",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=timezone.make_aware(datetime(2029, 10, 5, 8, 0)),
            end_datetime=timezone.make_aware(datetime(2029, 10, 5, 10, 0)),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle L1",
            created_by=self.supervisor,
            updated_by=self.supervisor,
            is_active=True,
        )
        self.other_event = AcademicScheduleEvent.objects.create(
            title="Cours Java",
            description="",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.other_class,
            ec=self.other_ec,
            teacher=self.teacher_other,
            branch=self.other_branch,
            academic_year=self.academic_year,
            start_datetime=timezone.make_aware(datetime(2029, 10, 5, 8, 0)),
            end_datetime=timezone.make_aware(datetime(2029, 10, 5, 10, 0)),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle G1",
            created_by=self.supervisor,
            updated_by=self.supervisor,
            is_active=True,
        )
        self.client.force_login(self.supervisor)

    def test_lesson_log_create_api_creates_record(self):
        response = self.client.post(
            reverse("academics:lesson_log_create"),
            data={
                "academic_class_id": self.academic_class.id,
                "ec_id": self.ec.id,
                "teacher_id": self.teacher.id,
                "schedule_event_id": self.event.id,
                "date": "2029-10-05",
                "start_time": "08:00",
                "end_time": "10:00",
                "status": LessonLog.STATUS_DONE,
                "content": "Variables et boucles",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(LessonLog.objects.count(), 1)
        self.assertEqual(LessonLog.objects.get().schedule_event, self.event)

    def test_lesson_log_create_api_rejects_cross_branch_event(self):
        response = self.client.post(
            reverse("academics:lesson_log_create"),
            data={
                "academic_class_id": self.other_class.id,
                "ec_id": self.other_ec.id,
                "teacher_id": self.teacher_other.id,
                "schedule_event_id": self.other_event.id,
                "date": "2029-10-05",
                "start_time": "08:00",
                "end_time": "10:00",
                "status": LessonLog.STATUS_DONE,
                "content": "Test",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(LessonLog.objects.count(), 0)

    def test_lesson_log_create_api_rejects_invalid_time(self):
        response = self.client.post(
            reverse("academics:lesson_log_create"),
            data={
                "academic_class_id": self.academic_class.id,
                "ec_id": self.ec.id,
                "teacher_id": self.teacher.id,
                "schedule_event_id": self.event.id,
                "date": "2029-10-05",
                "start_time": "10:00",
                "end_time": "08:00",
                "status": LessonLog.STATUS_DONE,
                "content": "Test",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(LessonLog.objects.count(), 0)

    def test_lesson_log_daily_status_api_returns_missing_course(self):
        response = self.client.get(
            reverse("academics:daily_lesson_status"),
            {"date": "2029-10-05"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertEqual(payload["missing_lesson_logs_count"], 1)

    def test_lesson_log_create_api_marks_absent_teacher_automatically(self):
        TeacherAttendance.objects.create(
            teacher=self.teacher,
            schedule_event=self.event,
            date=date(2029, 10, 5),
            status=TeacherAttendance.STATUS_ABSENT,
            recorded_by=self.supervisor,
            branch=self.branch,
        )

        response = self.client.post(
            reverse("academics:lesson_log_create"),
            data={
                "academic_class_id": self.academic_class.id,
                "ec_id": self.ec.id,
                "teacher_id": self.teacher.id,
                "schedule_event_id": self.event.id,
                "date": "2029-10-05",
                "start_time": "08:00",
                "end_time": "10:00",
                "status": LessonLog.STATUS_DONE,
                "content": "Tentative",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["lesson_log"]["status"], LessonLog.STATUS_ABSENT_TEACHER)


class CalendarFrontendViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="calendaruser", password="test")

    def test_calendar_frontend_page_renders(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("academics:calendar_frontend"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Calendrier académique")
        self.assertContains(response, "calendarApp")


class LessonLogHonorariumSignalTests(TestCase):
    """Vérifie que les changements de cahier de texte recalculent l'honoraire mensuel."""

    def setUp(self):
        self.branch = Branch.objects.create(name="ESFE Honoraria", code="HNR", slug="esfe-honoraria")
        self.supervisor = User.objects.create_user(username="hon_supervisor", password="pass1234")
        self.supervisor.profile.position = "academic_supervisor"
        self.supervisor.profile.user_type = "staff"
        self.supervisor.profile.branch = self.branch
        self.supervisor.profile.save(update_fields=["position", "user_type", "branch", "updated_at"])

        self.teacher = User.objects.create_user(username="hon_teacher", password="pass1234")
        self.teacher.profile.user_type = "teacher"
        self.teacher.profile.teacher_hourly_rate = 5000
        self.teacher.profile.branch = self.branch
        self.teacher.profile.save(update_fields=["user_type", "teacher_hourly_rate", "branch", "updated_at"])

        self.academic_year = AcademicYear.objects.create(
            name="2027-2028",
            start_date=date(2027, 9, 1),
            end_date=date(2028, 6, 30),
            is_active=True,
        )
        self.programme = Programme.objects.create(
            title="Licence Gestion",
            slug="licence-gestion",
            cycle=Cycle.objects.create(name="Licence", min_duration_years=3, max_duration_years=5),
            filiere=Filiere.objects.create(name="Gestion"),
            diploma_awarded=Diploma.objects.create(name="Licence", level="superieur"),
            duration_years=3,
            short_description="Licence en gestion",
            description="Description",
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
        self.semester = Semester.objects.create(
            academic_class=self.academic_class,
            number=1,
            total_required_credits=Decimal("30.00"),
        )
        self.ue = UE.objects.create(semester=self.semester, code="HON101", title="Honoraires")
        self.ec = EC.objects.create(
            ue=self.ue,
            title="Management",
            credit_required=Decimal("3.00"),
            coefficient=Decimal("3.00"),
        )
        self.lesson_date = date(2027, 10, 5)
        self.schedule_event = create_schedule_event(
            user=self.supervisor,
            title="Cours Management",
            description="Seance honoraires",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.academic_year,
            start_datetime=timezone.make_aware(datetime.combine(self.lesson_date, time(8, 0))),
            end_datetime=timezone.make_aware(datetime.combine(self.lesson_date, time(10, 0))),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle H1",
            is_online=False,
            meeting_link="",
            is_active=True,
        )

    def test_validated_lesson_log_creates_honorarium_entry(self):
        entry_before = TeacherHonorariumEntry.objects.filter(
            branch=self.branch, teacher=self.teacher, period_month=date(2027, 10, 1)
        ).first()
        self.assertIsNone(entry_before)

        create_lesson_log(
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            schedule_event=self.schedule_event,
            date=self.lesson_date,
            start_time=time(8, 0),
            end_time=time(10, 0),
            status=LessonLog.STATUS_DONE,
            branch=self.branch,
            created_by=self.supervisor,
            content="Cours dispense",
            validated_by=self.supervisor,
        )

        entry = TeacherHonorariumEntry.objects.get(
            branch=self.branch, teacher=self.teacher, period_month=date(2027, 10, 1)
        )
        self.assertEqual(entry.validated_hours, Decimal("2.00"))
        self.assertEqual(entry.hourly_rate, 5000)

    def test_unvalidated_lesson_log_does_not_count_hours(self):
        create_lesson_log(
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            schedule_event=self.schedule_event,
            date=self.lesson_date,
            start_time=time(8, 0),
            end_time=time(10, 0),
            status=LessonLog.STATUS_DONE,
            branch=self.branch,
            created_by=self.supervisor,
            content="Cours soumis",
        )

        entry = TeacherHonorariumEntry.objects.filter(
            branch=self.branch, teacher=self.teacher, period_month=date(2027, 10, 1)
        ).first()
        self.assertIsNone(entry)

    def test_absent_teacher_lesson_log_does_not_count_hours(self):
        create_lesson_log(
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            schedule_event=self.schedule_event,
            date=self.lesson_date,
            start_time=time(8, 0),
            end_time=time(10, 0),
            status=LessonLog.STATUS_ABSENT_TEACHER,
            branch=self.branch,
            created_by=self.supervisor,
            content="Absence",
            validated_by=self.supervisor,
        )

        entry = TeacherHonorariumEntry.objects.filter(
            branch=self.branch, teacher=self.teacher, period_month=date(2027, 10, 1)
        ).first()
        self.assertIsNone(entry)

    def test_deleting_validated_lesson_log_resets_honorarium(self):
        lesson_log = create_lesson_log(
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            schedule_event=self.schedule_event,
            date=self.lesson_date,
            start_time=time(8, 0),
            end_time=time(10, 0),
            status=LessonLog.STATUS_DONE,
            branch=self.branch,
            created_by=self.supervisor,
            content="Cours dispense",
            validated_by=self.supervisor,
        )

        entry = TeacherHonorariumEntry.objects.get(
            branch=self.branch, teacher=self.teacher, period_month=date(2027, 10, 1)
        )
        self.assertEqual(entry.validated_hours, Decimal("2.00"))

        lesson_log.delete()

        entry.refresh_from_db()
        self.assertEqual(entry.validated_hours, Decimal("0.00"))


class LessonLogNotificationTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(name="Annexe Notif", code="NOT", slug="annexe-notif")
        self.other_branch = Branch.objects.create(name="Autre Notif", code="NOT2", slug="autre-notif")

        self.manager = User.objects.create_user(username="notif_manager", password="pass1234", is_staff=True)
        self.manager_group, _ = Group.objects.get_or_create(name="gestionnaire")
        self.manager.groups.add(self.manager_group)
        self.manager.profile.branch = self.branch
        self.manager.profile.save(update_fields=["branch", "updated_at"])

        self.other_manager = User.objects.create_user(username="other_notif_manager", password="pass1234", is_staff=True)
        self.other_manager.groups.add(self.manager_group)
        self.other_manager.profile.branch = self.other_branch
        self.other_manager.profile.save(update_fields=["branch", "updated_at"])

        self.supervisor = User.objects.create_user(username="notif_supervisor", password="pass1234")
        self.supervisor.profile.position = "director_of_studies"
        self.supervisor.profile.user_type = "supervisor"
        self.supervisor.profile.branch = self.branch
        self.supervisor.profile.save(update_fields=["position", "user_type", "branch", "updated_at"])

        self.teacher = User.objects.create_user(username="notif_teacher", password="pass1234")
        self.teacher.profile.user_type = "teacher"
        self.teacher.profile.teacher_hourly_rate = 5000
        self.teacher.profile.branch = self.branch
        self.teacher.profile.save(update_fields=["user_type", "teacher_hourly_rate", "branch", "updated_at"])

        self.academic_year = AcademicYear.objects.create(
            name="2027-2028",
            start_date=date(2027, 9, 1),
            end_date=date(2028, 6, 30),
            is_active=True,
        )
        self.programme = Programme.objects.create(
            title="Licence Gestion",
            slug="licence-gestion-notif",
            cycle=Cycle.objects.create(name="Licence", min_duration_years=3, max_duration_years=5),
            filiere=Filiere.objects.create(name="Gestion"),
            diploma_awarded=Diploma.objects.create(name="Licence", level="superieur"),
            duration_years=3,
            short_description="Licence en gestion",
            description="Description",
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
        self.semester = Semester.objects.create(
            academic_class=self.academic_class,
            number=1,
            total_required_credits=Decimal("30.00"),
        )
        self.ue = UE.objects.create(
            semester=self.semester,
            code="UE_GEST",
            title="Gestion",
        )
        self.ec = EC.objects.create(
            ue=self.ue,
            title="Communication",
            credit_required=Decimal("3.00"),
            coefficient=Decimal("1.00"),
        )
        self.schedule_event = AcademicScheduleEvent.objects.create(
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            title="Cours Communication",
            start_datetime=datetime(2027, 10, 15, 8, 0),
            end_datetime=datetime(2027, 10, 15, 10, 0),
            is_active=True,
        )
        self.lesson_date = date(2027, 10, 15)

    def test_submitting_lesson_log_notifies_branch_managers(self):
        create_lesson_log(
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            schedule_event=self.schedule_event,
            date=self.lesson_date,
            start_time=time(8, 0),
            end_time=time(10, 0),
            status=LessonLog.STATUS_DONE,
            branch=self.branch,
            created_by=self.teacher,
            content="Cours dispense",
        )
        self.assertTrue(
            NotificationMessage.objects.filter(
                recipient=self.manager,
                event_type="lesson_log_submitted",
            ).exists()
        )
        self.assertFalse(
            NotificationMessage.objects.filter(
                recipient=self.other_manager,
                event_type="lesson_log_submitted",
            ).exists()
        )

    def test_validating_lesson_log_notifies_teacher(self):
        lesson_log = create_lesson_log(
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            schedule_event=self.schedule_event,
            date=self.lesson_date,
            start_time=time(8, 0),
            end_time=time(10, 0),
            status=LessonLog.STATUS_DONE,
            branch=self.branch,
            created_by=self.teacher,
            content="Cours dispense",
        )
        update_lesson_log(
            lesson_log=lesson_log,
            content="Cours dispense et valide",
            validated_by=self.supervisor,
            updated_by=self.supervisor,
        )
        self.assertTrue(
            NotificationMessage.objects.filter(
                recipient=self.teacher,
                event_type="lesson_log_validated",
            ).exists()
        )

    def test_editing_submitted_log_does_not_duplicate_manager_notification(self):
        lesson_log = create_lesson_log(
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            schedule_event=self.schedule_event,
            date=self.lesson_date,
            start_time=time(8, 0),
            end_time=time(10, 0),
            status=LessonLog.STATUS_DONE,
            branch=self.branch,
            created_by=self.teacher,
            content="Cours dispense",
        )
        update_lesson_log(
            lesson_log=lesson_log,
            content="Cours mis a jour",
            updated_by=self.teacher,
        )
        self.assertEqual(
            NotificationMessage.objects.filter(
                recipient=self.manager,
                event_type="lesson_log_submitted",
            ).count(),
            1,
        )

    def test_creating_absent_log_does_not_notify_managers(self):
        create_lesson_log(
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            schedule_event=self.schedule_event,
            date=self.lesson_date,
            start_time=time(8, 0),
            end_time=time(10, 0),
            status=LessonLog.STATUS_ABSENT_TEACHER,
            branch=self.branch,
            created_by=self.teacher,
            content="Absence",
        )
        self.assertFalse(
            NotificationMessage.objects.filter(
                recipient=self.manager,
                event_type="lesson_log_submitted",
            ).exists()
        )

