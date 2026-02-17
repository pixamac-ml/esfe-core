from django.views.generic import ListView, DetailView
from django.db.models import Q

from .models import News, Category, Program
from .filters import filter_news


# =====================================================
# ACTUALITÉS — LISTE
# =====================================================

class NewsListView(ListView):
    template_name = "news/list.html"
    context_object_name = "news"
    paginate_by = 10

    def get_queryset(self):
        queryset = (
            News.published
            .select_related("categorie", "auteur", "program")
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
            "page_title": "Actualités",
            "categories": Category.objects.filter(is_active=True),
            "current_category": self.request.GET.get("category"),
            "search_query": self.request.GET.get("q"),

            "urgent_news": published_qs.filter(is_urgent=True)[:2],
            "important_news": published_qs.filter(is_important=True, is_urgent=False)[:4],
            "featured_news": published_qs[:3],
            "recent_news": published_qs[:5],
            "popular_news": published_qs.order_by("-views_count")[:5],

            "active_programs": Program.objects.filter(is_active=True)[:5],
        })

        return context


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

            # Actualités liées même catégorie
            "related_news": (
                published_qs
                .filter(categorie=self.object.categorie)
                .exclude(id=self.object.id)[:4]
            ),

            # À la une
            "featured_news": published_qs[:3],

            # Si l'article est lié à un programme
            "program_related_news": (
                published_qs
                .filter(program=self.object.program)
                .exclude(id=self.object.id)[:3]
                if self.object.program else None
            ),
        })

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        obj.views_count += 1
        obj.save(update_fields=["views_count"])
        return obj

        return context


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
