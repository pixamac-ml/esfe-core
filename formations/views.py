from django.shortcuts import render, get_object_or_404
from django.db.models import Prefetch, Count, Q
from django.core.paginator import Paginator
from django_htmx.middleware import HtmxDetails

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

    # Déterminer le type de cycle pour affichage conditionnel
    cycle_name = programme.cycle.name.lower()
    cycle_type = "licence" if "licence" in cycle_name else "master" if "master" in cycle_name else "doctorat"

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
    }

    return render(
        request,
        "formations/detail.html",
        context
    )
