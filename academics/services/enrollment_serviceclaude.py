import logging

from academics.models import AcademicClass, AcademicEnrollment, AcademicYear


logger = logging.getLogger(__name__)


ENTRY_YEAR_TO_LEVEL = {
    1: "L1",
    2: "L2",
    3: "L3",
    4: "M1",
    5: "M2",
}


def _build_result(status, enrollment=None, reason=None):
    return {
        "status": status,
        "enrollment": enrollment,
        "reason": reason,
    }


def _resolve_academic_year(academic_year_name):
    """
    Résout l'AcademicYear à utiliser pour l'enrollment.

    Stratégie :
    1. On cherche d'abord par nom exact (ex: "2025-2026")
    2. Si introuvable, on prend l'année active en base
       (le texte de la candidature est une étiquette administrative,
        la référence officielle c'est l'AcademicYear active)

    Retourne (academic_year, used_fallback).
    """
    if academic_year_name:
        year = AcademicYear.objects.filter(name=academic_year_name).first()
        if year:
            return year, False

    # Fallback : année active
    active_year = AcademicYear.objects.filter(is_active=True).first()
    if active_year:
        logger.warning(
            "AcademicYear '%s' absente en base — fallback sur l'année active '%s'",
            academic_year_name,
            active_year.name,
        )
        return active_year, True

    return None, False


def assign_student_academic_enrollment(inscription):
    """
    Crée la liaison académique entre une inscription et une classe.

    Cette fonction est appelée automatiquement après la création du Student
    (premier paiement validé). Elle ne doit jamais bloquer le workflow principal.

    Résolution de l'année académique :
    - On utilise en priorité l'AcademicYear dont le nom correspond à
      candidature.academic_year (champ texte libre).
    - Si aucune correspondance, on bascule sur l'année académique active,
      car c'est elle qui pilote le système académique réel.
    """

    if not inscription:
        logger.error("Affectation academique impossible: inscription absente")
        return _build_result("error_inconsistent_data", reason="missing_inscription")

    try:
        student = inscription.student
    except Exception:
        logger.error(
            "Affectation academique impossible: student absent pour inscription=%s",
            getattr(inscription, "pk", None),
        )
        return _build_result("error_inconsistent_data", reason="missing_student")

    candidature = getattr(inscription, "candidature", None)
    if candidature is None:
        logger.error(
            "Affectation academique impossible: candidature absente pour inscription=%s",
            inscription.pk,
        )
        return _build_result("error_inconsistent_data", reason="missing_candidature")

    # Idempotence — déjà affecté, on sort
    if hasattr(inscription, "academic_enrollment"):
        enrollment = inscription.academic_enrollment
        logger.info(
            "AcademicEnrollment deja existant pour inscription=%s, class=%s",
            inscription.pk,
            enrollment.academic_class_id,
        )
        return _build_result("already_assigned", enrollment=enrollment)

    programme = candidature.programme
    branch = candidature.branch
    academic_year_name = str(candidature.academic_year or "").strip()
    entry_year = candidature.entry_year

    if not programme:
        logger.warning(
            "Affectation manuelle requise: programme absent pour inscription=%s",
            inscription.pk,
        )
        return _build_result("manual_required_missing_data", reason="missing_programme")

    if not branch:
        logger.warning(
            "Affectation manuelle requise: annexe absente pour inscription=%s",
            inscription.pk,
        )
        return _build_result("manual_required_missing_data", reason="missing_branch")

    if entry_year in (None, ""):
        logger.warning(
            "Affectation manuelle requise: niveau d'entree absent pour inscription=%s",
            inscription.pk,
        )
        return _build_result("manual_required_missing_data", reason="missing_entry_level")

    level = ENTRY_YEAR_TO_LEVEL.get(entry_year)
    if not level:
        logger.warning(
            "Niveau introuvable pour inscription=%s, entry_year=%s",
            inscription.pk,
            entry_year,
        )
        return _build_result("manual_required_missing_data", reason="level_not_resolved")

    # Résolution de l'année avec fallback sur l'année active
    academic_year, used_fallback = _resolve_academic_year(academic_year_name)
    if not academic_year:
        logger.warning(
            "Aucune AcademicYear disponible (ni '%s', ni aucune année active) "
            "pour inscription=%s",
            academic_year_name,
            inscription.pk,
        )
        return _build_result("manual_required_missing_data", reason="academic_year_not_found")

    # Recherche de la classe
    class_queryset = AcademicClass.objects.filter(
        programme=programme,
        branch=branch,
        academic_year=academic_year,
        level=level,
        is_active=True,
    )
    match_count = class_queryset.count()

    if match_count == 0:
        logger.warning(
            "Aucune classe active pour inscription=%s "
            "[programme=%s, branch=%s, year='%s', level=%s]%s",
            inscription.pk,
            programme.pk,
            branch.pk,
            academic_year.name,
            level,
            " [fallback sur année active]" if used_fallback else "",
        )
        return _build_result("manual_required_no_class", reason="academic_class_not_found")

    if match_count > 1:
        logger.warning(
            "Plusieurs classes pour inscription=%s "
            "[programme=%s, branch=%s, year='%s', level=%s] — affectation manuelle requise",
            inscription.pk,
            programme.pk,
            branch.pk,
            academic_year.name,
            level,
        )
        return _build_result("manual_required_ambiguous", reason="multiple_academic_classes")

    academic_class = class_queryset.first()

    try:
        enrollment, created = AcademicEnrollment.objects.get_or_create(
            inscription=inscription,
            defaults={
                "student": student.user,
                "programme": programme,
                "branch": branch,
                "academic_year": academic_year,
                "academic_class": academic_class,
            },
        )
    except Exception:
        logger.exception(
            "Erreur lors de la creation AcademicEnrollment pour inscription=%s",
            inscription.pk,
        )
        return _build_result("error_inconsistent_data", reason="academic_enrollment_creation_failed")

    if created:
        logger.info(
            "AcademicEnrollment cree pour inscription=%s → classe '%s'%s",
            inscription.pk,
            academic_class,
            f" [fallback, candidature avait '{academic_year_name}']" if used_fallback else "",
        )
        return _build_result("assigned", enrollment=enrollment)

    logger.info(
        "AcademicEnrollment recupere pour inscription=%s → class=%s",
        inscription.pk,
        enrollment.academic_class_id,
    )
    return _build_result("already_assigned", enrollment=enrollment)
