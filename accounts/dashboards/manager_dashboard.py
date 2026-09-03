from datetime import date, timedelta
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.core.paginator import Paginator
from django.db import OperationalError, ProgrammingError
from django.db.models import Count, F, Q, Sum
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET

from academics.models import AcademicClass, AcademicYear
from admissions.models import Candidature
from accounts.forms import BranchBankTransferForm, BranchCashMovementForm, BranchExpenseForm, BranchMonthlyClosureForm, BranchWalletForm, CashRegisterCloseForm, CashRegisterOpenForm, DonationForm, WalletAmountForm
from accounts.models import BranchBankTransfer, BranchCashMovement, BranchCashRegisterSession, BranchExpense, BranchMonthlyClosure, BranchWallet, Donation, PayrollEntry, Profile, TeacherHonorariumEntry
from accounts.services.manager_intelligence import build_manager_intelligence_context
from accounts.services.manager_intelligence import get_branch_cash_balance
from accounts.services.wallets import branch_unallocated_cash, wallet_balance
from accounts.services.financial_reports import build_manager_financial_report_context, resolve_financial_report_period
from accounts.services.manager_dashboard_presentation import (
    MANAGER_SUBVIEW_DEFINITIONS,
    build_manager_dashboard_presentation,
    normalize_manager_subview,
)
from accounts.services.manager_workspace_access import manager_workspace_required
from coupons.services.querysets import active_coupons_for_branch
from shop.forms import ShopCounterOrderForm, ShopProductForm, ShopStockAdjustmentForm, ShopStockInForm
from shop.services.shop_cash_session import manager_shop_sessions_for_agent
from shop.services.shop_service import get_manager_shop_context
from shop.views import get_branch_public_shop_identifier
from inscriptions.models import Inscription
from payments.models import CashPaymentSession, FinancialLog, Payment, PaymentAgent
from students.models import Student

from accounts.dashboards.helpers import get_user_branch, is_manager
from portal.services import build_role_dashboard_shell
from portal.services.reenrollment_service import get_reenrollment_dashboard_context


PAYABLE_INSCRIPTION_STATUSES = {
    Inscription.STATUS_CREATED,
    Inscription.STATUS_AWAITING_PAYMENT,
    Inscription.STATUS_PARTIAL,
}

# Dashboard workspaces stay scannable: pages show at most ten records and
# summary widgets show at most five. The complete branch-scoped data remains
# available through the existing pagination controls.
DASHBOARD_LIST_PAGE_SIZE = 10
DASHBOARD_PREVIEW_SIZE = 5


def manager_required(view_func):
    """Authorize a role context inside the single manager workspace."""

    return login_required(manager_workspace_required("view_manager_workspace")(view_func))


def _paginate(request, queryset, *, param_name, per_page=DASHBOARD_LIST_PAGE_SIZE):
    paginator = Paginator(queryset, per_page)
    return paginator.get_page(request.GET.get(param_name, 1))


def _resolve_report_period(request, today):
    return resolve_financial_report_period(request, today=today)


def _read_activity_date(request, parameter):
    """Return one safe ISO date used only to consult a workspace history."""

    raw_value = (request.GET.get(parameter) or "").strip()
    if not raw_value:
        return None, ""
    try:
        return date.fromisoformat(raw_value), raw_value
    except ValueError:
        return None, ""


def _get_manager_agent(user, branch):
    return (
        PaymentAgent.objects
        .select_related("user", "branch")
        .filter(user=user, branch=branch, is_active=True)
        .first()
    )


def _manager_context(request, active_section="overview"):
    branch = request.branch
    today = timezone.now().date()

    reenrollment_context = {}
    if active_section == "reenrollment":
        source_year = AcademicYear.objects.filter(pk=request.GET.get("source_year")).first() if str(request.GET.get("source_year", "")).isdigit() else None
        target_year = AcademicYear.objects.filter(pk=request.GET.get("target_year")).first() if str(request.GET.get("target_year", "")).isdigit() else None
        scoped_classes = AcademicClass.objects.filter(branch=branch, is_archived=False).select_related(
            "academic_year", "programme", "branch"
        )
        source_class = scoped_classes.filter(pk=request.GET.get("source_class")).first() if str(request.GET.get("source_class", "")).isdigit() else None
        target_class = scoped_classes.filter(pk=request.GET.get("target_class"), is_active=True).first() if str(request.GET.get("target_class", "")).isdigit() else None
        if source_class is not None:
            source_year = source_class.academic_year
        if target_class is not None:
            target_year = target_class.academic_year
        programme = None
        programme_id = request.GET.get("programme", "")
        if str(programme_id).isdigit():
            programme = scoped_classes.filter(programme_id=programme_id).values_list("programme", flat=True).first()
            if programme is not None:
                from formations.models import Programme

                programme = Programme.objects.filter(pk=programme).first()
        reenrollment_context = get_reenrollment_dashboard_context(
            branch=branch,
            source_year=source_year,
            source_class=source_class,
            target_year=target_year,
            target_class=target_class,
            programme=programme,
            decision_value=(request.GET.get("decision") or "").strip(),
            workflow_status=(request.GET.get("workflow_status") or "").strip(),
            finance_state=(request.GET.get("finance_state") or "").strip(),
            search=(request.GET.get("q") or "").strip()[:120],
            actor=request.user,
            surface="manager",
            workspace_target="#reenrollment-workspace",
        )
    start_of_week = today - timedelta(days=today.weekday())
    start_of_month = today.replace(day=1)
    now = timezone.now()
    selected_month = (request.GET.get("salary_month") or "").strip()
    if selected_month:
        try:
            payroll_month = date.fromisoformat(f"{selected_month}-01")
        except ValueError:
            payroll_month = today.replace(day=1)
    else:
        payroll_month = today.replace(day=1)

    base_inscriptions = Inscription.objects.filter(
        candidature__branch=branch,
        candidature__is_deleted=False,
        is_archived=False,
    )
    base_candidatures = Candidature.objects.filter(
        branch=branch,
        is_deleted=False,
    )
    base_payments = Payment.objects.filter(
        inscription__candidature__branch=branch,
        inscription__candidature__is_deleted=False,
        inscription__is_archived=False,
    )
    branch_staff_profiles = (
        Profile.objects
        .select_related("user", "branch")
        .filter(
            branch=branch,
            user__is_active=True,
        )
        .exclude(position="student")
        .exclude(user_type="public")
        .order_by("user__first_name", "user__last_name")
    )
    branch_teacher_profiles = (
        Profile.objects
        .select_related("user", "branch")
        .filter(
            branch=branch,
            user__is_active=True,
            position="teacher",
        )
        .exclude(user_type="public")
        .order_by("user__first_name", "user__last_name")
    )
    branch_salary_profiles = branch_staff_profiles.exclude(position="teacher")
    branch_staff_user_ids = list(
        branch_salary_profiles.values_list("user_id", flat=True)
    )
    branch_teacher_user_ids = list(branch_teacher_profiles.values_list("user_id", flat=True))
    manager_agent = _get_manager_agent(request.user, branch)
    active_cash_sessions = []
    active_cash_sessions_count = 0
    if manager_agent:
        active_cash_sessions_qs = (
            CashPaymentSession.objects
            .filter(
                agent=manager_agent,
                is_used=False,
                expires_at__gt=now,
            )
            .select_related(
                "agent__user",
                "inscription",
                "inscription__candidature",
                "inscription__candidature__programme",
            )
            .order_by("-created_at")[:DASHBOARD_PREVIEW_SIZE]
        )
        active_cash_sessions = list(active_cash_sessions_qs)
        active_cash_sessions_count = CashPaymentSession.objects.filter(
            agent=manager_agent,
            is_used=False,
            expires_at__gt=now,
        ).count()
    active_cash_sessions_by_inscription = {
        session.inscription_id: session for session in active_cash_sessions
    }
    active_shop_cash_sessions = []
    if manager_agent:
        active_shop_cash_sessions = manager_shop_sessions_for_agent(
            manager_agent, limit=DASHBOARD_PREVIEW_SIZE
        )

    overview_inscriptions = (
        base_inscriptions
        .select_related(
            "candidature",
            "candidature__programme",
            "candidature__programme__cycle",
        )
        .order_by("-created_at")[:DASHBOARD_PREVIEW_SIZE]
    )
    recent_candidatures = (
        base_candidatures
        .select_related("programme", "programme__cycle")
        .order_by("-submitted_at")[:5]
    )
    payments_today = (
        base_payments
        .filter(paid_at__date=today)
        .select_related(
            "inscription__candidature",
            "inscription__candidature__programme",
        )
        .order_by("-paid_at")
    )
    recent_payments = (
        base_payments
        .select_related(
            "inscription__candidature",
            "inscription__candidature__programme",
        )
        .order_by("-paid_at")[:5]
    )

    total_inscriptions = base_inscriptions.count()
    inscriptions_this_month = base_inscriptions.filter(created_at__date__gte=start_of_month).count()
    inscriptions_active = base_inscriptions.filter(status=Inscription.STATUS_ACTIVE).count()
    inscriptions_with_balance = base_inscriptions.filter(
        status__in=[Inscription.STATUS_PARTIAL, Inscription.STATUS_AWAITING_PAYMENT]
    ).count()
    inscriptions_to_finalize = base_inscriptions.filter(
        status__in=[
            Inscription.STATUS_CREATED,
            Inscription.STATUS_AWAITING_PAYMENT,
            Inscription.STATUS_PARTIAL,
        ]
    ).count()
    inscription_amounts = base_inscriptions.aggregate(
        due=Sum("amount_due"),
        paid=Sum("amount_paid"),
    )
    total_amount_due = inscription_amounts["due"] or 0
    total_amount_paid = inscription_amounts["paid"] or 0
    collection_rate = round((total_amount_paid / total_amount_due) * 100) if total_amount_due else 0

    candidatures_pending = base_candidatures.filter(
        status__in=["submitted", "under_review"],
    ).count()
    candidatures_to_complete = base_candidatures.filter(status="to_complete").count()
    candidatures_accepted = base_candidatures.filter(
        status__in=["accepted", "accepted_with_reserve"],
    ).count()

    total_students = Student.objects.filter(
        inscription__candidature__branch=branch,
        inscription__candidature__is_deleted=False,
        inscription__is_archived=False,
        is_active=True,
    ).count()

    total_today = base_payments.filter(
        status=Payment.STATUS_VALIDATED,
        paid_at__date=today,
    ).aggregate(total=Sum("amount"))["total"] or 0
    validated_today_count = base_payments.filter(
        status=Payment.STATUS_VALIDATED,
        paid_at__date=today,
    ).count()
    total_week = base_payments.filter(
        status=Payment.STATUS_VALIDATED,
        paid_at__date__gte=start_of_week,
    ).aggregate(total=Sum("amount"))["total"] or 0
    total_month = base_payments.filter(
        status=Payment.STATUS_VALIDATED,
        paid_at__date__gte=start_of_month,
    ).aggregate(total=Sum("amount"))["total"] or 0
    pending_payments = base_payments.filter(status=Payment.STATUS_PENDING).count()
    pending_payments_amount = base_payments.filter(
        status=Payment.STATUS_PENDING
    ).aggregate(total=Sum("amount"))["total"] or 0

    cand_status = request.GET.get("cand_status", "").strip()
    cand_search = request.GET.get("cand_q", "").strip()
    cand_activity_date, cand_activity_date_value = _read_activity_date(request, "cand_date")
    candidatures_qs = (
        base_candidatures
        .select_related("programme", "programme__cycle", "inscription")
        .order_by("-submitted_at")
    )
    if cand_status:
        if cand_status == "open":
            candidatures_qs = candidatures_qs.filter(status__in=["submitted", "under_review"])
        elif cand_status == "accepted":
            candidatures_qs = candidatures_qs.filter(status__in=["accepted", "accepted_with_reserve"])
        else:
            candidatures_qs = candidatures_qs.filter(status=cand_status)
    if cand_activity_date:
        candidatures_qs = candidatures_qs.filter(
            Q(submitted_at__date=cand_activity_date)
            | Q(reviewed_at__date=cand_activity_date)
        )
    if cand_search:
        candidatures_qs = candidatures_qs.filter(
            Q(first_name__icontains=cand_search)
            | Q(last_name__icontains=cand_search)
            | Q(email__icontains=cand_search)
        )
    candidatures_page = _paginate(request, candidatures_qs, param_name="cand_page")
    candidature_stats = {
        "total": base_candidatures.count(),
        "submitted": base_candidatures.filter(status="submitted").count(),
        "under_review": base_candidatures.filter(status="under_review").count(),
        "to_complete": base_candidatures.filter(status="to_complete").count(),
        "accepted": base_candidatures.filter(status__in=["accepted", "accepted_with_reserve"]).count(),
        "rejected": base_candidatures.filter(status="rejected").count(),
    }

    ins_status = request.GET.get("ins_status", "").strip()
    ins_search = request.GET.get("ins_q", "").strip()
    ins_activity_date, ins_activity_date_value = _read_activity_date(request, "ins_date")
    inscriptions_qs = (
        base_inscriptions
        .select_related(
            "candidature",
            "candidature__programme",
            "candidature__programme__cycle",
        )
        .order_by("-created_at")
    )
    if ins_status:
        if ins_status == "open":
            inscriptions_qs = inscriptions_qs.filter(
                status__in=[
                    Inscription.STATUS_CREATED,
                    Inscription.STATUS_AWAITING_PAYMENT,
                    Inscription.STATUS_PARTIAL,
                ]
            )
        else:
            inscriptions_qs = inscriptions_qs.filter(status=ins_status)
    if ins_activity_date:
        inscriptions_qs = inscriptions_qs.filter(
            Q(created_at__date=ins_activity_date)
            | Q(updated_at__date=ins_activity_date)
        )
    if ins_search:
        inscriptions_qs = inscriptions_qs.filter(
            Q(candidature__first_name__icontains=ins_search)
            | Q(candidature__last_name__icontains=ins_search)
            | Q(candidature__email__icontains=ins_search)
            | Q(public_token__icontains=ins_search)
        )
    inscriptions_page = _paginate(request, inscriptions_qs, param_name="ins_page")
    inscription_stats = {
        "total": base_inscriptions.count(),
        "active": base_inscriptions.filter(status=Inscription.STATUS_ACTIVE).count(),
        "partial": base_inscriptions.filter(status=Inscription.STATUS_PARTIAL).count(),
        "awaiting": base_inscriptions.filter(status=Inscription.STATUS_AWAITING_PAYMENT).count(),
        "created": base_inscriptions.filter(status=Inscription.STATUS_CREATED).count(),
    }

    pay_status = request.GET.get("pay_status", "").strip()
    pay_method = request.GET.get("pay_method", "").strip()
    pay_date = request.GET.get("pay_date", "").strip()
    pay_search = request.GET.get("pay_q", "").strip()
    payments_qs = (
        base_payments
        .select_related(
            "inscription__candidature",
            "inscription__candidature__programme",
            "agent__user",
            "cash_session",
        )
        .order_by("-paid_at", "-created_at")
    )
    if pay_status:
        payments_qs = payments_qs.filter(status=pay_status)
    if pay_method:
        payments_qs = payments_qs.filter(method=pay_method)
    if pay_date == "today":
        payments_qs = payments_qs.filter(paid_at__date=today)
    elif pay_date == "week":
        payments_qs = payments_qs.filter(paid_at__date__gte=start_of_week)
    elif pay_date == "month":
        payments_qs = payments_qs.filter(paid_at__date__gte=start_of_month)
    if pay_search:
        payments_qs = payments_qs.filter(
            Q(reference__icontains=pay_search)
            | Q(inscription__candidature__first_name__icontains=pay_search)
            | Q(inscription__candidature__last_name__icontains=pay_search)
            | Q(receipt_number__icontains=pay_search)
        )
    payments_page = _paginate(request, payments_qs, param_name="pay_page")
    for inscription in overview_inscriptions:
        inscription.active_cash_session = active_cash_sessions_by_inscription.get(inscription.id)
    for inscription in inscriptions_page.object_list:
        inscription.active_cash_session = active_cash_sessions_by_inscription.get(inscription.id)

    payable_inscriptions = list(
        base_inscriptions
        .filter(
            status__in=PAYABLE_INSCRIPTION_STATUSES,
            amount_due__gt=F("amount_paid"),
        )
        .select_related(
            "candidature",
            "candidature__programme",
            "candidature__programme__cycle",
        )
        .order_by("-created_at")[:DASHBOARD_LIST_PAGE_SIZE]
    )
    for inscription in payable_inscriptions:
        inscription.active_cash_session = active_cash_sessions_by_inscription.get(inscription.id)

    payment_stats = {
        "total": base_payments.count(),
        "validated": base_payments.filter(status=Payment.STATUS_VALIDATED).count(),
        "pending": base_payments.filter(status=Payment.STATUS_PENDING).count(),
        "cancelled": base_payments.filter(status=Payment.STATUS_CANCELLED).count(),
        "total_amount": base_payments.filter(
            status=Payment.STATUS_VALIDATED
        ).aggregate(total=Sum("amount"))["total"] or 0,
    }
    annual_revenue_rows = list(
        base_payments
        .filter(status=Payment.STATUS_VALIDATED)
        .values("paid_at__year")
        .annotate(total_amount=Sum("amount"), payments_count=Count("id"))
        .order_by("-paid_at__year")
    )
    annual_revenue_rows = [row for row in annual_revenue_rows if row.get("paid_at__year") is not None]
    current_year = today.year
    current_year_revenue = next(
        ((row["total_amount"] or 0) for row in annual_revenue_rows if row["paid_at__year"] == current_year),
        0,
    )
    previous_year_revenue = next(
        ((row["total_amount"] or 0) for row in annual_revenue_rows if row["paid_at__year"] == current_year - 1),
        0,
    )
    annual_revenue_growth = 0
    if previous_year_revenue > 0:
        annual_revenue_growth = round(
            ((current_year_revenue - previous_year_revenue) / previous_year_revenue) * 100,
            1,
        )

    financial_report = build_manager_financial_report_context(branch=branch, request=request, today=today)
    report_period = financial_report["report_period"]
    report_rows = financial_report["report_summary_rows"]

    expense_status = request.GET.get("expense_status", "").strip()
    expense_category = request.GET.get("expense_category", "").strip()
    expense_search = request.GET.get("expense_q", "").strip()
    expenses_qs = BranchExpense.objects.filter(branch=branch).order_by("-expense_date", "-created_at")
    if expense_status:
        expenses_qs = expenses_qs.filter(status=expense_status)
    if expense_category:
        expenses_qs = expenses_qs.filter(category=expense_category)
    if expense_search:
        expenses_qs = expenses_qs.filter(
            Q(title__icontains=expense_search)
            | Q(supplier__icontains=expense_search)
            | Q(reference__icontains=expense_search)
        )
    expenses_page = _paginate(
        request, expenses_qs, param_name="expense_page", per_page=DASHBOARD_LIST_PAGE_SIZE
    )
    expenses_month = BranchExpense.objects.filter(branch=branch, expense_date__gte=start_of_month)
    expense_stats = {
        "total": BranchExpense.objects.filter(branch=branch).count(),
        "submitted": BranchExpense.objects.filter(branch=branch, status=BranchExpense.STATUS_SUBMITTED).count(),
        "approved": BranchExpense.objects.filter(branch=branch, status=BranchExpense.STATUS_APPROVED).count(),
        "paid": BranchExpense.objects.filter(branch=branch, status=BranchExpense.STATUS_PAID).count(),
        "month_amount": expenses_month.exclude(status=BranchExpense.STATUS_REJECTED).aggregate(total=Sum("amount"))["total"] or 0,
        "paid_month_amount": expenses_month.filter(status=BranchExpense.STATUS_PAID).aggregate(total=Sum("amount"))["total"] or 0,
        "pending_amount": BranchExpense.objects.filter(
            branch=branch,
            status__in=[BranchExpense.STATUS_SUBMITTED, BranchExpense.STATUS_APPROVED],
        ).aggregate(total=Sum("amount"))["total"] or 0,
    }

    cash_type = request.GET.get("cash_type", "").strip()
    cash_source = request.GET.get("cash_source", "").strip()
    cash_search = request.GET.get("cash_q", "").strip()
    cash_activity_date, cash_activity_date_value = _read_activity_date(request, "cash_date")
    cash_movements_qs = BranchCashMovement.objects.filter(branch=branch).select_related("expense", "created_by")
    if cash_type:
        cash_movements_qs = cash_movements_qs.filter(movement_type=cash_type)
    if cash_source:
        cash_movements_qs = cash_movements_qs.filter(source=cash_source)
    if cash_activity_date:
        cash_movements_qs = cash_movements_qs.filter(movement_date=cash_activity_date)
    if cash_search:
        cash_movements_qs = cash_movements_qs.filter(
            Q(label__icontains=cash_search)
            | Q(reference__icontains=cash_search)
            | Q(notes__icontains=cash_search)
        )
    cash_movements_page = _paginate(
        request,
        cash_movements_qs.order_by("-movement_date", "-created_at"),
        param_name="cash_page",
        per_page=DASHBOARD_LIST_PAGE_SIZE,
    )
    cash_month_movements = BranchCashMovement.objects.filter(branch=branch, movement_date__gte=start_of_month)
    cash_in_month = cash_month_movements.filter(movement_type=BranchCashMovement.TYPE_IN).aggregate(total=Sum("amount"))["total"] or 0
    cash_out_month = cash_month_movements.filter(movement_type=BranchCashMovement.TYPE_OUT).aggregate(total=Sum("amount"))["total"] or 0
    salary_paid_month = PayrollEntry.objects.filter(
        branch=branch,
        period_month=start_of_month,
    ).aggregate(total=Sum("paid_amount"))["total"] or 0
    honorarium_paid_month = TeacherHonorariumEntry.objects.filter(
        branch=branch,
        period_month=start_of_month,
    ).aggregate(total=Sum("paid_amount"))["total"] or 0
    estimated_month_balance = cash_in_month - cash_out_month
    cash_stats = {
        "movements": BranchCashMovement.objects.filter(branch=branch).count(),
        "in_month": cash_in_month,
        "out_month": cash_out_month,
        "net_month": cash_in_month - cash_out_month,
        "estimated_month_balance": estimated_month_balance,
        "available_balance": get_branch_cash_balance(branch),
        "student_receipts_month": total_month,
        "expenses_paid_month": expense_stats["paid_month_amount"],
        "salary_paid_month": salary_paid_month,
        "honorarium_paid_month": honorarium_paid_month,
    }
    cash_stats["estimated_month_balance_abs"] = abs(estimated_month_balance)
    cash_stats["bar_max"] = max(
        cash_stats["student_receipts_month"],
        cash_stats["expenses_paid_month"],
        cash_stats["salary_paid_month"],
        cash_stats["honorarium_paid_month"],
        cash_stats["estimated_month_balance_abs"],
    ) or 1
    recent_financial_logs = (
        FinancialLog.objects
        .filter(branch=branch)
        .select_related("actor", "payment", "correction")
        .order_by("-created_at")[:DASHBOARD_LIST_PAGE_SIZE]
    )

    payroll_entries_qs = (
        PayrollEntry.objects
        .filter(
            branch=branch,
            employee_id__in=branch_staff_user_ids,
            period_month=payroll_month,
        )
        .select_related("employee", "employee__profile", "branch")
        .order_by("employee__first_name", "employee__last_name")
    )
    payroll_entries_by_employee = {
        entry.employee_id: entry for entry in payroll_entries_qs
    }
    salary_status = request.GET.get("salary_status", "").strip()
    salary_search = request.GET.get("salary_q", "").strip()
    staff_profiles_filtered = branch_salary_profiles
    if salary_status:
        if salary_status == "missing":
            staff_profiles_filtered = [
                profile for profile in staff_profiles_filtered
                if profile.user_id not in payroll_entries_by_employee
            ]
        elif salary_status == "payable":
            staff_profiles_filtered = [
                profile for profile in staff_profiles_filtered
                if payroll_entries_by_employee.get(profile.user_id)
                and payroll_entries_by_employee[profile.user_id].status in {
                    PayrollEntry.STATUS_READY,
                    PayrollEntry.STATUS_PARTIAL,
                }
            ]
        else:
            staff_profiles_filtered = [
                profile for profile in staff_profiles_filtered
                if payroll_entries_by_employee.get(profile.user_id)
                and payroll_entries_by_employee[profile.user_id].status == salary_status
            ]
    else:
        staff_profiles_filtered = list(staff_profiles_filtered)
    if salary_search:
        search_value = salary_search.lower()
        staff_profiles_filtered = [
            profile for profile in staff_profiles_filtered
            if search_value in (profile.user.get_full_name() or profile.user.username).lower()
            or search_value in (profile.employee_code or "").lower()
            or search_value in (profile.position or "").lower()
        ]
    for profile in staff_profiles_filtered:
        profile.current_payroll = payroll_entries_by_employee.get(profile.user_id)

    payroll_entries_page = _paginate(
        request,
        staff_profiles_filtered,
        param_name="salary_page",
        per_page=DASHBOARD_LIST_PAGE_SIZE,
    )
    payroll_total_due = sum(entry.net_salary for entry in payroll_entries_qs)
    payroll_total_paid = sum(entry.paid_amount for entry in payroll_entries_qs)
    payroll_remaining = max(payroll_total_due - payroll_total_paid, 0)
    payroll_stats = {
        "employees": len(branch_staff_user_ids),
        "prepared": payroll_entries_qs.count(),
        "paid": sum(1 for entry in payroll_entries_qs if entry.status == PayrollEntry.STATUS_PAID),
        "partial": sum(1 for entry in payroll_entries_qs if entry.status == PayrollEntry.STATUS_PARTIAL),
        "to_review": sum(1 for entry in payroll_entries_qs if entry.status == PayrollEntry.STATUS_DRAFT),
        "ready": sum(1 for entry in payroll_entries_qs if entry.status == PayrollEntry.STATUS_READY),
        "payable": sum(
            1 for entry in payroll_entries_qs
            if entry.status in {PayrollEntry.STATUS_READY, PayrollEntry.STATUS_PARTIAL}
        ),
        "due_total": payroll_total_due,
        "paid_total": payroll_total_paid,
        "remaining_total": payroll_remaining,
    }
    honorarium_entries_qs = (
        TeacherHonorariumEntry.objects
        .filter(
            branch=branch,
            teacher_id__in=branch_teacher_user_ids,
            period_month=payroll_month,
        )
        .select_related("teacher", "teacher__profile", "branch")
        .order_by("teacher__first_name", "teacher__last_name")
    )
    honorarium_entries_by_teacher = {entry.teacher_id: entry for entry in honorarium_entries_qs}
    honorarium_status = request.GET.get("honorarium_status", "").strip()
    honorarium_search = request.GET.get("honorarium_q", "").strip()
    teacher_profiles_filtered = branch_teacher_profiles
    if honorarium_status:
        if honorarium_status == "missing":
            teacher_profiles_filtered = [
                profile for profile in teacher_profiles_filtered
                if profile.user_id not in honorarium_entries_by_teacher
            ]
        elif honorarium_status == "payable":
            teacher_profiles_filtered = [
                profile for profile in teacher_profiles_filtered
                if honorarium_entries_by_teacher.get(profile.user_id)
                and honorarium_entries_by_teacher[profile.user_id].status in {
                    TeacherHonorariumEntry.STATUS_READY,
                    TeacherHonorariumEntry.STATUS_PARTIAL,
                }
            ]
        else:
            teacher_profiles_filtered = [
                profile for profile in teacher_profiles_filtered
                if honorarium_entries_by_teacher.get(profile.user_id)
                and honorarium_entries_by_teacher[profile.user_id].status == honorarium_status
            ]
    else:
        teacher_profiles_filtered = list(teacher_profiles_filtered)
    if honorarium_search:
        search_value = honorarium_search.lower()
        teacher_profiles_filtered = [
            profile for profile in teacher_profiles_filtered
            if search_value in (profile.user.get_full_name() or profile.user.username).lower()
            or search_value in (profile.employee_code or "").lower()
            or search_value in (profile.position or "").lower()
        ]
    for profile in teacher_profiles_filtered:
        profile.current_honorarium = honorarium_entries_by_teacher.get(profile.user_id)
    honorarium_entries_page = _paginate(
        request,
        teacher_profiles_filtered,
        param_name="honorarium_page",
        per_page=DASHBOARD_LIST_PAGE_SIZE,
    )
    honorarium_total_due = sum(entry.net_amount for entry in honorarium_entries_qs)
    honorarium_total_paid = sum(entry.paid_amount for entry in honorarium_entries_qs)
    honorarium_remaining = max(honorarium_total_due - honorarium_total_paid, 0)
    honorarium_stats = {
        "teachers": len(branch_teacher_user_ids),
        "prepared": honorarium_entries_qs.count(),
        "paid": sum(1 for entry in honorarium_entries_qs if entry.status == TeacherHonorariumEntry.STATUS_PAID),
        "partial": sum(1 for entry in honorarium_entries_qs if entry.status == TeacherHonorariumEntry.STATUS_PARTIAL),
        "to_review": sum(1 for entry in honorarium_entries_qs if entry.status == TeacherHonorariumEntry.STATUS_DRAFT),
        "ready": sum(1 for entry in honorarium_entries_qs if entry.status == TeacherHonorariumEntry.STATUS_READY),
        "payable": sum(
            1 for entry in honorarium_entries_qs
            if entry.status in {
                TeacherHonorariumEntry.STATUS_READY,
                TeacherHonorariumEntry.STATUS_PARTIAL,
            }
        ),
        "due_total": honorarium_total_due,
        "paid_total": honorarium_total_paid,
        "remaining_total": honorarium_remaining,
    }
    intelligence = build_manager_intelligence_context(
        branch=branch,
        payroll_month=payroll_month,
        base_payments=base_payments,
        base_inscriptions=base_inscriptions,
        payroll_stats=payroll_stats,
        honorarium_stats=honorarium_stats,
        expense_stats=expense_stats,
        cash_stats=cash_stats,
        branch_staff_user_ids=branch_staff_user_ids,
        branch_teacher_user_ids=branch_teacher_user_ids,
    )
    daily_work_items = [
        {
            "label": "Candidatures à traiter",
            "description": "Dossiers soumis ou en analyse",
            "count": candidatures_pending,
            "href": "?section=candidatures&view=to_process",
            "icon": "file-check",
            "tone": "primary",
        },
        {
            "label": "Inscriptions à finaliser",
            "description": "Créées, en attente ou partielles",
            "count": inscriptions_to_finalize,
            "href": "?section=inscriptions&view=pending",
            "icon": "id-card",
            "tone": "info",
        },
        {
            "label": "Paiements à valider",
            "description": "Justificatifs ou encaissements en attente",
            "count": pending_payments,
            "href": "?section=paiements&view=to_validate",
            "icon": "circle-dollar-sign",
            "tone": "success",
        },
        {
            "label": "Dépenses à traiter",
            "description": "Soumises ou approuvées, à suivre",
            "count": expense_stats["submitted"] + expense_stats["approved"],
            "href": "?section=depenses&view=to_approve",
            "icon": "receipt-text",
            "tone": "warning",
        },
        {
            "label": "Salaires à payer",
            "description": "Fiches disponibles ou paiements partiels",
            "count": payroll_stats["payable"],
            "href": "?section=salaires&view=to_pay",
            "icon": "users-round",
            "tone": "warning",
        },
        {
            "label": "Honoraires à payer",
            "description": "Fiches disponibles ou paiements partiels",
            "count": honorarium_stats["payable"],
            "href": "?section=honoraires&view=to_pay",
            "icon": "graduation-cap",
            "tone": "info",
        },
    ]
    today_activity_count = (
        base_candidatures.filter(reviewed_at__date=today).count()
        + base_inscriptions.filter(Q(created_at__date=today) | Q(updated_at__date=today)).count()
        + base_payments.filter(status=Payment.STATUS_VALIDATED, paid_at__date=today).count()
        + BranchCashMovement.objects.filter(branch=branch, movement_date=today).count()
        + BranchExpense.objects.filter(branch=branch, paid_at__date=today).count()
    )
    daily_work_pending_count = sum(item["count"] for item in daily_work_items)
    shop_context = {
        "shop_products": [],
        "shop_catalogue_products": [],
        "shop_counter_catalog": [],
        "shop_orders": [],
        "shop_order_queues": {"pending": [], "paid": [], "ready": []},
        "shop_recent_payments": [],
        "shop_recent_stock_movements": [],
        "shop_journal_query": "",
        "shop_journal_date": "",
        "shop_stock_query": "",
        "shop_stock_state": "",
        "shop_stock_category": "",
        "shop_stats": {
            "products": 0,
            "required": 0,
            "low_stock": 0,
            "pending_orders": 0,
            "paid_not_delivered": 0,
            "ready_orders": 0,
            "month_sales": 0,
            "today_sales": 0,
            "today_sales_count": 0,
        },
        "shop_error": "",
    }
    if active_section == "boutique":
        try:
            shop_context = get_manager_shop_context(
                branch,
                journal_query=request.GET.get("shop_q", ""),
                journal_date=request.GET.get("shop_date", ""),
                stock_query=request.GET.get("shop_stock_q", ""),
                stock_state=request.GET.get("shop_stock_state", ""),
                stock_category=request.GET.get("shop_stock_category", ""),
            )
            shop_context.setdefault("shop_error", "")
        except (ProgrammingError, OperationalError):
            shop_context["shop_error"] = (
                "Le module shop attend encore l'application de sa migration locale. "
                "Les autres sections du dashboard restent utilisables."
            )
    shop_stats = shop_context.get("shop_stats", {})
    shop_sales_month = shop_stats.get("month_sales", 0) or 0
    period_revenue = total_month + shop_sales_month
    period_paid_charges = cash_stats["expenses_paid_month"] + cash_stats["salary_paid_month"] + cash_stats["honorarium_paid_month"]
    period_commitments = payroll_stats["remaining_total"] + honorarium_stats["remaining_total"] + expense_stats["pending_amount"]
    period_net_result = period_revenue - period_paid_charges
    period_balance_after_commitments = cash_stats["estimated_month_balance"] - period_commitments
    candidature_total = candidature_stats["total"]
    candidature_conversion_rate = round((candidatures_accepted / candidature_total) * 100) if candidature_total else 0
    period_summary = {
        "student_revenue": total_month,
        "shop_revenue": shop_sales_month,
        "total_revenue": period_revenue,
        "expenses_paid": cash_stats["expenses_paid_month"],
        "salary_paid": cash_stats["salary_paid_month"],
        "honorarium_paid": cash_stats["honorarium_paid_month"],
        "charges_paid": period_paid_charges,
        "net_result": period_net_result,
        "estimated_cash": cash_stats["estimated_month_balance"],
        "commitments": period_commitments,
        "balance_after_commitments": period_balance_after_commitments,
        "collection_rate": collection_rate,
        "candidature_conversion_rate": candidature_conversion_rate,
    }
    operational_flow = [
        {
            "label": "Candidatures a traiter",
            "value": candidatures_pending,
            "section": "candidatures",
            "tone": "amber",
        },
        {
            "label": "Dossiers acceptes",
            "value": candidatures_accepted,
            "section": "candidatures",
            "tone": "blue",
        },
        {
            "label": "Inscriptions actives",
            "value": inscriptions_active,
            "section": "inscriptions",
            "tone": "emerald",
        },
        {
            "label": "Paiements en attente",
            "value": pending_payments,
            "section": "paiements",
            "tone": "rose",
        },
        {
            "label": "Mouvements de caisse",
            "value": cash_stats["movements"],
            "section": "caisse",
            "tone": "slate",
        },
    ]

    quick_search = request.GET.get("q", "").strip()
    quick_results = {"candidatures": [], "inscriptions": [], "payments": []}
    if quick_search:
        quick_results["candidatures"] = list(
            base_candidatures.filter(
                Q(first_name__icontains=quick_search)
                | Q(last_name__icontains=quick_search)
                | Q(email__icontains=quick_search)
            ).select_related("programme")[:5]
        )
        quick_results["inscriptions"] = list(
            base_inscriptions.filter(
                Q(candidature__first_name__icontains=quick_search)
                | Q(candidature__last_name__icontains=quick_search)
                | Q(public_token__icontains=quick_search)
            ).select_related("candidature")[:5]
        )
        quick_results["payments"] = list(
            base_payments.filter(
                Q(reference__icontains=quick_search)
                | Q(inscription__candidature__last_name__icontains=quick_search)
            ).select_related("inscription__candidature")[:5]
        )

    donations_page = _paginate(
        request,
        Donation.objects.filter(branch=branch).order_by("-date", "-created_at"),
        param_name="donation_page",
        per_page=DASHBOARD_LIST_PAGE_SIZE,
    )
    monthly_closures_page = _paginate(
        request,
        BranchMonthlyClosure.objects.filter(branch=branch).order_by(
            "-period_month", "-created_at"
        ),
        param_name="closure_page",
    )
    bank_transfers_page = _paginate(
        request,
        BranchBankTransfer.objects.filter(branch=branch)
        .select_related("closure")
        .order_by("-transfer_date", "-created_at"),
        param_name="transfer_page",
    )
    cash_register_session = (
        BranchCashRegisterSession.objects.filter(branch=branch, session_date=today)
        .select_related("opened_by", "closed_by")
        .first()
    )
    wallets = list(BranchWallet.objects.filter(branch=branch).order_by("-is_favorite", "name"))
    for wallet in wallets:
        wallet.current_balance = wallet_balance(wallet)

    return {
        "active_page": "manager",
        "active_section": active_section,
        "branch": branch,
        "today": today,
        "overview_inscriptions": overview_inscriptions,
        "total_inscriptions": total_inscriptions,
        "inscriptions_this_month": inscriptions_this_month,
        "inscriptions_active": inscriptions_active,
        "inscriptions_with_balance": inscriptions_with_balance,
        "inscriptions_to_finalize": inscriptions_to_finalize,
        "candidatures_pending": candidatures_pending,
        "candidatures_to_complete": candidatures_to_complete,
        "candidatures_accepted": candidatures_accepted,
        "recent_candidatures": recent_candidatures,
        "total_students": total_students,
        "payments_today": payments_today,
        "recent_payments": recent_payments,
        "pending_payments": pending_payments,
        "pending_payments_amount": pending_payments_amount,
        "validated_today_count": validated_today_count,
        "total_today": total_today,
        "total_week": total_week,
        "total_month": total_month,
        "branch_staff_count": len(branch_staff_user_ids),
        "manager_agent": manager_agent,
        "active_cash_sessions": active_cash_sessions,
        "active_cash_sessions_count": active_cash_sessions_count,
        "active_shop_cash_sessions": active_shop_cash_sessions,
        "active_shop_cash_sessions_count": len(active_shop_cash_sessions),
        "coupons": active_coupons_for_branch(branch),
        "payable_inscriptions": payable_inscriptions,
        "payroll_month": payroll_month,
        "salary_month_value": payroll_month.strftime("%Y-%m"),
        "payroll_entries": payroll_entries_page,
        "payroll_stats": payroll_stats,
        "salary_status": salary_status,
        "salary_search": salary_search,
        "honorarium_entries": honorarium_entries_page,
        "honorarium_stats": honorarium_stats,
        "honorarium_status": honorarium_status,
        "honorarium_search": honorarium_search,
        "candidatures": candidatures_page,
        "candidature_stats": candidature_stats,
        "cand_status": cand_status,
        "cand_search": cand_search,
        "cand_activity_date": cand_activity_date_value,
        "inscriptions": inscriptions_page,
        "inscription_stats": inscription_stats,
        "ins_status": ins_status,
        "ins_search": ins_search,
        "ins_activity_date": ins_activity_date_value,
        "payments": payments_page,
        "payment_stats": payment_stats,
        "report_period": report_period,
        "report_rows": report_rows,
        "annual_revenue_rows": annual_revenue_rows,
        "annual_revenue_total": sum((row.get("total_amount") or 0) for row in annual_revenue_rows),
        "annual_revenue_current_year": current_year_revenue,
        "annual_revenue_previous_year": previous_year_revenue,
        "annual_revenue_growth": annual_revenue_growth,
        "annual_revenue_current_year_label": current_year,
        "annual_revenue_previous_year_label": current_year - 1,
        "pay_status": pay_status,
        "pay_method": pay_method,
        "pay_date": pay_date,
        "pay_search": pay_search,
        "expenses": expenses_page,
        "expense_stats": expense_stats,
        "expense_status": expense_status,
        "expense_category": expense_category,
        "expense_search": expense_search,
        "expense_form": BranchExpenseForm(),
        "expense_categories": BranchExpense.CATEGORY_CHOICES,
        "cash_movements": cash_movements_page,
        "cash_stats": cash_stats,
        "recent_financial_logs": recent_financial_logs,
        "period_summary": period_summary,
        "operational_flow": operational_flow,
        "daily_work_items": daily_work_items,
        "daily_work_pending_count": daily_work_pending_count,
        "today_activity_count": today_activity_count,
        "cash_type": cash_type,
        "cash_source": cash_source,
        "cash_search": cash_search,
        "cash_activity_date": cash_activity_date_value,
        "cash_form": BranchCashMovementForm(),
        "cash_register_session": cash_register_session,
        "cash_register_open_form": CashRegisterOpenForm(initial={"opening_amount": get_branch_cash_balance(branch)}),
        "cash_register_close_form": CashRegisterCloseForm(initial={"counted_amount": get_branch_cash_balance(branch)}),
        "wallets": wallets,
        "favorite_wallets": [wallet for wallet in wallets if wallet.is_favorite and wallet.status == BranchWallet.STATUS_ACTIVE][:4],
        "wallet_unallocated_balance": branch_unallocated_cash(branch),
        "wallet_form": BranchWalletForm(),
        "wallet_amount_form": WalletAmountForm(),
        "cash_sources": BranchCashMovement.SOURCE_CHOICES,
        "closure_form": BranchMonthlyClosureForm(initial={
            "period_month": payroll_month,
            "bank_transfer_amount": max(get_branch_cash_balance(branch) - branch.cash_reserve_target, 0),
        }),
        "available_cash_balance": get_branch_cash_balance(branch),
        "cash_reserve_target": branch.cash_reserve_target,
        "suggested_transfer_amount": max(get_branch_cash_balance(branch) - branch.cash_reserve_target, 0),
        "transfer_form": BranchBankTransferForm(initial={
            "transfer_date": today,
            "amount": 0,
        }),
        **financial_report,
        "manager_intelligence": intelligence,
        "monthly_closures": monthly_closures_page,
        "bank_transfers": bank_transfers_page,
        "donations": donations_page,
        "donation_stats": {
            "total": Donation.objects.filter(branch=branch).aggregate(total=Sum("amount"))["total"] or 0,
            "count": Donation.objects.filter(branch=branch).count(),
            "this_month": Donation.objects.filter(
                branch=branch,
                date__gte=today.replace(day=1),
            ).aggregate(total=Sum("amount"))["total"] or 0,
        },
        "donation_form": DonationForm(),
        "shop_product_form": ShopProductForm(),
        "shop_stock_form": ShopStockInForm(branch=branch),
        "shop_stock_adjustment_form": ShopStockAdjustmentForm(branch=branch),
        "shop_counter_order_form": ShopCounterOrderForm(branch=branch),
        "shop_public_identifier": get_branch_public_shop_identifier(branch),
        **shop_context,
        "manager_search": quick_search,
        "quick_results": quick_results,
        "dashboard_type": "manager",
        **reenrollment_context,
    }


def _manager_navigation_groups(context, access, *, dashboard_url="", workspace_url=""):
    groups = [
        {
            "label": "Pilotage du jour",
            "items": [
                {"key": "overview", "label": "Travail du jour", "icon": "layout-dashboard"},
            ],
        },
        {
            "label": "Parcours étudiant",
            "items": [
                {"key": "candidatures", "label": "Candidatures", "icon": "file-check", "badge": context.get("candidatures_pending") or None},
                {"key": "inscriptions", "label": "Inscriptions et échéances", "icon": "id-card", "badge": context.get("inscriptions_to_finalize") or None},
                {"key": "reenrollment", "label": "Réinscriptions", "icon": "refresh-cw", "badge": (context.get("reenrollment_metrics") or {}).get("awaiting_payment") or None},
            ],
        },
        {
            "label": "Tresorerie",
            "items": [
                {"key": "paiements", "label": "Encaissements", "icon": "credit-card", "badge": context.get("pending_payments") or None},
                {"key": "caisse", "label": "Caisse et mouvements", "icon": "vault"},
            ],
        },
        {
            "label": "Dépenses et logistique",
            "items": [
                {"key": "depenses", "label": "Dépenses", "icon": "receipt"},
                {"key": "boutique", "label": "Boutique et stock", "icon": "store"},
                {"key": "dons", "label": "Dons et appuis", "icon": "hand-heart"},
            ],
        },
        {
            "label": "Personnel et engagements",
            "items": [
                {"key": "salaires", "label": "Salaires du personnel", "icon": "user-round-cog"},
                {"key": "honoraires", "label": "Honoraires enseignants", "icon": "graduation-cap"},
            ],
        },
        {
            "label": "Contrôle, rapports et clôture",
            "items": [
                {"key": "cloture", "label": "Clôture mensuelle", "icon": "lock"},
                {"key": "rapport", "label": "Rapports et archives", "icon": "chart-no-axes-combined"},
            ],
        },
        {
            "label": "Compte",
            "items": [
                {"key": "settings", "label": "Mon compte", "icon": "user-cog"},
            ],
        },
    ]
    filtered_groups = []
    for group in groups:
        items = []
        for source in group["items"]:
            if source["key"] not in access.allowed_sections:
                continue
            item = dict(source)
            if workspace_url:
                item.update(
                    {
                        "hx_get": f"{workspace_url}?section={item['key']}",
                        "hx_target": "#manager-workspace",
                        "hx_swap": "innerHTML",
                        "hx_push_url": f"{dashboard_url}?section={item['key']}",
                        "hx_indicator": "#manager-loading",
                    }
                )
            items.append(item)
        if items:
            filtered_groups.append({"label": group["label"], "items": items})

    if workspace_url:
        # Espace personnel : messagerie interne et salaire via les endpoints
        # génériques staff, échangés dans le workspace gestionnaire.
        filtered_groups.append(
            {
                "label": "Espace personnel",
                "items": [
                    {
                        "key": "messagerie",
                        "label": "Messagerie",
                        "icon": "mail",
                        "url": dashboard_url,
                        "hx_get": f"{reverse('accounts_portal:staff_messaging')}?dash=manager",
                        "hx_target": "#manager-workspace",
                        "hx_swap": "innerHTML",
                        "hx_push_url": dashboard_url,
                        "hx_indicator": "#manager-loading",
                    },
                    {
                        "key": "mon-salaire",
                        "label": "Mon salaire",
                        "icon": "wallet",
                        "url": dashboard_url,
                        "hx_get": f"{reverse('accounts_portal:staff_salary')}?dash=manager",
                        "hx_target": "#manager-workspace",
                        "hx_swap": "innerHTML",
                        "hx_push_url": dashboard_url,
                        "hx_indicator": "#manager-loading",
                    },
                ],
            }
        )
    return filtered_groups


def _render_manager_dashboard(
    request,
    active_section,
    *,
    workspace_only=False,
    subcontent_only=False,
    forced_subview=None,
):
    access = request.manager_workspace_access
    if active_section not in access.allowed_sections:
        return render(request, "core/errors/403.html", status=403)
    context = _manager_context(request, active_section=active_section)
    branch = context["branch"]
    context["manager_workspace_access"] = access
    context["manager_capabilities"] = access.capabilities_context()
    finance_context = access.position in {"finance_manager", "payment_agent"}
    admissions_context = access.position == "admissions"
    if finance_context:
        dashboard_url = reverse("accounts_portal:portal_finance")
    elif admissions_context:
        dashboard_url = reverse("accounts_portal:portal_admissions")
    else:
        dashboard_url = reverse("accounts_portal:portal_annex_manager")
    workspace_url = reverse("accounts_portal:manager_workspace")
    subcontent_url = reverse("accounts_portal:manager_subcontent")
    requested_subview = (
        forced_subview if forced_subview is not None else request.GET.get("view")
    )
    role_default_subview = {
        "paiements": "payments" if finance_context else "to_validate",
        "candidatures": "list" if admissions_context else "to_process",
        "inscriptions": "pending",
        "reenrollment": "overview",
        "depenses": "to_approve",
        "salaires": "to_validate",
        "honoraires": "to_validate",
        "boutique": "sell",
    }.get(active_section, "overview")
    active_subview = normalize_manager_subview(
        active_section,
        requested_subview or role_default_subview,
    )
    context["manager_subview"] = active_subview
    context["manager_subcontent_url"] = subcontent_url
    context["manager_dashboard_url"] = dashboard_url
    context["manager_ui"] = build_manager_dashboard_presentation(
        active_section=active_section,
        context=context,
        capabilities=access.capabilities,
        dashboard_url=dashboard_url,
        workspace_url=workspace_url,
        subcontent_url=subcontent_url,
        active_subview=active_subview,
    )
    context["manager_subview"] = active_subview
    context.update(
        build_role_dashboard_shell(
            request,
            role=access.position,
            key="manager",
            title="Dashboard Gestionnaire",
            subtitle=(
                "Finance et encaissements"
                if finance_context
                else "Admissions et inscriptions"
                if admissions_context
                else "Gestion de l'annexe"
            ),
            active_section=active_section,
            dashboard_url=dashboard_url,
            branch=branch,
            context_label=f"Annexe - {branch.name}",
            groups=_manager_navigation_groups(
                context,
                access,
                dashboard_url=dashboard_url,
                workspace_url=workspace_url,
            ),
            workspace_target="#manager-workspace",
            modal_title="Gestion d'annexe",
            script_path="src/js/portal/manager_dashboard.js",
        )
    )
    if subcontent_only:
        if active_section not in MANAGER_SUBVIEW_DEFINITIONS:
            return render(request, "core/errors/404.html", status=404)
        response = render(
            request,
            context["manager_ui"]["subcontent_template"],
            context,
        )
        push_query = request.GET.copy()
        push_query["section"] = active_section
        push_query["view"] = active_subview
        response["HX-Push-Url"] = (
            f"{dashboard_url}?{push_query.urlencode()}"
        )
        return response
    if workspace_only:
        response = render(
            request,
            "accounts/dashboard/partials/manager_workspace.html",
            context,
        )
        response["HX-Push-Url"] = (
            f"{dashboard_url}?{urlencode({'section': active_section, 'view': active_subview})}"
        )
        return response
    return render(
        request,
        "accounts/dashboard/manager_dashboard.html",
        context,
    )


@manager_required
@require_GET
def manager_dashboard(request, default_section=None):
    access = request.manager_workspace_access
    default_section = default_section or access.default_section
    if default_section not in access.allowed_sections:
        default_section = access.default_section
    section = request.GET.get("section", default_section).strip() or default_section
    if section not in access.allowed_sections:
        section = default_section
    return _render_manager_dashboard(request, section)


@manager_required
@require_GET
def manager_workspace(request):
    """HTMX-only workspace endpoint sharing the Director dashboard contract."""

    access = request.manager_workspace_access
    default_section = access.default_section
    section = request.GET.get("section", default_section).strip() or default_section
    if section not in access.allowed_sections:
        section = default_section
    return _render_manager_dashboard(request, section, workspace_only=True)


@manager_required
@require_GET
def manager_subcontent(request):
    """HTMX subview endpoint — swaps only the domain subcontent region."""

    access = request.manager_workspace_access
    section = request.GET.get("section", "").strip()
    if section not in access.allowed_sections:
        return render(request, "core/errors/403.html", status=403)
    return _render_manager_dashboard(
        request,
        section,
        subcontent_only=True,
    )


@manager_required
@require_GET
def manager_candidatures(request):
    return _render_manager_dashboard(request, "candidatures")


@manager_required
@require_GET
def manager_inscriptions(request):
    return _render_manager_dashboard(request, "inscriptions")


@manager_required
@require_GET
def manager_paiements(request):
    return _render_manager_dashboard(request, "paiements")
