from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from academics.models import ECGrade
from academic_cycle import constants
from academic_cycle.models import StudentAcademicDebt
from academic_cycle.services.audit_service import log_action


def detect_academic_debts(student, source_year):
    enrollment = student.user.academic_enrollments.filter(academic_year=source_year, is_active=True).select_related(
        "academic_class", "branch"
    ).first()
    if not enrollment:
        return []

    threshold = enrollment.academic_class.validation_threshold or Decimal("10.00")
    debts = []
    grades = ECGrade.objects.select_related("ec__ue__semester").filter(enrollment=enrollment)
    for grade in grades:
        score = grade.final_score if grade.final_score is not None else grade.note
        if score is None or score < threshold or not grade.is_validated:
            required = grade.ec.credit_required or Decimal("0.00")
            earned = grade.credit_obtained or Decimal("0.00")
            debts.append(
                {
                    "student": student,
                    "source_academic_year": source_year,
                    "source_class": enrollment.academic_class,
                    "branch": enrollment.branch,
                    "debt_type": constants.DEBT_EC,
                    "semester_label": f"S{grade.ec.ue.semester.number}",
                    "ue": grade.ec.ue,
                    "ec": grade.ec,
                    "required_credits": required,
                    "earned_credits": earned,
                    "missing_credits": max(required - earned, Decimal("0.00")),
                    "validation_threshold": threshold,
                }
            )
    return debts


@transaction.atomic
def create_academic_debts_for_student(student, decision):
    created = []
    for payload in detect_academic_debts(student, decision.academic_year):
        debt, was_created = StudentAcademicDebt.objects.get_or_create(
            student=student,
            source_academic_year=payload["source_academic_year"],
            source_class=payload["source_class"],
            ec=payload["ec"],
            defaults=payload,
        )
        if was_created:
            created.append(debt)
    return created


def resolve_academic_debt(debt, evaluation, actor):
    old_values = {"status": debt.status, "missing_credits": str(debt.missing_credits)}
    debt.status = constants.DEBT_RESOLVED
    debt.resolved_at = timezone.now()
    debt.resolution_note = evaluation.notes or "Dette academique resolue par evaluation speciale."
    debt.earned_credits = debt.required_credits
    debt.missing_credits = Decimal("0.00")
    debt.save(update_fields=["status", "resolved_at", "resolution_note", "earned_credits", "missing_credits", "updated_at"])
    log_action(
        actor,
        "student_academic_debt.resolved",
        debt,
        old_values=old_values,
        new_values={"status": debt.status, "missing_credits": str(debt.missing_credits)},
        branch=debt.branch,
        academic_year=debt.current_academic_year or debt.source_academic_year,
        student=debt.student,
    )
    return debt


def recompute_student_credits(student):
    grades = ECGrade.objects.filter(enrollment__student=student.user)
    required = sum((grade.ec.credit_required or Decimal("0.00")) for grade in grades.select_related("ec"))
    earned = sum((grade.credit_obtained or Decimal("0.00")) for grade in grades)
    return {"required_credits": required, "earned_credits": earned, "missing_credits": max(required - earned, Decimal("0.00"))}
