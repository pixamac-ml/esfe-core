from decimal import Decimal
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404

from academic_cycle.models import StudentYearDecision
from academics.models import AcademicClass, AcademicEnrollment, Semester
from academics.services.annual_deliberation import get_annual_semesters
from academics.services.semester import compute_semester_result
from students.models import Student


def format_decimal(value):
    if value in (None, ""):
        return "0,00"
    return f"{Decimal(value):.2f}".replace(".", ",")


def get_student_full_name(student):
    if hasattr(student, "full_name"):
        return student.full_name
    if hasattr(student, "user"):
        return f"{student.user.last_name} {student.user.first_name}".strip()
    return str(student)


def _resolve_student(student_id):
    student = Student.objects.select_related("user").filter(id=student_id).first()
    if student:
        return student
    return get_object_or_404(Student.objects.select_related("user"), user_id=student_id)


def build_student_semester_report(student_id: int, semester_id: int) -> dict:
    """Build a semester report for the enrollment belonging to that semester.

    The enrollment is intentionally not filtered on ``is_active``: a student
    who has since been re-enrolled must still be able to consult a published
    semester from a previous academic year.
    """
    student = _resolve_student(student_id)
    semester = get_object_or_404(
        Semester.objects.select_related("academic_class"), id=semester_id
    )
    enrollment = (
        AcademicEnrollment.objects.select_related(
            "student", "academic_class", "academic_year", "programme", "branch"
        )
        .filter(
            student=student.user,
            academic_class=semester.academic_class,
            academic_year=semester.academic_class.academic_year,
        )
        .order_by("-id")
        .first()
    )
    if enrollment is None:
        raise Http404("Aucune inscription ne correspond a cet etudiant, cette classe et ce semestre.")

    semester_result = compute_semester_result(semester=semester, enrollment=enrollment)
    programme = enrollment.programme
    semester_result["average_display"] = format_decimal(semester_result.get("average"))
    semester_result["percentage_display"] = format_decimal(semester_result.get("percentage"))
    semester_result["credit_required_display"] = format_decimal(semester_result.get("credit_required"))
    semester_result["credit_obtained_display"] = format_decimal(semester_result.get("credit_obtained"))
    semester_result["total_coefficients_display"] = format_decimal(semester_result.get("total_coefficients"))
    for ue_result in semester_result.get("ue_results", []):
        ue_result["average_display"] = format_decimal(ue_result.get("average"))
        ue_result["credit_required_display"] = format_decimal(ue_result.get("credit_required"))
        ue_result["credit_obtained_display"] = format_decimal(ue_result.get("credit_obtained"))
        ue_result["total_coefficients_display"] = format_decimal(ue_result.get("total_coefficients"))
        ue_result["total_note_coefficients_display"] = format_decimal(ue_result.get("total_note_coefficients"))
        for row in ue_result.get("rows", []):
            row["note_display"] = format_decimal(row.get("note"))
            row["note_coefficient_display"] = format_decimal(row.get("note_coefficient"))
            row["credit_required_display"] = format_decimal(row.get("credit_required"))
            row["credit_obtained_display"] = format_decimal(row.get("credit_obtained"))
            row["ec_coefficient_display"] = format_decimal(getattr(row.get("ec"), "coefficient", None))

    candidature = getattr(getattr(student, "inscription", None), "candidature", None)
    birth_date = getattr(candidature, "birth_date", None)
    birth_place = (getattr(candidature, "birth_place", "") or "").strip()
    birth_parts = []
    if birth_date:
        birth_parts.append(birth_date.strftime("%d/%m/%Y"))
    if birth_place:
        birth_parts.append(birth_place)
    return {
        "student": student,
        "enrollment": enrollment,
        "semester": semester,
        "semester_result": semester_result,
        "academic_year": enrollment.academic_year,
        "formation": programme,
        "programme_name": programme.title if programme else "",
        "department_name": programme.filiere.name if programme and programme.filiere else "",
        "domain_name": programme.cycle.name if programme and programme.cycle else "",
        "student_full_name": get_student_full_name(student),
        "student_matricule": getattr(student, "matricule", "N/A"),
        "student_last_name": getattr(candidature, "last_name", "") or student.user.last_name,
        "student_first_name": getattr(candidature, "first_name", "") or student.user.first_name,
        "student_birth_info": " a ".join(birth_parts) if birth_parts else "Non renseigne",
    }


def _published_annual_semesters(academic_class: AcademicClass) -> list[Semester]:
    from academics.services.workflow import get_semester_permissions

    try:
        semesters = get_annual_semesters(academic_class)
    except ValidationError as exc:
        raise Http404(str(exc)) from exc
    for semester in semesters:
        if not get_semester_permissions(semester)["can_generate_reports"]:
            raise Http404("Les releves annuels ne sont disponibles qu'apres publication.")
    return semesters


def _official_semester_rows(decision: StudentYearDecision, semesters: list[Semester]) -> list[dict]:
    snapshots = {
        snapshot.get("number"): snapshot
        for snapshot in (decision.synthesis_snapshot or {}).get("semesters", [])
    }
    rows = []
    for semester in semesters:
        snapshot = snapshots.get(semester.number, {})
        rows.append(
            {
                "semester": semester,
                "average": format_decimal(snapshot.get("average")),
                "credits": format_decimal(snapshot.get("credit_obtained")),
                "credits_required": format_decimal(snapshot.get("credit_required")),
                "is_validated": bool(snapshot.get("is_validated")),
                "status": "VALIDE" if snapshot.get("is_validated") else "NON VALIDE",
            }
        )
    return rows


def _annual_decision_label(decision: StudentYearDecision) -> str:
    return (decision.synthesis_snapshot or {}).get("academic_decision") or decision.get_decision_display()


def build_annual_class_report(class_id: int) -> dict:
    """Build an official, historical annual class report.

    Values come from the final annual deliberation snapshot, never from a
    student's current enrollment or a fresh recalculation of historic grades.
    """
    academic_class = get_object_or_404(
        AcademicClass.objects.select_related("academic_year", "programme", "branch"),
        id=class_id,
    )
    semesters = _published_annual_semesters(academic_class)
    decisions = (
        StudentYearDecision.objects.select_related(
            "student__user",
            "student__inscription__candidature",
            "source_enrollment__programme",
        )
        .filter(
            current_class=academic_class,
            academic_year=academic_class.academic_year,
            is_final=True,
        )
        .exclude(synthesis_snapshot={})
        .order_by(
            "student__inscription__candidature__last_name",
            "student__inscription__candidature__first_name",
        )
    )
    programme = academic_class.programme
    return {
        "students": [
            {
                "student": decision.student,
                "semesters": _official_semester_rows(decision, semesters),
                "decision": _annual_decision_label(decision),
                "observation": decision.reason,
            }
            for decision in decisions
        ],
        "semesters": semesters,
        "academic_class": academic_class,
        "academic_year": academic_class.academic_year,
        "formation": SimpleNamespace(name=programme.title if programme else ""),
    }


def build_student_annual_report(student_id: int, academic_year_id: int | None = None) -> dict:
    """Return the exact final decision selected by academic year, if supplied."""
    student = _resolve_student(student_id)
    decisions = StudentYearDecision.objects.select_related(
        "source_enrollment__academic_class",
        "source_enrollment__academic_year",
        "source_enrollment__programme",
    ).filter(student=student, is_final=True).exclude(synthesis_snapshot={})
    if academic_year_id is not None:
        decisions = decisions.filter(academic_year_id=academic_year_id)
    decision = decisions.order_by("-academic_year__start_date", "-id").first()
    if decision is None or decision.source_enrollment_id is None:
        raise Http404("Aucun releve annuel officiel n'est disponible pour cet etudiant.")

    enrollment = decision.source_enrollment
    semesters = _published_annual_semesters(enrollment.academic_class)
    programme = enrollment.programme
    return {
        "student": student,
        "enrollment": enrollment,
        "academic_class": enrollment.academic_class,
        "academic_year": enrollment.academic_year,
        "formation": SimpleNamespace(name=programme.title if programme else ""),
        "semesters": _official_semester_rows(decision, semesters),
        "decision": _annual_decision_label(decision),
        "observation": decision.reason,
    }
