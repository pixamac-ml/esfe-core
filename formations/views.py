from django.shortcuts import render, get_object_or_404
from django.db.models import Prefetch, Count
from django.core.paginator import Paginator
from django_htmx.middleware import HtmxDetails

from .models import (
    Programme,
    ProgrammeYear,
    Cycle,
)


# ==================================================
# PAGE FORMATIONS (PAGE COMPLETE)
# ==================================================
# ==================================================
# LISTE DES FORMATIONS (HTMX + PAGE COMPLETE)
# ==================================================
from django.shortcuts import render, get_object_or_404
from django.db.models import Prefetch, Count, Q
from django.core.paginator import Paginator

from .models import Programme, ProgrammeYear, Cycle


def formation_list(request):

    cycle_slug = request.GET.get("cycle")
    search_query = request.GET.get("q")
    page_number = request.GET.get("page", 1)

    programmes = (
        Programme.objects
        .filter(is_active=True)
        .select_related("cycle", "filiere", "diploma_awarded")
        .annotate(years_count=Count("years"))
    )

    if search_query:
        programmes = programmes.filter(
            Q(title__icontains=search_query) |
            Q(short_description__icontains=search_query)
        )

    if cycle_slug:
        programmes = programmes.filter(cycle__slug=cycle_slug)

    programmes = programmes.order_by(
        "-is_featured",
        "cycle__min_duration_years",
        "title"
    )

    paginator = Paginator(programmes, 6)
    page_obj = paginator.get_page(page_number)

    context = {
        "programmes": page_obj.object_list,
        "page_obj": page_obj,
        "total_programmes": paginator.count,
        "cycles": Cycle.objects.filter(is_active=True).order_by("min_duration_years"),
        "current_cycle": cycle_slug,
        "search_query": search_query,
    }

    if request.headers.get("HX-Request") == "true":
        return render(
            request,
            "formations/fragments/_programme_list.html",
            context
        )
    return render(
        request,
        "formations/list.html",
        context
    )



# ==================================================
# DETAIL FORMATION
# ==================================================
# ==================================================
# DETAIL FORMATION
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

    # Frais
    total_programme_cost = 0
    years_with_totals = []

    for year in programme_years:
        year_total = sum(fee.amount for fee in year.fees.all())
        total_programme_cost += year_total

        years_with_totals.append({
            "year": year,
            "year_total": year_total,
        })

    has_documents = bool(required_documents)
    has_fees = total_programme_cost > 0

    cycle_type = programme.cycle.name.lower()

    context = {
        "programme": programme,
        "programme_years": programme_years,
        "years_with_totals": years_with_totals,
        "required_documents": required_documents,
        "has_documents": has_documents,
        "has_fees": has_fees,
        "can_apply": programme.is_active,
        "cycle_type": cycle_type,
    }

    return render(
        request,
        "formations/detail.html",
        context
    )
