# accounts/dashboards/exports.py

"""
Fonctions d'export CSV pour les dashboards.

- Export candidatures
- Export paiements
- Export rapport exécutif
"""

import csv
from datetime import timedelta

from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import redirect
from django.utils import timezone
from django.db.models import Sum, Count

from admissions.models import Candidature
from inscriptions.models import Inscription
from payments.models import Payment, PaymentAgent, CashPaymentSession
from branches.models import Branch

from .permissions import (
    check_admissions_access,
    check_finance_access,
    check_executive_access,
)
from .querysets import get_base_queryset


# ==========================================================
# EXPORT CANDIDATURES CSV
# ==========================================================

@login_required
def export_candidatures_csv(request):
    """
    Exporte les candidatures en CSV.
    """

    user = request.user

    if not check_admissions_access(user):
        messages.error(request, "Accès refusé.")
        return redirect("accounts:admissions_dashboard")

    # Récupération des candidatures accessibles
    candidatures = (
        get_base_queryset(user, "candidature")
        .filter(is_deleted=False)
        .select_related("programme", "branch")
        .order_by("-created_at")
    )

    # Filtres depuis GET
    status = request.GET.get("status")
    programme_id = request.GET.get("programme")

    if status:
        candidatures = candidatures.filter(status=status)

    if programme_id:
        candidatures = candidatures.filter(programme_id=programme_id)

    # Création de la réponse CSV
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="candidatures_{timezone.now().strftime("%Y%m%d_%H%M")}.csv"'
    )
    response.write("\ufeff")  # BOM pour Excel

    writer = csv.writer(response, delimiter=";")

    # En-têtes
    writer.writerow([
        "Référence",
        "Nom",
        "Prénom",
        "Email",
        "Téléphone",
        "Programme",
        "Annexe",
        "Statut",
        "Date de soumission",
        "Date de révision",
        "Révisé par",
    ])

    # Données
    status_labels = {
        "draft": "Brouillon",
        "submitted": "Soumise",
        "under_review": "En révision",
        "to_complete": "À compléter",
        "accepted": "Acceptée",
        "rejected": "Rejetée",
    }

    for c in candidatures:
        writer.writerow([
            c.reference,
            c.last_name,
            c.first_name,
            c.email,
            c.phone or "",
            c.programme.title if c.programme else "",
            c.branch.name if c.branch else "",
            status_labels.get(c.status, c.status),
            c.created_at.strftime("%d/%m/%Y %H:%M") if c.created_at else "",
            c.reviewed_at.strftime("%d/%m/%Y %H:%M") if c.reviewed_at else "",
            c.reviewed_by.get_full_name() if c.reviewed_by else "",
        ])

    return response


# ==========================================================
# EXPORT PAIEMENTS CSV
# ==========================================================

@login_required
def export_payments_csv(request):
    """
    Exporte les paiements en CSV.
    """

    user = request.user

    if not check_finance_access(user):
        messages.error(request, "Accès refusé.")
        return redirect("accounts:finance_dashboard")

    # Récupération des paiements accessibles
    payments = (
        get_base_queryset(user, "payment")
        .select_related(
            "inscription",
            "inscription__candidature",
            "inscription__candidature__programme",
            "inscription__candidature__branch",
            "agent",
            "validated_by",
        )
        .order_by("-created_at")
    )

    # Filtres depuis GET
    status = request.GET.get("status")
    method = request.GET.get("method")
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")

    if status:
        payments = payments.filter(status=status)

    if method:
        payments = payments.filter(method=method)

    if date_from:
        payments = payments.filter(paid_at__date__gte=date_from)

    if date_to:
        payments = payments.filter(paid_at__date__lte=date_to)

    # Création de la réponse CSV
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="paiements_{timezone.now().strftime("%Y%m%d_%H%M")}.csv"'
    )
    response.write("\ufeff")  # BOM pour Excel

    writer = csv.writer(response, delimiter=";")

    # En-têtes
    writer.writerow([
        "Référence",
        "Montant (FCFA)",
        "Méthode",
        "Statut",
        "Inscription",
        "Étudiant",
        "Programme",
        "Annexe",
        "Agent",
        "Date paiement",
        "Validé par",
    ])

    # Labels
    method_labels = {
        "cash": "Espèces",
        "orange_money": "Orange Money",
        "bank_transfer": "Virement bancaire",
    }

    status_labels = {
        "pending": "En attente",
        "validated": "Validé",
        "cancelled": "Annulé",
    }

    # Données
    for p in payments:
        candidature = p.inscription.candidature if p.inscription else None

        writer.writerow([
            p.reference,
            p.amount,
            method_labels.get(p.method, p.method),
            status_labels.get(p.status, p.status),
            p.inscription.public_token if p.inscription else "",
            candidature.full_name if candidature else "",
            candidature.programme.title if candidature and candidature.programme else "",
            candidature.branch.name if candidature and candidature.branch else "",
            p.agent.user.get_full_name() if p.agent else "",
            p.paid_at.strftime("%d/%m/%Y %H:%M") if p.paid_at else "",
            p.validated_by.get_full_name() if p.validated_by else "",
        ])

    return response


# ==========================================================
# EXPORT RAPPORT EXÉCUTIF CSV
# ==========================================================

@login_required
def export_executive_csv(request):
    """
    Exporte le rapport exécutif complet en CSV.
    """

    user = request.user

    if not check_executive_access(user):
        messages.error(request, "Accès refusé.")
        return redirect("accounts:executive_dashboard")

    # Création de la réponse CSV
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="rapport_executif_{timezone.now().strftime("%Y%m%d_%H%M")}.csv"'
    )
    response.write("\ufeff")  # BOM pour Excel

    writer = csv.writer(response, delimiter=";")

    # Dates
    today = timezone.now().date()
    month_start = today.replace(day=1)
    month_start_dt = timezone.make_aware(
        timezone.datetime.combine(month_start, timezone.datetime.min.time())
    )

    # ========================================
    # SECTION 1: RÉSUMÉ GLOBAL
    # ========================================
    writer.writerow(["=== RÉSUMÉ GLOBAL ==="])
    writer.writerow(["Métrique", "Valeur"])

    total_candidatures = Candidature.objects.filter(is_deleted=False).count()
    total_inscriptions = Inscription.objects.count()
    total_revenue = (
        Payment.objects
        .filter(status="validated")
        .aggregate(total=Sum("amount"))["total"] or 0
    )
    monthly_revenue = (
        Payment.objects
        .filter(status="validated", paid_at__gte=month_start_dt)
        .aggregate(total=Sum("amount"))["total"] or 0
    )

    conversion_rate = 0
    if total_candidatures > 0:
        conversion_rate = round((total_inscriptions / total_candidatures * 100), 1)

    writer.writerow(["Total Candidatures", total_candidatures])
    writer.writerow(["Total Inscriptions", total_inscriptions])
    writer.writerow(["Revenus Totaux (FCFA)", total_revenue])
    writer.writerow(["Revenus du Mois (FCFA)", monthly_revenue])
    writer.writerow(["Taux de Conversion (%)", conversion_rate])
    writer.writerow([])

    # ========================================
    # SECTION 2: PERFORMANCE PAR ANNEXE
    # ========================================
    writer.writerow(["=== PERFORMANCE PAR ANNEXE ==="])
    writer.writerow([
        "Annexe",
        "Code",
        "Candidatures",
        "Acceptées",
        "Inscriptions",
        "Agents",
        "Revenus Total (FCFA)",
        "Revenus Mois (FCFA)"
    ])

    branches = Branch.objects.filter(is_active=True)

    for branch in branches:

        branch_candidatures = Candidature.objects.filter(
            branch=branch,
            is_deleted=False
        )
        candidatures_count = branch_candidatures.count()
        candidatures_accepted = branch_candidatures.filter(status="accepted").count()

        inscriptions_count = Inscription.objects.filter(
            candidature__branch=branch
        ).count()

        agents_count = PaymentAgent.objects.filter(
            branch=branch,
            is_active=True
        ).count()

        branch_revenue = (
            Payment.objects
            .filter(
                status="validated",
                inscription__candidature__branch=branch
            )
            .aggregate(total=Sum("amount"))["total"] or 0
        )

        branch_monthly = (
            Payment.objects
            .filter(
                status="validated",
                inscription__candidature__branch=branch,
                paid_at__gte=month_start_dt
            )
            .aggregate(total=Sum("amount"))["total"] or 0
        )

        writer.writerow([
            branch.name,
            branch.code,
            candidatures_count,
            candidatures_accepted,
            inscriptions_count,
            agents_count,
            branch_revenue,
            branch_monthly
        ])

    writer.writerow([])

    # ========================================
    # SECTION 3: TOP AGENTS
    # ========================================
    writer.writerow(["=== TOP 10 AGENTS ==="])
    writer.writerow([
        "Rang",
        "Agent",
        "Code",
        "Annexe",
        "Sessions Total",
        "Revenus Total (FCFA)",
        "Revenus Mois (FCFA)"
    ])

    all_agents = (
        PaymentAgent.objects
        .filter(is_active=True)
        .select_related("user", "branch")
    )

    agent_ranking = []

    for agent in all_agents:

        session_ids = (
            CashPaymentSession.objects
            .filter(agent=agent, is_used=True)
            .values_list("inscription_id", flat=True)
        )

        agent_revenue = (
            Payment.objects
            .filter(inscription_id__in=session_ids, status="validated")
            .aggregate(total=Sum("amount"))["total"] or 0
        )

        agent_monthly = (
            Payment.objects
            .filter(
                inscription_id__in=session_ids,
                status="validated",
                paid_at__gte=month_start_dt
            )
            .aggregate(total=Sum("amount"))["total"] or 0
        )

        sessions_total = (
            CashPaymentSession.objects
            .filter(agent=agent, is_used=True)
            .count()
        )

        agent_ranking.append({
            "agent": agent,
            "revenue": agent_revenue,
            "monthly": agent_monthly,
            "sessions": sessions_total
        })

    # Tri par revenus décroissants
    agent_ranking.sort(key=lambda x: x["revenue"], reverse=True)

    for i, item in enumerate(agent_ranking[:10], 1):
        agent = item["agent"]
        writer.writerow([
            i,
            agent.user.get_full_name() or agent.user.username,
            agent.agent_code,
            agent.branch.name if agent.branch else "Non assigné",
            item["sessions"],
            item["revenue"],
            item["monthly"]
        ])

    writer.writerow([])

    # ========================================
    # SECTION 4: TOP PROGRAMMES
    # ========================================
    writer.writerow(["=== TOP PROGRAMMES ==="])
    writer.writerow(["Rang", "Programme", "Inscriptions", "Revenus (FCFA)"])

    programmes_stats = (
        Inscription.objects
        .values("candidature__programme__title")
        .annotate(
            count=Count("id"),
            revenue=Sum("amount_paid")
        )
        .order_by("-count")[:10]
    )

    for i, prog in enumerate(programmes_stats, 1):
        writer.writerow([
            i,
            prog["candidature__programme__title"],
            prog["count"],
            prog["revenue"] or 0
        ])

    writer.writerow([])

    # ========================================
    # SECTION 5: STATISTIQUES PAR STATUT
    # ========================================
    writer.writerow(["=== CANDIDATURES PAR STATUT ==="])
    writer.writerow(["Statut", "Nombre", "Pourcentage"])

    status_stats = (
        Candidature.objects
        .filter(is_deleted=False)
        .values("status")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    status_labels = {
        "draft": "Brouillon",
        "submitted": "Soumise",
        "under_review": "En révision",
        "to_complete": "À compléter",
        "accepted": "Acceptée",
        "rejected": "Rejetée",
    }

    for stat in status_stats:
        percentage = 0
        if total_candidatures > 0:
            percentage = round((stat["count"] / total_candidatures * 100), 1)

        writer.writerow([
            status_labels.get(stat["status"], stat["status"]),
            stat["count"],
            f"{percentage}%"
        ])

    return response