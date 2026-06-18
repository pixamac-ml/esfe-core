from datetime import date, timedelta

from django.db.models import Q, Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from admissions.models import Candidature
from accounts.models import BranchCashMovement, BranchExpense, PayrollEntry, Profile, TeacherHonorariumEntry
from accounts.services.manager_intelligence import build_manager_intelligence_context, get_branch_cash_balance
from inscriptions.models import Inscription
from payments.models import Payment
from students.models import Student

from accounts.dashboards.htmx_utils import manager_required


@manager_required
@require_GET
def widget_cash_balance(request: HttpRequest) -> HttpResponse:
    branch = request.branch
    balance = get_branch_cash_balance(branch)
    today = timezone.now().date()
    start_of_month = today.replace(day=1)
    cash_in_month = BranchCashMovement.objects.filter(
        branch=branch, movement_date__gte=start_of_month,
        movement_type=BranchCashMovement.TYPE_IN,
    ).aggregate(total=Sum("amount"))["total"] or 0
    cash_out_month = BranchCashMovement.objects.filter(
        branch=branch, movement_date__gte=start_of_month,
        movement_type=BranchCashMovement.TYPE_OUT,
    ).aggregate(total=Sum("amount"))["total"] or 0
    return render(
        request,
        "accounts/dashboard/partials/widget_cash_balance.html",
        {
            "balance": balance,
            "cash_in_month": cash_in_month,
            "cash_out_month": cash_out_month,
            "net_month": cash_in_month - cash_out_month,
        },
    )


@manager_required
@require_GET
def widget_scope_bar(request: HttpRequest) -> HttpResponse:
    branch = request.branch
    today = timezone.now().date()
    total_students = Student.objects.filter(
        inscription__candidature__branch=branch,
        inscription__candidature__is_deleted=False,
        inscription__is_archived=False,
        is_active=True,
    ).count()
    candidatures_pending = Candidature.objects.filter(
        branch=branch, is_deleted=False,
        status__in=["submitted", "under_review"],
    ).count()
    pending_payments = Payment.objects.filter(
        inscription__candidature__branch=branch,
        inscription__candidature__is_deleted=False,
        inscription__is_archived=False,
        status=Payment.STATUS_PENDING,
    ).count()
    balance = get_branch_cash_balance(branch)
    return render(
        request,
        "accounts/dashboard/partials/widget_scope_bar.html",
        {
            "branch": branch,
            "total_students": total_students,
            "candidatures_pending": candidatures_pending,
            "pending_payments": pending_payments,
            "cash_balance": balance,
        },
    )


@manager_required
@require_GET
def widget_alerts_badge(request: HttpRequest) -> HttpResponse:
    branch = request.branch
    payroll_month = timezone.now().date().replace(day=1)
    today = timezone.now().date()
    base_payments = Payment.objects.filter(
        inscription__candidature__branch=branch,
        inscription__candidature__is_deleted=False,
        inscription__is_archived=False,
    )
    base_inscriptions = Inscription.objects.filter(
        candidature__branch=branch,
        candidature__is_deleted=False,
        is_archived=False,
    )
    branch_staff_profiles = Profile.objects.filter(
        branch=branch, user__is_active=True,
    ).exclude(position="student").exclude(user_type="public")
    branch_teacher_profiles = branch_staff_profiles.filter(position="teacher")
    branch_staff_user_ids = list(branch_staff_profiles.exclude(position="teacher").values_list("user_id", flat=True))
    branch_teacher_user_ids = list(branch_teacher_profiles.values_list("user_id", flat=True))
    payroll_entries_qs = PayrollEntry.objects.filter(
        branch=branch, employee_id__in=branch_staff_user_ids, period_month=payroll_month,
    )
    honorarium_entries_qs = TeacherHonorariumEntry.objects.filter(
        branch=branch, teacher_id__in=branch_teacher_user_ids, period_month=payroll_month,
    )
    cash_stats = {"available_balance": get_branch_cash_balance(branch)}
    expense_stats = {
        "pending_amount": BranchExpense.objects.filter(
            branch=branch, status__in=[BranchExpense.STATUS_SUBMITTED, BranchExpense.STATUS_APPROVED],
        ).aggregate(total=Sum("amount"))["total"] or 0,
    }
    payroll_stats = {"due_total": sum(e.net_salary for e in payroll_entries_qs), "paid_total": sum(e.paid_amount for e in payroll_entries_qs)}
    honorarium_stats = {"due_total": sum(e.net_amount for e in honorarium_entries_qs), "paid_total": sum(e.paid_amount for e in honorarium_entries_qs)}
    intelligence = build_manager_intelligence_context(
        branch=branch, payroll_month=payroll_month,
        base_payments=base_payments, base_inscriptions=base_inscriptions,
        payroll_stats=payroll_stats, honorarium_stats=honorarium_stats,
        expense_stats=expense_stats, cash_stats=cash_stats,
        branch_staff_user_ids=branch_staff_user_ids,
        branch_teacher_user_ids=branch_teacher_user_ids,
    )
    return render(
        request,
        "accounts/dashboard/partials/widget_alerts_badge.html",
        {"alerts_count": len(intelligence.get("alerts", [])), "priorities_count": len(intelligence.get("priorities", []))},
    )


@manager_required
@require_GET
def widget_today_payments(request: HttpRequest) -> HttpResponse:
    branch = request.branch
    today = timezone.now().date()
    start_of_month = today.replace(day=1)
    base_payments = Payment.objects.filter(
        inscription__candidature__branch=branch,
        inscription__candidature__is_deleted=False,
        inscription__is_archived=False,
    )
    today_count = base_payments.filter(
        status=Payment.STATUS_VALIDATED, paid_at__date=today,
    ).count()
    today_total = base_payments.filter(
        status=Payment.STATUS_VALIDATED, paid_at__date=today,
    ).aggregate(total=Sum("amount"))["total"] or 0
    month_total = base_payments.filter(
        status=Payment.STATUS_VALIDATED, paid_at__date__gte=start_of_month,
    ).aggregate(total=Sum("amount"))["total"] or 0
    pending_count = base_payments.filter(status=Payment.STATUS_PENDING).count()
    pending_amount = base_payments.filter(status=Payment.STATUS_PENDING).aggregate(total=Sum("amount"))["total"] or 0
    return render(
        request,
        "accounts/dashboard/partials/widget_today_payments.html",
        {
            "today_count": today_count,
            "today_total": today_total,
            "month_total": month_total,
            "pending_count": pending_count,
            "pending_amount": pending_amount,
        },
    )


@manager_required
@require_GET
def widget_active_sessions(request: HttpRequest) -> HttpResponse:
    branch = request.branch
    from payments.models import CashPaymentSession, PaymentAgent
    now = timezone.now()
    agent = PaymentAgent.objects.filter(user=request.user, branch=branch, is_active=True).first()
    sessions = []
    if agent:
        sessions = CashPaymentSession.objects.filter(
            agent=agent, is_used=False, expires_at__gt=now,
        ).select_related("inscription", "inscription__candidature").order_by("-created_at")[:5]
    return render(
        request,
        "accounts/dashboard/partials/widget_active_sessions.html",
        {"sessions": sessions, "count": len(sessions)},
    )


@manager_required
@require_GET
def widget_sidebar_badges(request: HttpRequest) -> HttpResponse:
    branch = request.branch
    candidatures_pending = Candidature.objects.filter(
        branch=branch, is_deleted=False,
        status__in=["submitted", "under_review"],
    ).count()
    pending_payments = Payment.objects.filter(
        inscription__candidature__branch=branch,
        inscription__candidature__is_deleted=False,
        inscription__is_archived=False,
        status=Payment.STATUS_PENDING,
    ).count()
    return render(
        request,
        "accounts/dashboard/partials/widget_sidebar_badges.html",
        {
            "candidatures_pending": candidatures_pending,
            "pending_payments": pending_payments,
        },
    )
