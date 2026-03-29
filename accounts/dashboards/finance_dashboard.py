# accounts/dashboards/finance_dashboard.py

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.core.paginator import Paginator
from datetime import timedelta

from payments.models import Payment, CashPaymentSession, PaymentAgent
from inscriptions.models import Inscription

from .permissions import check_finance_access, is_global_viewer
from .helpers import get_user_branch
from .querysets import get_base_queryset


@login_required
def finance_dashboard(request):

    user = request.user

    if not check_finance_access(user):
        messages.error(request, "Accès refusé.")
        return redirect("core:home")

    branch = get_user_branch(user)
    is_global = is_global_viewer(user)

    # =====================================================
    # QUERYSETS OPTIMISÉS
    # =====================================================

    payments = (
        get_base_queryset(user, "payment")
        .select_related(
            "inscription",
            "inscription__candidature",
            "agent",
        )
    )

    inscriptions = (
        get_base_queryset(user, "inscription")
        .select_related(
            "candidature",
            "candidature__programme",
            "candidature__branch",
        )
    )

    # =====================================================
    # FILTRES
    # =====================================================

    method = request.GET.get("method")
    status = request.GET.get("status")
    search = request.GET.get("q")

    if method:
        payments = payments.filter(method=method)

    if status:
        payments = payments.filter(status=status)

    if search:
        payments = payments.filter(
            Q(reference__icontains=search)
            | Q(inscription__public_token__icontains=search)
            | Q(inscription__candidature__last_name__icontains=search)
            | Q(inscription__candidature__first_name__icontains=search)
        )

    # =====================================================
    # STATS JOUR
    # =====================================================

    today = timezone.now().date()

    today_payments = payments.filter(
        paid_at__date=today,
        status="validated"
    )

    stats_today = today_payments.aggregate(
        total=Sum("amount"),
        count=Count("id")
    )

    # =====================================================
    # STATS SEMAINE
    # =====================================================

    week = today - timedelta(days=7)

    stats_week = payments.filter(
        paid_at__date__gte=week,
        status="validated"
    ).aggregate(
        total=Sum("amount"),
        count=Count("id")
    )

    # =====================================================
    # STATS GLOBALES
    # =====================================================

    stats_global = payments.filter(
        status="validated"
    ).aggregate(
        total=Sum("amount"),
        count=Count("id")
    )

    # =====================================================
    # PAIEMENTS EN ATTENTE
    # =====================================================

    pending_payments = (
        payments
        .filter(status="pending")
        .order_by("-created_at")[:20]
    )

    # =====================================================
    # INSCRIPTIONS À PAYER
    # =====================================================

    inscriptions_pending = (
        inscriptions
        .filter(
            Q(status="created") |
            Q(status="awaiting_payment") |
            Q(status="partial_paid")
        )
        .order_by("-created_at")[:20]
    )

    # =====================================================
    # AGENT CONNECTÉ
    # =====================================================

    try:
        agent = PaymentAgent.objects.get(user=user)
    except PaymentAgent.DoesNotExist:
        agent = None

    # =====================================================
    # SESSIONS CASH
    # =====================================================

    sessions = []

    if agent:

        sessions = (
            CashPaymentSession.objects
            .filter(
                agent=agent,
                is_used=False,
                expires_at__gt=timezone.now(),
            )
            .order_by("-created_at")[:10]
        )

    # =====================================================
    # TRI
    # =====================================================

    order = request.GET.get("order")

    if order == "amount":

        payments = payments.order_by("-amount")

    elif order == "oldest":

        payments = payments.order_by("paid_at")

    else:

        payments = payments.order_by("-paid_at")

    # =====================================================
    # PAGINATION
    # =====================================================

    paginator = Paginator(payments, 25)

    page = request.GET.get("page")

    payments_page = paginator.get_page(page)

    # =====================================================
    # CONTEXTE
    # =====================================================

    context = {

        "stats_today": stats_today,
        "stats_week": stats_week,
        "stats_global": stats_global,

        "pending_payments": pending_payments,
        "inscriptions_pending": inscriptions_pending,

        "payments": payments_page,

        "sessions": sessions,

        "branch": branch,
        "is_global": is_global,

        "dashboard_type": "finance"

    }

    return render(
        request,
        "accounts/dashboard/finance.html",
        context
    )