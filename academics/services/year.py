from decimal import Decimal

from django.http import Http404
from django.shortcuts import get_object_or_404

from academics.models import AcademicEnrollment, AcademicYear
from academics.services.semester import compute_semester_result
from students.models import Student


def _format_decimal(value):
    if value in (None, ""):
        return "0,00"
    return f"{Decimal(value):.2f}".replace(".", ",")


def _resolve_student(student):
    if isinstance(student, Student):
        return student

    student_obj = (
        Student.objects.select_related("user")
        .filter(id=student)
        .first()
    )
    if student_obj:
        return student_obj

    return get_object_or_404(
        Student.objects.select_related("user"),
        user_id=student,
    )


def _resolve_academic_year(academic_year):
    if isinstance(academic_year, AcademicYear):
        return academic_year

    return get_object_or_404(AcademicYear, id=academic_year)


def _decision_from_semesters(s1_validated, s2_validated):
    if s1_validated and s2_validated:
        return "ADMIS"
    if s1_validated or s2_validated:
        return "ADMISSIBLE"
    return "DOUBLE"


def compute_year_result(student, academic_year):
    # Resolve input early so the service stays usable from views or other services.
    student_obj = _resolve_student(student)
    academic_year_obj = _resolve_academic_year(academic_year)

    enrollments = (
        AcademicEnrollment.objects.select_related(
            "student",
            "academic_class",
            "academic_year",
            "programme",
            "branch",
        )
        .filter(
            student=student_obj.user,
            academic_year=academic_year_obj,
            is_active=True,
        )
        .order_by("academic_class__level", "-id")
    )
    enrollment = enrollments.first()
    if enrollment is None:
        raise Http404("Aucune inscription active trouvée pour cet étudiant sur cette année académique.")

    semesters = {
        semester.number: semester
        for semester in enrollment.academic_class.semesters.all().order_by("number")
    }

    s1_result = compute_semester_result(semesters[1], enrollment) if 1 in semesters else None
    s2_result = compute_semester_result(semesters[2], enrollment) if 2 in semesters else None

    s1_validated = bool(s1_result and s1_result.get("is_validated"))
    s2_validated = bool(s2_result and s2_result.get("is_validated"))

    return {
        "student": student_obj,
        "academic_year": academic_year_obj,
        "enrollment": enrollment,
        "S1": {
            "semester": semesters.get(1),
            "result": s1_result,
            "average_display": _format_decimal(s1_result.get("average")) if s1_result else "0,00",
            "status": "VALIDÉ" if s1_validated else "NON VALIDÉ",
            "is_validated": s1_validated,
        },
        "S2": {
            "semester": semesters.get(2),
            "result": s2_result,
            "average_display": _format_decimal(s2_result.get("average")) if s2_result else "0,00",
            "status": "VALIDÉ" if s2_validated else "NON VALIDÉ",
            "is_validated": s2_validated,
        },
        "decision": _decision_from_semesters(s1_validated, s2_validated),
    }
