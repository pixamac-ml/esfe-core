from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.core.paginator import Paginator
from datetime import timedelta

from inscriptions.models import Inscription
from payments.models import Payment
from admissions.models import Candidature
from students.models import Student

from accounts.dashboards.helpers import get_user_branch, is_manager


def manager_required(view_func):
    """Décorateur pour vérifier l'accès gestionnaire."""

    def wrapper(request, *args, **kwargs):
        if not is_manager(request.user):
            return redirect("accounts:dashboard_redirect")
        branch = get_user_branch(request.user)
        if not branch:
            return render(request, "core/errors/403.html")
        request.branch = branch
        return view_func(request, *args, **kwargs)

    return login_required(wrapper)


@manager_required
def manager_dashboard(request):
    """Dashboard principal."""
    branch = request.branch
    today = timezone.now().date()
    start_of_week = today - timedelta(days=today.weekday())
    start_of_month = today.replace(day=1)

    # Inscriptions
    inscriptions = (
        Inscription.objects
        .filter(candidature__branch=branch)
        .select_related(
            "candidature",
            "candidature__programme",
            "candidature__programme__cycle",
        )
        .order_by("-created_at")[:10]
    )

    total_inscriptions = Inscription.objects.filter(candidature__branch=branch).count()
    inscriptions_this_month = Inscription.objects.filter(
        candidature__branch=branch,
        created_at__date__gte=start_of_month
    ).count()
    inscriptions_active = Inscription.objects.filter(
        candidature__branch=branch,
        status=Inscription.STATUS_ACTIVE
    ).count()

    # Candidatures
    candidatures_pending = Candidature.objects.filter(
        branch=branch,
        status__in=["submitted", "under_review"],
        is_deleted=False
    ).count()

    candidatures_to_complete = Candidature.objects.filter(
        branch=branch,
        status="to_complete",
        is_deleted=False
    ).count()

    candidatures_accepted = Candidature.objects.filter(
        branch=branch,
        status__in=["accepted", "accepted_with_reserve"],
        is_deleted=False
    ).count()

    recent_candidatures = (
        Candidature.objects
        .filter(branch=branch, is_deleted=False)
        .select_related("programme", "programme__cycle")
        .order_by("-submitted_at")[:5]
    )

    # Étudiants
    total_students = Student.objects.filter(
        inscription__candidature__branch=branch,
        is_active=True
    ).count()

    # Paiements
    payments_today = (
        Payment.objects
        .filter(
            inscription__candidature__branch=branch,
            created_at__date=today
        )
        .select_related(
            "inscription__candidature",
            "inscription__candidature__programme",
        )
        .order_by("-created_at")
    )

    recent_payments = (
        Payment.objects
        .filter(inscription__candidature__branch=branch)
        .select_related(
            "inscription__candidature",
            "inscription__candidature__programme",
        )
        .order_by("-created_at")[:5]
    )

    # Stats financières
    total_today = Payment.objects.filter(
        inscription__candidature__branch=branch,
        status=Payment.STATUS_VALIDATED,
        created_at__date=today
    ).aggregate(total=Sum("amount"))["total"] or 0

    validated_today_count = Payment.objects.filter(
        inscription__candidature__branch=branch,
        status=Payment.STATUS_VALIDATED,
        created_at__date=today
    ).count()

    total_week = Payment.objects.filter(
        inscription__candidature__branch=branch,
        status=Payment.STATUS_VALIDATED,
        created_at__date__gte=start_of_week
    ).aggregate(total=Sum("amount"))["total"] or 0

    total_month = Payment.objects.filter(
        inscription__candidature__branch=branch,
        status=Payment.STATUS_VALIDATED,
        created_at__date__gte=start_of_month
    ).aggregate(total=Sum("amount"))["total"] or 0

    pending_payments = Payment.objects.filter(
        inscription__candidature__branch=branch,
        status=Payment.STATUS_PENDING
    ).count()

    pending_payments_amount = Payment.objects.filter(
        inscription__candidature__branch=branch,
        status=Payment.STATUS_PENDING
    ).aggregate(total=Sum("amount"))["total"] or 0

    inscriptions_with_balance = Inscription.objects.filter(
        candidature__branch=branch,
        status__in=[Inscription.STATUS_PARTIAL, Inscription.STATUS_AWAITING_PAYMENT]
    ).count()

    context = {
        "inscriptions": inscriptions,
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
        "branch": branch,
        "today": today,
        "active_page": "dashboard",
    }

    return render(request, "accounts/dashboard/manager_dashboard.html", context)


@manager_required
def manager_candidatures(request):
    """Liste des candidatures avec filtres."""
    branch = request.branch

    # Filtres
    status_filter = request.GET.get("status", "")
    search = request.GET.get("q", "")

    candidatures = (
        Candidature.objects
        .filter(branch=branch, is_deleted=False)
        .select_related("programme", "programme__cycle")
        .order_by("-submitted_at")
    )

    if status_filter:
        candidatures = candidatures.filter(status=status_filter)

    if search:
        candidatures = candidatures.filter(
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(email__icontains=search)
        )

    # Pagination
    paginator = Paginator(candidatures, 20)
    page = request.GET.get("page", 1)
    candidatures = paginator.get_page(page)

    # Stats
    stats = {
        "total": Candidature.objects.filter(branch=branch, is_deleted=False).count(),
        "submitted": Candidature.objects.filter(branch=branch, status="submitted", is_deleted=False).count(),
        "under_review": Candidature.objects.filter(branch=branch, status="under_review", is_deleted=False).count(),
        "to_complete": Candidature.objects.filter(branch=branch, status="to_complete", is_deleted=False).count(),
        "accepted": Candidature.objects.filter(branch=branch, status__in=["accepted", "accepted_with_reserve"],
                                               is_deleted=False).count(),
        "rejected": Candidature.objects.filter(branch=branch, status="rejected", is_deleted=False).count(),
    }

    context = {
        "candidatures": candidatures,
        "stats": stats,
        "status_filter": status_filter,
        "search": search,
        "branch": branch,
        "active_page": "candidatures",
    }

    return render(request, "accounts/dashboard/manager_candidatures.html", context)


@manager_required
def manager_inscriptions(request):
    """Liste des inscriptions avec filtres."""
    branch = request.branch

    # Filtres
    status_filter = request.GET.get("status", "")
    search = request.GET.get("q", "")

    inscriptions = (
        Inscription.objects
        .filter(candidature__branch=branch)
        .select_related(
            "candidature",
            "candidature__programme",
            "candidature__programme__cycle",
        )
        .order_by("-created_at")
    )

    if status_filter:
        inscriptions = inscriptions.filter(status=status_filter)

    if search:
        inscriptions = inscriptions.filter(
            Q(candidature__first_name__icontains=search) |
            Q(candidature__last_name__icontains=search) |
            Q(candidature__email__icontains=search) |
            Q(public_token__icontains=search)
        )

    # Pagination
    paginator = Paginator(inscriptions, 20)
    page = request.GET.get("page", 1)
    inscriptions = paginator.get_page(page)

    # Stats
    stats = {
        "total": Inscription.objects.filter(candidature__branch=branch).count(),
        "active": Inscription.objects.filter(candidature__branch=branch, status=Inscription.STATUS_ACTIVE).count(),
        "partial": Inscription.objects.filter(candidature__branch=branch, status=Inscription.STATUS_PARTIAL).count(),
        "awaiting": Inscription.objects.filter(candidature__branch=branch,
                                               status=Inscription.STATUS_AWAITING_PAYMENT).count(),
        "created": Inscription.objects.filter(candidature__branch=branch, status=Inscription.STATUS_CREATED).count(),
    }

    context = {
        "inscriptions": inscriptions,
        "stats": stats,
        "status_filter": status_filter,
        "search": search,
        "branch": branch,
        "active_page": "inscriptions",
    }

    return render(request, "accounts/dashboard/manager_inscriptions.html", context)


@manager_required
def manager_paiements(request):
    """Liste des paiements avec filtres."""
    branch = request.branch
    today = timezone.now().date()

    # Filtres
    status_filter = request.GET.get("status", "")
    date_filter = request.GET.get("date", "")
    search = request.GET.get("q", "")

    payments = (
        Payment.objects
        .filter(inscription__candidature__branch=branch)
        .select_related(
            "inscription__candidature",
            "inscription__candidature__programme",
            "agent__user",
        )
        .order_by("-created_at")
    )

    if status_filter:
        payments = payments.filter(status=status_filter)

    if date_filter == "today":
        payments = payments.filter(created_at__date=today)
    elif date_filter == "week":
        start_of_week = today - timedelta(days=today.weekday())
        payments = payments.filter(created_at__date__gte=start_of_week)
    elif date_filter == "month":
        start_of_month = today.replace(day=1)
        payments = payments.filter(created_at__date__gte=start_of_month)

    if search:
        payments = payments.filter(
            Q(reference__icontains=search) |
            Q(inscription__candidature__first_name__icontains=search) |
            Q(inscription__candidature__last_name__icontains=search)
        )

    # Pagination
    paginator = Paginator(payments, 20)
    page = request.GET.get("page", 1)
    payments = paginator.get_page(page)

    # Stats
    stats = {
        "total": Payment.objects.filter(inscription__candidature__branch=branch).count(),
        "validated": Payment.objects.filter(inscription__candidature__branch=branch,
                                            status=Payment.STATUS_VALIDATED).count(),
        "pending": Payment.objects.filter(inscription__candidature__branch=branch,
                                          status=Payment.STATUS_PENDING).count(),
        "cancelled": Payment.objects.filter(inscription__candidature__branch=branch,
                                            status=Payment.STATUS_CANCELLED).count(),
        "total_amount": Payment.objects.filter(
            inscription__candidature__branch=branch,
            status=Payment.STATUS_VALIDATED
        ).aggregate(total=Sum("amount"))["total"] or 0,
    }

    context = {
        "payments": payments,
        "stats": stats,
        "status_filter": status_filter,
        "date_filter": date_filter,
        "search": search,
        "branch": branch,
        "active_page": "paiements",
    }

    return render(request, "accounts/dashboard/manager_paiements.html", context)