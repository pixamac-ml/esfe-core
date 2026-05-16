from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from unidecode import unidecode

from academics.models import AcademicClass, AcademicEnrollment, EC, ECGrade, Semester
from academics.services.grading import apply_ec_grade


@dataclass
class ImportGradesResult:
    updated: int = 0
    skipped_empty: int = 0
    skipped_unknown_columns: int = 0
    skipped_unknown_students: int = 0
    skipped_invalid_scores: int = 0
    unknown_columns: list[str] = field(default_factory=list)
    student_issues: list[dict[str, Any]] = field(default_factory=list)


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\ufeff", " ").strip()
    if not text:
        return ""
    return " ".join(unidecode(text).upper().split())


def _get_ec_human_label(ec: EC) -> str:
    return f"{ec.ue.code} - {ec.title}"


def _resolve_ec_column(header: str, ecs: list[EC]) -> EC | None:
    normalized_header = _normalize_text(header)
    if not normalized_header:
        return None
    for prefix in ("NOTE /20 - ", "NOTE SUR 20 - ", "NOTE - "):
        if normalized_header.startswith(prefix):
            normalized_header = normalized_header[len(prefix):].strip()

    exact_label_map = {
        _normalize_text(_get_ec_human_label(ec)): ec
        for ec in ecs
    }
    if normalized_header in exact_label_map:
        return exact_label_map[normalized_header]

    title_candidate = normalized_header.split(" - ", 1)[-1].strip()
    title_matches = [ec for ec in ecs if _normalize_text(ec.title) == title_candidate]
    if len(title_matches) == 1:
        return title_matches[0]

    contains_matches = [
        ec for ec in ecs
        if title_candidate and title_candidate in _normalize_text(ec.title)
    ]
    if len(contains_matches) == 1:
        return contains_matches[0]

    return None


def _to_decimal_score(value: Any) -> Decimal | None:
    try:
        import pandas as pd
    except Exception:  # pragma: no cover
        pd = None

    if pd is not None and pd.isna(value):
        return None
    if value in (None, ""):
        return None
    raw = str(value).strip()
    if not raw:
        return None
    raw = raw.replace(",", ".")
    try:
        score = Decimal(raw)
    except (InvalidOperation, ValueError):
        return None
    return score



@transaction.atomic
def import_grades(file, academic_class: AcademicClass, semester: Semester) -> ImportGradesResult:
    """Importe les notes depuis un Excel simple et lisible.

    Format supporté:
    - 4 lignes de contexte ignorées
    - NOM
    - PRENOM
    - colonnes matières de type `UE.code - EC.title`

    Le mapping étudiant se fait par NOM/PRENOM dans la classe sélectionnée.
    """

    if semester.academic_class_id != academic_class.id:
        raise ValueError("Le semestre ne correspond pas à la classe académique.")

    import pandas as pd

    if hasattr(file, "seek"):
        file.seek(0)

    df = pd.read_excel(file, skiprows=4, dtype=object)
    df.columns = pd.Index([
        str(col).replace("\ufeff", "").strip()
        for col in df.columns
    ])

    result = ImportGradesResult()

    headers = list(df.columns)

    normalized_columns = {
        _normalize_text(column): column
        for column in headers
    }

    if "NOM" not in normalized_columns or "PRENOM" not in normalized_columns:
        raise ValueError("Template invalide: colonnes NOM et PRENOM obligatoires.")

    nom_column = normalized_columns["NOM"]
    prenom_column = normalized_columns["PRENOM"]
    enrollment_id_column = normalized_columns.get("ENROLLMENT_ID")
    matricule_column = normalized_columns.get("MATRICULE")

    semester_ecs = list(EC.objects.filter(ue__semester=semester).select_related("ue").order_by("ue__id", "id"))
    ec_col_map: dict[str, EC] = {}
    for header in headers:
        if header in {nom_column, prenom_column, enrollment_id_column, matricule_column}:
            continue
        ec = _resolve_ec_column(header, semester_ecs)
        if ec is None:
            result.skipped_unknown_columns += 1
            result.unknown_columns.append(header)
            continue
        ec_col_map[header] = ec

    enrollments_by_name: dict[tuple[str, str], list[AcademicEnrollment]] = {}
    enrollments_by_id: dict[str, AcademicEnrollment] = {}
    enrollments_by_matricule: dict[str, AcademicEnrollment] = {}
    for enr in AcademicEnrollment.objects.select_related(
        "student__student_profile__inscription__candidature",
        "inscription__candidature",
    ).filter(
        academic_class=academic_class,
        academic_year=academic_class.academic_year,
        is_active=True,
    ):
        candidature = enr.inscription.candidature
        key = (
            _normalize_text(getattr(candidature, "last_name", "")),
            _normalize_text(getattr(candidature, "first_name", "")),
        )
        enrollments_by_name.setdefault(key, []).append(enr)
        enrollments_by_id[str(enr.id)] = enr
        student_profile = getattr(enr.student, "student_profile", None)
        matricule = _normalize_text(getattr(student_profile, "matricule", ""))
        if matricule:
            enrollments_by_matricule[matricule] = enr

    def _row_has_data(row) -> bool:
        for column_name in ec_col_map.keys():
            if _to_decimal_score(row.get(column_name)) is not None:
                return True
        return False

    pending_updates: list[tuple[AcademicEnrollment, EC, Decimal]] = []

    for _idx, row in df.iterrows():
        excel_row_number = int(_idx) + 6
        nom = _normalize_text(row.get(nom_column))
        prenom = _normalize_text(row.get(prenom_column))
        enrollment_id = str(row.get(enrollment_id_column) or "").strip() if enrollment_id_column else ""
        if enrollment_id.endswith(".0"):
            enrollment_id = enrollment_id[:-2]
        matricule = _normalize_text(row.get(matricule_column)) if matricule_column else ""
        display_nom = str(row.get(nom_column) or "").strip()
        display_prenom = str(row.get(prenom_column) or "").strip()

        if not enrollment_id and not matricule and not nom and not prenom:
            if _row_has_data(row):
                result.skipped_unknown_students += 1
                result.student_issues.append({
                    "row_number": excel_row_number,
                    "nom": display_nom,
                    "prenom": display_prenom,
                    "reason": "missing_identity",
                    "message": "Ligne avec notes mais sans ENROLLMENT_ID, MATRICULE, NOM ou PRENOM.",
                })
            continue

        enrollment = None
        if enrollment_id:
            enrollment = enrollments_by_id.get(enrollment_id)
            if enrollment is None:
                result.skipped_unknown_students += 1
                result.student_issues.append({
                    "row_number": excel_row_number,
                    "nom": display_nom,
                    "prenom": display_prenom,
                    "reason": "enrollment_not_found",
                    "message": "Identifiant d'inscription academique introuvable dans la classe selectionnee.",
                })
                continue

        if enrollment is None and matricule:
            enrollment = enrollments_by_matricule.get(matricule)
            if enrollment is None:
                result.skipped_unknown_students += 1
                result.student_issues.append({
                    "row_number": excel_row_number,
                    "nom": display_nom,
                    "prenom": display_prenom,
                    "reason": "matricule_not_found",
                    "message": "Matricule introuvable dans la classe selectionnee.",
                })
                continue

        matching_enrollments = [] if enrollment is not None else enrollments_by_name.get((nom, prenom), [])
        if enrollment is None and not matching_enrollments:
            result.skipped_unknown_students += 1
            result.student_issues.append({
                "row_number": excel_row_number,
                "nom": display_nom,
                "prenom": display_prenom,
                "reason": "not_found",
                "message": "Étudiant introuvable dans la classe sélectionnée.",
            })
            continue

        if enrollment is None and len(matching_enrollments) > 1:
            result.skipped_unknown_students += 1
            result.student_issues.append({
                "row_number": excel_row_number,
                "nom": display_nom,
                "prenom": display_prenom,
                "reason": "ambiguous",
                "matches_count": len(matching_enrollments),
                "message": "Plusieurs étudiants correspondent à ce NOM/PRENOM dans la classe.",
            })
            continue

        if enrollment is None:
            enrollment = matching_enrollments[0]

        for column_name, ec in ec_col_map.items():
            value = row.get(column_name)
            score = _to_decimal_score(value)
            if score is None:
                result.skipped_empty += 1
                continue
            if score < Decimal("0") or score > Decimal("20"):
                result.skipped_invalid_scores += 1
                result.student_issues.append({
                    "row_number": excel_row_number,
                    "nom": display_nom,
                    "prenom": display_prenom,
                    "reason": "invalid_score",
                    "message": f"Note invalide pour {ec.title}: {value}. La note doit etre comprise entre 0 et 20.",
                })
                continue

            pending_updates.append((enrollment, ec, score))

    if result.skipped_invalid_scores or result.skipped_unknown_students:
        return result

    for enrollment, ec, score in pending_updates:
        grade, _created = ECGrade.objects.update_or_create(
            enrollment=enrollment,
            ec=ec,
            defaults={"normal_score": score},
        )
        apply_ec_grade(grade)
        grade.save()
        result.updated += 1

    return result

