# ==================================================
# FILE: academics/services/grading.py
# VERSION: PRODUCTION SAFE
# ==================================================

from decimal import Decimal, ROUND_HALF_UP
import logging
from django.db.models import Sum, Prefetch


# ================================
# UTILS
# ================================

def to_decimal(value, default="0.00"):
    """
    Convertit proprement en Decimal.
    Gere None, string vide, etc.
    """
    try:
        return Decimal(str(value))
    except:
        return Decimal(default)


def resolve_threshold(enrollment):
    """
    Resout le seuil metier de validation.

    PRIORITE :
    1. seuil defini sur la classe
    2. fallback base sur study_level
    3. fallback global = 10
    """
    academic_class = enrollment.academic_class

    if academic_class.validation_threshold:
        return to_decimal(academic_class.validation_threshold)

    study_level = academic_class.study_level

    if study_level == "DEF":
        return Decimal("10.00")
    elif study_level == "BAC":
        return Decimal("12.00")
    elif study_level == "LICENCE":
        return Decimal("12.00")
    elif study_level == "MASTER":
        return Decimal("12.00")

    return Decimal("10.00")


def format_note(note):
    if note is None:
        return "-"
    try:
        return f"{Decimal(note):.2f}".replace(".", ",")
    except Exception:
        return str(note)


def format_average(avg):
    if avg is None:
        return "-"
    try:
        return f"{Decimal(avg):.2f}".replace(".", ",")
    except Exception:
        return str(avg)


logger = logging.getLogger("esfe.grading")


TWO_PLACES = Decimal("0.01")


def compute_final_score(instance):
    if instance.retake_score is not None:
        if instance.normal_score is not None:
            instance.final_score = max(instance.normal_score, instance.retake_score)
        else:
            instance.final_score = instance.retake_score
    else:
        instance.final_score = instance.normal_score
    return instance


def compute_ec_status(final_score, threshold):
    if final_score is None:
        return "empty"

    final_score = to_decimal(final_score)
    threshold = to_decimal(threshold)

    if final_score >= threshold:
        return "validated"

    return "failed"


# ================================
# CORE CALCUL EC
# ================================

def calculate_ec_grade(note, coefficient, credit_required, threshold):
    """
    Calcule le resultat d'un EC.

    SAFE :
    - aucun None
    - aucun crash
    """

    note_value = None if note in (None, "") else to_decimal(note)
    coefficient = to_decimal(coefficient)
    credit_required = to_decimal(credit_required)
    threshold = to_decimal(threshold)

    if threshold <= Decimal("0.00"):
        threshold = Decimal("10.00")

    if note_value is None:
        note_for_math = Decimal("0.00")
    else:
        note_for_math = note_value
        if note_for_math < Decimal("0.00"):
            note_for_math = Decimal("0.00")
        if note_for_math > Decimal("20.00"):
            note_for_math = Decimal("20.00")

    note_coefficient = note_for_math * coefficient

    if note_value is None:
        credit_obtained = Decimal("0.00")
        is_validated = False
    elif note_for_math >= threshold:
        credit_obtained = credit_required
        is_validated = True
    else:
        credit_obtained = (note_for_math * credit_required) / threshold
        is_validated = False

    if credit_obtained < Decimal("0.00"):
        credit_obtained = Decimal("0.00")
    if credit_obtained > credit_required:
        credit_obtained = credit_required

    note_coefficient = note_coefficient.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    credit_obtained = credit_obtained.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

    return {
        "note": note_value,
        "note_coefficient": note_coefficient,
        "credit_obtained": credit_obtained,
        "is_validated": is_validated,
    }


# ================================
# APPLICATION SUR MODEL
# ================================

def apply_ec_grade(instance):
    compute_final_score(instance)
    threshold = resolve_threshold(instance.enrollment)
    result = calculate_ec_grade(
        note=instance.final_score,
        coefficient=instance.ec.coefficient,
        credit_required=instance.ec.credit_required,
        threshold=threshold,
    )
    instance.note = instance.final_score
    instance.note_coefficient = result["note_coefficient"]
    instance.credit_obtained = result["credit_obtained"]
    instance.is_validated = result["is_validated"]
    logger.info(
        f"Note EC enregistree: enrollment={instance.enrollment_id}, ec={instance.ec_id}, "
        f"normal={instance.normal_score}, retake={instance.retake_score}, final={instance.final_score}"
    )
    return instance


# ================================
# STATUTS & MOYENNES SEMESTRIELLES
# ================================

def calculate_semester_summary(enrollment, semester):
    """
    Calcule la moyenne, credits obtenus, credits requis, statut validation pour un semestre donne.
    """
    from academics.services.semester import compute_semester_result

    result = compute_semester_result(semester, enrollment)
    moyenne = result["average"]
    total_credits = result["credit_required"]
    credits_obtained = result["credit_obtained"]
    threshold = resolve_threshold(enrollment)
    statut = "EN COURS"
    if moyenne is not None and total_credits > Decimal("0.00"):
        if moyenne >= threshold and credits_obtained >= total_credits:
            statut = "VALIDE"
        elif moyenne < threshold or credits_obtained < total_credits:
            statut = "NON VALIDE"
    logger.info(f"Recalcul semestre: enrollment={enrollment.id}, semestre={semester.id}, moyenne={moyenne}, credits={credits_obtained}/{total_credits}, statut={statut}")
    return {
        "moyenne": moyenne,
        "credits_obtenus": credits_obtained,
        "credits_requis": total_credits,
        "statut": statut,
    }


def calculate_academic_year_summary(enrollment):
    """
    Calcule la moyenne generale, credits totaux, validation finale pour l'annee academique.
    """
    from academics.models import Semester
    semesters = Semester.objects.filter(academic_class=enrollment.academic_class).prefetch_related(
        Prefetch('ues__ecs__grades', to_attr='all_grades')
    )
    total_coef = Decimal('0.00')
    total_note_coef = Decimal('0.00')
    total_credits = Decimal('0.00')
    credits_obtained = Decimal('0.00')
    threshold = resolve_threshold(enrollment)
    for semester in semesters:
        sem_summary = calculate_semester_summary(enrollment, semester)
        semester_credits = sem_summary["credits_requis"]
        if sem_summary["moyenne"] is not None:
            total_note_coef += sem_summary["moyenne"] * semester_credits
            total_coef += semester_credits
        total_credits += semester_credits
        credits_obtained += sem_summary["credits_obtenus"]
    moyenne = (total_note_coef / total_coef) if total_coef > 0 else None
    statut = "EN COURS"
    if moyenne is not None:
        if moyenne >= threshold and credits_obtained >= total_credits:
            statut = "VALIDE"
        elif moyenne < threshold or credits_obtained < total_credits:
            statut = "NON VALIDE"
    logger.info(f"Recalcul annee: enrollment={enrollment.id}, moyenne={moyenne}, credits={credits_obtained}/{total_credits}, statut={statut}")
    return {
        "moyenne": moyenne,
        "credits_obtenus": credits_obtained,
        "credits_requis": total_credits,
        "statut": statut,
    }
