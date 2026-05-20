from datetime import timedelta

from django.db.models import Count, Q, Sum
from django.utils import timezone

from academics.models import AcademicClass, AcademicEnrollment
from accounts.models import BranchExpense, Profile
from admissions.models import Candidature
from branches.models import Branch
from inscriptions.models import Inscription
from payments.models import Payment
from students.models import AttendanceAlert, Student, StudentCase, StudentYearDecision


def get_active_branches():
    return (
        Branch.objects.filter(is_active=True)
        .select_related("manager")
        .order_by("name")
    )


def get_dg_base_querysets(branch_ids):
    branch_filter = {"id__in": branch_ids}
    return {
        "students": Student.objects.filter(
            is_active=True,
            inscription__candidature__branch_id__in=branch_ids,
        ),
        "classes": AcademicClass.objects.filter(
            is_active=True,
            is_archived=False,
            branch_id__in=branch_ids,
        ),
        "enrollments": AcademicEnrollment.objects.filter(
            is_active=True,
            branch_id__in=branch_ids,
        ),
        "inscriptions": Inscription.objects.filter(
            status__in={"partial_paid", "active"},
            candidature__branch_id__in=branch_ids,
        ),
        "candidatures": Candidature.objects.filter(
            is_deleted=False,
            branch_id__in=branch_ids,
        ),
        "payments": Payment.objects.filter(
            status=Payment.STATUS_VALIDATED,
            inscription__candidature__branch_id__in=branch_ids,
        ),
        "pending_payments": Payment.objects.filter(
            status=Payment.STATUS_PENDING,
            inscription__candidature__branch_id__in=branch_ids,
        ),
        "expenses": BranchExpense.objects.filter(branch_id__in=branch_ids),
        "attendance_alerts": AttendanceAlert.objects.filter(
            is_resolved=False,
            branch_id__in=branch_ids,
        ),
        "student_cases": StudentCase.objects.filter(branch_id__in=branch_ids),
        "year_decisions": StudentYearDecision.objects.filter(
            source_enrollment__branch_id__in=branch_ids,
        ),
        "staff": Profile.objects.filter(
            user_type="staff",
            employment_status="active",
        ).filter(Q(branch_id__in=branch_ids) | Q(branch__isnull=True)),
        "branch_filter": branch_filter,
    }


def get_recent_candidatures_count(branch_ids, days=30):
    return Candidature.objects.filter(
        submitted_at__gte=timezone.now() - timedelta(days=days),
        branch_id__in=branch_ids,
        is_deleted=False,
    ).count()


def get_branch_finance(branch):
    revenue = (
        Payment.objects.filter(
            status=Payment.STATUS_VALIDATED,
            inscription__candidature__branch=branch,
        ).aggregate(total=Sum("amount"))["total"]
        or 0
    )
    expenses = (
        BranchExpense.objects.filter(
            branch=branch,
            status__in={
                BranchExpense.STATUS_SUBMITTED,
                BranchExpense.STATUS_APPROVED,
                BranchExpense.STATUS_PAID,
            },
        ).aggregate(total=Sum("amount"))["total"]
        or 0
    )
    return revenue, expenses, revenue - expenses


def get_top_classes_for_branch(branch, limit=5):
    return list(
        AcademicClass.objects.filter(branch=branch, is_active=True, is_archived=False)
        .annotate(student_count=Count("enrollments", filter=Q(enrollments__is_active=True)))
        .order_by("-student_count", "level", "programme__title")[:limit]
    )


def get_top_programmes_for_branch(branch, limit=3):
    return list(
        Candidature.objects.filter(branch=branch, is_deleted=False)
        .values("programme__title")
        .annotate(total=Count("id"))
        .order_by("-total", "programme__title")[:limit]
    )


def get_latest_payments_for_branch(branch, limit=5):
    return list(
        Payment.objects.filter(
            status=Payment.STATUS_VALIDATED,
            inscription__candidature__branch=branch,
        )
        .select_related("inscription__candidature")
        .order_by("-paid_at")[:limit]
    )
