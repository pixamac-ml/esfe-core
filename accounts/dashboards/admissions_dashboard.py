# accounts/dashboards/admissions_dashboard.py

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Q
from django.utils import timezone
from django.core.paginator import Paginator
from datetime import timedelta

from admissions.models import Candidature, CandidatureDocument
from formations.models import Programme
from branches.models import Branch

from .helpers import get_user_branch
from .permissions import check_admissions_access, is_global_viewer
from .querysets import get_base_queryset


@login_required
def admissions_dashboard(request):

    user = request.user

    if not check_admissions_access(user):
        messages.error(request, "Accès refusé.")
        return redirect("core:home")

    branch = get_user_branch(user)
    is_global = is_global_viewer(user)

    today = timezone.now().date()
    week_ago = timezone.now() - timedelta(days=7)
    month_ago = timezone.now() - timedelta(days=30)

    # =========================
    # QUERYSET BASE OPTIMISÉ
    # =========================

    candidatures = (
        get_base_queryset(user, "candidature")
        .select_related(
            "programme",
            "branch"
        )
    )

    # =========================
    # FILTRES
    # =========================

    status = request.GET.get("status")
    programme = request.GET.get("programme")
    search = request.GET.get("search")
    branch_filter = request.GET.get("branch")
    entry_year = request.GET.get("entry_year")
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")

    if status:
        candidatures = candidatures.filter(status=status)

    if programme:
        candidatures = candidatures.filter(programme_id=programme)

    if branch_filter and is_global:
        candidatures = candidatures.filter(branch_id=branch_filter)

    if entry_year:
        candidatures = candidatures.filter(entry_year=entry_year)

    if date_from:
        candidatures = candidatures.filter(submitted_at__date__gte=date_from)

    if date_to:
        candidatures = candidatures.filter(submitted_at__date__lte=date_to)

    if search:
        candidatures = candidatures.filter(
            Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(email__icontains=search)
            | Q(phone__icontains=search)
        )

    # =========================
    # STATS GÉNÉRALES
    # =========================

    base_candidatures = get_base_queryset(user, "candidature")

    stats = base_candidatures.aggregate(

        total=Count("id"),

        pending=Count(
            "id",
            filter=Q(status="submitted")
        ),

        under_review=Count(
            "id",
            filter=Q(status="under_review")
        ),

        accepted=Count(
            "id",
            filter=Q(status="accepted")
        ),

        rejected=Count(
            "id",
            filter=Q(status="rejected")
        ),

        to_complete=Count(
            "id",
            filter=Q(status="to_complete")
        ),

    )

    # =========================
    # STATS RÉCENTES
    # =========================

    recent = base_candidatures.filter(
        submitted_at__gte=week_ago
    ).count()

    today_count = base_candidatures.filter(
        submitted_at__date=today
    ).count()

    # =========================
    # CANDIDATURES EN ATTENTE
    # =========================

    pending_candidatures = (
        base_candidatures
        .filter(status__in=["submitted", "under_review", "to_complete"])
        .select_related("programme", "branch")
        .order_by("-submitted_at")
        [:30]
    )

    # =========================
    # CANDIDATURES ACCEPTÉES
    # =========================

    accepted_candidatures_qs = (
        base_candidatures
        .filter(status="accepted")
        .select_related("programme", "branch", "inscription")
        .order_by("-reviewed_at")
    )

    accepted_paginator = Paginator(accepted_candidatures_qs, 15)
    accepted_page = request.GET.get("accepted_page")
    accepted_candidatures = accepted_paginator.get_page(accepted_page)

    # =========================
    # DOCUMENTS À VALIDER
    # =========================

    pending_docs = (
        CandidatureDocument.objects
        .filter(
            candidature__in=base_candidatures,
            is_valid=False
        )
        .select_related(
            "candidature",
            "document_type"
        )
        .order_by("-uploaded_at")
        [:30]
    )

    # =========================
    # ACTIVITÉ RÉCENTE
    # =========================

    recent_activities = []

    # Candidatures récentes
    recent_cands = (
        base_candidatures
        .filter(submitted_at__gte=week_ago)
        .order_by("-submitted_at")
        [:5]
    )

    for cand in recent_cands:
        recent_activities.append({
            "action": "submitted",
            "description": f"{cand.full_name} a soumis une candidature",
            "created_at": cand.submitted_at,
        })

    # Candidatures acceptées récentes
    recent_accepted = (
        base_candidatures
        .filter(
            status="accepted",
            reviewed_at__gte=week_ago
        )
        .order_by("-reviewed_at")
        [:5]
    )

    for cand in recent_accepted:
        recent_activities.append({
            "action": "accepted",
            "description": f"{cand.full_name} a été accepté(e)",
            "created_at": cand.reviewed_at,
        })

    # Candidatures rejetées récentes
    recent_rejected = (
        base_candidatures
        .filter(
            status="rejected",
            reviewed_at__gte=week_ago
        )
        .order_by("-reviewed_at")
        [:5]
    )

    for cand in recent_rejected:
        recent_activities.append({
            "action": "rejected",
            "description": f"{cand.full_name} a été refusé(e)",
            "created_at": cand.reviewed_at,
        })

    # Tri par date
    recent_activities = sorted(
        recent_activities,
        key=lambda x: x["created_at"] or timezone.now(),
        reverse=True
    )[:10]

    # =========================
    # DONNÉES POUR GRAPHIQUES
    # =========================

    # Tendance hebdomadaire sur 8 semaines
    weekly_trend = []

    for i in range(7, -1, -1):
        week_start = timezone.now() - timedelta(weeks=i+1)
        week_end = timezone.now() - timedelta(weeks=i)

        count = base_candidatures.filter(
            submitted_at__gte=week_start,
            submitted_at__lt=week_end
        ).count()

        weekly_trend.append({
            "week": f"S-{i}" if i > 0 else "Cette sem.",
            "count": count
        })

    # =========================
    # TRI
    # =========================

    order = request.GET.get("order")

    if order == "oldest":
        candidatures = candidatures.order_by("submitted_at")

    elif order == "name":
        candidatures = candidatures.order_by("last_name")

    else:
        candidatures = candidatures.order_by("-submitted_at")

    # =========================
    # PAGINATION
    # =========================

    paginator = Paginator(candidatures, 25)

    page = request.GET.get("page")

    candidatures_page = paginator.get_page(page)

    # =========================
    # PROGRAMMES
    # =========================

    programmes = Programme.objects.filter(is_active=True).order_by("title")

    # =========================
    # ANNEXES (GLOBAL ONLY)
    # =========================

    branches = None
    branches_count = 0

    if is_global:

        branches = (
            Branch.objects
            .filter(is_active=True)
            .order_by("name")
        )

        branches_count = branches.count()

    # =========================
    # CONTEXTE
    # =========================

    import json

    context = {

        "stats": stats,

        "recent": recent,
        "today_count": today_count,

        "pending_docs": pending_docs,
        "pending_candidatures": pending_candidatures,

        "accepted_candidatures": accepted_candidatures,
        "accepted_candidatures_paginator": accepted_candidatures,

        "recent_activities": recent_activities,

        "candidatures": candidatures_page,

        "programmes": programmes,

        "branches": branches,
        "branches_count": branches_count,

        "stats_for_charts": {
            "weekly_trend": json.dumps(weekly_trend),
        },

        "dashboard_type": "admissions",

        "branch": branch,
        "is_global": is_global,

    }

    return render(
        request,
        "accounts/dashboard/admissions.html",
        context
    )