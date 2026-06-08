# ==================================================
# FILE: academics/services/semester.py
# ==================================================

from decimal import Decimal, ROUND_HALF_UP

from academics.services.grading import resolve_threshold, validate_average
from .ue import compute_ue_result


TWO_PLACES = Decimal("0.01")


def compute_semester_result(semester, enrollment):
    """
    Calcule le résultat global d'un semestre.

    Moyenne semestre = somme(note_coefficient UE) / somme(coefficients UE)
    Pourcentage = (crédits obtenus / crédits requis semestre) * 100
    """
    ues = semester.ues.all().order_by("id")

    ue_results = []
    total_ue_coefficients = Decimal("0.00")
    total_ue_note_coefficients = Decimal("0.00")
    total_required_credits = Decimal("0.00")
    total_obtained_credits = Decimal("0.00")
    expected_grades = 0
    entered_grades = 0
    missing_grades = 0
    failed_ues = []
    failed_subjects = []

    for ue in ues:
        ue_result = compute_ue_result(ue, enrollment)
        ue_results.append(ue_result)

        total_ue_coefficients += Decimal(str(ue.coefficient))
        if ue_result["average"] is not None:
            total_ue_note_coefficients += Decimal(str(ue_result["average"])) * Decimal(str(ue.coefficient))
        total_required_credits += Decimal(str(ue.credit_required or 0))
        total_obtained_credits += Decimal(str(ue_result["credit_obtained"] or 0))
        expected_grades += ue_result.get("expected_grades", 0)
        entered_grades += ue_result.get("entered_grades", 0)
        missing_grades += ue_result.get("missing_grades", 0)
        failed_subjects.extend(ue_result.get("failed_subjects", []))
        if ue_result.get("is_complete") and not ue_result.get("is_validated"):
            failed_ues.append(ue_result)

    semester_average = (
        total_ue_note_coefficients / total_ue_coefficients
        if total_ue_coefficients > 0 and missing_grades == 0 else None
    )
    if semester_average is not None:
        semester_average = semester_average.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        validate_average(semester_average, f"Moyenne semestre S{semester.number}")

    threshold = resolve_threshold(enrollment)

    percentage = (
        (total_obtained_credits / total_required_credits) * Decimal("100")
        if total_required_credits > 0 else Decimal("0.00")
    ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

    is_complete = missing_grades == 0 and expected_grades > 0
    is_validated = bool(
        is_complete
        and semester_average is not None
        and semester_average >= threshold
        and total_obtained_credits >= total_required_credits
    )
    blocking_reasons = []
    if missing_grades:
        blocking_reasons.append(f"{missing_grades} note(s) manquante(s).")
    if expected_grades == 0:
        blocking_reasons.append("Aucun EC configure pour ce semestre.")
    if is_complete and semester_average is not None and semester_average < threshold:
        blocking_reasons.append("Moyenne sous le seuil de validation.")
    if is_complete and total_obtained_credits < total_required_credits:
        blocking_reasons.append("Credits requis non entierement valides.")

    return {
        "semester": semester,
        "ue_results": ue_results,
        "average": semester_average,
        "percentage": percentage,
        "credit_required": total_required_credits,
        "credit_obtained": total_obtained_credits,
        "total_coefficients": total_ue_coefficients,
        "is_validated": is_validated,
        "is_complete": is_complete,
        "expected_grades": expected_grades,
        "entered_grades": entered_grades,
        "missing_grades": missing_grades,
        "failed_ues": failed_ues,
        "failed_subjects": failed_subjects,
        "blocking_reasons": blocking_reasons,
        "status": "incomplete" if not is_complete else ("validated" if is_validated else "failed"),
    }


def compute_class_ranking(semester, enrollments):
    """
    Classe les étudiants d'une classe pour un semestre donné.
    Gestion simple des ex-aequo : mêmes moyennes = même rang.
    """
    results = []

    for enrollment in enrollments:
        semester_result = compute_semester_result(semester, enrollment)
        results.append({
            "enrollment": enrollment,
            "average": semester_result["average"],
            "percentage": semester_result["percentage"],
            "credit_obtained": semester_result["credit_obtained"],
        })

    results.sort(
        key=lambda item: (
            item["average"] is not None,
            item["average"] or Decimal("0.00"),
        ),
        reverse=True,
    )

    last_average = None
    current_rank = 0

    for index, item in enumerate(results, start=1):
        if last_average is None or item["average"] != last_average:
            current_rank = index
        item["rank"] = current_rank
        last_average = item["average"]

    return results

