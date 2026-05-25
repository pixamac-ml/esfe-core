from django.db.models import Sum
from django.utils import timezone

from payments.models import Payment
from academic_cycle import constants
from academic_cycle.models import StudentFinancialPosition


def determine_financial_status(position):
    if position.remaining_amount <= 0:
        return constants.FINANCIAL_CLEAR
    if position.remaining_amount <= 50000:
        return constants.FINANCIAL_LIGHT_DEBT
    if position.remaining_amount <= 150000:
        return constants.FINANCIAL_MEDIUM_DEBT
    if position.remaining_amount <= 300000:
        return constants.FINANCIAL_CRITICAL_DEBT
    return constants.FINANCIAL_BLOCKED_DOCUMENTS


def compute_student_financial_position(student, academic_year):
    enrollment = student.user.academic_enrollments.filter(academic_year=academic_year).select_related("branch").first()
    branch = enrollment.branch if enrollment else student.inscription.candidature.branch
    due = getattr(student.inscription, "amount_due", 0) or 0
    paid = (
        Payment.objects.filter(inscription=student.inscription, status=Payment.STATUS_VALIDATED).aggregate(total=Sum("amount"))["total"]
        or 0
    )
    previous = (
        StudentFinancialPosition.objects.filter(student=student)
        .exclude(academic_year=academic_year)
        .order_by("-academic_year__start_date")
        .values_list("remaining_amount", flat=True)
        .first()
        or 0
    )
    total_due = due + previous
    remaining = max(total_due - paid, 0)
    position, _ = StudentFinancialPosition.objects.update_or_create(
        student=student,
        academic_year=academic_year,
        defaults={
            "branch": branch,
            "previous_debt_amount": previous,
            "current_year_due_amount": due,
            "current_year_paid_amount": paid,
            "total_due_amount": total_due,
            "total_paid_amount": paid,
            "remaining_amount": remaining,
            "last_computed_at": timezone.now(),
        },
    )
    position.status = determine_financial_status(position)
    position.save(update_fields=["status", "updated_at"])
    return position


def carry_forward_debt(student, source_year, target_year):
    source = compute_student_financial_position(student, source_year)
    target = compute_student_financial_position(student, target_year)
    target.previous_debt_amount = source.remaining_amount
    target.total_due_amount = target.current_year_due_amount + source.remaining_amount
    target.remaining_amount = max(target.total_due_amount - target.current_year_paid_amount, 0)
    target.status = determine_financial_status(target)
    target.last_computed_at = timezone.now()
    target.save()
    return target
