from academics.models import ECGrade, Semester


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
