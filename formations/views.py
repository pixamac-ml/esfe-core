from django.shortcuts import render, get_object_or_404
from django.db.models import Prefetch, Count
from django.core.paginator import Paginator

from .models import (
    Programme,
    ProgrammeYear,
    Cycle,
)


# ==================================================
# PAGE FORMATIONS (PAGE COMPLETE)
# ==================================================
def formation_list(request):
    """
    Page complète des formations.
    Sert uniquement à afficher la structure + filtres.
    Les données sont chargées via fragment HTMX.
    """

    cycles = Cycle.objects.filter(is_active=True)

    context = {
        "cycles": cycles,
    }

    return render(
        request,
        "formations/list.html",
        context
    )


# ==================================================
# FRAGMENT LISTE FORMATIONS (HTMX)
# ==================================================
def formation_list_fragment(request):
    """
    Fragment HTMX chargé dynamiquement.
    Contient uniquement la liste paginée des programmes.
    """

    cycle_slug = request.GET.get("cycle")
    page_number = request.GET.get("page", 1)

    programmes = (
        Programme.objects
        .filter(is_active=True)
        .select_related(
            "cycle",
            "filiere",
            "diploma_awarded"
        )
        .annotate(
            years_count=Count("years")
        )
        .order_by(
            "cycle__min_duration_years",
            "title"
        )
    )

    # 🔹 Filtrage par cycle
    if cycle_slug:
        programmes = programmes.filter(cycle__slug=cycle_slug)

    # 🔹 Pagination
    paginator = Paginator(programmes, 6)
    page_obj = paginator.get_page(page_number)

    context = {
        "programmes": page_obj.object_list,
        "page_obj": page_obj,
        "total_programmes": paginator.count,
        "current_cycle": cycle_slug,
    }

    return render(
        request,
        "formations/fragments/_programme_list.html",
        context
    )


# ==================================================
# DETAIL FORMATION
# ==================================================
def formation_detail(request, slug):
    """
    Page détail d’un programme.
    """

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

    required_documents = [
        prd.document for prd in programme.required_documents.all()
    ]

    has_documents = bool(required_documents)
    has_fees = any(year.fees.exists() for year in programme_years)

    context = {
        "programme": programme,
        "programme_years": programme_years,
        "required_documents": required_documents,
        "has_documents": has_documents,
        "has_fees": has_fees,
        "can_apply": programme.is_active,
    }

    return render(
        request,
        "formations/detail.html",
        context
    )
