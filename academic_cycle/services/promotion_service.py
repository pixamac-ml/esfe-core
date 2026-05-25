from django.db import transaction
from django.utils import timezone

from academic_cycle import constants
from academic_cycle.models import StudentYearDecision
from academic_cycle.services.academic_debt_service import detect_academic_debts
from academic_cycle.services.audit_service import log_action


def compute_student_year_decision(student, source_year, actor=None, target_year=None, target_class=None):
    enrollment = student.user.academic_enrollments.filter(academic_year=source_year, is_active=True).select_related(
        "academic_class", "branch"
    ).first()
    if not enrollment:
        raise ValueError("Aucune inscription academique active trouvee pour cette annee.")

    debts = detect_academic_debts(student, source_year)
    decision_value = constants.DECISION_PROMOTED_WITH_ACADEMIC_DEBT if debts else constants.DECISION_PROMOTED
    return StudentYearDecision.objects.update_or_create(
        student=student,
        academic_year=source_year,
        defaults={
            "branch": enrollment.branch,
            "current_class": enrollment.academic_class,
            "target_year": target_year,
            "target_class": target_class,
            "decision": decision_value,
            "reason": "Decision automatique V1 basee sur les dettes academiques detectees.",
            "decided_by": actor if getattr(actor, "is_authenticated", False) else None,
            "decided_at": timezone.now(),
            "is_final": False,
        },
    )[0]


def _set_decision(student, decision, target_class=None, actor=None, reason=""):
    enrollment = student.current_academic_enrollment or student.user.academic_enrollments.filter(is_active=True).first()
    if not enrollment:
        raise ValueError("Aucune inscription academique active trouvee.")
    obj, _ = StudentYearDecision.objects.update_or_create(
        student=student,
        academic_year=enrollment.academic_year,
        defaults={
            "branch": enrollment.branch,
            "current_class": enrollment.academic_class,
            "target_year": target_class.academic_year if target_class else None,
            "target_class": target_class,
            "decision": decision,
            "reason": reason,
            "decided_by": actor if getattr(actor, "is_authenticated", False) else None,
            "decided_at": timezone.now(),
            "is_final": True,
        },
    )
    log_action(actor, "student_year_decision.set", obj, new_values={"decision": decision}, branch=obj.branch, academic_year=obj.academic_year, student=student)
    return obj


def promote_student(student, target_class, actor=None):
    return _set_decision(student, constants.DECISION_PROMOTED, target_class=target_class, actor=actor, reason="Promotion validee.")


def repeat_student(student, target_class, actor=None):
    return _set_decision(student, constants.DECISION_REPEATED, target_class=target_class, actor=actor, reason="Redoublement valide.")


def graduate_student(student, actor=None):
    return _set_decision(student, constants.DECISION_GRADUATED, actor=actor, reason="Cycle termine, passage alumni.")


def mark_student_dropped(student, actor=None):
    return _set_decision(student, constants.DECISION_DROPPED, actor=actor, reason="Abandon ou pause signalee.")
