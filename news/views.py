# views.py
from django.views.generic import ListView, DetailView
from .models import News
from .filters import filter_news

class NewsListView(ListView):
    template_name = "news/list.html"
    context_object_name = "news"
    paginate_by = 10

    def get_queryset(self):
        qs = News.published.select_related('categorie')
        return filter_news(qs, self.request.GET)


class NewsDetailView(DetailView):
    template_name = "news/detail.html"
    context_object_name = "news"

    def get_queryset(self):
        return News.published.select_related('categorie')
