from decimal import Decimal
import logging

from django.http import Http404
from django.shortcuts import get_object_or_404

from academics.models import AcademicDebt, AcademicEnrollment, AcademicYear
from academics.services.grading import resolve_threshold
from academics.services.semester import compute_semester_result
from students.models import Student

logger = logging.getLogger("esfe.year")

DECISION_VALIDE = "VALIDE"
DECISION_ADMISSIBLE = "ADMISSIBLE"
DECISION_NON_ADMIS = "NON_ADMIS"

RULE_ALL_SEMESTERS_VALIDATED = "all_semesters_validated"
RULE_ADMISSIBLE_GAP = "admissible_gap"
RULE_NO_SEMESTER_VALIDATED = "no_semester_validated"
RULE_GAP_TOO_LARGE = "gap_too_large"
RULE_INCOMPLETE_GRADES = "incomplete_grades"


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


def carry_forward_debts(source_enrollment, target_enrollment):
    """
    Reporte les dettes academiques non soldees vers la nouvelle inscription.

    Clone chaque dette pending de l'ancienne inscription vers la nouvelle,
    de sorte que le mecanisme _clear_debts_on_validation() puisse les
    retrouver lors du retake des EC en annee superieure.
    """
    pending_debts = AcademicDebt.objects.filter(
        enrollment=source_enrollment,
        status=AcademicDebt.STATUS_PENDING,
    ).select_related("semester")
    created = 0
    for debt in pending_debts:
        _, was_created = AcademicDebt.objects.get_or_create(
            enrollment=target_enrollment,
            ec=debt.ec,
            semester=debt.semester,
            academic_year=target_enrollment.academic_year,
            defaults={
                "academic_class": target_enrollment.academic_class,
                "score_original": debt.score_original,
                "carry_forward_to": None,
            },
        )
        if was_created:
            created += 1
        debt.carry_forward_to = target_enrollment.academic_year
        debt.save(update_fields=["carry_forward_to"])
    if created:
        logger.info(
            f"Dettes reportees: source={source_enrollment.id}, "
            f"cible={target_enrollment.id}, nb={created}"
        )
    return created


def create_academic_debts(enrollment, semester_result):
    """
    Cree des enregistrements AcademicDebt pour chaque EC echoue d'un semestre.
    """
    academic_year = enrollment.academic_year
    academic_class = enrollment.academic_class
    semester = semester_result.get("semester")
    created = 0
    for failed in semester_result.get("failed_subjects", []):
        ec = failed.get("ec")
        if not ec or not semester:
            continue
        score = Decimal(str(failed.get("score", "0")))
        _, created_flag = AcademicDebt.objects.get_or_create(
            enrollment=enrollment,
            ec=ec,
            semester=semester,
            academic_year=academic_year,
            defaults={
                "academic_class": academic_class,
                "score_original": score,
                "carry_forward_to": None,
            },
        )
        if created_flag:
            created += 1
    if created:
        logger.info(
            f"Dettes creees: enrollment={enrollment.id}, "
            f"semestre=S{semester.number}, nb={created}"
        )
    return created


def compute_annual_result(enrollment):
    """
    Consolide les resultats des semestres sans calculer de moyenne annuelle.

    Le resultat annuel affiche simplement :
    - moyenne S1, credits S1
    - moyenne S2, credits S2
    - decision : VALIDE / ADMISSIBLE / NON ADMIS
    """
    semesters = list(enrollment.academic_class.semesters.all().order_by("number"))
    total_credits = Decimal("0.00")
    credits_obtained = Decimal("0.00")
    missing_grades = 0
    semester_results = []
    blocking_reasons = []

    for semester in semesters:
        result = compute_semester_result(semester, enrollment)
        semester_results.append(result)
        credit_required = Decimal(str(result.get("credit_required") or "0"))
        credit_obtained_sem = Decimal(str(result.get("credit_obtained") or "0"))
        credits_obtained += credit_obtained_sem
        total_credits += credit_required
        missing_grades += result.get("missing_grades", 0)
        for reason in result.get("blocking_reasons", []):
            blocking_reasons.append(f"S{semester.number}: {reason}")

    is_complete = missing_grades == 0 and bool(semesters)
    if missing_grades and not blocking_reasons:
        blocking_reasons.append(f"{missing_grades} note(s) manquante(s).")

    logger.info(
        f"Consolidation annuelle: enrollment={enrollment.id}, "
        f"credits={credits_obtained}/{total_credits}, complete={is_complete}"
    )

    return {
        "enrollment": enrollment,
        "semester_results": semester_results,
        "average": None,
        "credit_required": total_credits,
        "credit_obtained": credits_obtained,
        "is_complete": is_complete,
        "missing_grades": missing_grades,
        "blocking_reasons": blocking_reasons,
        "status": "incomplete" if not is_complete else "complete",
    }


def compute_annual_decision(enrollment):
    """
    Determine la decision annuelle : VALIDE / ADMISSIBLE / NON_ADMIS.

    Regles :
    - S1 valide ET S2 valide → VALIDE
    - S1 valide ET S2 proche seuil (ou inverse) → ADMISSIBLE (avec dette)
    - Sinon → NON_ADMIS

    La marge d'admissibilite est lue depuis AcademicClass.admissibility_gap.
    """
    annual_result = compute_annual_result(enrollment)
    academic_class = enrollment.academic_class
    threshold = resolve_threshold(enrollment)
    gap = _decimal_or_none(academic_class.admissibility_gap) or Decimal("2.00")
    semester_results = annual_result.get("semester_results", [])
    debt_subjects = []
    reasons = list(annual_result.get("blocking_reasons", []))

    decision = DECISION_NON_ADMIS
    rule_code = RULE_INCOMPLETE_GRADES
    requires_academic_debt = False

    if not annual_result.get("is_complete"):
        reasons.append("Decision finale bloquee tant que toutes les notes ne sont pas disponibles.")
    else:
        validated = []
        non_validated = []
        for result in semester_results:
            if result.get("is_validated"):
                validated.append(result)
            else:
                non_validated.append(result)

        if len(validated) == len(semester_results):
            decision = DECISION_VALIDE
            rule_code = RULE_ALL_SEMESTERS_VALIDATED
            reasons = ["Tous les semestres sont valides."]
        elif len(validated) >= 1:
            failed_semester = non_validated[0]
            failed_avg = _decimal_or_none(failed_semester.get("average"))
            is_near = (
                failed_avg is not None
                and failed_avg >= threshold - gap
            )
            if is_near:
                decision = DECISION_ADMISSIBLE
                rule_code = RULE_ADMISSIBLE_GAP
                requires_academic_debt = True
                debt_subjects = _debt_subjects_from_semester(failed_semester)
                create_academic_debts(enrollment, failed_semester)
                reasons = [
                    f"{_semester_label(failed_semester)} non valide (moyenne={failed_avg:.2f}) "
                    f"mais dans la marge d'admissibilite de {gap:.2f} point(s) sous le seuil de {threshold:.2f}.",
                    "Admissible avec dette academique a rattraper.",
                ]
            else:
                decision = DECISION_NON_ADMIS
                rule_code = RULE_GAP_TOO_LARGE
                reasons.append(
                    f"{_semester_label(failed_semester)} trop faible (moyenne={failed_avg:.2f}, "
                    f"seuil={threshold:.2f}, marge max={gap:.2f})."
                )
        else:
            decision = DECISION_NON_ADMIS
            rule_code = RULE_NO_SEMESTER_VALIDATED
            reasons.append("Aucun semestre valide.")

    logger.info(
        f"Decision annuelle: enrollment={enrollment.id}, "
        f"decision={decision}, regle={rule_code}, dette={requires_academic_debt}"
    )

    return {
        "decision": decision,
        "rule_code": rule_code,
        "rule_label": {
            RULE_ALL_SEMESTERS_VALIDATED: "Semestres valides",
            RULE_ADMISSIBLE_GAP: "Admissible avec marge",
            RULE_NO_SEMESTER_VALIDATED: "Aucun semestre valide",
            RULE_GAP_TOO_LARGE: "Ecart trop important",
            RULE_INCOMPLETE_GRADES: "Notes incompletes",
        }.get(rule_code, rule_code),
        "annual_result": annual_result,
        "annual_average": None,
        "threshold": threshold,
        "admissibility_gap": gap,
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
    annual_decision = compute_annual_decision(enrollment)

    s1_validated = bool(s1_result and s1_result.get("is_validated"))
    s2_validated = bool(s2_result and s2_result.get("is_validated"))

    decision_code = annual_decision.get("decision", DECISION_NON_ADMIS)

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
        "annual_decision": annual_decision,
        "decision": decision_code,
    }
