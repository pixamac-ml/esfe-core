from django.db.models import Count, Q, Sum

from academics.models import AcademicClass, AcademicEnrollment
from students.models import Student

from . import constants
from .models import (
    AcademicReEnrollment,
    BranchAcademicCycle,
    ClassCycleStatus,
    StudentAcademicDebt,
    StudentFinancialPosition,
)
from .permissions import has_branch_scope, is_global_cycle_user, user_branch


def scope_branch_queryset(queryset, user, branch_field="branch"):
    if is_global_cycle_user(user):
        return queryset
    branch = user_branch(user)
    if not branch:
        return queryset.none()
    return queryset.filter(**{branch_field: branch})


def get_branch_cycle(branch, academic_year):
    return BranchAcademicCycle.objects.select_related("branch", "academic_year").get(
        branch=branch,
        academic_year=academic_year,
    )


def get_active_branch_cycles(user=None):
    qs = BranchAcademicCycle.objects.select_related("branch", "academic_year").filter(
        status__in=[
            constants.BRANCH_CYCLE_PREPARATION,
            constants.BRANCH_CYCLE_REGISTRATION_OPEN,
            constants.BRANCH_CYCLE_ACTIVE,
            constants.BRANCH_CYCLE_EXAMS,
            constants.BRANCH_CYCLE_DELIBERATION,
            constants.BRANCH_CYCLE_CLOSING,
        ]
    )
    return scope_branch_queryset(qs, user) if user else qs


def get_students_for_branch_year(branch, academic_year):
    enrollments = AcademicEnrollment.objects.filter(
        branch=branch,
        academic_year=academic_year,
        is_active=True,
    ).values("student_id")
    return Student.objects.select_related("user", "inscription").filter(user_id__in=enrollments)


def get_students_pending_reenrollment(branch, target_year):
    return AcademicReEnrollment.objects.select_related("student", "target_class").filter(
        branch=branch,
        target_academic_year=target_year,
        status__in=[
            AcademicReEnrollment.STATUS_PREPARED,
            AcademicReEnrollment.STATUS_NOTIFIED,
            AcademicReEnrollment.STATUS_STARTED,
            AcademicReEnrollment.STATUS_PENDING_PAYMENT,
        ],
    )


def get_students_with_financial_debt(branch, academic_year):
    return StudentFinancialPosition.objects.select_related("student").filter(
        branch=branch,
        academic_year=academic_year,
        remaining_amount__gt=0,
    )


def get_students_with_academic_debt(branch, academic_year):
    return StudentAcademicDebt.objects.select_related("student", "source_class", "current_class").filter(
        branch=branch,
        current_academic_year=academic_year,
    ).exclude(status__in=[constants.DEBT_RESOLVED, constants.DEBT_CANCELLED])


def get_branch_classes(branch, academic_year):
    return AcademicClass.objects.select_related("programme", "branch", "academic_year").filter(
        branch=branch,
        academic_year=academic_year,
        is_active=True,
        is_archived=False,
    )


def get_ready_classes(branch_cycle):
    return ClassCycleStatus.objects.select_related("academic_class").filter(
        branch_cycle=branch_cycle,
        status__in=[constants.CLASS_READY_FOR_DELIBERATION, constants.CLASS_DELIBERATED, constants.CLASS_CLOSED],
        has_blocking_anomaly=False,
    )


def get_blocked_classes(branch_cycle):
    return ClassCycleStatus.objects.select_related("academic_class").filter(
        Q(branch_cycle=branch_cycle),
        Q(has_blocking_anomaly=True) | Q(status__in=[constants.CLASS_TEACHING, constants.CLASS_SEMESTER_1_COMPLETED]),
    )


def get_dg_cycle_overview(user=None):
    qs = BranchAcademicCycle.objects.select_related("branch", "academic_year")
    if user:
        qs = scope_branch_queryset(qs, user)
    return (
        qs.values("academic_year__name", "status")
        .annotate(total=Count("id"))
        .order_by("academic_year__name", "status")
    )


def get_branch_financial_summary(branch, academic_year):
    return StudentFinancialPosition.objects.filter(branch=branch, academic_year=academic_year).aggregate(
        total_due=Sum("total_due_amount"),
        total_paid=Sum("total_paid_amount"),
        remaining=Sum("remaining_amount"),
    )


def ensure_user_can_see_branch(user, branch):
    return has_branch_scope(user, branch)
