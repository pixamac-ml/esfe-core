from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from unidecode import unidecode

from academics.models import AcademicClass, AcademicEnrollment, EC, ECGrade, Semester


@dataclass
class ImportGradesResult:
    updated: int = 0
    skipped_empty: int = 0
    skipped_unknown_columns: int = 0
    skipped_unknown_students: int = 0
    skipped_invalid_scores: int = 0
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

    semester_ecs = list(EC.objects.filter(ue__semester=semester).select_related("ue").order_by("ue__id", "id"))
    ec_col_map: dict[str, EC] = {}
    for header in headers:
        if header in {nom_column, prenom_column}:
            continue
        ec = _resolve_ec_column(header, semester_ecs)
        if ec is None:
            result.skipped_unknown_columns += 1
            continue
        ec_col_map[header] = ec

    enrollments_by_name: dict[tuple[str, str], list[AcademicEnrollment]] = {}
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

    def _row_has_data(row) -> bool:
        for column_name in ec_col_map.keys():
            if _to_decimal_score(row.get(column_name)) is not None:
                return True
        return False

    for _idx, row in df.iterrows():
        excel_row_number = int(_idx) + 6
        nom = _normalize_text(row.get(nom_column))
        prenom = _normalize_text(row.get(prenom_column))
        display_nom = str(row.get(nom_column) or "").strip()
        display_prenom = str(row.get(prenom_column) or "").strip()

        if not nom and not prenom:
            if _row_has_data(row):
                result.skipped_unknown_students += 1
                result.student_issues.append({
                    "row_number": excel_row_number,
                    "nom": display_nom,
                    "prenom": display_prenom,
                    "reason": "missing_identity",
                    "message": "Ligne avec notes mais sans NOM/PRENOM.",
                })
            continue

        matching_enrollments = enrollments_by_name.get((nom, prenom), [])
        if not matching_enrollments:
            result.skipped_unknown_students += 1
            result.student_issues.append({
                "row_number": excel_row_number,
                "nom": display_nom,
                "prenom": display_prenom,
                "reason": "not_found",
                "message": "Étudiant introuvable dans la classe sélectionnée.",
            })
            continue

        if len(matching_enrollments) > 1:
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

        enrollment = matching_enrollments[0]

        for column_name, ec in ec_col_map.items():
            value = row.get(column_name)
            score = _to_decimal_score(value)
            if score is None:
                result.skipped_empty += 1
                continue
            if score < Decimal("0") or score > Decimal("20"):
                result.skipped_invalid_scores += 1
                continue

            ECGrade.objects.update_or_create(
                enrollment=enrollment,
                ec=ec,
                defaults={"normal_score": score},
            )
            result.updated += 1

    return result

