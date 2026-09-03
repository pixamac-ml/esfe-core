"""Presentation context for the Director of Studies deliberation workflow."""

from decimal import Decimal

from academic_cycle import constants
from django.db.models import Count
from academic_cycle.models import BranchAcademicCycle, ClassDeliberationSession, StudentYearDecision
from academic_cycle.services.deliberation_session_service import get_session, session_metrics, simulate_threshold
from academics.models import AcademicClass, AcademicEnrollment
from academics.services.annual_deliberation import get_class_deliberation_rows


_TERMINAL_STATUSES = {
    constants.BRANCH_CYCLE_DELIBERATION,
    constants.BRANCH_CYCLE_CLOSED,
    constants.BRANCH_CYCLE_ARCHIVED,
}


def build_director_deliberation_context(*, branch, academic_year, selected_class_id=None, selected_tab="overview"):
    selected_tab = selected_tab if selected_tab in {"overview", "session", "cases", "rules", "finalisation"} else "overview"
    cycle = None
    if branch is not None and academic_year is not None:
        cycle = (
            BranchAcademicCycle.objects.select_related("branch", "academic_year")
            .prefetch_related("class_statuses__academic_class")
            .filter(branch=branch, academic_year=academic_year)
            .first()
        )

    if cycle is None:
        return {
            "deliberation_cycle": None,
            "deliberation_report": None,
            "deliberation_class_rows": [],
            "deliberation_metrics": {
                "total_classes": 0,
                "completed_classes": 0,
                "blocked_classes": 0,
                "missing_grades_count": 0,
                "bulletin_missing_count": 0,
            },
            "deliberation_can_start": False,
            "deliberation_is_started": False,
            "deliberation_classes": [],
            "deliberation_selected_class": None,
            "deliberation_student_rows": [],
            "deliberation_tab": selected_tab,
        }

    report = cycle.closure_reports.order_by("-generated_at", "-id").first()
    class_rows = []
    for item in cycle.class_statuses.all():
        class_rows.append(
            {
                "academic_class": item.academic_class,
                "status": item.get_status_display(),
                "readiness_score": item.readiness_score,
                "is_blocked": item.has_blocking_anomaly,
                "grades_done": item.grades_done,
                "bulletins_done": item.bulletins_done,
                "last_checked_at": item.last_checked_at,
            }
        )

    # Les statuts de classe sont le contrôle le plus récent disponible. Ils
    # restent la source des KPI tant qu'un rapport de clôture n'a pas encore
    # été explicitement généré depuis le bouton « Actualiser le contrôle ».
    metrics = {
        "total_classes": getattr(report, "total_classes", None),
        "completed_classes": getattr(report, "completed_classes", None),
        "blocked_classes": getattr(report, "blocked_classes", None),
        "missing_grades_count": getattr(report, "missing_grades_count", None),
        "bulletin_missing_count": getattr(report, "bulletin_missing_count", None),
    }
    if report is None and class_rows:
        metrics = {
            "total_classes": len(class_rows),
            "completed_classes": sum(not item["is_blocked"] for item in class_rows),
            "blocked_classes": sum(item["is_blocked"] for item in class_rows),
            "missing_grades_count": sum(0 if item["grades_done"] else 1 for item in class_rows),
            "bulletin_missing_count": sum(0 if item["bulletins_done"] else 1 for item in class_rows),
        }
    else:
        metrics = {key: value or 0 for key, value in metrics.items()}
    classes = list(
        AcademicClass.objects.filter(
            branch=cycle.branch,
            academic_year=cycle.academic_year,
            is_active=True,
            is_archived=False,
        )
        .select_related("programme", "academic_year")
        .prefetch_related("semesters")
        .order_by("programme__title", "level", "name", "id")
    )
    decision_counts = {}
    for decision in StudentYearDecision.objects.filter(
        current_class__in=classes,
        academic_year=cycle.academic_year,
    ).values("current_class_id", "is_final"):
        counts = decision_counts.setdefault(decision["current_class_id"], {"prepared": 0, "finalised": 0})
        counts["prepared"] += 1
        if decision["is_final"]:
            counts["finalised"] += 1

    selected_class = None
    if selected_class_id and str(selected_class_id).isdigit():
        selected_class = next((item for item in classes if item.id == int(selected_class_id)), None)
    if selected_class is None and classes:
        selected_class = classes[0]

    enrollment_counts = {
        item["academic_class_id"]: item["total"]
        for item in AcademicEnrollment.objects.filter(
            academic_class__in=classes,
            academic_year=cycle.academic_year,
            is_active=True,
        ).values("academic_class_id").annotate(total=Count("id"))
    }
    sessions_by_class = {
        item.academic_class_id: item
        for item in ClassDeliberationSession.objects.filter(academic_class__in=classes)
    }
    class_options = []
    for academic_class in classes:
        semesters = list(academic_class.semesters.all())
        counts = decision_counts.get(academic_class.id, {"prepared": 0, "finalised": 0})
        class_options.append(
            {
                "academic_class": academic_class,
                "semester_labels": [f"S{semester.number}" for semester in semesters],
                "semester_statuses": [semester.get_status_display() for semester in semesters],
                "is_annual_pair": len(semesters) == 2,
                "student_count": enrollment_counts.get(academic_class.id, 0),
                "session": sessions_by_class.get(academic_class.id),
                **counts,
            }
        )

    student_rows = (
        get_class_deliberation_rows(academic_class=selected_class)
        if selected_class is not None
        else []
    )
    selected_is_prepared = bool(student_rows) and all(
        row["decision"] is not None and bool(row["decision"].synthesis_snapshot)
        for row in student_rows
    )
    deliberation_session = get_session(selected_class) if selected_class is not None else None
    deliberation_session_metrics = session_metrics(selected_class) if selected_class is not None else {
        "total": 0, "processed": 0, "remaining": 0, "review": 0, "debts": 0, "repeated": 0, "rescued": 0,
    }
    session_eligible_ids = set()
    if deliberation_session and deliberation_session.session_threshold is not None:
        session_eligible_ids = {
            decision.id
            for decision in simulate_threshold(
                academic_class=selected_class,
                threshold=deliberation_session.session_threshold,
            )["impacted"]
        }
    for row in student_rows:
        decision = row["decision"]
        row["session_repechage_eligible"] = bool(decision and decision.id in session_eligible_ids)
        row["session_proposal"] = (
            "Éligible au repêchage" if row["session_repechage_eligible"] and not row["jury_processed"] else row["cycle_decision"]
        )
        categories = []
        if row["anomalies"]:
            categories.append("anomalie")
        if row["debt_count"]:
            categories.append("dette")
        if any(not semester.get("is_validated") for semester in row["semesters"]):
            categories.append("semestre")
        if decision and decision.decision == "repeated":
            categories.append("redoublement")
        if row["session_repechage_eligible"]:
            categories.append("repechage")
        row["case_categories"] = categories
    cases = [row for row in student_rows if row["requires_review"] and not row["jury_processed"]]
    ordinary_rows = [row for row in student_rows if not row["requires_review"]]
    review_rows = [row for row in student_rows if row["requires_review"]]
    blocking_anomalies = [
        anomaly for row in student_rows for anomaly in row["anomalies"]
    ]
    deliberation_session_metrics.update(
        {
            "ordinary_total": len(ordinary_rows),
            "review_total": len(review_rows),
            "review_processed": sum(row["jury_processed"] for row in review_rows),
            "review_remaining": len(cases),
            "blocking_anomalies": len(blocking_anomalies),
            "closable": bool(
                deliberation_session
                and deliberation_session.status in {
                    ClassDeliberationSession.STATUS_IN_SESSION,
                    ClassDeliberationSession.STATUS_READY,
                }
                and not cases
                and not blocking_anomalies
            ),
        }
    )
    semester_rules = []
    if student_rows:
        for semester in student_rows[0]["semesters"]:
            semester_rules.append(
                {
                    "label": semester.get("label"),
                    "credit_required": semester.get("credit_required"),
                    "status": semester.get("status"),
                }
            )
    semester_averages = []
    for index in range(2):
        values = [
            Decimal(str(row["semesters"][index].get("average")))
            for row in student_rows
            if len(row["semesters"]) > index
            and row["semesters"][index].get("average") is not None
        ]
        semester_averages.append(
            (sum(values) / len(values)) if values else None
        )
    normal_threshold = (
        deliberation_session.normal_threshold
        if deliberation_session else selected_class.validation_threshold if selected_class else None
    )
    distribution = {
        "semester_averages": semester_averages,
        "under_threshold": sum(
            1
            for row in student_rows
            if any(
                Decimal(str(semester.get("average") or 0)) < normal_threshold
                for semester in row["semesters"]
            )
        ) if normal_threshold is not None else 0,
        "near_threshold": sum(
            1
            for row in student_rows
            if any(
                Decimal(str(semester.get("average") or 0)) >= normal_threshold - selected_class.admissibility_gap
                and Decimal(str(semester.get("average") or 0)) < normal_threshold
                for semester in row["semesters"]
            )
        ) if normal_threshold is not None else 0,
        "validated": sum(not row["requires_review"] for row in student_rows),
        "retake_validated": sum(
            1 for row in student_rows if any(semester.get("is_validated") for semester in row["semesters"])
        ),
    }
    for item in class_options:
        session = item["session"]
        item["session_status"] = session.status if session else ClassDeliberationSession.STATUS_PREPARATION
        item["session_status_label"] = session.get_status_display() if session else "Prête à ouvrir"
        item_metrics = session_metrics(item["academic_class"])
        item["progression"] = f"{item_metrics['processed']}/{item['student_count']}"
    overview_metrics = {
        "total_classes": len(class_options),
        "ready_classes": sum(item["session_status"] == ClassDeliberationSession.STATUS_PREPARATION for item in class_options),
        "in_session_classes": sum(item["session_status"] == ClassDeliberationSession.STATUS_IN_SESSION for item in class_options),
        "finalised_classes": sum(item["finalised"] == item["student_count"] and item["student_count"] > 0 for item in class_options),
        "remaining_cases": sum(session_metrics(item["academic_class"])["review"] for item in class_options),
    }
    return {
        "deliberation_cycle": cycle,
        "deliberation_report": report,
        "deliberation_class_rows": class_rows,
        "deliberation_metrics": metrics,
        "deliberation_can_start": bool(
            report
            and report.status == constants.CLOSURE_REPORT_VALID
            and cycle.status not in _TERMINAL_STATUSES
        ),
        "deliberation_is_started": cycle.status == constants.BRANCH_CYCLE_DELIBERATION,
        "deliberation_classes": class_options,
        "deliberation_selected_class": selected_class,
        "deliberation_student_rows": student_rows,
        "deliberation_selected_class_is_prepared": selected_is_prepared,
        "deliberation_tab": selected_tab,
        "deliberation_session": deliberation_session,
        "deliberation_session_metrics": deliberation_session_metrics,
        "deliberation_cases": cases,
        "deliberation_overview_metrics": overview_metrics,
        "deliberation_semester_rules": semester_rules,
        "deliberation_distribution": distribution,
    }
