from django.db.models import Count, Q
from django.utils import timezone

from academics.models import ECGrade, Semester
from academic_cycle import constants
from academic_cycle.models import AcademicClosureReport, ClassCycleStatus
from academic_cycle.selectors import get_branch_classes, get_branch_financial_summary


FINAL_SEMESTER_STATUSES = {Semester.STATUS_FINALIZED, Semester.STATUS_PUBLISHED}


def check_class_readiness(academic_class, actor=None, branch_cycle=None):
    if branch_cycle is None:
        branch_cycle = academic_class.academic_year.branch_cycles.get(branch=academic_class.branch)

    semesters = list(academic_class.semesters.all())
    semester_map = {semester.number: semester for semester in semesters}
    semester_1_done = semester_map.get(1) is not None and semester_map[1].status in FINAL_SEMESTER_STATUSES
    semester_2_done = semester_map.get(2) is not None and semester_map[2].status in FINAL_SEMESTER_STATUSES

    expected_ec_ids = list(academic_class.semesters.values_list("ues__ecs", flat=True).exclude(ues__ecs__isnull=True))
    enrollments = academic_class.enrollments.filter(is_active=True)
    expected_grade_count = len(expected_ec_ids) * enrollments.count()
    completed_grade_count = ECGrade.objects.filter(
        enrollment__in=enrollments,
        ec_id__in=expected_ec_ids,
        final_score__isnull=False,
    ).count()
    missing_grades_count = max(expected_grade_count - completed_grade_count, 0)
    grades_done = missing_grades_count == 0
    bulletins_done = grades_done and semester_1_done and semester_2_done
    has_blocking_anomaly = not (semester_1_done and semester_2_done and grades_done)

    score_parts = [semester_1_done, semester_2_done, grades_done, bulletins_done]
    readiness_score = int(sum(1 for part in score_parts if part) / len(score_parts) * 100)
    if has_blocking_anomaly:
        status = constants.CLASS_GRADES_COMPLETED if grades_done else constants.CLASS_TEACHING
    else:
        status = constants.CLASS_READY_FOR_DELIBERATION

    class_status, _ = ClassCycleStatus.objects.update_or_create(
        branch_cycle=branch_cycle,
        academic_class=academic_class,
        defaults={
            "status": status,
            "semester_1_done": semester_1_done,
            "semester_2_done": semester_2_done,
            "grades_done": grades_done,
            "bulletins_done": bulletins_done,
            "has_blocking_anomaly": has_blocking_anomaly,
            "readiness_score": readiness_score,
            "last_checked_at": timezone.now(),
            "checked_by": actor if getattr(actor, "is_authenticated", False) else None,
        },
    )
    return {
        "class_status": class_status,
        "missing_grades_count": missing_grades_count,
        "semester_1_done": semester_1_done,
        "semester_2_done": semester_2_done,
        "grades_done": grades_done,
        "bulletins_done": bulletins_done,
        "has_blocking_anomaly": has_blocking_anomaly,
        "readiness_score": readiness_score,
    }


def check_branch_readiness(branch_cycle, actor=None):
    details = []
    totals = {
        "total_classes": 0,
        "completed_classes": 0,
        "blocked_classes": 0,
        "missing_grades_count": 0,
        "anomaly_count": 0,
        "bulletin_missing_count": 0,
    }
    for academic_class in get_branch_classes(branch_cycle.branch, branch_cycle.academic_year).prefetch_related("semesters__ues__ecs"):
        result = check_class_readiness(academic_class, actor=actor, branch_cycle=branch_cycle)
        totals["total_classes"] += 1
        totals["missing_grades_count"] += result["missing_grades_count"]
        if result["has_blocking_anomaly"]:
            totals["blocked_classes"] += 1
            totals["anomaly_count"] += 1
        else:
            totals["completed_classes"] += 1
        if not result["bulletins_done"]:
            totals["bulletin_missing_count"] += 1
        details.append(
            {
                "class_id": academic_class.pk,
                "class_name": str(academic_class),
                "readiness_score": result["readiness_score"],
                "missing_grades_count": result["missing_grades_count"],
                "has_blocking_anomaly": result["has_blocking_anomaly"],
            }
        )
    return {"is_ready": totals["blocked_classes"] == 0 and totals["total_classes"] > 0, "totals": totals, "details": details}


def generate_closure_report(branch_cycle, actor=None):
    readiness = check_branch_readiness(branch_cycle, actor=actor)
    totals = readiness["totals"]
    report_status = constants.CLOSURE_REPORT_VALID if readiness["is_ready"] else constants.CLOSURE_REPORT_INVALID
    return AcademicClosureReport.objects.create(
        branch_cycle=branch_cycle,
        generated_by=actor if getattr(actor, "is_authenticated", False) else None,
        status=report_status,
        total_classes=totals["total_classes"],
        completed_classes=totals["completed_classes"],
        blocked_classes=totals["blocked_classes"],
        missing_grades_count=totals["missing_grades_count"],
        anomaly_count=totals["anomaly_count"],
        bulletin_missing_count=totals["bulletin_missing_count"],
        financial_summary_snapshot=get_branch_financial_summary(branch_cycle.branch, branch_cycle.academic_year),
        academic_summary_snapshot=totals,
        details={"classes": readiness["details"]},
    )
