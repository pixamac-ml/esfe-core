from decimal import Decimal

from django.http import Http404
from django.shortcuts import get_object_or_404

from academics.models import AcademicEnrollment, AcademicYear
from academics.services.grading import resolve_threshold
from academics.services.semester import compute_semester_result
from students.models import Student

DECISION_PROMOTED = "promoted"
DECISION_PROMOTED_WITH_DEBT = "promoted_with_debt"
DECISION_REPEATED = "repeated"
DECISION_COMPLETED = "completed"

RULE_ALL_SEMESTERS_VALIDATED = "all_semesters_validated"
RULE_COMPENSATED_SEMESTER_DEBT = "compensated_semester_debt"
RULE_NO_SEMESTER_VALIDATED = "no_semester_validated"
RULE_SEMESTER_GAP_TOO_LARGE = "semester_gap_too_large"
RULE_INCOMPLETE_GRADES = "incomplete_grades"
RULE_TERMINAL_DEBT_BLOCKED = "terminal_debt_blocked"

DEFAULT_SEMESTER_COMPENSATION_MAX_GAP = Decimal("0.50")


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


def _is_terminal_level(level):
    return str(level or "").upper().strip() in {"L3", "M2"}


def _decimal_or_none(value):
    if value in (None, ""):
        return None
    return Decimal(str(value))


def _semester_label(semester_result):
    semester = semester_result.get("semester")
    number = getattr(semester, "number", None)
    return f"S{number}" if number else "Semestre"


def _debt_subjects_from_semester(semester_result):
    debts = []
    for failed in semester_result.get("failed_subjects", []):
        ec = failed.get("ec")
        ue = getattr(ec, "ue", None)
        debts.append(
            {
                "semester": _semester_label(semester_result),
                "ue": getattr(ue, "code", "") or getattr(ue, "title", ""),
                "ec": getattr(ec, "title", ""),
                "score": str(failed.get("score") or ""),
                "credit_required": str(failed.get("credit_required") or "0"),
                "credit_obtained": str(failed.get("credit_obtained") or "0"),
            }
        )
    return debts


def _semester_snapshot(semester_result):
    return {
        "semester": _semester_label(semester_result),
        "average": str(semester_result.get("average")) if semester_result.get("average") is not None else None,
        "credit_required": str(semester_result.get("credit_required") or "0"),
        "credit_obtained": str(semester_result.get("credit_obtained") or "0"),
        "is_complete": bool(semester_result.get("is_complete")),
        "is_validated": bool(semester_result.get("is_validated")),
        "status": semester_result.get("status"),
        "blocking_reasons": list(semester_result.get("blocking_reasons", [])),
    }


def compute_annual_result(enrollment):
    semesters = list(enrollment.academic_class.semesters.all().order_by("number"))
    threshold = resolve_threshold(enrollment)
    total_weighted = Decimal("0.00")
    total_credits = Decimal("0.00")
    credits_obtained = Decimal("0.00")
    missing_grades = 0
    semester_results = []
    blocking_reasons = []

    for semester in semesters:
        result = compute_semester_result(semester, enrollment)
        semester_results.append(result)
        credit_required = Decimal(str(result.get("credit_required") or "0"))
        credit_obtained = Decimal(str(result.get("credit_obtained") or "0"))
        credits_obtained += credit_obtained
        total_credits += credit_required
        missing_grades += result.get("missing_grades", 0)
        if result.get("average") is not None and credit_required > 0:
            total_weighted += Decimal(str(result["average"])) * credit_required
        for reason in result.get("blocking_reasons", []):
            blocking_reasons.append(f"S{semester.number}: {reason}")

    average = (total_weighted / total_credits).quantize(Decimal("0.01")) if total_credits > 0 and missing_grades == 0 else None
    is_complete = missing_grades == 0 and bool(semesters)
    is_validated = bool(
        is_complete
        and average is not None
        and average >= threshold
        and total_credits > 0
        and credits_obtained >= total_credits
    )
    status = "incomplete" if not is_complete else ("validated" if is_validated else "failed")
    if missing_grades and not blocking_reasons:
        blocking_reasons.append(f"{missing_grades} note(s) manquante(s).")

    return {
        "enrollment": enrollment,
        "semester_results": semester_results,
        "average": average,
        "threshold": threshold,
        "credit_required": total_credits,
        "credit_obtained": credits_obtained,
        "is_complete": is_complete,
        "is_validated": is_validated,
        "missing_grades": missing_grades,
        "blocking_reasons": blocking_reasons,
        "status": status,
    }


def compute_annual_decision(enrollment, *, compensation_max_gap=DEFAULT_SEMESTER_COMPENSATION_MAX_GAP):
    """
    Determine la decision academique automatique.

    Le directeur des etudes valide la conformite du calcul; il ne choisit pas
    arbitrairement le passage. La compensation est volontairement stricte:
    un seul semestre echoue, il est complet, et sa moyenne reste dans l'ecart
    autorise sous le seuil.
    """
    annual_result = compute_annual_result(enrollment)
    threshold = _decimal_or_none(annual_result.get("threshold")) or Decimal("10.00")
    max_gap = Decimal(str(compensation_max_gap))
    semester_results = annual_result.get("semester_results", [])
    complete_semesters = [result for result in semester_results if result.get("is_complete")]
    validated_semesters = [result for result in semester_results if result.get("is_validated")]
    failed_complete_semesters = [
        result for result in semester_results
        if result.get("is_complete") and not result.get("is_validated")
    ]
    debt_subjects = []
    reasons = list(annual_result.get("blocking_reasons", []))

    decision = DECISION_REPEATED
    rule_code = RULE_INCOMPLETE_GRADES
    requires_academic_debt = False
    compensation_gap = None

    if not annual_result.get("is_complete") or len(complete_semesters) != len(semester_results):
        reasons.append("Decision finale bloquee tant que toutes les notes ne sont pas disponibles.")
    elif len(validated_semesters) == len(semester_results) and semester_results:
        decision = DECISION_COMPLETED if _is_terminal_level(enrollment.academic_class.level) else DECISION_PROMOTED
        rule_code = RULE_ALL_SEMESTERS_VALIDATED
        reasons = ["Tous les semestres sont valides."]
    elif len(validated_semesters) == 0:
        decision = DECISION_REPEATED
        rule_code = RULE_NO_SEMESTER_VALIDATED
        reasons.append("Aucun semestre n'est valide.")
    elif len(validated_semesters) == 1 and len(failed_complete_semesters) == 1:
        failed_semester = failed_complete_semesters[0]
        failed_average = _decimal_or_none(failed_semester.get("average"))
        if failed_average is not None:
            compensation_gap = (threshold - failed_average).quantize(Decimal("0.01"))
        can_compensate = (
            failed_average is not None
            and failed_average < threshold
            and compensation_gap <= max_gap
        )
        if can_compensate and not _is_terminal_level(enrollment.academic_class.level):
            decision = DECISION_PROMOTED_WITH_DEBT
            rule_code = RULE_COMPENSATED_SEMESTER_DEBT
            requires_academic_debt = True
            debt_subjects = _debt_subjects_from_semester(failed_semester)
            reasons = [
                (
                    f"{_semester_label(failed_semester)} non valide mais dans l'ecart "
                    f"autorise de {max_gap:.2f} point(s)."
                ),
                "Passage autorise avec dette academique a rattraper l'annee suivante.",
            ]
        elif can_compensate:
            decision = DECISION_REPEATED
            rule_code = RULE_TERMINAL_DEBT_BLOCKED
            reasons.append("Un niveau terminal ne peut pas etre cloture avec une dette academique.")
        else:
            decision = DECISION_REPEATED
            rule_code = RULE_SEMESTER_GAP_TOO_LARGE
            reasons.append(f"Ecart superieur au maximum autorise de {max_gap:.2f} point(s).")
    else:
        decision = DECISION_REPEATED
        rule_code = RULE_SEMESTER_GAP_TOO_LARGE

    return {
        "decision": decision,
        "rule_code": rule_code,
        "rule_label": {
            RULE_ALL_SEMESTERS_VALIDATED: "Semestres valides",
            RULE_COMPENSATED_SEMESTER_DEBT: "Compensation avec dette",
            RULE_NO_SEMESTER_VALIDATED: "Aucun semestre valide",
            RULE_SEMESTER_GAP_TOO_LARGE: "Ecart trop important",
            RULE_INCOMPLETE_GRADES: "Notes incompletes",
            RULE_TERMINAL_DEBT_BLOCKED: "Dette interdite en terminal",
        }.get(rule_code, rule_code),
        "annual_result": annual_result,
        "annual_average": annual_result.get("average"),
        "threshold": threshold,
        "compensation_max_gap": max_gap,
        "compensation_gap": compensation_gap,
        "requires_academic_debt": requires_academic_debt,
        "debt_subjects": debt_subjects,
        "reasons": reasons,
        "semester_results": [_semester_snapshot(result) for result in semester_results],
    }


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
    annual_result = compute_annual_result(enrollment)
    annual_decision = compute_annual_decision(enrollment)

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
        "annual_result": annual_result,
        "annual_decision": annual_decision,
        "decision": "ADMIS" if annual_result["is_validated"] else (
            "INCOMPLET" if not annual_result["is_complete"] else _decision_from_semesters(s1_validated, s2_validated)
        ),
    }
