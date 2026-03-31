from django.shortcuts import render, get_object_or_404
from django.db.models import Prefetch, Count, Q
from django.core.paginator import Paginator
from django_htmx.middleware import HtmxDetails
from branches.models import Branch
from core.models import Testimonial

from .models import (
    Programme,
    ProgrammeYear,
    Cycle,
)


# ==================================================
# LISTE DES FORMATIONS (HTMX + PAGE COMPLETE)
# ==================================================
def formation_list(request):
    # Récupération des paramètres
    cycle_slug = request.GET.get("cycle") or None
    search_query = request.GET.get("q") or ""
    page_number = request.GET.get("page", 1)

    # Queryset de base - toutes les formations actives
    programmes = (
        Programme.objects
        .filter(is_active=True)
        .select_related("cycle", "filiere", "diploma_awarded")
    )

    # Recherche textuelle
    if search_query:
        programmes = programmes.filter(
            Q(title__icontains=search_query) |
            Q(short_description__icontains=search_query) |
            Q(description__icontains=search_query)
        )

    # Filtrage par cycle
    if cycle_slug:
        programmes = programmes.filter(cycle__slug=cycle_slug)

    # Tri stratégique
    programmes = programmes.order_by(
        "-is_featured",
        "cycle__min_duration_years",
        "title"
    )

    # Compter le total AVANT pagination (pour affichage)
    total_programmes = programmes.count()

    # Pagination - 9 formations par page pour meilleure affichage
    paginator = Paginator(programmes, 9)
    page_obj = paginator.get_page(page_number)

    # Context de base
    context = {
        "programmes": page_obj.object_list,
        "page_obj": page_obj,
        "total_programmes": total_programmes,
        "cycles": Cycle.objects.filter(is_active=True).order_by("min_duration_years"),
        "current_cycle": cycle_slug,
        "search_query": search_query,
        "featured_count": programmes.filter(is_featured=True).count(),
        "cycle_count": Cycle.objects.filter(is_active=True).count(),
    }

    # ==================================================
    # GESTION HTMX - Retourner Sidebar + Liste ensemble
    # ==================================================
    if request.htmx:
        # On retourne le fragment de liste uniquement
        # La sidebar reste côté client (gérée par Alpine.js)
        return render(
            request,
            "formations/fragments/_programme_list.html",
            context
        )

    # Retour page complète
    return render(
        request,
        "formations/list.html",
        context
    )


import json  # ← AJOUTE EN HAUT DU FICHIER

# ==================================================
# DÉTAIL D'UNE FORMATION
# ==================================================
def formation_detail(request, slug):
    programme = get_object_or_404(
        Programme.objects
        .filter(is_active=True)
        .select_related(
            "cycle",
            "filiere",
            "diploma_awarded"
        )
        .prefetch_related(
            Prefetch(
                "years",
                queryset=ProgrammeYear.objects
                .order_by("year_number")
                .prefetch_related("fees")
            ),
            "required_documents__document"
        ),
        slug=slug
    )

    programme_years = programme.years.all()

    # Documents requis
    required_documents = [
        prd.document for prd in programme.required_documents.all()
    ]

    # Calcul des frais par année
    total_programme_cost = 0
    years_with_totals = []

    for year in programme_years:
        year_total = sum(fee.amount for fee in year.fees.all())
        total_programme_cost += year_total

        years_with_totals.append({
            "year": year,
            "year_total": year_total,
            "fees": list(year.fees.all()),
        })

    has_documents = bool(required_documents)
    has_fees = total_programme_cost > 0
    average_year_cost = int(total_programme_cost / programme.duration_years) if programme.duration_years else 0

    # Déterminer le type de cycle pour affichage conditionnel
    cycle_name = programme.cycle.name.lower()
    cycle_type = "licence" if "licence" in cycle_name else "master" if "master" in cycle_name else "doctorat"

    # =============================================
    # OBJECTIFS DE FORMATION (JSON)
    # =============================================
    try:
        learning_objectives = json.loads(programme.learning_outcomes) if programme.learning_outcomes else []
    except (json.JSONDecodeError, TypeError):
        learning_objectives = []

    # Fallback si learning_outcomes n'est pas en JSON
    if not learning_objectives and programme.learning_outcomes:
        learning_objectives = [
            {
                "title": "Objectif",
                "desc": line.strip(),
                "icon": "lightbulb",
                "color": "primary",
            }
            for line in programme.learning_outcomes.splitlines()
            if line.strip()
        ]

    career_points = [line.strip(" -\u2022") for line in (programme.career_opportunities or "").splitlines() if line.strip()]
    structure_points = [line.strip(" -\u2022") for line in (programme.program_structure or "").splitlines() if line.strip()]

    testimonials = (
        Testimonial.objects
        .filter(is_active=True)
        .filter(Q(programme=programme) | Q(programme__isnull=True))
        .order_by("-is_featured", "order")[:3]
    )

    related_programmes = (
        Programme.objects
        .filter(is_active=True)
        .exclude(pk=programme.pk)
        .filter(cycle=programme.cycle)
        .select_related("cycle", "diploma_awarded")
        .order_by("-is_featured", "title")[:3]
    )

    main_branch = Branch.objects.filter(is_active=True).order_by("name").first()

    context = {
        "programme": programme,
        "programme_years": programme_years,
        "years_with_totals": years_with_totals,
        "required_documents": required_documents,
        "has_documents": has_documents,
        "has_fees": has_fees,
        "can_apply": programme.is_active,
        "cycle_type": cycle_type,
        "total_cost": total_programme_cost,
        "total_programme_cost": total_programme_cost,
        "average_year_cost": average_year_cost,
        "learning_objectives": learning_objectives,
        "career_points": career_points,
        "structure_points": structure_points,
        "testimonials": testimonials,
        "related_programmes": related_programmes,
        "main_branch": main_branch,
    }
    return render(
        request,
        "formations/detail.html",
        context
    )
