
# ==================================================
# FILE: academics/services/ue.py
# ==================================================

from decimal import Decimal


def compute_ue_result(ue, enrollment):
    """
    Calcule le résultat global d'une UE pour un étudiant.

    La moyenne UE = somme(note_coefficient EC) / somme(coefficients EC)
    Les crédits obtenus UE = somme(crédits obtenus EC)
    """
    from academics.models import ECGrade

    ecs = ue.ecs.all().order_by("id")

    total_coefficients = Decimal("0.00")
    total_note_coefficients = Decimal("0.00")
    total_obtained_credits = Decimal("0.00")

    grades_by_ec_id = {
        grade.ec_id: grade
        for grade in ECGrade.objects.filter(enrollment=enrollment, ec__ue=ue).select_related("ec")
    }

    rows = []

    for ec in ecs:
        grade = grades_by_ec_id.get(ec.id)

        note = grade.final_score if grade and grade.final_score is not None else Decimal("0.00")
        note_coefficient = grade.note_coefficient if grade and grade.note_coefficient is not None else Decimal("0.00")
        credit_obtained = grade.credit_obtained if grade and grade.credit_obtained is not None else Decimal("0.00")
        is_validated = grade.is_validated if grade else False

        total_coefficients += Decimal(str(ec.coefficient))
        total_note_coefficients += Decimal(str(note_coefficient))
        total_obtained_credits += Decimal(str(credit_obtained))

        rows.append({
            "ec": ec,
            "note": note,
            "note_coefficient": note_coefficient,
            "credit_required": ec.credit_required,
            "credit_obtained": credit_obtained,
            "is_validated": is_validated,
        })

    ue_average = (
        total_note_coefficients / total_coefficients
        if total_coefficients > 0 else Decimal("0.00")
    )

    return {
        "ue": ue,
        "rows": rows,
        "average": ue_average,
        "total_coefficients": total_coefficients,
        "total_note_coefficients": total_note_coefficients,
        "credit_required": ue.credit_required,
        "credit_obtained": total_obtained_credits,
    }
