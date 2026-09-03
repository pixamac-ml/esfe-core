"""Synthèse annuelle et délibération collective fondées sur la maquette réelle."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from academic_cycle import constants
from academic_cycle.models import BranchAcademicCycle, ClassCycleStatus, StudentYearDecision
from academic_cycle.services.audit_service import log_action
from academics.models import AcademicBulletin, AcademicClass, AcademicDecisionLog, AcademicEnrollment, ECGrade, Semester
from academics.services.year import (
    DECISION_ADMISSIBLE,
    DECISION_NON_ADMIS,
    DECISION_VALIDE,
    compute_annual_decision,
    create_academic_debts,
)


FINAL_SEMESTER_STATUSES = {Semester.STATUS_FINALIZED, Semester.STATUS_PUBLISHED}

ACADEMIC_TO_CYCLE_DECISION = {
    DECISION_VALIDE: constants.DECISION_PROMOTED,
    DECISION_ADMISSIBLE: constants.DECISION_PROMOTED_WITH_ACADEMIC_DEBT,
    DECISION_NON_ADMIS: constants.DECISION_REPEATED,
}


def get_annual_semesters(academic_class: AcademicClass) -> list[Semester]:
    """Return the two semesters configured by the class curriculum.

    Semester numbers are deliberately not interpreted here: a L1 may expose
    S1/S2 while a L2 exposes S3/S4.  The class maquette is the source of truth.
    """
    semesters = list(
        Semester.objects.filter(academic_class=academic_class)
        .prefetch_related("ues__ecs")
        .order_by("number", "id")
    )
    if len(semesters) != 2:
        raise ValidationError(
            "La synthèse annuelle exige exactement deux semestres configurés pour ce niveau."
        )
    return semesters


def _semester_snapshot(result: dict, official_result: dict | None = None) -> dict:
    semester = result["semester"]
    official_result = official_result or {}
    return {
        "id": semester.id,
        "number": semester.number,
        "label": f"S{semester.number}",
        "status": semester.status,
        "average": official_result.get("average", str(result.get("average")) if result.get("average") is not None else None),
        "percentage": official_result.get("percentage", str(result.get("percentage") or Decimal("0"))),
        "credit_required": official_result.get("credit_required", str(result.get("credit_required") or Decimal("0"))),
        "credit_obtained": official_result.get("credit_obtained", str(result.get("credit_obtained") or Decimal("0"))),
        "is_complete": bool(official_result.get("is_complete", result.get("is_complete"))),
        "is_validated": bool(official_result.get("is_validated", result.get("is_validated"))),
        "missing_grades": int(result.get("missing_grades") or 0),
        "blocking_reasons": list(result.get("blocking_reasons") or []),
    }


def _official_semester_results(*, enrollment: AcademicEnrollment, semesters: list[Semester]) -> dict[int, dict | None]:
    """Return and verify the frozen semester results used for deliberation.

    The grade engine still supplies the existing academic rule details (UE/EC
    debts), but an annual deliberation may proceed only when these values match
    the already published individual transcript snapshot.
    """
    bulletins = {
        bulletin.semester_id: bulletin
        for bulletin in AcademicBulletin.objects.filter(
            enrollment=enrollment,
            semester__in=semesters,
            bulletin_type=AcademicBulletin.TYPE_SEMESTER,
            status=AcademicBulletin.STATUS_PUBLISHED,
        )
    }
    official = {}
    for semester in semesters:
        bulletin = bulletins.get(semester.id)
        result = (bulletin.snapshot or {}).get("result", {}) if bulletin else {}
        # New publications always create the transcript snapshot.  A fallback
        # is retained solely for historical published semesters created before
        # that workflow existed; their grade state remains locked by Semester.
        official[semester.id] = result or None
    return official


def _assert_result_matches_published_snapshot(*, result: dict, official_result: dict) -> None:
    comparable = ("average", "percentage", "credit_required", "credit_obtained", "is_complete", "is_validated")
    for field in comparable:
        current = result.get(field)
        published = official_result.get(field)
        if field in {"is_complete", "is_validated"}:
            matches = bool(current) == bool(published)
        else:
            if current is None or published is None:
                matches = current is None and published is None
            else:
                try:
                    # Les snapshots JSON peuvent normaliser Decimal("0.00")
                    # en "0". La valeur academique est identique : une
                    # comparaison textuelle bloquait a tort la deliberation.
                    matches = Decimal(str(current)) == Decimal(str(published))
                except Exception:
                    matches = str(current) == str(published)
        if not matches:
            raise ValidationError(
                "Les résultats courants divergent du relevé semestriel publié ; une correction officielle est requise avant délibération."
            )


def _ensure_class_is_ready_for_synthesis(academic_class: AcademicClass) -> list[Semester]:
    semesters = get_annual_semesters(academic_class)
    incomplete = [
        f"S{semester.number} ({semester.get_status_display()})"
        for semester in semesters
        if semester.status not in FINAL_SEMESTER_STATUSES
    ]
    if incomplete:
        raise ValidationError(
            "La synthèse annuelle est bloquée : résultats semestriels non validés ("
            + ", ".join(incomplete)
            + ")."
        )
    return semesters


def build_enrollment_annual_synthesis(
    enrollment: AcademicEnrollment,
    *,
    semesters=None,
    grades_by_ec_id=None,
) -> dict:
    """Build a serialisable proposal without persisting an official decision."""
    if enrollment.academic_class_id is None:
        raise ValidationError("L'inscription académique ne possède pas de classe.")
    if semesters is None:
        semesters = _ensure_class_is_ready_for_synthesis(enrollment.academic_class)
    else:
        semesters = list(semesters)
        if len(semesters) != 2 or any(
            semester.academic_class_id != enrollment.academic_class_id
            or semester.status not in FINAL_SEMESTER_STATUSES
            for semester in semesters
        ):
            raise ValidationError(
                "Les semestres transmis ne correspondent pas a une synthese annuelle finalisee."
            )
    decision = compute_annual_decision(
        enrollment,
        semesters=semesters,
        grades_by_ec_id=grades_by_ec_id,
    )
    official_results = _official_semester_results(enrollment=enrollment, semesters=semesters)
    for result in decision["annual_result"].get("semester_results", []):
        official_result = official_results[result["semester"].id]
        if official_result is not None:
            _assert_result_matches_published_snapshot(
                result=result,
                official_result=official_result,
            )
    annual_result = decision["annual_result"]
    if not annual_result.get("is_complete"):
        reasons = "; ".join(annual_result.get("blocking_reasons") or [])
        raise ValidationError(
            "La synthèse annuelle est bloquée par des données incomplètes"
            + (f" : {reasons}" if reasons else ".")
        )

    academic_decision = decision["decision"]
    cycle_decision = ACADEMIC_TO_CYCLE_DECISION.get(academic_decision)
    if cycle_decision is None:
        raise ValidationError("La règle académique renvoie une décision non exploitable.")

    semester_results = annual_result.get("semester_results") or []
    return {
        "version": 1,
        "academic_decision": academic_decision,
        "cycle_decision": cycle_decision,
        "rule_code": decision.get("rule_code"),
        "rule_label": decision.get("rule_label"),
        "reasons": list(decision.get("reasons") or []),
        "threshold": str(decision.get("threshold") or Decimal("0")),
        "admissibility_gap": str(decision.get("admissibility_gap") or Decimal("0")),
        "requires_academic_debt": bool(decision.get("requires_academic_debt")),
        "debt_subjects": list(decision.get("debt_subjects") or []),
        "semesters": [
            _semester_snapshot(result, official_results[result["semester"].id])
            for result in semester_results
        ],
        "credits": {
            "required": str(annual_result.get("credit_required") or Decimal("0")),
            "obtained": str(annual_result.get("credit_obtained") or Decimal("0")),
        },
    }


def _student_for_enrollment(enrollment: AcademicEnrollment):
    student = getattr(enrollment.student, "student_profile", None)
    if student is None:
        raise ValidationError("Le profil étudiant est introuvable pour cette inscription académique.")
    return student


def _proposal_reason(synthesis: dict) -> str:
    label = synthesis.get("rule_label") or synthesis.get("academic_decision") or "Décision calculée"
    reasons = "; ".join(synthesis.get("reasons") or [])
    return f"Proposition automatique — {label}." + (f" {reasons}" if reasons else "")


@transaction.atomic
def prepare_class_annual_synthesis(*, academic_class: AcademicClass, actor) -> dict:
    """Prepare all ordinary cases for one class without making them official.

    The operation is idempotent for a draft and refuses to replace an already
    finalised annual decision.  It is deliberately class-scoped so that a
    director can review a large promotion collectively.
    """
    academic_class = (
        AcademicClass.objects.select_for_update()
        .select_related("branch", "academic_year")
        .get(pk=academic_class.pk)
    )
    semesters = _ensure_class_is_ready_for_synthesis(academic_class)
    enrollments = list(
        AcademicEnrollment.objects.select_related(
            "student__student_profile",
            "academic_class",
            "academic_year",
            "branch",
        )
        .filter(
            academic_class=academic_class,
            academic_year=academic_class.academic_year,
            is_active=True,
        )
        .order_by("id")
    )

    grades_by_enrollment = defaultdict(dict)
    for grade in ECGrade.objects.filter(
        enrollment__in=enrollments,
        ec__ue__semester__in=semesters,
    ).select_related("ec"):
        grades_by_enrollment[grade.enrollment_id][grade.ec_id] = grade

    prepared, finalised = [], []
    for enrollment in enrollments:
        student = _student_for_enrollment(enrollment)
        synthesis = build_enrollment_annual_synthesis(
            enrollment,
            semesters=semesters,
            grades_by_ec_id=grades_by_enrollment[enrollment.id],
        )
        decision, created = StudentYearDecision.objects.select_for_update().get_or_create(
            student=student,
            academic_year=enrollment.academic_year,
            defaults={
                "branch": enrollment.branch,
                "current_class": academic_class,
                "source_enrollment": enrollment,
                "decision": synthesis["cycle_decision"],
                "reason": _proposal_reason(synthesis),
                "synthesis_snapshot": synthesis,
                "decided_by": actor if getattr(actor, "is_authenticated", False) else None,
                "decided_at": timezone.now(),
                "is_final": False,
            },
        )
        if not created and (
            decision.branch_id != enrollment.branch_id
            or decision.current_class_id != academic_class.id
            or (
                decision.source_enrollment_id is not None
                and decision.source_enrollment_id != enrollment.id
            )
        ):
            raise ValidationError(
                "Une autre décision annuelle existe déjà pour cet étudiant et cette année."
            )
        if decision.is_final:
            finalised.append(decision)
            continue
        if not created:
            old_values = {
                "decision": decision.decision,
                "synthesis_snapshot": decision.synthesis_snapshot,
            }
            decision.branch = enrollment.branch
            decision.current_class = academic_class
            decision.source_enrollment = enrollment
            decision.decision = synthesis["cycle_decision"]
            decision.reason = _proposal_reason(synthesis)
            decision.synthesis_snapshot = synthesis
            decision.decided_by = actor if getattr(actor, "is_authenticated", False) else None
            decision.decided_at = timezone.now()
            decision.save(
                update_fields=[
                    "branch", "current_class", "source_enrollment", "decision", "reason",
                    "synthesis_snapshot", "decided_by", "decided_at", "updated_at",
                ]
            )
            log_action(
                actor,
                "annual_synthesis.refreshed",
                decision,
                old_values=old_values,
                new_values={"decision": decision.decision, "synthesis_snapshot": synthesis},
                branch=academic_class.branch,
                academic_year=academic_class.academic_year,
                student=student,
            )
        else:
            log_action(
                actor,
                "annual_synthesis.prepared",
                decision,
                new_values={"decision": decision.decision, "synthesis_snapshot": synthesis},
                branch=academic_class.branch,
                academic_year=academic_class.academic_year,
                student=student,
            )
        prepared.append(decision)

    return {
        "academic_class": academic_class,
        "prepared": prepared,
        "finalised": finalised,
        "total": len(enrollments),
    }


def _create_decision_log(*, academic_class: AcademicClass, actor, decisions: list[StudentYearDecision]):
    snapshots = [decision.synthesis_snapshot or {} for decision in decisions]
    academic_codes = [snapshot.get("academic_decision") for snapshot in snapshots]
    return AcademicDecisionLog.objects.create(
        academic_class=academic_class,
        academic_year=academic_class.academic_year,
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        threshold=Decimal(str(snapshots[0].get("threshold") or "0")) if snapshots else Decimal("0"),
        admissibility_gap=Decimal(str(snapshots[0].get("admissibility_gap") or "0")) if snapshots else Decimal("0"),
        total_students=len(decisions),
        validated_count=academic_codes.count(DECISION_VALIDE),
        admissible_count=academic_codes.count(DECISION_ADMISSIBLE),
        non_admis_count=academic_codes.count(DECISION_NON_ADMIS),
        rule_codes_used=sorted({snapshot.get("rule_code") for snapshot in snapshots if snapshot.get("rule_code")}),
        details={
            "stage": "annual_collective_deliberation",
            "decision_ids": [decision.id for decision in decisions],
        },
    )


@transaction.atomic
def finalise_class_deliberation(*, academic_class: AcademicClass, actor, branch_cycle) -> dict:
    """Make a prepared class decision official in one atomic, auditable action."""
    # Serialise preparation/finalisation for this class and the state change of
    # the annex cycle.  This is especially important when two DE sessions are
    # opened concurrently from the dashboard.
    academic_class = (
        AcademicClass.objects.select_for_update()
        .select_related("branch", "academic_year")
        .get(pk=academic_class.pk)
    )
    branch_cycle = BranchAcademicCycle.objects.select_for_update().get(pk=branch_cycle.pk)
    if branch_cycle.branch_id != academic_class.branch_id or branch_cycle.academic_year_id != academic_class.academic_year_id:
        raise ValidationError("La classe ne correspond pas au cycle de délibération sélectionné.")
    if branch_cycle.status != constants.BRANCH_CYCLE_DELIBERATION:
        raise ValidationError("La délibération de l'annexe doit être ouverte avant validation officielle.")

    semesters = _ensure_class_is_ready_for_synthesis(academic_class)
    enrollments = list(
        AcademicEnrollment.objects.select_for_update().filter(
            academic_class=academic_class,
            academic_year=academic_class.academic_year,
            is_active=True,
        )
    )
    expected_count = len(enrollments)
    if not expected_count:
        raise ValidationError("Aucun étudiant actif ne peut être délibéré pour cette classe.")
    enrollment_by_id = {enrollment.id: enrollment for enrollment in enrollments}
    grades_by_enrollment = defaultdict(dict)
    for grade in ECGrade.objects.filter(
        enrollment__in=enrollments,
        ec__ue__semester__in=semesters,
    ).select_related("ec"):
        grades_by_enrollment[grade.enrollment_id][grade.ec_id] = grade
    decisions = list(
        StudentYearDecision.objects.select_for_update()
        .select_related("source_enrollment", "student")
        .filter(
            current_class=academic_class,
            academic_year=academic_class.academic_year,
        )
        .order_by("id")
    )
    if len(decisions) != expected_count or any(
        not decision.synthesis_snapshot for decision in decisions
    ):
        raise ValidationError(
            "Préparez et contrôlez d'abord la synthèse annuelle de toute la classe."
        )
    if any(not decision.jury_processed for decision in decisions):
        raise ValidationError(
            "La finalisation exige que chaque dossier ait été traité par le jury."
        )

    already_final = [decision for decision in decisions if decision.is_final]
    if already_final:
        if len(already_final) == len(decisions):
            return {"academic_class": academic_class, "decisions": decisions, "idempotent": True}
        raise ValidationError("La délibération contient un état partiellement finalisé et ne peut pas être écrasée.")

    for decision in decisions:
        enrollment = enrollment_by_id.get(decision.source_enrollment_id)
        if enrollment is None:
            raise ValidationError("Une décision finale ne peut pas être liée à une inscription source absente.")
        # A correction exceptionnelle de notes après la préparation rend la
        # proposition caduque.  Ne jamais créer des dettes à partir de notes
        # différentes de celles qui ont été contrôlées par le DE.
        current_synthesis = build_enrollment_annual_synthesis(
            enrollment,
            semesters=semesters,
            grades_by_ec_id=grades_by_enrollment[enrollment.id],
        )
        if current_synthesis != (decision.synthesis_snapshot or {}):
            raise ValidationError(
                "Les notes ont changé depuis la préparation. Recalculez puis contrôlez la synthèse annuelle."
            )
        automatic_decision = decision.decision
        effective_decision = decision.jury_decision or automatic_decision
        old_values = {"decision": automatic_decision, "is_final": False}
        decision.decision = effective_decision
        decision.is_final = True
        decision.decided_by = actor if getattr(actor, "is_authenticated", False) else None
        decision.decided_at = timezone.now()
        decision.save(update_fields=["decision", "is_final", "decided_by", "decided_at", "updated_at"])
        snapshot = decision.synthesis_snapshot or {}
        if (
            snapshot.get("requires_academic_debt")
            and effective_decision == constants.DECISION_PROMOTED_WITH_ACADEMIC_DEBT
        ):
            annual_result = compute_annual_decision(
                enrollment,
                semesters=semesters,
                grades_by_ec_id=grades_by_enrollment[enrollment.id],
            )["annual_result"]
            for semester_result in annual_result.get("semester_results", []):
                if not semester_result.get("is_validated"):
                    create_academic_debts(enrollment, semester_result)
        log_action(
            actor,
            "annual_deliberation.finalised",
            decision,
            old_values=old_values,
            new_values={
                "automatic_decision": automatic_decision,
                "jury_decision": decision.jury_decision,
                "decision": decision.decision,
                "is_final": True,
            },
            branch=academic_class.branch,
            academic_year=academic_class.academic_year,
            student=decision.student,
        )

    ClassCycleStatus.objects.filter(
        branch_cycle=branch_cycle,
        academic_class=academic_class,
    ).update(status=constants.CLASS_DELIBERATED)
    _create_decision_log(academic_class=academic_class, actor=actor, decisions=decisions)
    return {"academic_class": academic_class, "decisions": decisions, "idempotent": False}


def get_class_deliberation_rows(*, academic_class: AcademicClass) -> list[dict]:
    """Rows for the DE review table, using persisted proposals only."""
    decisions = {
        decision.student_id: decision
        for decision in StudentYearDecision.objects.filter(
            current_class=academic_class,
            academic_year=academic_class.academic_year,
        ).select_related("student__user")
    }
    rows = []
    for enrollment in AcademicEnrollment.objects.filter(
        academic_class=academic_class,
        academic_year=academic_class.academic_year,
        is_active=True,
    ).select_related("student__student_profile__user").order_by("id"):
        student = _student_for_enrollment(enrollment)
        decision = decisions.get(student.id)
        snapshot = decision.synthesis_snapshot if decision else {}
        semesters = snapshot.get("semesters", [])
        debt_subjects = snapshot.get("debt_subjects", [])
        academic_code = snapshot.get("academic_decision", "")
        requires_review = bool(
            snapshot.get("requires_academic_debt")
            or debt_subjects
            or academic_code == DECISION_NON_ADMIS
            or any(not item.get("is_validated") for item in semesters)
        )
        rows.append(
            {
                "student": student,
                "last_name": getattr(getattr(student, "user", None), "last_name", "") or "",
                "first_name": getattr(getattr(student, "user", None), "first_name", "") or "",
                "matricule": getattr(student, "matricule", "") or "-",
                "decision": decision,
                "semesters": semesters,
                "academic_decision": snapshot.get("academic_decision", "À préparer"),
                "cycle_decision": decision.get_decision_display() if decision else "À préparer",
                "jury_decision": (
                    decision.get_jury_decision_display()
                    if decision and decision.jury_decision
                    else "Non traitée"
                ),
                "jury_processed": bool(decision and decision.jury_processed),
                "debts": debt_subjects,
                "debt_count": len(debt_subjects),
                "requires_review": requires_review,
                "is_repeat_proposal": bool(decision and decision.decision == "repeated"),
                "proposal_label": snapshot.get("rule_label") or academic_code or "À préparer",
                "proposal_reasons": list(snapshot.get("reasons", [])),
                "is_final": bool(decision and decision.is_final),
                "anomalies": [
                    reason
                    for semester in semesters
                    for reason in semester.get("blocking_reasons", [])
                ],
            }
        )
    return rows


def get_deliberation_student_detail(*, academic_class: AcademicClass, student_id: int) -> dict:
    """Retourne le dossier de jury à partir des données et snapshots officiels."""
    row = next(
        (item for item in get_class_deliberation_rows(academic_class=academic_class) if item["student"].id == student_id),
        None,
    )
    if row is None:
        raise ValidationError("Étudiant introuvable dans cette délibération.")
    enrollment = AcademicEnrollment.objects.select_related(
        "student__student_profile__inscription__candidature",
        "programme",
        "academic_year",
    ).get(
        pk=row["decision"].source_enrollment_id if row["decision"] and row["decision"].source_enrollment_id else 0
    )
    grades = list(
        ECGrade.objects.filter(enrollment=enrollment)
        .filter(ec__ue__semester__academic_class=academic_class)
        .select_related("ec", "ec__ue", "ec__ue__semester")
        .order_by("ec__ue__semester__number", "ec__ue__code", "ec__title")
    )
    return {"row": row, "enrollment": enrollment, "grades": grades}


def get_final_annual_decision(*, enrollment: AcademicEnrollment) -> StudentYearDecision:
    """Return the immutable official decision for the exact yearly enrollment."""
    student = _student_for_enrollment(enrollment)
    decision = (
        StudentYearDecision.objects.select_related("source_enrollment")
        .filter(
            student=student,
            academic_year=enrollment.academic_year,
            current_class=enrollment.academic_class,
            is_final=True,
        )
        .first()
    )
    if decision is None or not decision.synthesis_snapshot:
        raise ValidationError(
            "Le bulletin annuel est disponible après la délibération annuelle validée."
        )
    if decision.source_enrollment_id and decision.source_enrollment_id != enrollment.id:
        raise ValidationError("La décision annuelle ne correspond pas à cette inscription académique.")
    return decision
