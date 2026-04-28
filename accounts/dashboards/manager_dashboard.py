from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, F, Q, Sum
from django.shortcuts import redirect, render
from django.utils import timezone

from admissions.models import Candidature
from accounts.forms import BranchCashMovementForm, BranchExpenseForm
from accounts.models import BranchCashMovement, BranchExpense, PayrollEntry, Profile
from accounts.services.manager_intelligence import build_manager_intelligence_context
from inscriptions.models import Inscription
from payments.models import CashPaymentSession, Payment, PaymentAgent
from students.models import Student

from accounts.dashboards.helpers import get_user_branch, is_manager


PAYABLE_INSCRIPTION_STATUSES = {
    Inscription.STATUS_CREATED,
    Inscription.STATUS_AWAITING_PAYMENT,
    Inscription.STATUS_PARTIAL,
}


def manager_required(view_func):
    """Verifie l'acces gestionnaire et injecte l'annexe dans la requete."""

    def wrapper(request, *args, **kwargs):
        if not is_manager(request.user):
            return redirect("accounts:dashboard_redirect")
        branch = get_user_branch(request.user)
        if not branch:
            return render(request, "core/errors/403.html")
        request.branch = branch
        return view_func(request, *args, **kwargs)

    return login_required(wrapper)


def _paginate(request, queryset, *, param_name, per_page=20):
    paginator = Paginator(queryset, per_page)
    return paginator.get_page(request.GET.get(param_name, 1))


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
    branch_staff_user_ids = list(branch_staff_profiles.values_list("user_id", flat=True))
    manager_agent = _get_manager_agent(request.user, branch)
    active_cash_sessions = []
    if manager_agent:
        active_cash_sessions = list(
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
            .order_by("-created_at")[:10]
        )
    active_cash_sessions_by_inscription = {
        session.inscription_id: session for session in active_cash_sessions
    }

    overview_inscriptions = (
        base_inscriptions
        .select_related(
            "candidature",
            "candidature__programme",
            "candidature__programme__cycle",
        )
        .order_by("-created_at")[:10]
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
    candidatures_qs = (
        base_candidatures
        .select_related("programme", "programme__cycle")
        .order_by("-submitted_at")
    )
    if cand_status:
        if cand_status == "accepted":
            candidatures_qs = candidatures_qs.filter(status__in=["accepted", "accepted_with_reserve"])
        else:
            candidatures_qs = candidatures_qs.filter(status=cand_status)
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
        inscriptions_qs = inscriptions_qs.filter(status=ins_status)
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
        .order_by("-created_at")[:20]
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
    expenses_page = _paginate(request, expenses_qs, param_name="expense_page", per_page=15)
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
    cash_movements_qs = BranchCashMovement.objects.filter(branch=branch).select_related("expense", "created_by")
    if cash_type:
        cash_movements_qs = cash_movements_qs.filter(movement_type=cash_type)
    if cash_source:
        cash_movements_qs = cash_movements_qs.filter(source=cash_source)
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
        per_page=15,
    )
    cash_month_movements = BranchCashMovement.objects.filter(branch=branch, movement_date__gte=start_of_month)
    cash_in_month = cash_month_movements.filter(movement_type=BranchCashMovement.TYPE_IN).aggregate(total=Sum("amount"))["total"] or 0
    cash_out_month = cash_month_movements.filter(movement_type=BranchCashMovement.TYPE_OUT).aggregate(total=Sum("amount"))["total"] or 0
    salary_paid_month = PayrollEntry.objects.filter(
        branch=branch,
        period_month=start_of_month,
    ).aggregate(total=Sum("paid_amount"))["total"] or 0
    cash_stats = {
        "movements": BranchCashMovement.objects.filter(branch=branch).count(),
        "in_month": cash_in_month,
        "out_month": cash_out_month,
        "net_month": cash_in_month - cash_out_month,
        "estimated_month_balance": cash_in_month - cash_out_month,
        "student_receipts_month": total_month,
        "expenses_paid_month": expense_stats["paid_month_amount"],
        "salary_paid_month": salary_paid_month,
    }

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
    staff_profiles_filtered = branch_staff_profiles
    if salary_status:
        if salary_status == "missing":
            staff_profiles_filtered = [
                profile for profile in staff_profiles_filtered
                if profile.user_id not in payroll_entries_by_employee
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
        per_page=15,
    )
    payroll_total_due = sum(entry.net_salary for entry in payroll_entries_qs)
    payroll_total_paid = sum(entry.paid_amount for entry in payroll_entries_qs)
    payroll_remaining = max(payroll_total_due - payroll_total_paid, 0)
    payroll_stats = {
        "employees": len(branch_staff_user_ids),
        "prepared": payroll_entries_qs.count(),
        "paid": sum(1 for entry in payroll_entries_qs if entry.status == PayrollEntry.STATUS_PAID),
        "partial": sum(1 for entry in payroll_entries_qs if entry.status == PayrollEntry.STATUS_PARTIAL),
        "ready": sum(1 for entry in payroll_entries_qs if entry.status == PayrollEntry.STATUS_READY),
        "due_total": payroll_total_due,
        "paid_total": payroll_total_paid,
        "remaining_total": payroll_remaining,
    }
    intelligence = build_manager_intelligence_context(
        branch=branch,
        payroll_month=payroll_month,
        base_payments=base_payments,
        base_inscriptions=base_inscriptions,
        payroll_stats=payroll_stats,
        expense_stats=expense_stats,
        cash_stats=cash_stats,
        branch_staff_user_ids=branch_staff_user_ids,
    )

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
        "active_cash_sessions_count": len(active_cash_sessions),
        "payable_inscriptions": payable_inscriptions,
        "payroll_month": payroll_month,
        "salary_month_value": payroll_month.strftime("%Y-%m"),
        "payroll_entries": payroll_entries_page,
        "payroll_stats": payroll_stats,
        "salary_status": salary_status,
        "salary_search": salary_search,
        "candidatures": candidatures_page,
        "candidature_stats": candidature_stats,
        "cand_status": cand_status,
        "cand_search": cand_search,
        "inscriptions": inscriptions_page,
        "inscription_stats": inscription_stats,
        "ins_status": ins_status,
        "ins_search": ins_search,
        "payments": payments_page,
        "payment_stats": payment_stats,
        "pay_status": pay_status,
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
        "cash_type": cash_type,
        "cash_source": cash_source,
        "cash_search": cash_search,
        "cash_form": BranchCashMovementForm(),
        "cash_sources": BranchCashMovement.SOURCE_CHOICES,
        "manager_intelligence": intelligence,
        "manager_search": quick_search,
        "quick_results": quick_results,
        "dashboard_type": "manager",
    }


def _render_manager_dashboard(request, active_section):
    return render(
        request,
        "accounts/dashboard/manager_dashboard.html",
        _manager_context(request, active_section=active_section),
    )


@manager_required
def manager_dashboard(request):
    section = request.GET.get("section", "overview").strip() or "overview"
    allowed_sections = {"overview", "candidatures", "inscriptions", "paiements", "salaires", "depenses", "caisse"}
    if section not in allowed_sections:
        section = "overview"
    return _render_manager_dashboard(request, section)


@manager_required
def manager_candidatures(request):
    return _render_manager_dashboard(request, "candidatures")


@manager_required
def manager_inscriptions(request):
    return _render_manager_dashboard(request, "inscriptions")


@manager_required
def manager_paiements(request):
    return _render_manager_dashboard(request, "paiements")
