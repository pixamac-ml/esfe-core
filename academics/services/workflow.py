from academics.models import AcademicEnrollment, ECGrade, Semester


def get_semester_permissions(semester):
    status = semester.status

    return {
        "can_enter_normal": status == Semester.STATUS_NORMAL_ENTRY,
        "can_enter_retake": status in {Semester.STATUS_NORMAL_LOCKED, Semester.STATUS_RETAKE_ENTRY},
        "can_publish": status == Semester.STATUS_FINALIZED,
        "can_generate_reports": status == Semester.STATUS_PUBLISHED,
        "is_locked": status in {Semester.STATUS_FINALIZED, Semester.STATUS_PUBLISHED},
    }


def can_publish_semester(semester, enrollment_list):
    ec_ids = list(semester.ues.values_list("ecs__id", flat=True).distinct())
    ec_ids = [ec_id for ec_id in ec_ids if ec_id is not None]
    if not ec_ids:
        return False

    for enrollment in enrollment_list:
        grades = {
            grade.ec_id: grade
            for grade in ECGrade.objects.filter(
                enrollment=enrollment,
                ec_id__in=ec_ids,
            )
        }
        for ec_id in ec_ids:
            grade = grades.get(ec_id)
            if grade is None or grade.final_score is None:
                return False

    return True


def is_session_complete_for_class(semester, session_type):
    """True si tous les etudiants actifs de la classe ont une note (normale ou
    rattrapage selon session_type) pour tous les EC du semestre. Utilise par
    le signal de notification (cf. CAHIER_DES_CHARGES_DIRECTEUR_ETUDES.md, 2.4)
    pour detecter qu'un enseignant a termine la saisie d'une session."""
    ec_ids = list(semester.ues.values_list("ecs__id", flat=True).distinct())
    ec_ids = [ec_id for ec_id in ec_ids if ec_id is not None]
    if not ec_ids:
        return False

    enrollments = list(
        AcademicEnrollment.objects.filter(
            academic_class=semester.academic_class,
            academic_year=semester.academic_class.academic_year,
            is_active=True,
        )
    )
    if not enrollments:
        return False

    score_field = "retake_score" if session_type == "retake" else "normal_score"
    for enrollment in enrollments:
        scores = {
            grade.ec_id: getattr(grade, score_field)
            for grade in ECGrade.objects.filter(enrollment=enrollment, ec_id__in=ec_ids)
        }
        for ec_id in ec_ids:
            if scores.get(ec_id) is None:
                return False

    return True
