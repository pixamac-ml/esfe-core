"""Jury workflow layered on top of the existing annual deliberation proposals."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from academic_cycle.models import ClassDeliberationSession, StudentYearDecision


JURY_REASONS = {"confirmation", "repechage", "jury", "particular", "other"}
ORDINARY_DECISIONS = {"promoted", "graduated"}


def get_session(academic_class):
    """Return the sole class-scoped session record (safe on repeated loads)."""
    session, _ = ClassDeliberationSession.objects.get_or_create(
        academic_class=academic_class,
        defaults={
            "branch": academic_class.branch,
            "academic_year": academic_class.academic_year,
            "normal_threshold": academic_class.validation_threshold,
        },
    )
    return session


def _class_decisions(academic_class):
    return StudentYearDecision.objects.filter(
        current_class=academic_class,
        academic_year=academic_class.academic_year,
    )


def requires_jury_review(decision):
    """Whether the annual proposal really needs an explicit human decision."""
    snapshot = decision.synthesis_snapshot or {}
    semesters = snapshot.get("semesters", [])
    return bool(
        snapshot.get("requires_academic_debt")
        or snapshot.get("debt_subjects")
        or snapshot.get("academic_decision") == "NON_ADMIS"
        or any(not semester.get("is_validated") for semester in semesters)
    )


def _blocking_anomalies(decision):
    return [
        reason
        for semester in (decision.synthesis_snapshot or {}).get("semesters", [])
        for reason in semester.get("blocking_reasons", [])
    ]


def session_metrics(academic_class):
    decisions = _class_decisions(academic_class)
    total = decisions.count()
    processed = decisions.filter(jury_processed=True).count()
    return {
        "total": total,
        "processed": processed,
        "remaining": total - processed,
        "review": decisions.filter(jury_processed=False).exclude(
            decision__in=ORDINARY_DECISIONS
        ).count(),
        "ordinary": decisions.filter(
            jury_processed=True, jury_decision__in=ORDINARY_DECISIONS
        ).count(),
        "debts": decisions.filter(
            jury_processed=True, jury_decision="promoted_with_academic_debt"
        ).count(),
        "repeated": decisions.filter(
            jury_processed=True, jury_decision="repeated"
        ).count(),
        "rescued": decisions.filter(
            jury_processed=True, jury_reason="repechage"
        ).count(),
        "exceptional": decisions.filter(jury_processed=True).exclude(
            jury_decision=F("decision")
        ).count(),
    }


@transaction.atomic
def open_session(*, academic_class, actor):
    session = ClassDeliberationSession.objects.select_for_update().get(
        pk=get_session(academic_class).pk
    )
    if session.status == session.STATUS_PREPARATION:
        session.status = session.STATUS_IN_SESSION
        session.opened_by = actor
        session.opened_at = timezone.now()
        session.save(update_fields=["status", "opened_by", "opened_at", "updated_at"])
    return session


def _mark_ready_when_complete(*, academic_class, session):
    if not _class_decisions(academic_class).filter(jury_processed=False).exists():
        session.status = session.STATUS_READY
        session.prepared_at = timezone.now()
        session.save(update_fields=["status", "prepared_at", "updated_at"])


@transaction.atomic
def save_jury_decision(*, decision, actor, jury_decision, reason="", justification=""):
    if decision.is_final:
        raise ValidationError("Une décision annuelle officielle est immuable.")
    session = ClassDeliberationSession.objects.select_for_update().get(
        pk=get_session(decision.current_class).pk
    )
    if session.status != session.STATUS_IN_SESSION:
        raise ValidationError("Ouvrez la séance de délibération avant de décider.")
    allowed_decisions = dict(StudentYearDecision._meta.get_field("jury_decision").choices)
    if jury_decision not in allowed_decisions or jury_decision == "pending":
        raise ValidationError("Décision de jury non autorisée.")
    if reason and reason not in JURY_REASONS:
        raise ValidationError("Motif de jury non autorisé.")
    if jury_decision != decision.decision and not (justification or "").strip():
        raise ValidationError("Une justification est obligatoire pour une dérogation à la proposition système.")
    decision.jury_decision = jury_decision
    decision.jury_reason = (reason or "").strip()
    decision.jury_justification = (justification or "").strip()
    decision.jury_processed = True
    decision.jury_decided_by = actor
    decision.jury_decided_at = timezone.now()
    decision.save()
    _mark_ready_when_complete(academic_class=decision.current_class, session=session)
    return decision


@transaction.atomic
def confirm_proposals(*, academic_class, actor, decision_ids):
    session = ClassDeliberationSession.objects.select_for_update().get(
        pk=get_session(academic_class).pk
    )
    if session.status != session.STATUS_IN_SESSION:
        raise ValidationError("La séance doit être ouverte.")
    decisions = StudentYearDecision.objects.select_for_update().filter(
        pk__in=decision_ids,
        current_class=academic_class,
        academic_year=academic_class.academic_year,
        is_final=False,
        jury_processed=False,
        decision__in=ORDINARY_DECISIONS,
    )
    now = timezone.now()
    confirmed = 0
    for decision in decisions:
        decision.jury_decision = decision.decision
        decision.jury_reason = "confirmation"
        decision.jury_processed = True
        decision.jury_decided_by = actor
        decision.jury_decided_at = now
        decision.save()
        confirmed += 1
    _mark_ready_when_complete(academic_class=academic_class, session=session)
    return confirmed


def simulate_threshold(*, academic_class, threshold):
    session = get_session(academic_class)
    threshold = Decimal(str(threshold))
    normal_threshold = session.normal_threshold or academic_class.validation_threshold
    admissibility_gap = academic_class.admissibility_gap or Decimal("0")
    if normal_threshold is None:
        raise ValidationError("Le seuil normal de la classe doit être configuré.")
    if threshold > normal_threshold:
        raise ValidationError("Le seuil de séance ne peut pas dépasser le seuil normal configuré.")
    if threshold < normal_threshold - admissibility_gap:
        raise ValidationError("Le seuil proposé dépasse la marge d'admissibilité configurée.")
    impacted, maintained_repeats = [], 0
    for decision in _class_decisions(academic_class).select_related("student__user"):
        semesters = (decision.synthesis_snapshot or {}).get("semesters", [])
        averages = [Decimal(str(item.get("average") or 0)) for item in semesters]
        if decision.decision != "repeated":
            continue
        if averages and max(averages) >= threshold:
            impacted.append(decision)
        else:
            maintained_repeats += 1
    analysed = _class_decisions(academic_class).count()
    return {"threshold": threshold, "analysed": analysed, "impacted": impacted, "unchanged": analysed - len(impacted), "maintained_repeats": maintained_repeats}


@transaction.atomic
def apply_session_threshold(*, academic_class, actor, threshold, reason):
    """Persist an exceptional eligibility rule; no grade is ever changed."""
    simulation = simulate_threshold(academic_class=academic_class, threshold=threshold)
    if not (reason or "").strip():
        raise ValidationError("Le motif de la règle de séance est obligatoire.")
    session = ClassDeliberationSession.objects.select_for_update().get(
        pk=get_session(academic_class).pk
    )
    if session.status != session.STATUS_IN_SESSION:
        raise ValidationError("Ouvrez la séance avant d'appliquer une règle exceptionnelle.")
    session.session_threshold = simulation["threshold"]
    session.session_rule_reason = reason.strip()
    session.save(update_fields=["session_threshold", "session_rule_reason", "updated_at"])
    return simulation


def _closed_snapshot(*, academic_class, session, decisions):
    rows = []
    for decision in decisions:
        student = decision.student
        user = getattr(student, "user", None)
        snapshot = decision.synthesis_snapshot or {}
        rows.append(
            {
                "decision_id": decision.id,
                "student_id": student.id,
                "matricule": student.matricule,
                "last_name": getattr(user, "last_name", "") or "",
                "first_name": getattr(user, "first_name", "") or "",
                "student_name": student.full_name,
                "semesters": snapshot.get("semesters", []),
                "automatic_decision": decision.decision,
                "automatic_label": decision.get_decision_display(),
                "jury_decision": decision.jury_decision,
                "jury_label": decision.get_jury_decision_display(),
                "cycle_decision": decision.get_jury_decision_display(),
                "jury_reason": decision.jury_reason,
                "jury_justification": decision.jury_justification,
                "requires_review": requires_jury_review(decision),
                "debt_count": len(snapshot.get("debt_subjects", [])),
            }
        )
    decisions_by_code = {}
    for row in rows:
        decisions_by_code[row["jury_decision"]] = decisions_by_code.get(row["jury_decision"], 0) + 1
    return {
        "version": 1,
        "closed_at": timezone.now().isoformat(),
        "branch_id": academic_class.branch_id,
        "branch_name": academic_class.branch.name,
        "academic_year_id": academic_class.academic_year_id,
        "academic_year_name": academic_class.academic_year.name,
        "class_id": academic_class.id,
        "class_name": academic_class.display_name,
        "normal_threshold": str(session.normal_threshold or academic_class.validation_threshold or ""),
        "session_threshold": str(session.session_threshold or ""),
        "session_rule_reason": session.session_rule_reason,
        "total_students": len(rows),
        "ordinary_count": sum(not row["requires_review"] for row in rows),
        "review_count": sum(row["requires_review"] for row in rows),
        "review_processed": sum(row["requires_review"] for row in rows),
        "decisions": decisions_by_code,
        "repechage_count": sum(row["jury_reason"] == "repechage" for row in rows),
        "rows": rows,
    }


@transaction.atomic
def close_session(*, academic_class, actor):
    """Freeze a completed DE/jury session while leaving annual decisions unofficial."""
    session = ClassDeliberationSession.objects.select_for_update().get(
        pk=get_session(academic_class).pk
    )
    if session.status == session.STATUS_CLOSED:
        return {"session": session, "snapshot": session.transmission_snapshot, "idempotent": True}
    if session.status in {session.STATUS_TRANSMITTED, session.STATUS_OFFICIAL}:
        raise ValidationError("Cette délibération est déjà verrouillée pour le circuit institutionnel.")
    if session.status not in {session.STATUS_IN_SESSION, session.STATUS_READY}:
        raise ValidationError("Ouvrez la séance avant de la clôturer.")
    decisions = list(
        _class_decisions(academic_class)
        .select_for_update()
        .select_related("student__user")
        .order_by("student__matricule", "id")
    )
    if not decisions:
        raise ValidationError("Aucun étudiant actif ne peut être clôturé pour cette classe.")
    blockers = [
        decision for decision in decisions
        if requires_jury_review(decision) and not decision.jury_processed
    ]
    if blockers:
        raise ValidationError(f"{len(blockers)} dossier(s) à examiner doivent recevoir une décision du jury.")
    anomalies = [reason for decision in decisions for reason in _blocking_anomalies(decision)]
    if anomalies:
        raise ValidationError("La clôture est bloquée par une anomalie académique : " + anomalies[0])
    now = timezone.now()
    for decision in decisions:
        if not decision.jury_processed:
            decision.jury_decision = decision.decision
            decision.jury_reason = "collective_closure"
            decision.jury_processed = True
            decision.jury_decided_by = actor
            decision.jury_decided_at = now
            decision.save()
    snapshot = _closed_snapshot(academic_class=academic_class, session=session, decisions=decisions)
    session.status = session.STATUS_CLOSED
    session.closed_by = actor
    session.closed_at = now
    session.prepared_at = session.prepared_at or now
    session.transmission_snapshot = snapshot
    session.save(update_fields=["status", "closed_by", "closed_at", "prepared_at", "transmission_snapshot", "updated_at"])
    return {"session": session, "snapshot": snapshot, "idempotent": False}


@transaction.atomic
def submit_closed_session(*, academic_class):
    session = ClassDeliberationSession.objects.select_for_update().get(
        pk=get_session(academic_class).pk
    )
    if session.status == session.STATUS_TRANSMITTED:
        return session
    if session.status != session.STATUS_CLOSED or not session.transmission_snapshot:
        raise ValidationError("La délibération doit être clôturée et figée avant soumission au DG.")
    session.status = session.STATUS_TRANSMITTED
    session.transmitted_at = timezone.now()
    session.save(update_fields=["status", "transmitted_at", "updated_at"])
    return session
