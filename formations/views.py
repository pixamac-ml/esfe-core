from django.shortcuts import render, get_object_or_404
from django.db.models import Prefetch, Count

from .models import Programme, ProgrammeYear


# ==================================================
# LISTE DES FORMATIONS (SITE VITRINE)
# ==================================================
def formation_list(request):
    """
    Page vitrine listant toutes les formations actives.
    Utilisée par les visiteurs pour découvrir les programmes.
    """

    programmes = (
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
            )
        )
        .annotate(
            years_count=Count("years")
        )
        .order_by(
            "cycle__min_duration_years",
            "title"
        )
    )

    context = {
        "programmes": programmes,
        "total_programmes": programmes.count(),
    }

    return render(
        request,
        "formations/list.html",
        context
    )


# ==================================================
# DÉTAIL D’UNE FORMATION
# ==================================================
def formation_detail(request, slug):
    """
    Page détail d'une formation.
    Point d’entrée vers la candidature.
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

    # Années structurées avec frais
    programme_years = programme.years.all()

    # Documents requis
    required_documents = [
        prd.document for prd in programme.required_documents.all()
    ]

    # Indicateurs métier (pour l’UI et la logique future)
    has_documents = len(required_documents) > 0
    has_fees = any(year.fees.exists() for year in programme_years)

    context = {
        "programme": programme,
        "programme_years": programme_years,
        "required_documents": required_documents,
        "has_documents": has_documents,
        "has_fees": has_fees,

        # CTA
        "can_apply": programme.is_active,
    }

    return render(
        request,
        "formations/detail.html",
        context
    )
