from __future__ import annotations

import io

from django.db.models import QuerySet

from academics.models import AcademicClass, AcademicEnrollment, EC, Semester


def _get_class_enrollments(academic_class: AcademicClass) -> QuerySet[AcademicEnrollment]:
    return (
        AcademicEnrollment.objects.filter(
            academic_class=academic_class,
            academic_year=academic_class.academic_year,
            is_active=True,
        )
        .select_related(
            "student__student_profile__inscription__candidature",
            "student",
            "academic_class",
            "academic_year",
        )
        .order_by(
            "student__student_profile__inscription__candidature__last_name",
            "student__student_profile__inscription__candidature__first_name",
        )
    )


def _get_semester_ecs(semester: Semester) -> QuerySet[EC]:
    return (
        EC.objects.filter(ue__semester=semester)
        .select_related("ue")
        .order_by("ue__id", "id")
    )


def _get_student_last_name(enrollment: AcademicEnrollment) -> str:
    profile = getattr(enrollment.student, "student_profile", None)
    candidature = getattr(getattr(profile, "inscription", None), "candidature", None) if profile else None
    return (getattr(candidature, "last_name", "") or "").strip()


def _get_student_first_name(enrollment: AcademicEnrollment) -> str:
    profile = getattr(enrollment.student, "student_profile", None)
    candidature = getattr(getattr(profile, "inscription", None), "candidature", None) if profile else None
    return (getattr(candidature, "first_name", "") or "").strip()


def _get_ec_human_label(ec: EC) -> str:
    return f"{ec.ue.code} - {ec.title}"


def generate_import_template(academic_class: AcademicClass, semester: Semester) -> io.BytesIO:
    """Génère un template Excel humain pour l'import des notes.

    Format imposé:
    - 4 lignes de contexte ignorables
    - NOM
    - PRENOM
    - une colonne matière par EC: `UE.code - EC.title`
    """

    if semester.academic_class_id != academic_class.id:
        raise ValueError("Le semestre ne correspond pas à la classe académique.")

    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = f"Import S{semester.number}"

    enrollments = list(_get_class_enrollments(academic_class))
    ecs = list(_get_semester_ecs(semester))

    ws.append(["Ecole", "ESFE"])
    ws.append(["Classe", academic_class.display_name])
    ws.append(["Année académique", str(academic_class.academic_year)])
    ws.append(["Semestre", f"Semestre {semester.number}"])

    headers = ["NOM", "PRENOM", *[_get_ec_human_label(ec) for ec in ecs]]
    ws.append(headers)

    header_fill = PatternFill("solid", fgColor="1F2937")
    header_font = Font(color="FFFFFF", bold=True)
    align_center = Alignment(horizontal="center", vertical="center")
    align_left = Alignment(horizontal="left", vertical="center")

    header_row = 5
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=header_row, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = align_center

    for enrollment in enrollments:
        ws.append([
            _get_student_last_name(enrollment),
            _get_student_first_name(enrollment),
            *([""] * len(ecs)),
        ])

    ws.freeze_panes = "A6"
    ws.column_dimensions["A"].width = 16
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 18
    for col_idx in range(3, len(headers) + 1):
        ws.column_dimensions[ws.cell(row=header_row, column=col_idx).column_letter].width = 24

    for row_idx in range(6, ws.max_row + 1):
        ws.cell(row=row_idx, column=1).alignment = align_left
        ws.cell(row=row_idx, column=2).alignment = align_left
        for col_idx in range(3, len(headers) + 1):
            ws.cell(row=row_idx, column=col_idx).alignment = align_center
            ws.cell(row=row_idx, column=col_idx).number_format = "0.00"

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output

