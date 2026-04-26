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

    programme = candidature.programme
    branch = candidature.branch
    academic_year_name = str(candidature.academic_year or "").strip()
    entry_year = candidature.entry_year

    if not programme:
        logger.warning(
            "Affectation academique manuelle requise: programme absent pour inscription=%s",
            inscription.pk,
        )
        return _build_result("manual_required_missing_data", reason="missing_programme")

    if not branch:
        logger.warning(
            "Affectation academique manuelle requise: annexe absente pour inscription=%s",
            inscription.pk,
        )
        return _build_result("manual_required_missing_data", reason="missing_branch")

    if not academic_year_name:
        logger.warning(
            "Affectation academique manuelle requise: annee academique absente pour inscription=%s",
            inscription.pk,
        )
        return _build_result("manual_required_missing_data", reason="missing_academic_year")

    if entry_year in (None, ""):
        logger.warning(
            "Affectation academique manuelle requise: niveau d'entree absent pour inscription=%s",
            inscription.pk,
        )
        return _build_result("manual_required_missing_data", reason="missing_entry_level")

    academic_year = AcademicYear.objects.filter(name=academic_year_name).first()
    if not academic_year:
        logger.warning(
            "AcademicYear introuvable pour inscription=%s, value=%s",
            inscription.pk,
            academic_year_name,
        )
        return _build_result("manual_required_missing_data", reason="academic_year_not_found")

    level = ENTRY_YEAR_TO_LEVEL.get(entry_year)
    if not level:
        logger.warning(
            "Niveau introuvable pour inscription=%s, entry_year=%s",
            inscription.pk,
            entry_year,
        )
        return _build_result("manual_required_missing_data", reason="level_not_resolved")

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
            "Aucune classe academique pour inscription=%s, programme=%s, branch=%s, year=%s, level=%s",
            inscription.pk,
            programme.pk,
            branch.pk,
            academic_year.pk,
            level,
        )
        return _build_result("manual_required_no_class", reason="academic_class_not_found")

    if match_count > 1:
        logger.warning(
            "Plusieurs classes academiques pour inscription=%s, programme=%s, branch=%s, year=%s, level=%s",
            inscription.pk,
            programme.pk,
            branch.pk,
            academic_year.pk,
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
            "Erreur metier lors de la creation AcademicEnrollment pour inscription=%s",
            inscription.pk,
        )
        return _build_result("error_inconsistent_data", reason="academic_enrollment_creation_failed")

    if created:
        logger.info(
            "AcademicEnrollment cree pour inscription=%s, class=%s",
            inscription.pk,
            academic_class.pk,
        )
        status = "assigned"
    else:
        logger.info(
            "AcademicEnrollment recupere pour inscription=%s, class=%s",
            inscription.pk,
            enrollment.academic_class_id,
        )
        status = "already_assigned"

    return _build_result(status, enrollment=enrollment)
