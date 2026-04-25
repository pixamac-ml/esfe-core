# ==================================================
# FILE: academics/services/semester.py
# ==================================================

from decimal import Decimal

from .ue import compute_ue_result


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

    for ue in ues:
        ue_result = compute_ue_result(ue, enrollment)
        ue_results.append(ue_result)

        total_ue_coefficients += Decimal(str(ue.coefficient))
        total_ue_note_coefficients += Decimal(str(ue_result["average"])) * Decimal(str(ue.coefficient))
        total_required_credits += Decimal(str(ue.credit_required or 0))

    semester_average = (
        total_ue_note_coefficients / total_ue_coefficients
        if total_ue_coefficients > 0 else Decimal("0.00")
    )

    threshold = Decimal(str(semester.academic_class.validation_threshold or 0))
    if threshold <= Decimal("0.00"):
        threshold = Decimal("10.00")

    if semester_average >= threshold:
        total_obtained_credits = total_required_credits
    else:
        total_obtained_credits = (
            (semester_average * total_required_credits) / threshold
            if total_required_credits > 0 else Decimal("0.00")
        )

    percentage = (
        (total_obtained_credits / total_required_credits) * Decimal("100")
        if total_required_credits > 0 else Decimal("0.00")
    )

    is_validated = semester_average >= threshold

    return {
        "semester": semester,
        "ue_results": ue_results,
        "average": semester_average,
        "percentage": percentage,
        "credit_required": total_required_credits,
        "credit_obtained": total_obtained_credits,
        "total_coefficients": total_ue_coefficients,
        "is_validated": is_validated,
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

    results.sort(key=lambda item: item["average"], reverse=True)

    last_average = None
    current_rank = 0

    for index, item in enumerate(results, start=1):
        if last_average is None or item["average"] != last_average:
            current_rank = index
        item["rank"] = current_rank
        last_average = item["average"]

    return results

