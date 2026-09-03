from datetime import datetime, time, timedelta

from django.db.models import Count, Q, Sum
from django.utils import timezone

from academics.models import AcademicClass, AcademicEnrollment
from accounts.models import BranchExpense, BranchMonthlyClosure, Profile
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


def get_academic_year_datetime_bounds(academic_year):
    """Return timezone-aware inclusive/exclusive bounds for a DG academic year."""
    return (
        timezone.make_aware(datetime.combine(academic_year.start_date, time.min)),
        timezone.make_aware(datetime.combine(academic_year.end_date + timedelta(days=1), time.min)),
    )


def get_dg_base_querysets(branch_ids, *, academic_year=None):
    """Canonical DG querysets constrained by branches and, when selected, year."""
    branch_filter = {"id__in": branch_ids}
    candidature_filters = {}
    class_filters = {}
    enrollment_filters = {}
    payment_filters = {}
    expense_filters = {}
    closure_filters = {}
    alert_filters = {}
    case_filters = {}
    decision_filters = {}
    if academic_year is not None:
        academic_year_start, academic_year_end = get_academic_year_datetime_bounds(academic_year)
        candidature_filters["academic_year"] = academic_year.name
        class_filters["academic_year"] = academic_year
        enrollment_filters["academic_year"] = academic_year
        payment_filters.update(
            {
                "paid_at__gte": academic_year_start,
                "paid_at__lt": academic_year_end,
            }
        )
        expense_filters.update(
            {
                "expense_date__gte": academic_year.start_date,
                "expense_date__lte": academic_year.end_date,
            }
        )
        closure_filters.update(
            {
                "period_month__gte": academic_year.start_date,
                "period_month__lte": academic_year.end_date,
            }
        )
        alert_filters.update(
            {
                "triggered_at__gte": academic_year_start,
                "triggered_at__lt": academic_year_end,
            }
        )
        case_filters.update(
            {
                "created_at__gte": academic_year_start,
                "created_at__lt": academic_year_end,
            }
        )
        decision_filters["source_enrollment__academic_year"] = academic_year
    student_queryset = Student.objects.filter(
        is_active=True,
        user__academic_enrollments__branch_id__in=branch_ids,
    )
    if academic_year is not None:
        student_queryset = student_queryset.filter(
            user__academic_enrollments__academic_year=academic_year,
        )

    return {
        # AcademicEnrollment is the authoritative yearly student state.  The
        # original administrative inscription remains the identity anchor but
        # must not reconstruct a historical academic year.
        "students": student_queryset.distinct(),
        "classes": AcademicClass.objects.filter(
            is_active=True,
            is_archived=False,
            branch_id__in=branch_ids,
            **class_filters,
        ),
        "enrollments": AcademicEnrollment.objects.filter(
            is_active=True,
            branch_id__in=branch_ids,
            **enrollment_filters,
        ),
        "inscriptions": Inscription.objects.filter(
            status__in={"partial_paid", "active"},
            candidature__branch_id__in=branch_ids,
            **{f"candidature__{key}": value for key, value in candidature_filters.items()},
        ),
        "candidatures": Candidature.objects.filter(
            is_deleted=False,
            branch_id__in=branch_ids,
            **candidature_filters,
        ),
        "payments": Payment.objects.filter(
            status=Payment.STATUS_VALIDATED,
            inscription__candidature__branch_id__in=branch_ids,
            **{f"inscription__candidature__{key}": value for key, value in candidature_filters.items()},
            **payment_filters,
        ),
        "pending_payments": Payment.objects.filter(
            status=Payment.STATUS_PENDING,
            inscription__candidature__branch_id__in=branch_ids,
            **{f"inscription__candidature__{key}": value for key, value in candidature_filters.items()},
            **payment_filters,
        ),
        "expenses": BranchExpense.objects.filter(branch_id__in=branch_ids, **expense_filters),
        "attendance_alerts": AttendanceAlert.objects.filter(
            is_resolved=False,
            branch_id__in=branch_ids,
            **alert_filters,
        ),
        "student_cases": StudentCase.objects.filter(branch_id__in=branch_ids, **case_filters),
        "year_decisions": StudentYearDecision.objects.filter(
            source_enrollment__branch_id__in=branch_ids,
            **decision_filters,
        ),
        "staff": Profile.objects.filter(
            user_type="staff",
            employment_status="active",
        ).filter(Q(branch_id__in=branch_ids) | Q(branch__isnull=True)),
        "monthly_closures": BranchMonthlyClosure.objects.filter(
            branch_id__in=branch_ids,
            **closure_filters,
        ).select_related("branch", "validated_by"),
        "branch_filter": branch_filter,
    }


def get_recent_candidatures_count(branch_ids, days=30, *, academic_year=None):
    academic_year_filter = {"academic_year": academic_year.name} if academic_year else {}
    return Candidature.objects.filter(
        submitted_at__gte=timezone.now() - timedelta(days=days),
        branch_id__in=branch_ids,
        is_deleted=False,
        **academic_year_filter,
    ).count()


def get_branch_finance(branch, *, academic_year=None):
    payment_date_filters = {}
    expense_date_filters = {}
    candidature_filters = {}
    if academic_year is not None:
        academic_year_start, academic_year_end = get_academic_year_datetime_bounds(academic_year)
        candidature_filters["inscription__candidature__academic_year"] = academic_year.name
        payment_date_filters = {
            "paid_at__gte": academic_year_start,
            "paid_at__lt": academic_year_end,
        }
        expense_date_filters = {
            "expense_date__gte": academic_year.start_date,
            "expense_date__lte": academic_year.end_date,
        }
    revenue = (
        Payment.objects.filter(
            status=Payment.STATUS_VALIDATED,
            inscription__candidature__branch=branch,
            **candidature_filters,
            **payment_date_filters,
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
            **expense_date_filters,
        ).aggregate(total=Sum("amount"))["total"]
        or 0
    )
    return revenue, expenses, revenue - expenses


def get_top_classes_for_branch(branch, limit=5, *, academic_year=None):
    year_filter = {"academic_year": academic_year} if academic_year else {}
    return list(
        AcademicClass.objects.filter(branch=branch, is_active=True, is_archived=False, **year_filter)
        .annotate(student_count=Count("enrollments", filter=Q(enrollments__is_active=True)))
        .order_by("-student_count", "level", "programme__title")[:limit]
    )


def get_top_programmes_for_branch(branch, limit=3, *, academic_year=None):
    year_filter = {"academic_year": academic_year.name} if academic_year else {}
    return list(
        Candidature.objects.filter(branch=branch, is_deleted=False, **year_filter)
        .values("programme__title")
        .annotate(total=Count("id"))
        .order_by("-total", "programme__title")[:limit]
    )


def get_latest_payments_for_branch(branch, limit=5, *, academic_year=None):
    candidature_filters = {}
    payment_date_filters = {}
    if academic_year is not None:
        academic_year_start, academic_year_end = get_academic_year_datetime_bounds(academic_year)
        candidature_filters["inscription__candidature__academic_year"] = academic_year.name
        payment_date_filters = {
            "paid_at__gte": academic_year_start,
            "paid_at__lt": academic_year_end,
        }
    return list(
        Payment.objects.filter(
            status=Payment.STATUS_VALIDATED,
            inscription__candidature__branch=branch,
            **candidature_filters,
            **payment_date_filters,
        )
        .select_related("inscription__candidature")
        .order_by("-paid_at")[:limit]
    )
