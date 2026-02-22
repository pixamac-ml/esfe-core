from django.shortcuts import render
from django.views.generic import ListView, DetailView
from django.db.models import Q

from .models import News, Category, Program
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
