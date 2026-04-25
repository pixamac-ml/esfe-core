from decimal import Decimal
from types import SimpleNamespace

from django.http import Http404
from django.shortcuts import get_object_or_404

from academics.models import AcademicClass, AcademicEnrollment, Semester
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
        first_name = getattr(student.user, "first_name", "")
        last_name = getattr(student.user, "last_name", "")
        return f"{last_name} {first_name}".strip()

    return str(student)


def _resolve_student(student_id):
    student = (
        Student.objects.select_related("user")
        .filter(id=student_id)
        .first()
    )
    if student:
        return student

    return get_object_or_404(
        Student.objects.select_related("user"),
        user_id=student_id,
    )


def _annual_decision(validation_s1, validation_s2):
    if validation_s1 and validation_s2:
        return "Admis"
    if validation_s1 or validation_s2:
        return "Admissible"
    return "Double"


def build_student_semester_report(student_id: int, semester_id: int) -> dict:
    student = _resolve_student(student_id)

    semester = get_object_or_404(
        Semester.objects.select_related("academic_class"),
        id=semester_id,
    )

    enrollment = (
        AcademicEnrollment.objects.select_related(
            "student",
            "academic_class",
            "academic_year",
            "programme",
            "branch",
        )
        .filter(student=student.user, is_active=True)
        .order_by("-id")
    )

    matched_enrollment = enrollment.filter(
        academic_class=semester.academic_class
    ).first()
    if matched_enrollment is None:
        matched_enrollment = enrollment.filter(
            academic_year=semester.academic_class.academic_year
        ).first()
    if matched_enrollment is None:
        matched_enrollment = enrollment.first()
    if matched_enrollment is None:
        raise Http404("Aucune inscription active trouvée pour cet étudiant.")

    semester_result = compute_semester_result(
        semester=semester,
        enrollment=matched_enrollment,
    )

    programme = matched_enrollment.programme
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

    return {
        "student": student,
        "enrollment": matched_enrollment,
        "semester": semester,
        "semester_result": semester_result,
        "academic_year": matched_enrollment.academic_year,
        "formation": programme,
        "programme_name": programme.title if programme else "",
        "department_name": programme.filiere.name if programme and programme.filiere else "",
        "domain_name": programme.cycle.name if programme and programme.cycle else "",
        "student_full_name": get_student_full_name(student),
        "student_matricule": getattr(student, "matricule", "N/A"),
        "student_last_name": getattr(student.user, "last_name", ""),
        "student_first_name": getattr(student.user, "first_name", ""),
        "student_birth_info": getattr(student, "birth_info", "Non renseigne"),
    }


def build_annual_class_report(class_id: int) -> dict:
    from academics.services.workflow import get_semester_permissions

    academic_class = get_object_or_404(
        AcademicClass.objects.select_related(
            "academic_year",
            "programme",
            "branch",
        ),
        id=class_id,
    )

    semesters = {
        semester.number: semester
        for semester in academic_class.semesters.all().order_by("number")
    }
    semester_1 = semesters.get(1)
    semester_2 = semesters.get(2)
    for semester in [semester_1, semester_2]:
        if semester and not get_semester_permissions(semester)["can_generate_reports"]:
            raise Http404("Les releves annuels ne sont disponibles qu'apres publication.")

    enrollments = list(
        AcademicEnrollment.objects.select_related(
            "student",
            "student__student_profile",
            "academic_class",
            "academic_year",
            "programme",
            "branch",
        )
        .filter(
            academic_class=academic_class,
            academic_year=academic_class.academic_year,
            is_active=True,
        )
        .order_by(
            "student__student_profile__inscription__candidature__last_name",
            "student__student_profile__inscription__candidature__first_name",
        )
    )

    sample_s1 = compute_semester_result(semester_1, enrollments[0]) if semester_1 and enrollments else None
    sample_s2 = compute_semester_result(semester_2, enrollments[0]) if semester_2 and enrollments else None

    students = []
    for enrollment in enrollments:
        student = enrollment.student.student_profile
        s1_result = compute_semester_result(semester_1, enrollment) if semester_1 else None
        s2_result = compute_semester_result(semester_2, enrollment) if semester_2 else None

        validation_s1 = bool(s1_result and s1_result.get("is_validated"))
        validation_s2 = bool(s2_result and s2_result.get("is_validated"))

        students.append({
            "student": student,
            "s1": {
                "average": format_decimal(s1_result.get("average")) if s1_result else "0,00",
                "percentage": format_decimal(s1_result.get("percentage")) if s1_result else "0,00",
                "credits": format_decimal(s1_result.get("credit_obtained")) if s1_result else "0,00",
            },
            "s2": {
                "average": format_decimal(s2_result.get("average")) if s2_result else "0,00",
                "percentage": format_decimal(s2_result.get("percentage")) if s2_result else "0,00",
                "credits": format_decimal(s2_result.get("credit_obtained")) if s2_result else "0,00",
            },
            "validation_s1": validation_s1,
            "validation_s2": validation_s2,
            "decision": _annual_decision(validation_s1, validation_s2),
            "observation": "",
        })

    programme = academic_class.programme

    return {
        "students": students,
        "academic_class": academic_class,
        "academic_year": academic_class.academic_year,
        "formation": SimpleNamespace(name=programme.title if programme else ""),
        "S1": {
            "total_credits": format_decimal(sample_s1.get("credit_required")) if sample_s1 else "0,00",
            "total_coefficients": format_decimal(sample_s1.get("total_coefficients")) if sample_s1 else "0,00",
        },
        "S2": {
            "total_credits": format_decimal(sample_s2.get("credit_required")) if sample_s2 else "0,00",
            "total_coefficients": format_decimal(sample_s2.get("total_coefficients")) if sample_s2 else "0,00",
        },
    }


def build_student_annual_report(student_id: int) -> dict:
    from academics.services.workflow import get_semester_permissions

    student = _resolve_student(student_id)

    enrollment = (
        AcademicEnrollment.objects.select_related(
            "student",
            "academic_class",
            "academic_year",
            "programme",
            "branch",
        )
        .filter(student=student.user, is_active=True)
        .order_by("-created_at", "-id")
        .first()
    )
    if enrollment is None:
        raise Http404("Aucune inscription active trouvée pour cet étudiant.")

    semesters = {
        semester.number: semester
        for semester in enrollment.academic_class.semesters.all().order_by("number")
    }
    semester_1 = semesters.get(1)
    semester_2 = semesters.get(2)
    for semester in [semester_1, semester_2]:
        if semester and not get_semester_permissions(semester)["can_generate_reports"]:
            raise Http404("Les releves annuels ne sont disponibles qu'apres publication.")

    s1_result = compute_semester_result(semester_1, enrollment) if semester_1 else None
    s2_result = compute_semester_result(semester_2, enrollment) if semester_2 else None

    validation_s1 = bool(s1_result and s1_result.get("is_validated"))
    validation_s2 = bool(s2_result and s2_result.get("is_validated"))
    programme = enrollment.programme

    return {
        "student": student,
        "academic_class": enrollment.academic_class,
        "academic_year": enrollment.academic_year,
        "formation": SimpleNamespace(name=programme.title if programme else ""),
        "S1": {
            "average": format_decimal(s1_result.get("average")) if s1_result else "0,00",
            "percentage": format_decimal(s1_result.get("percentage")) if s1_result else "0,00",
            "credits": format_decimal(s1_result.get("credit_obtained")) if s1_result else "0,00",
            "is_validated": validation_s1,
        },
        "S2": {
            "average": format_decimal(s2_result.get("average")) if s2_result else "0,00",
            "percentage": format_decimal(s2_result.get("percentage")) if s2_result else "0,00",
            "credits": format_decimal(s2_result.get("credit_obtained")) if s2_result else "0,00",
            "is_validated": validation_s2,
        },
        "decision": _annual_decision(validation_s1, validation_s2),
    }
