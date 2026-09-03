from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from unidecode import unidecode

from academics.models import AcademicClass, AcademicEnrollment, EC, ECGrade, Semester
from academics.services.grading import apply_ec_grade, compute_ec_status, resolve_ec_threshold
from academics.imports.template_service import (
    IMPORT_WORKBOOK_SCHEMA,
    get_notes_workbook_signature,
)


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


def _is_empty_score_value(value: Any) -> bool:
    try:
        import pandas as pd
    except Exception:  # pragma: no cover
        pd = None

    if pd is not None and pd.isna(value):
        return True
    if value in (None, ""):
        return True
    raw = str(value).strip()
    return not raw


def _to_decimal_score(value: Any) -> Decimal | None:
    if _is_empty_score_value(value):
        return None
    raw = str(value).strip().replace(",", ".")
    try:
        score = Decimal(raw)
    except (InvalidOperation, ValueError):
        return None
    return score


def _validate_official_workbook(*, file, academic_class, semester, session_type):
    """Reject a workbook that was not generated for this exact notes grid."""
    filename = (getattr(file, "name", "") or "").lower()
    if not filename.endswith(".xlsx"):
        raise ValueError("Le fichier doit etre un modele Excel ESFE au format .xlsx.")

    try:
        from openpyxl import load_workbook
        if hasattr(file, "seek"):
            file.seek(0)
        workbook = load_workbook(file, read_only=True, data_only=True)
    except Exception as exc:
        raise ValueError("Fichier Excel .xlsx invalide ou illisible.") from exc

    try:
        if "_ESFE_META" not in workbook.sheetnames:
            raise ValueError("Modele Excel ESFE invalide. Telechargez un nouveau modele depuis la grille.")
        metadata = dict(workbook["_ESFE_META"].iter_rows(min_col=1, max_col=2, values_only=True))
        expected_metadata = {
            "schema": IMPORT_WORKBOOK_SCHEMA,
            "class_id": academic_class.id,
            "semester_id": semester.id,
            "session_type": session_type,
            "signature": get_notes_workbook_signature(
                academic_class_id=academic_class.id,
                semester_id=semester.id,
                session_type=session_type,
            ),
        }
        for key, expected_value in expected_metadata.items():
            if str(metadata.get(key, "")).strip() != str(expected_value):
                raise ValueError(
                    "Le fichier ne correspond pas a la classe, au semestre ou a la session selectionnee."
                )
    finally:
        workbook.close()
        if hasattr(file, "seek"):
            file.seek(0)



@transaction.atomic
def import_grades(
    file,
    academic_class: AcademicClass,
    semester: Semester,
    *,
    session_type: str = "normal",
) -> ImportGradesResult:
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

    session_type = (session_type or "normal").strip().lower()
    if session_type not in {"normal", "retake"}:
        raise ValidationError("Type de session de notes invalide.")
    expected_status = (
        Semester.STATUS_RETAKE_ENTRY
        if session_type == "retake"
        else Semester.STATUS_NORMAL_ENTRY
    )
    if semester.status != expected_status:
        label = "rattrapage" if session_type == "retake" else "normale"
        raise ValidationError(
            f"L'import de la session {label} est verrouille pour ce semestre "
            f"(statut actuel: {semester.get_status_display()})."
        )

    _validate_official_workbook(
        file=file,
        academic_class=academic_class,
        semester=semester,
        session_type=session_type,
    )

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
    if not semester_ecs:
        raise ValueError("Aucun EC n'est configure pour ce semestre.")

    identity_headers = {"ENROLLMENT_ID", "MATRICULE", "NOM", "PRENOM"}
    expected_ec_headers = {
        _normalize_text(f"NOTE /20 - {_get_ec_human_label(ec)}"): ec
        for ec in semester_ecs
    }
    actual_headers = {_normalize_text(header) for header in headers}
    expected_headers = identity_headers | set(expected_ec_headers)
    missing_headers = expected_headers - actual_headers
    unexpected_headers = actual_headers - expected_headers
    if missing_headers or unexpected_headers:
        details = []
        if missing_headers:
            details.append(f"colonnes manquantes: {', '.join(sorted(missing_headers))}")
        if unexpected_headers:
            details.append(f"colonnes inconnues: {', '.join(sorted(unexpected_headers))}")
        raise ValueError(
            "Structure du modele Excel invalide (" + "; ".join(details) + "). "
            "Telechargez un nouveau modele depuis la grille."
        )

    ec_col_map: dict[str, EC] = {
        header: expected_ec_headers[_normalize_text(header)]
        for header in headers
        if _normalize_text(header) in expected_ec_headers
    }

    enrollments_by_name: dict[tuple[str, str], list[AcademicEnrollment]] = {}
    enrollments_by_id: dict[str, AcademicEnrollment] = {}
    enrollments_by_matricule: dict[str, AcademicEnrollment] = {}
    # Lock only academic-enrollment rows.  The joined profile/candidature
    # relations can be absent in legacy data, which makes PostgreSQL render
    # nullable OUTER JOINs that cannot be targets of a bare FOR UPDATE.
    for enr in AcademicEnrollment.objects.select_for_update(of=("self",)).select_related(
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
            if not _is_empty_score_value(row.get(column_name)):
                return True
        return False

    pending_updates: list[tuple[AcademicEnrollment, EC, Decimal]] = []
    seen_enrollment_rows: dict[int, int] = {}

    for _idx, row in df.iterrows():
        excel_row_number = int(_idx) + 6
        nom = _normalize_text(row.get(nom_column))
        prenom = _normalize_text(row.get(prenom_column))
        enrollment_value = row.get(enrollment_id_column) if enrollment_id_column else None
        enrollment_id = "" if _is_empty_score_value(enrollment_value) else str(enrollment_value).strip()
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

        if _row_has_data(row) and enrollment.id in seen_enrollment_rows:
            result.skipped_unknown_students += 1
            result.student_issues.append({
                "row_number": excel_row_number,
                "nom": display_nom,
                "prenom": display_prenom,
                "reason": "duplicate_enrollment",
                "message": (
                    "Etudiant duplique dans le fichier "
                    f"(deja present a la ligne {seen_enrollment_rows[enrollment.id]})."
                ),
            })
            continue
        if _row_has_data(row):
            seen_enrollment_rows[enrollment.id] = excel_row_number

        for column_name, ec in ec_col_map.items():
            value = row.get(column_name)
            score = _to_decimal_score(value)
            if score is None:
                if _is_empty_score_value(value):
                    result.skipped_empty += 1
                    continue
                result.skipped_invalid_scores += 1
                result.student_issues.append({
                    "row_number": excel_row_number,
                    "nom": display_nom,
                    "prenom": display_prenom,
                    "reason": "invalid_score",
                    "message": f"Note invalide pour {ec.title}: {value}. Saisissez un nombre entre 0 et 20.",
                })
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

            normalized_score = score.quantize(Decimal("0.01"))
            if score != normalized_score:
                result.skipped_invalid_scores += 1
                result.student_issues.append({
                    "row_number": excel_row_number,
                    "nom": display_nom,
                    "prenom": display_prenom,
                    "reason": "invalid_precision",
                    "message": (
                        f"Note invalide pour {ec.title}: {value}. "
                        "Utilisez au maximum deux decimales (exemple : 12,50)."
                    ),
                })
                continue
            score = normalized_score

            if session_type == "retake":
                existing_grade = ECGrade.objects.filter(enrollment=enrollment, ec=ec).first()
                threshold = resolve_ec_threshold(ec.coefficient)
                is_eligible = bool(
                    existing_grade
                    and existing_grade.normal_score is not None
                    and compute_ec_status(existing_grade.normal_score, threshold) == "failed"
                )
                if not is_eligible:
                    result.skipped_invalid_scores += 1
                    result.student_issues.append({
                        "row_number": excel_row_number,
                        "nom": display_nom,
                        "prenom": display_prenom,
                        "reason": "retake_not_allowed",
                        "message": f"Rattrapage non autorise pour {ec.title}.",
                    })
                    continue

            pending_updates.append((enrollment, ec, score))

    if result.skipped_invalid_scores or result.skipped_unknown_students:
        return result

    for enrollment, ec, score in pending_updates:
        grade, _created = ECGrade.objects.get_or_create(
            enrollment=enrollment,
            ec=ec,
        )
        if session_type == "retake":
            grade.retake_score = score
        else:
            grade.normal_score = score
        apply_ec_grade(grade)
        grade.save()
        result.updated += 1

    return result

