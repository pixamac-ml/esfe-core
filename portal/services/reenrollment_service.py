from __future__ import annotations

import logging
from decimal import Decimal

logger = logging.getLogger("esfe.reenrollment")

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from academics.models import AcademicClass, AcademicEnrollment, AcademicYear
from academics.services.academic_positioning import get_positioning_fee_for_level
from academics.services.year import DECISION_VALIDE, DECISION_ADMISSIBLE, DECISION_NON_ADMIS, carry_forward_debts, compute_annual_decision, compute_annual_result
from accounts.access import get_user_position
from accounts.dashboards.helpers import is_executive, is_finance, is_manager
from admissions.models import Candidature
from inscriptions.models import Inscription
from portal.models import SupportAuditLog
from portal.services.it_support_service import log_support_action
from students.models import Student, StudentYearDecision


def _semester_averages(enrollment):
    result = compute_annual_decision(enrollment)
    averages = [
        Decimal(str(sr.get("average")))
        for sr in result.get("semester_results", [])
        if sr.get("average") is not None
    ]
    return averages


def _annual_average(enrollment):
    averages = _semester_averages(enrollment)
    if not averages:
        return None
    return (sum(averages) / len(averages)).quantize(Decimal("0.01"))


def _decision_from_annual_result(*, enrollment, annual_result):
    return compute_annual_decision(enrollment)["decision"]


def _decision_from_average(*, academic_class, annual_average):
    if annual_average is None:
        return StudentYearDecision.DECISION_REPEATED

    threshold = academic_class.validation_threshold or Decimal("10.00")
    if annual_average >= threshold:
        return StudentYearDecision.DECISION_PROMOTED
    return StudentYearDecision.DECISION_REPEATED


def _next_level(level):
    value = str(level or "").upper().strip()
    ordered = ["L1", "L2", "L3", "M1", "M2"]
    if value not in ordered:
        return None
    index = ordered.index(value)
    return ordered[index + 1] if index + 1 < len(ordered) else None


def _is_terminal_level(level):
    return str(level or "").upper().strip() in {"L3", "M2"}


def _financial_status(inscription):
    if inscription is None:
        return {"status": "missing", "label": "Inscription absente", "balance": 0}
    if inscription.balance > 0:
        return {"status": "debt", "label": "Solde restant", "balance": inscription.balance}
    return {"status": "paid", "label": "A jour", "balance": 0}


def can_user_handle_reenrollment(user):
    position = getattr(getattr(user, "profile", None), "position", "") or get_user_position(user)
    role = getattr(getattr(user, "profile", None), "role", "")
    return user.is_superuser or position in {
        "it_support",
        "branch_manager",
        "finance_manager",
        "payment_agent",
        "director_of_studies",
        "executive_director",
        "deputy_executive_director",
    } or role in {"finance", "executive", "superadmin"} or is_manager(user) or is_finance(user) or is_executive(user)


def can_user_validate_academic(user):
    position = getattr(getattr(user, "profile", None), "position", "") or get_user_position(user)
    return user.is_superuser or position in {"director_of_studies", "executive_director", "deputy_executive_director", "it_support"} or is_executive(user)


def can_user_validate_finance(user):
    position = getattr(getattr(user, "profile", None), "position", "") or get_user_position(user)
    role = getattr(getattr(user, "profile", None), "role", "")
    return user.is_superuser or position in {"branch_manager", "finance_manager", "payment_agent"} or role == "finance" or is_manager(user) or is_finance(user)


def can_user_apply_reenrollment(user):
    position = getattr(getattr(user, "profile", None), "position", "") or get_user_position(user)
    return user.is_superuser or position in {"it_support", "branch_manager", "director_of_studies", "executive_director", "deputy_executive_director"} or is_manager(user) or is_executive(user)


def _decision_target_label(decision):
    return f"{decision.student} - {decision.source_academic_year} - {decision.get_decision_display()}"


def _audit_decision(*, decision, actor, action_type, details):
    return log_support_action(
        actor=actor,
        branch=decision.source_enrollment.branch,
        action_type=action_type,
        target_user=decision.student.user,
        target_label=_decision_target_label(decision),
        details=details,
    )


DECISION_MAP_NEW_TO_OLD = {
    DECISION_VALIDE: StudentYearDecision.DECISION_PROMOTED,
    DECISION_ADMISSIBLE: StudentYearDecision.DECISION_PROMOTED_WITH_DEBT,
    DECISION_NON_ADMIS: StudentYearDecision.DECISION_REPEATED,
}


def _map_decision(annual_decision_code):
    return DECISION_MAP_NEW_TO_OLD.get(annual_decision_code, StudentYearDecision.DECISION_REPEATED)


TARGET_DECISIONS = {
    StudentYearDecision.DECISION_PROMOTED,
    StudentYearDecision.DECISION_PROMOTED_WITH_DEBT,
    StudentYearDecision.DECISION_REPEATED,
}

ADMINISTRATIVE_DECISIONS = {
    StudentYearDecision.DECISION_TRANSFERRED,
    StudentYearDecision.DECISION_SUSPENDED,
    StudentYearDecision.DECISION_ABANDONED,
    StudentYearDecision.DECISION_COMPLETED,
}

FINANCE_CLEARANCE_REQUIRED_DECISIONS = {
    StudentYearDecision.DECISION_PROMOTED,
    StudentYearDecision.DECISION_PROMOTED_WITH_DEBT,
    StudentYearDecision.DECISION_REPEATED,
    StudentYearDecision.DECISION_TRANSFERRED,
    StudentYearDecision.DECISION_COMPLETED,
}

ACADEMIC_RULE_DECISIONS = TARGET_DECISIONS | {StudentYearDecision.DECISION_COMPLETED}


def _decision_payload_from_rule(annual_decision):
    return {
        "rule_source": "computed",
        "rule_code": annual_decision.get("rule_code"),
        "rule_label": annual_decision.get("rule_label"),
        "threshold": str(annual_decision.get("threshold") or ""),
        "admissibility_gap": str(annual_decision.get("admissibility_gap") or ""),
        "requires_academic_debt": bool(annual_decision.get("requires_academic_debt")),
        "debt_subjects": annual_decision.get("debt_subjects", []),
        "reasons": annual_decision.get("reasons", []),
        "semester_results": annual_decision.get("semester_results", []),
    }


def _decision_payload_from_manual_average(*, academic_class, annual_average):
    threshold = academic_class.validation_threshold or Decimal("10.00")
    return {
        "rule_source": "manual_average",
        "rule_code": "manual_average_legacy",
        "rule_label": "Moyenne annuelle fournie",
        "threshold": str(threshold),
        "annual_average": str(annual_average) if annual_average is not None else None,
        "reasons": ["Decision calculee depuis une moyenne annuelle fournie au service."],
    }


def _assert_decision_matches_academic_rules(decision):
    if decision.decision not in ACADEMIC_RULE_DECISIONS:
        return
    if decision.decision_payload.get("rule_source") == "manual_average":
        return
    automatic = compute_annual_decision(decision.source_enrollment)
    expected = automatic["decision"]
    if decision.decision != expected:
        expected_label = dict(StudentYearDecision.DECISION_CHOICES).get(expected, expected)
        raise ValidationError(
            "La decision choisie ne correspond pas aux regles academiques automatiques. "
            f"Decision attendue: {expected_label}."
        )


def _validate_decision_ready(decision):
    if decision.decision in ADMINISTRATIVE_DECISIONS:
        return
    if decision.decision not in TARGET_DECISIONS:
        raise ValidationError("Decision annuelle inconnue.")
    if decision.target_class is None or decision.target_academic_year is None:
        raise ValidationError("Classe et annee cible obligatoires.")
    if decision.target_class.academic_year_id != decision.target_academic_year_id:
        raise ValidationError("La classe cible ne correspond pas a l'annee cible.")
    if not decision.target_class.is_active or decision.target_class.is_archived:
        raise ValidationError("La classe cible doit etre active et non archivee.")
    if decision.target_class.programme_id != decision.source_enrollment.programme_id:
        raise ValidationError("La classe cible doit rester dans le meme programme.")
    if decision.target_class.branch_id != decision.source_enrollment.branch_id:
        raise ValidationError("La classe cible doit rester dans la meme annexe.")


def build_reenrollment_candidates(*, source_year=None, source_class=None, branch=None):
    queryset = AcademicEnrollment.objects.select_related(
        "student",
        "student__student_profile",
        "inscription",
        "academic_class",
        "academic_year",
        "programme",
        "branch",
    ).filter(
        status=AcademicEnrollment.STATUS_ACTIVE,
        is_active=True,
        is_archived=False,
        academic_class__is_archived=False,
    )

    if source_year is not None:
        queryset = queryset.filter(academic_year=source_year)
    if source_class is not None:
        queryset = queryset.filter(academic_class=source_class)
    if branch is not None:
        queryset = queryset.filter(branch=branch)

    candidates = []
    for enrollment in queryset.order_by("academic_class__level", "student__last_name", "student__first_name"):
        student = getattr(enrollment.student, "student_profile", None)
        annual_decision = compute_annual_decision(enrollment)
        annual_result = annual_decision["annual_result"]
        annual_average = annual_decision.get("annual_average")
        proposed_decision = _map_decision(annual_decision["decision"])
        proposed_decision_label = dict(StudentYearDecision.DECISION_CHOICES).get(proposed_decision, proposed_decision)
        candidates.append(
            {
                "student": student,
                "user": enrollment.student,
                "enrollment": enrollment,
                "matricule": getattr(student, "matricule", ""),
                "full_name": getattr(student, "full_name", enrollment.student.get_full_name() or enrollment.student.username),
                "source_class": enrollment.academic_class,
                "source_year": enrollment.academic_year,
                "annual_average": annual_average,
                "annual_result": annual_result,
                "annual_decision": annual_decision,
                "financial_status": _financial_status(enrollment.inscription),
                "proposed_decision": proposed_decision,
                "proposed_decision_label": proposed_decision_label,
                "year_decision": StudentYearDecision.objects.filter(
                    student=student,
                    source_enrollment=enrollment,
                ).first() if student else None,
            }
        )
    return candidates


def get_reenrollment_dashboard_context(*, branch, source_year=None, source_class=None, target_year=None, actor=None, toast=None):
    academic_years = AcademicYear.objects.all().order_by("-start_date")
    classes = AcademicClass.objects.select_related("academic_year", "programme", "branch").filter(
        is_archived=False,
    )
    if branch is not None:
        classes = classes.filter(branch=branch)
    classes = classes.order_by("-academic_year__start_date", "programme__title", "level")
    target_classes = AcademicClass.objects.select_related("academic_year", "programme", "branch").filter(
        is_active=True,
        is_archived=False,
    )
    if branch is not None:
        target_classes = target_classes.filter(branch=branch)
    target_classes = target_classes.order_by("-academic_year__start_date", "programme__title", "level")
    if target_year is not None:
        target_classes = target_classes.filter(academic_year=target_year)

    candidate_filters_required = source_year is None and source_class is None
    candidates = []
    if not candidate_filters_required:
        candidates = build_reenrollment_candidates(
            source_year=source_year,
            source_class=source_class,
            branch=branch,
        )
    decisions = StudentYearDecision.objects.select_related(
        "student",
        "student__user",
        "source_enrollment",
        "source_class",
        "source_academic_year",
        "target_class",
        "target_academic_year",
        "target_inscription",
        "target_enrollment",
    )
    if branch is not None:
        decisions = decisions.filter(source_enrollment__branch=branch)
    decisions = decisions.order_by("-created_at")[:80]
    return {
        "branch": branch,
        "source_year": source_year,
        "source_class": source_class,
        "target_year": target_year,
        "academic_years": academic_years,
        "classes": classes,
        "target_classes": target_classes,
        "candidates": candidates,
        "candidate_filters_required": candidate_filters_required,
        "decisions": decisions,
        "decision_choices": StudentYearDecision.DECISION_CHOICES,
        "target_decision_values": TARGET_DECISIONS,
        "can_academic_validate": can_user_validate_academic(actor) if actor else False,
        "can_finance_validate": can_user_validate_finance(actor) if actor else False,
        "can_apply": can_user_apply_reenrollment(actor) if actor else False,
        "dashboard_type": "reenrollment",
        "toast": toast,
    }


@transaction.atomic
def archive_enrollment_for_transition(*, enrollment, archived_at=None):
    if not isinstance(enrollment, AcademicEnrollment):
        enrollment = AcademicEnrollment.objects.select_for_update().get(pk=enrollment)
    else:
        enrollment = AcademicEnrollment.objects.select_for_update().get(pk=enrollment.pk)

    enrollment.status = AcademicEnrollment.STATUS_ARCHIVED
    enrollment.is_active = False
    enrollment.is_archived = True
    enrollment.archived_at = archived_at or timezone.now()
    enrollment.save(update_fields=["status", "is_active", "is_archived", "archived_at"])
    return enrollment


def _carry_forward_debts(source_enrollment, target_enrollment):
    """
    Reporte les dettes academiques non soldees vers la nouvelle inscription.
    Delegue a academics.services.year.carry_forward_debts().
    """
    carry_forward_debts(source_enrollment, target_enrollment)


def _resolve_target_class(*, source_enrollment, target_academic_year, decision, target_class=None):
    if target_class is not None:
        return target_class

    if decision == StudentYearDecision.DECISION_REPEATED and target_academic_year is not None:
        return AcademicClass.objects.filter(
            programme=source_enrollment.programme,
            branch=source_enrollment.branch,
            academic_year=target_academic_year,
            level=source_enrollment.academic_class.level,
            is_active=True,
            is_archived=False,
        ).first()
    if decision in {StudentYearDecision.DECISION_PROMOTED, StudentYearDecision.DECISION_PROMOTED_WITH_DEBT} and target_academic_year is not None:
        next_level = _next_level(source_enrollment.academic_class.level)
        if next_level:
            return AcademicClass.objects.filter(
                programme=source_enrollment.programme,
                branch=source_enrollment.branch,
                academic_year=target_academic_year,
                level=next_level,
                is_active=True,
                is_archived=False,
            ).first()

    return None


@transaction.atomic
def propose_student_decision(
    *,
    student,
    source_enrollment,
    target_academic_year=None,
    target_class=None,
    decision=None,
    annual_average=None,
    proposed_by=None,
    note="",
):
    if not isinstance(student, Student):
        student = Student.objects.select_related("user").get(pk=student)

    if not isinstance(source_enrollment, AcademicEnrollment):
        source_enrollment = AcademicEnrollment.objects.select_related(
            "academic_class",
            "academic_year",
            "programme",
            "branch",
        ).get(pk=source_enrollment)

    if source_enrollment.student_id != student.user_id:
        raise ValidationError("L'inscription academique source ne correspond pas a l'etudiant.")

    provided_average = annual_average is not None
    annual_average = annual_average if provided_average else _annual_average(source_enrollment)
    annual_decision = compute_annual_decision(source_enrollment)
    decision_from_rule = _map_decision(annual_decision["decision"])
    decision = decision or (
        _decision_from_average(academic_class=source_enrollment.academic_class, annual_average=annual_average)
        if provided_average
        else decision_from_rule
    )
    if decision in ACADEMIC_RULE_DECISIONS and decision != decision_from_rule and not provided_average:
        expected_label = dict(StudentYearDecision.DECISION_CHOICES).get(decision_from_rule, decision_from_rule)
        raise ValidationError(
            "La decision academique doit suivre le calcul automatique. "
            f"Decision attendue: {expected_label}."
        )

    if target_academic_year is not None and not isinstance(target_academic_year, AcademicYear):
        target_academic_year = AcademicYear.objects.get(pk=target_academic_year)

    if target_class is not None and not isinstance(target_class, AcademicClass):
        target_class = AcademicClass.objects.get(pk=target_class)

    target_class = _resolve_target_class(
        source_enrollment=source_enrollment,
        target_academic_year=target_academic_year,
        decision=decision,
        target_class=target_class,
    )
    if target_class is not None and target_academic_year is None:
        target_academic_year = target_class.academic_year

    if target_class and (not target_class.is_active or target_class.is_archived):
        raise ValidationError("La classe cible doit etre active et non archivee.")
    if target_class and target_class.academic_year_id != target_academic_year.id:
        raise ValidationError("La classe cible ne correspond pas a l'annee cible.")
    if decision in TARGET_DECISIONS and (
        target_class is None or target_academic_year is None
    ):
        raise ValidationError("Classe et annee cible obligatoires pour un passage ou un redoublement.")
    if decision in ADMINISTRATIVE_DECISIONS:
        target_class = None
        target_academic_year = None

    existing = StudentYearDecision.objects.filter(student=student, source_enrollment=source_enrollment).first()
    if existing and existing.workflow_status == StudentYearDecision.WORKFLOW_APPLIED:
        raise ValidationError("Cette decision est deja appliquee et ne peut plus etre modifiee.")

    decision_obj, _created = StudentYearDecision.objects.update_or_create(
        student=student,
        source_enrollment=source_enrollment,
        defaults={
            "source_academic_year": source_enrollment.academic_year,
            "source_class": source_enrollment.academic_class,
            "target_academic_year": target_academic_year,
            "target_class": target_class,
            "decision": decision,
            "annual_average": annual_average,
            "decision_payload": (
                _decision_payload_from_manual_average(
                    academic_class=source_enrollment.academic_class,
                    annual_average=annual_average,
                )
                if provided_average
                else _decision_payload_from_rule(annual_decision)
            ),
            "note": note,
            "proposed_by": proposed_by,
            "workflow_status": StudentYearDecision.WORKFLOW_DRAFT,
            "academic_validated_by": None,
            "academic_validated_at": None,
            "finance_validated_by": None,
            "finance_validated_at": None,
            "rejected_by": None,
            "rejected_at": None,
            "rejection_reason": "",
        },
    )
    if proposed_by:
        _audit_decision(
            decision=decision_obj,
            actor=proposed_by,
            action_type=SupportAuditLog.ACTION_REENROLLMENT_PROPOSED,
            details=(
                f"Decision proposee: {decision_obj.get_decision_display()} | "
                f"Source: {source_enrollment.academic_class} | Cible: {target_class or '-'}"
            ),
        )
    return decision_obj


@transaction.atomic
def validate_student_decision_academic(*, decision, actor):
    if not can_user_validate_academic(actor):
        raise ValidationError("Vous ne pouvez pas valider pedagogiquement cette decision.")
    decision_pk = decision.pk if isinstance(decision, StudentYearDecision) else decision
    decision = StudentYearDecision.objects.select_related(
        "student",
        "student__user",
        "source_enrollment",
        "target_class",
        "target_academic_year",
    ).select_for_update(of=("self",)).get(pk=decision_pk)
    if decision.workflow_status != StudentYearDecision.WORKFLOW_DRAFT:
        raise ValidationError("Seule une decision en brouillon peut etre validee pedagogiquement.")
    _validate_decision_ready(decision)
    _assert_decision_matches_academic_rules(decision)
    if decision.source_enrollment.status != AcademicEnrollment.STATUS_ACTIVE:
        raise ValidationError("L'inscription source n'est plus active.")
    decision.workflow_status = StudentYearDecision.WORKFLOW_ACADEMIC_VALIDATED
    decision.academic_validated_by = actor
    decision.academic_validated_at = timezone.now()
    decision.save(update_fields=["workflow_status", "academic_validated_by", "academic_validated_at", "updated_at"])
    _audit_decision(
        decision=decision,
        actor=actor,
        action_type=SupportAuditLog.ACTION_REENROLLMENT_VALIDATED,
        details="Validation pedagogique enregistree.",
    )
    return decision


@transaction.atomic
def validate_student_decision_finance(*, decision, actor):
    if not can_user_validate_finance(actor):
        raise ValidationError("Vous ne pouvez pas valider le volet financier.")
    decision_pk = decision.pk if isinstance(decision, StudentYearDecision) else decision
    decision = StudentYearDecision.objects.select_related(
        "student",
        "student__user",
        "source_enrollment",
        "source_enrollment__inscription",
        "target_class",
        "target_academic_year",
    ).select_for_update(of=("self",)).get(pk=decision_pk)
    if decision.workflow_status != StudentYearDecision.WORKFLOW_ACADEMIC_VALIDATED:
        raise ValidationError("La decision doit d'abord etre validee par la direction des etudes.")
    _validate_decision_ready(decision)
    balance = decision.source_enrollment.inscription.balance
    if balance > 0 and decision.decision in FINANCE_CLEARANCE_REQUIRED_DECISIONS:
        raise ValidationError(f"Solde restant sur l'ancienne inscription: {balance} FCFA.")
    decision.workflow_status = StudentYearDecision.WORKFLOW_FINANCE_VALIDATED
    decision.finance_validated_by = actor
    decision.finance_validated_at = timezone.now()
    decision.save(update_fields=["workflow_status", "finance_validated_by", "finance_validated_at", "updated_at"])
    _audit_decision(
        decision=decision,
        actor=actor,
        action_type=SupportAuditLog.ACTION_REENROLLMENT_VALIDATED,
        details="Visa financier enregistre.",
    )
    return decision


@transaction.atomic
def reject_student_decision(*, decision, actor, reason=""):
    if not can_user_handle_reenrollment(actor):
        raise ValidationError("Vous ne pouvez pas rejeter cette decision.")
    decision_pk = decision.pk if isinstance(decision, StudentYearDecision) else decision
    decision = StudentYearDecision.objects.select_related(
        "student",
        "student__user",
        "source_enrollment",
    ).select_for_update(of=("self",)).get(pk=decision_pk)
    if decision.workflow_status == StudentYearDecision.WORKFLOW_APPLIED:
        raise ValidationError("Une decision appliquee ne peut pas etre rejetee.")
    decision.workflow_status = StudentYearDecision.WORKFLOW_REJECTED
    decision.rejected_by = actor
    decision.rejected_at = timezone.now()
    decision.rejection_reason = reason.strip()
    decision.save(update_fields=["workflow_status", "rejected_by", "rejected_at", "rejection_reason", "updated_at"])
    _audit_decision(
        decision=decision,
        actor=actor,
        action_type=SupportAuditLog.ACTION_REENROLLMENT_REJECTED,
        details=decision.rejection_reason or "Decision rejetee.",
    )
    return decision


def _target_entry_year(target_class):
    digits = "".join(ch for ch in str(target_class.level or "") if ch.isdigit())
    return int(digits) if digits else 1


def _finalize_source_enrollment(*, decision, actor):
    source_enrollment = decision.source_enrollment
    status_by_decision = {
        StudentYearDecision.DECISION_TRANSFERRED: AcademicEnrollment.STATUS_TRANSFERRED,
        StudentYearDecision.DECISION_SUSPENDED: AcademicEnrollment.STATUS_SUSPENDED,
        StudentYearDecision.DECISION_ABANDONED: AcademicEnrollment.STATUS_ABANDONED,
        StudentYearDecision.DECISION_COMPLETED: AcademicEnrollment.STATUS_COMPLETED,
    }
    inscription_status_by_decision = {
        StudentYearDecision.DECISION_TRANSFERRED: Inscription.STATUS_COMPLETED,
        StudentYearDecision.DECISION_SUSPENDED: Inscription.STATUS_SUSPENDED,
        StudentYearDecision.DECISION_ABANDONED: Inscription.STATUS_CANCELLED,
        StudentYearDecision.DECISION_COMPLETED: Inscription.STATUS_COMPLETED,
    }
    if decision.decision not in status_by_decision:
        raise ValidationError("Cette decision administrative n'est pas prise en charge.")

    source_enrollment.status = status_by_decision[decision.decision]
    source_enrollment.is_active = False
    source_enrollment.is_archived = True
    source_enrollment.archived_at = timezone.now()
    source_enrollment.save(update_fields=["status", "is_active", "is_archived", "archived_at"])

    inscription = source_enrollment.inscription
    inscription.status = inscription_status_by_decision[decision.decision]
    inscription.is_archived = True
    inscription.archived_at = timezone.now()
    inscription.save(update_fields=["status", "is_archived", "archived_at", "updated_at"])

    decision.student.current_academic_enrollment = None
    if decision.decision in {
        StudentYearDecision.DECISION_TRANSFERRED,
        StudentYearDecision.DECISION_SUSPENDED,
        StudentYearDecision.DECISION_ABANDONED,
    }:
        decision.student.is_active = False
        decision.student.save(update_fields=["current_academic_enrollment", "is_active"])
    else:
        decision.student.save(update_fields=["current_academic_enrollment"])

    decision.workflow_status = StudentYearDecision.WORKFLOW_APPLIED
    decision.applied_by = actor
    decision.applied_at = timezone.now()
    decision.save(update_fields=["workflow_status", "applied_by", "applied_at", "updated_at"])
    _audit_decision(
        decision=decision,
        actor=actor,
        action_type=SupportAuditLog.ACTION_REENROLLMENT_APPLIED,
        details=f"Decision administrative appliquee: {decision.get_decision_display()}.",
    )
    return decision


@transaction.atomic
def apply_student_decision(*, decision, actor):
    if not can_user_apply_reenrollment(actor):
        raise ValidationError("Vous ne pouvez pas appliquer cette transition.")
    decision_pk = decision.pk if isinstance(decision, StudentYearDecision) else decision
    decision = StudentYearDecision.objects.select_for_update(of=("self",)).select_related(
        "student",
        "student__user",
        "source_enrollment",
        "source_enrollment__inscription",
        "source_enrollment__inscription__candidature",
        "target_class",
        "target_academic_year",
    ).get(pk=decision_pk)

    if decision.workflow_status == StudentYearDecision.WORKFLOW_APPLIED:
        return decision
    if decision.workflow_status != StudentYearDecision.WORKFLOW_FINANCE_VALIDATED:
        raise ValidationError("La decision doit d'abord etre validee par la direction et la finance.")
    _validate_decision_ready(decision)

    source_enrollment = decision.source_enrollment
    if source_enrollment.status != AcademicEnrollment.STATUS_ACTIVE or not source_enrollment.is_active:
        raise ValidationError("L'inscription source n'est plus active.")
    if decision.decision in ADMINISTRATIVE_DECISIONS:
        return _finalize_source_enrollment(decision=decision, actor=actor)
    existing_target = AcademicEnrollment.objects.filter(
        student=decision.student.user,
        programme=source_enrollment.programme,
        academic_year=decision.target_academic_year,
        status=AcademicEnrollment.STATUS_ACTIVE,
        is_active=True,
        is_archived=False,
    ).exclude(pk=decision.target_enrollment_id).first()
    if existing_target:
        raise ValidationError("Cet etudiant a deja une inscription academique active pour cette annee cible.")

    source_candidature = source_enrollment.inscription.candidature
    entry_year = _target_entry_year(decision.target_class)
    amount_due = get_positioning_fee_for_level(source_enrollment.programme, decision.target_class.level)
    if amount_due <= 0:
        amount_due = source_enrollment.inscription.amount_due

    candidature, _created = Candidature.objects.get_or_create(
        email=source_candidature.email,
        programme=source_enrollment.programme,
        academic_year=decision.target_academic_year.name,
        defaults={
            "branch": source_enrollment.branch,
            "entry_year": entry_year,
            "first_name": source_candidature.first_name,
            "last_name": source_candidature.last_name,
            "birth_date": source_candidature.birth_date,
            "birth_place": source_candidature.birth_place,
            "gender": source_candidature.gender,
            "phone": source_candidature.phone,
            "address": source_candidature.address,
            "city": source_candidature.city,
            "country": source_candidature.country,
            "status": "accepted",
            "reviewed_by": actor,
            "reviewed_at": timezone.now(),
            "admin_comment": f"Reinscription interne depuis {source_enrollment.academic_year}.",
        },
    )
    if candidature.status not in {"accepted", "accepted_with_reserve"}:
        candidature.status = "accepted"
        candidature.reviewed_by = actor
        candidature.reviewed_at = timezone.now()
        candidature.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
    if candidature.branch_id != source_enrollment.branch_id:
        raise ValidationError("La candidature cible existe deja dans une autre annexe.")

    inscription, _created = Inscription.objects.get_or_create(
        candidature=candidature,
        defaults={
            "academic_class": decision.target_class,
            "academic_level": decision.target_class.level,
            "amount_due": amount_due,
            "status": Inscription.STATUS_ACTIVE,
        },
    )
    if inscription.academic_class_id != decision.target_class_id:
        inscription.academic_class = decision.target_class
        inscription.academic_level = decision.target_class.level
        inscription.status = Inscription.STATUS_ACTIVE
        inscription.amount_due = amount_due
        inscription.save(update_fields=["academic_class", "academic_level", "status", "amount_due", "updated_at"])
    elif inscription.status != Inscription.STATUS_ACTIVE:
        inscription.status = Inscription.STATUS_ACTIVE
        inscription.save(update_fields=["status", "updated_at"])

    archive_enrollment_for_transition(enrollment=source_enrollment)
    target_enrollment, _created = AcademicEnrollment.objects.get_or_create(
        inscription=inscription,
        defaults={
            "student": decision.student.user,
            "programme": source_enrollment.programme,
            "branch": source_enrollment.branch,
            "academic_year": decision.target_academic_year,
            "academic_class": decision.target_class,
            "status": AcademicEnrollment.STATUS_ACTIVE,
        },
    )
    if target_enrollment.student_id != decision.student.user_id:
        raise ValidationError("L'inscription academique cible appartient a un autre etudiant.")
    if (
        target_enrollment.programme_id != source_enrollment.programme_id
        or target_enrollment.branch_id != source_enrollment.branch_id
        or target_enrollment.academic_year_id != decision.target_academic_year_id
        or target_enrollment.academic_class_id != decision.target_class_id
    ):
        raise ValidationError("L'inscription academique cible existante ne correspond pas a la decision.")
    if target_enrollment.status != AcademicEnrollment.STATUS_ACTIVE or not target_enrollment.is_active or target_enrollment.is_archived:
        target_enrollment.status = AcademicEnrollment.STATUS_ACTIVE
        target_enrollment.is_active = True
        target_enrollment.is_archived = False
        target_enrollment.archived_at = None
        target_enrollment.save(update_fields=["status", "is_active", "is_archived", "archived_at"])

    _carry_forward_debts(source_enrollment, target_enrollment)

    decision.student.current_academic_enrollment = target_enrollment
    decision.student.save(update_fields=["current_academic_enrollment"])
    decision.target_inscription = inscription
    decision.target_enrollment = target_enrollment
    decision.workflow_status = StudentYearDecision.WORKFLOW_APPLIED
    decision.applied_by = actor
    decision.applied_at = timezone.now()
    decision.save(update_fields=[
        "target_inscription",
        "target_enrollment",
        "workflow_status",
        "applied_by",
        "applied_at",
        "updated_at",
    ])
    _audit_decision(
        decision=decision,
        actor=actor,
        action_type=SupportAuditLog.ACTION_REENROLLMENT_APPLIED,
        details=f"Transition appliquee vers {decision.target_class} ({decision.target_academic_year}).",
    )
    return decision
