import logging

from django.db import transaction

from academics.models import AcademicEnrollment
from academics.services.academic_context_resolver import (
    LEGACY_ENTRY_YEAR_TO_LEVEL,
    resolve_academic_context,
)


logger = logging.getLogger(__name__)


ENTRY_YEAR_TO_LEVEL = LEGACY_ENTRY_YEAR_TO_LEVEL


def _build_result(status, enrollment=None, reason=None, context=None):
    return {
        "status": status,
        "enrollment": enrollment,
        "reason": reason,
        "context": context or {},
    }


def assign_student_academic_enrollment(inscription):
    """
    Tente de creer la liaison academique d'une inscription apres creation du Student.

    Cette fonction ne doit jamais casser le workflow principal.
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

    if hasattr(inscription, "academic_enrollment"):
        enrollment = inscription.academic_enrollment
        logger.info(
            "AcademicEnrollment deja existant pour inscription=%s, class=%s",
            inscription.pk,
            enrollment.academic_class_id,
        )
        return _build_result("already_assigned", enrollment=enrollment)

    resolution = resolve_academic_context(candidature=candidature)
    if resolution["status"] != "resolved":
        logger.warning(
            "Provisioning academique manuel requis inscription=%s status=%s reason=%s year=%s level=%s",
            inscription.pk,
            resolution["status"],
            resolution["reason"],
            resolution["academic_year_name"],
            resolution["resolved_level"],
        )
        return _build_result(
            resolution["status"],
            reason=resolution["reason"],
            context=resolution,
        )

    try:
        with transaction.atomic():
            enrollment, created = AcademicEnrollment.objects.get_or_create(
                inscription=inscription,
                defaults={
                    "student": student.user,
                    "programme": resolution["programme"],
                    "branch": resolution["branch"],
                    "academic_year": resolution["academic_year"],
                    "academic_class": resolution["academic_class"],
                },
            )
    except Exception:
        logger.exception(
            "Erreur metier lors de la creation AcademicEnrollment pour inscription=%s",
            inscription.pk,
        )
        return _build_result("error_inconsistent_data", reason="academic_enrollment_creation_failed")

    if created:
        logger.info(
            "AcademicEnrollment cree pour inscription=%s, class=%s, year=%s, level=%s",
            inscription.pk,
            resolution["academic_class"].pk,
            resolution["academic_year_name"],
            resolution["resolved_level"],
        )
        status = "assigned"
    else:
        logger.info(
            "AcademicEnrollment recupere pour inscription=%s, class=%s",
            inscription.pk,
            enrollment.academic_class_id,
        )
        status = "already_assigned"

    return _build_result(status, enrollment=enrollment, context=resolution)
