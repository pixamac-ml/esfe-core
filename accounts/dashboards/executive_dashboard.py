# accounts/dashboards/executive_dashboard.py

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Count, Q
from django.utils import timezone
from datetime import timedelta

from students.models import Student
from admissions.models import Candidature
from inscriptions.models import Inscription
from payments.models import Payment, PaymentAgent
from branches.models import Branch
from formations.models import Programme

from .permissions import check_executive_access


@login_required
def executive_dashboard(request):

    user = request.user

    if not check_executive_access(user):
        messages.error(request, "Accès refusé.")
        return redirect("core:home")

    today = timezone.now().date()
    week = today - timedelta(days=7)
    month = today - timedelta(days=30)

    # =====================================================
    # STATISTIQUES GLOBALES
    # =====================================================

    total_students = Student.objects.filter(
        is_active=True
    ).count()

    total_candidatures = Candidature.objects.count()

    total_inscriptions = Inscription.objects.count()

    total_revenue = (
        Payment.objects
        .filter(status="validated")
        .aggregate(total=Sum("amount"))["total"]
        or 0
    )

    # =====================================================
    # INDICATEURS TEMPORELS
    # =====================================================

    revenue_today = (
        Payment.objects
        .filter(
            status="validated",
            paid_at__date=today
        )
        .aggregate(total=Sum("amount"))["total"]
        or 0
    )

    revenue_week = (
        Payment.objects
        .filter(
            status="validated",
            paid_at__date__gte=week
        )
        .aggregate(total=Sum("amount"))["total"]
        or 0
    )

    revenue_month = (
        Payment.objects
        .filter(
            status="validated",
            paid_at__date__gte=month
        )
        .aggregate(total=Sum("amount"))["total"]
        or 0
    )

    # =====================================================
    # TAUX DE CONVERSION
    # =====================================================

    accepted_candidatures = Candidature.objects.filter(
        status="accepted"
    ).count()

    conversion_rate = 0
    if total_candidatures > 0:
        conversion_rate = round(
            (accepted_candidatures / total_candidatures) * 100, 1
        )

    # =====================================================
    # ADMISSIONS STATS
    # =====================================================

    admissions_stats = Candidature.objects.aggregate(

        submitted=Count("id", filter=Q(status="submitted")),

        reviewing=Count("id", filter=Q(status="under_review")),

        accepted=Count("id", filter=Q(status="accepted")),

        rejected=Count("id", filter=Q(status="rejected")),

    )

    # =====================================================
    # STATISTIQUES PAR ANNEXE (ENRICHIES)
    # =====================================================

    branches = Branch.objects.filter(is_active=True)

    branch_stats = []

    for branch in branches:

        # Revenus totaux
        revenue = (
            Payment.objects
            .filter(
                inscription__candidature__branch=branch,
                status="validated"
            )
            .aggregate(total=Sum("amount"))["total"]
            or 0
        )

        # Revenus du mois
        monthly_revenue = (
            Payment.objects
            .filter(
                inscription__candidature__branch=branch,
                status="validated",
                paid_at__date__gte=month
            )
            .aggregate(total=Sum("amount"))["total"]
            or 0
        )

        # Nombre d'étudiants actifs
        students_count = Student.objects.filter(
            inscription__candidature__branch=branch,
            is_active=True
        ).count()

        # Total candidatures
        candidatures_count = Candidature.objects.filter(
            branch=branch
        ).count()

        # Candidatures acceptées
        accepted_count = Candidature.objects.filter(
            branch=branch,
            status="accepted"
        ).count()

        # Inscriptions
        inscriptions_count = Inscription.objects.filter(
            candidature__branch=branch
        ).count()

        # Agents de paiement
        agents_count = PaymentAgent.objects.filter(
            branch=branch,
            is_active=True
        ).count()

        branch_stats.append({

            "branch": branch,

            "revenue": revenue,
            "monthly_revenue": monthly_revenue,

            "students": students_count,

            "candidatures": candidatures_count,
            "accepted": accepted_count,

            "inscriptions": inscriptions_count,

            "agents": agents_count,

        })

    # Tri par revenus
    branch_stats = sorted(
        branch_stats,
        key=lambda x: x["revenue"],
        reverse=True
    )

    # =====================================================
    # TOP AGENTS
    # =====================================================

    agent_ranking = (
        PaymentAgent.objects
        .filter(is_active=True)
        .select_related("user", "branch")
        .annotate(
            total_collected=Sum(
                "payments__amount",
                filter=Q(payments__status="validated")
            ),
            monthly_collected=Sum(
                "payments__amount",
                filter=Q(
                    payments__status="validated",
                    payments__paid_at__date__gte=month
                )
            ),
        )
        .order_by("-total_collected")
        [:10]
    )

    # =====================================================
    # TOP PROGRAMMES
    # =====================================================

    programmes_popularity = (
        Inscription.objects
        .values("candidature__programme__title")
        .annotate(count=Count("id"))
        .order_by("-count")
        [:10]
    )

    # =====================================================
    # INSCRIPTIONS RÉCENTES
    # =====================================================

    recent_inscriptions = (
        Inscription.objects
        .select_related(
            "candidature",
            "candidature__programme",
            "candidature__branch"
        )
        .order_by("-created_at")
        [:10]
    )

    # =====================================================
    # PAIEMENTS RÉCENTS
    # =====================================================

    recent_payments = (
        Payment.objects
        .filter(status="validated")
        .select_related(
            "inscription",
            "inscription__candidature",
        )
        .order_by("-paid_at")
        [:10]
    )

    # =====================================================
    # CONTEXTE
    # =====================================================

    context = {

        "total_students": total_students,

        "total_candidatures": total_candidatures,

        "total_inscriptions": total_inscriptions,

        "total_revenue": total_revenue,

        "revenue_today": revenue_today,
        "revenue_week": revenue_week,
        "revenue_month": revenue_month,

        "conversion_rate": conversion_rate,

        "admissions_stats": admissions_stats,

        "branch_stats": branch_stats,

        "agent_ranking": agent_ranking,

        "programmes_popularity": programmes_popularity,

        "recent_inscriptions": recent_inscriptions,

        "recent_payments": recent_payments,

        "dashboard_type": "executive"

    }

    return render(
        request,
        "accounts/dashboard/executive.html",
        context
    )