from django.views.generic import ListView, DetailView

from .models import News
from .filters import filter_news


class NewsListView(ListView):
    template_name = "news/list.html"
    context_object_name = "news"
    paginate_by = 10

    def get_queryset(self):
        queryset = (
            News.published
            .select_related("categorie", "auteur")
        )
        return filter_news(queryset, self.request.GET)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_category"] = self.request.GET.get("category")
        context["search_query"] = self.request.GET.get("q")
        context["page_title"] = "Actualités"
        return context


class NewsDetailView(DetailView):
    template_name = "news/detail.html"
    context_object_name = "news"

    def get_queryset(self):
        return (
            News.published
            .select_related("categorie", "auteur")
            .prefetch_related("gallery")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = self.object.titre
        return context
