
# ==================================================
# FILE: academics/services/ue.py
# ==================================================

from decimal import Decimal, ROUND_HALF_UP

from academics.services.grading import calculate_ec_grade, resolve_ec_threshold, resolve_threshold, validate_average


TWO_PLACES = Decimal("0.01")


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
    expected_grades = 0
    entered_grades = 0
    missing_grades = 0
    failed_subjects = []

    grades_by_ec_id = {
        grade.ec_id: grade
        for grade in ECGrade.objects.filter(enrollment=enrollment, ec__ue=ue).select_related("ec")
    }
    class_threshold = resolve_threshold(enrollment)

    rows = []

    for ec in ecs:
        grade = grades_by_ec_id.get(ec.id)

        expected_grades += 1
        note = None
        if grade:
            if grade.retake_score is not None and grade.normal_score is not None:
                note = max(grade.normal_score, grade.retake_score)
            elif grade.retake_score is not None:
                note = grade.retake_score
            else:
                note = grade.normal_score
        has_score = note is not None
        if has_score:
            entered_grades += 1
        else:
            missing_grades += 1
        ec_threshold = resolve_ec_threshold(ec.coefficient)
        ec_result = calculate_ec_grade(
            note=note,
            coefficient=ec.coefficient,
            credit_required=ec.credit_required,
            threshold=ec_threshold,
        )
        note_coefficient = ec_result["note_coefficient"]
        credit_obtained = ec_result["credit_obtained"]
        is_validated = ec_result["is_validated"]
        if has_score and not is_validated:
            failed_subjects.append(
                {
                    "ec": ec,
                    "score": note,
                    "credit_required": ec.credit_required,
                    "credit_obtained": credit_obtained,
                }
            )

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
        if total_coefficients > 0 and missing_grades == 0 else None
    )
    if ue_average is not None:
        ue_average = ue_average.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        validate_average(ue_average, f"Moyenne UE {ue.code}")
    is_complete = missing_grades == 0 and expected_grades > 0
    is_validated = bool(
        is_complete
        and ue_average is not None
        and ue_average >= class_threshold
        and total_obtained_credits >= Decimal(str(ue.credit_required or 0))
    )

    return {
        "ue": ue,
        "rows": rows,
        "average": ue_average,
        "total_coefficients": total_coefficients,
        "total_note_coefficients": total_note_coefficients,
        "credit_required": ue.credit_required,
        "credit_obtained": total_obtained_credits,
        "expected_grades": expected_grades,
        "entered_grades": entered_grades,
        "missing_grades": missing_grades,
        "is_complete": is_complete,
        "is_validated": is_validated,
        "failed_subjects": failed_subjects,
        "status": "incomplete" if not is_complete else ("validated" if is_validated else "failed"),
    }
