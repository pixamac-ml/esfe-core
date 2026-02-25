from django.shortcuts import render
from django.views.generic import ListView, DetailView
from django.db.models import Q

from .models import News, Category, Program, ResultSession
from .filters import filter_news


# =====================================================
# ACTUALITÉS — LISTE
# =====================================================

from django.shortcuts import render
from django.views.generic import ListView
from django.shortcuts import render
from django.db.models import Q

from .models import News, Category, Program
from .filters import filter_news

from django.views.generic import ListView
from django.shortcuts import render

from .models import News, Category, Program
from .filters import filter_news


class NewsListView(ListView):
    template_name = "news/list.html"
    context_object_name = "news"
    paginate_by = 10

    def get_queryset(self):
        queryset = (
            News.published
            .select_related("categorie", "auteur", "program")
            .order_by("-published_at")
        )
        return filter_news(queryset, self.request.GET)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        published_qs = (
            News.published
            .select_related("categorie", "program")
            .order_by("-published_at")
        )

        context.update({
            "categories": Category.objects.filter(is_active=True),
            "current_category": self.request.GET.get("category"),

            "featured_news": published_qs[:3],
            "recent_news": published_qs[:5],
        })

        return context

    def render_to_response(self, context, **response_kwargs):
        if self.request.headers.get("HX-Request"):
            return render(
                self.request,
                "news/fragments/news_content_fragment.html",
                context
            )
        return super().render_to_response(context, **response_kwargs)


# =====================================================
# ACTUALITÉS — DÉTAIL
# =====================================================

class NewsDetailView(DetailView):
    template_name = "news/detail.html"
    context_object_name = "news"

    def get_queryset(self):
        return (
            News.published
            .select_related("categorie", "auteur", "program")
            .prefetch_related("gallery")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        published_qs = (
            News.published
            .select_related("categorie", "program")
            .order_by("-published_at")
        )

        context.update({
            "page_title": self.object.titre,
            "related_news": (
                published_qs
                .filter(categorie=self.object.categorie)
                .exclude(id=self.object.id)[:4]
            ),
            "featured_news": published_qs[:3],
            "program_related_news": (
                published_qs
                .filter(program=self.object.program)
                .exclude(id=self.object.id)[:3]
                if self.object.program else None
            ),
        })

        return context  # ← MANQUAIT ICI

# =====================================================
# PROGRAMMES — LISTE
# =====================================================

class ProgramListView(ListView):
    model = Program
    template_name = "news/program_list.html"
    context_object_name = "programs"

    def get_queryset(self):
        return Program.objects.filter(is_active=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context.update({
            "page_title": "Programmes & Initiatives",
            "recent_program_news": (
                News.published
                .filter(program__isnull=False)
                .select_related("program")[:6]
            )
        })

        return context


# =====================================================
# PROGRAMME — DÉTAIL
# =====================================================

class ProgramDetailView(DetailView):
    model = Program
    template_name = "news/program_detail.html"
    context_object_name = "program"

    def get_queryset(self):
        return Program.objects.filter(is_active=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        program_news = (
            self.object.news
            .select_related("categorie")
            .filter(status="published")
            .order_by("-published_at")
        )

        context.update({
            "page_title": self.object.nom,
            "program_news": program_news,
            "recent_news": News.published[:5],
        })

        return context


from django.views.generic import ListView
from django.db.models import Count
from .models import ResultSession


class ResultSessionListView(ListView):
    model = ResultSession
    template_name = "news/result_list.html"
    context_object_name = "results"
    paginate_by = 24

    def get_queryset(self):
        queryset = (
            ResultSession.objects
            .filter(is_published=True)
            .order_by("-annee_academique", "-created_at")
        )

        annee = self.request.GET.get("annee")
        annexe = self.request.GET.get("annexe")
        type_result = self.request.GET.get("type")
        search = self.request.GET.get("q")

        if annee:
            queryset = queryset.filter(annee_academique=annee)

        if annexe:
            queryset = queryset.filter(annexe__iexact=annexe)

        if type_result:
            queryset = queryset.filter(type=type_result)

        if search:
            queryset = queryset.filter(
                titre__icontains=search
            )

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Années distinctes (pour sidebar)
        annees = (
            ResultSession.objects
            .filter(is_published=True)
            .values_list("annee_academique", flat=True)
            .distinct()
            .order_by("-annee_academique")
        )

        # Annexes distinctes
        annexes = (
            ResultSession.objects
            .filter(is_published=True)
            .values_list("annexe", flat=True)
            .distinct()
            .order_by("annexe")
        )

        # Mapping Année → Annexes
        annexes_par_annee = {}
        for annee in annees:
            annexes_par_annee[annee] = (
                ResultSession.objects
                .filter(is_published=True, annee_academique=annee)
                .values_list("annexe", flat=True)
                .distinct()
                .order_by("annexe")
            )

        context.update({
            "page_title": "Résultats académiques",
            "annees": annees,
            "annexes": annexes,
            "annexes_par_annee": annexes_par_annee,

            # Garder les filtres actifs dans le template
            "current_annee": self.request.GET.get("annee", ""),
            "current_annexe": self.request.GET.get("annexe", ""),
            "current_type": self.request.GET.get("type", ""),
            "current_search": self.request.GET.get("q", ""),
        })

        return context



from django.shortcuts import render, get_object_or_404
from django.db.models import Count, Q, Prefetch
from django.core.paginator import Paginator
from django.utils import timezone

from .models import Event, EventType, MediaItem


# ==========================================================
# EVENT LIST VIEW
# ==========================================================

def event_list_view(request):

    events_queryset = (
        Event.objects
        .filter(is_published=True)
        .select_related("event_type")
        .prefetch_related(
            Prefetch(
                "media_items",
                queryset=MediaItem.objects.only(
                    "id",
                    "media_type",
                    "thumbnail",
                    "video_url",
                    "video_file",
                    "is_featured",
                )
            )
        )
    )

    # ========================
    # FILTRAGE PAR TYPE
    # ========================

    type_slug = request.GET.get("type")
    if type_slug:
        events_queryset = events_queryset.filter(event_type__slug=type_slug)

    # ========================
    # FILTRAGE PAR ANNÉE
    # ========================

    year = request.GET.get("year")
    if year and year.isdigit():
        events_queryset = events_queryset.filter(event_date__year=int(year))

    # ========================
    # ANNOTATIONS
    # ========================

    events_queryset = events_queryset.annotate(
        total_media=Count("media_items", distinct=True),
        total_images=Count(
            "media_items",
            filter=Q(media_items__media_type=MediaItem.IMAGE),
            distinct=True
        ),
        total_videos=Count(
            "media_items",
            filter=Q(media_items__media_type=MediaItem.VIDEO),
            distinct=True
        ),
    )

    # ========================
    # PAGINATION
    # ========================

    paginator = Paginator(events_queryset, 9)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # ========================
    # SIDEBAR
    # ========================

    event_types = EventType.objects.filter(is_active=True)

    years = (
        Event.objects
        .filter(is_published=True)
        .dates("event_date", "year", order="DESC")
    )

    context = {
        "page_obj": page_obj,
        "event_types": event_types,
        "current_type": type_slug,
        "years": years,
        "current_year": year,
    }

    return render(request, "news/event_list.html", context)


# ==========================================================
# EVENT DETAIL VIEW
# ==========================================================

def event_detail_view(request, slug):

    event = get_object_or_404(
        Event.objects
        .select_related("event_type")
        .prefetch_related(
            Prefetch(
                "media_items",
                queryset=MediaItem.objects.order_by("-is_featured", "-created_at")
            )
        ),
        slug=slug,
        is_published=True
    )

    # ========================
    # MÉDIAS ORGANISÉS
    # ========================

    images = [
        media for media in event.media_items.all()
        if media.media_type == MediaItem.IMAGE
    ]

    videos = [
        media for media in event.media_items.all()
        if media.media_type == MediaItem.VIDEO
    ]

    # ========================
    # RELATED EVENTS
    # ========================

    related_events = (
        Event.objects
        .filter(
            event_type=event.event_type,
            is_published=True
        )
        .exclude(id=event.id)
        .select_related("event_type")
        .only(
            "title",
            "slug",
            "cover_thumbnail",
            "event_date"
        )
        .order_by("-event_date")[:4]
    )

    context = {
        "event": event,
        "images": images,
        "videos": videos,
        "related_events": related_events,
    }

    return render(request, "news/event_detail.html", context)