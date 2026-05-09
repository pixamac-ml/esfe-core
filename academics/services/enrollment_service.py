import logging

from academics.models import AcademicEnrollment
from academics.services.academic_context_resolver import resolve_academic_context
from academics.services.academic_positioning import validate_academic_class_for_candidature


logger = logging.getLogger(__name__)


def _build_result(status, enrollment=None, reason=None):
    return {
        "status": status,
        "enrollment": enrollment,
        "reason": reason,
    }


def assign_student_academic_enrollment(inscription):
    """
    Cree la liaison academique entre une inscription et une classe.

    Priorite :
    1. classe explicitement positionnee sur l'inscription
    2. fallback legacy via la candidature pour les anciennes inscriptions
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
            getattr(inscription, "pk", None),
        )
        return _build_result("error_inconsistent_data", reason="missing_candidature")

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

    if inscription.academic_class_id:
        academic_class = inscription.academic_class
        validation = validate_academic_class_for_candidature(
            candidature=candidature,
            academic_class=academic_class,
        )
        if not validation["ok"]:
            logger.warning(
                "Classe administrative invalide pour inscription=%s: %s",
                inscription.pk,
                validation["reason"],
            )
            return _build_result("manual_required_missing_class", reason=validation["reason"])
        academic_year = validation["academic_year"]
    else:
        context_result = resolve_academic_context(candidature=candidature)
        if context_result["status"] != "resolved":
            logger.warning(
                "Contexte academique non resolu pour inscription=%s: %s",
                inscription.pk,
                context_result["reason"],
            )
            return _build_result(context_result["status"], reason=context_result["reason"])
        academic_class = context_result["academic_class"]
        academic_year = context_result["academic_year"]

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
            "AcademicEnrollment cree pour inscription=%s -> classe '%s'",
            inscription.pk,
            academic_class,
        )
        return _build_result("assigned", enrollment=enrollment)

    logger.info(
        "AcademicEnrollment recupere pour inscription=%s -> class=%s",
        inscription.pk,
        enrollment.academic_class_id,
    )
    return _build_result("already_assigned", enrollment=enrollment)
