from django_components import component
from django.db.models import Prefetch

from formations.models import Cycle, Programme
from news.models import Category as NewsCategory
from blog.models import Category as BlogCategory


@component.register("navbar")
class Navbar(component.Component):

    template_name = "layout/navbar/navbar.html"

    def get_context_data(self, request, **kwargs):

        cycles = (
            Cycle.objects
            .filter(is_active=True)
            .prefetch_related(
                Prefetch(
                    "programmes",
                    queryset=Programme.objects.filter(is_active=True)
                )
            )
            .order_by("min_duration_years")
        )

        # NEWS
        news_categories = (
            NewsCategory.objects
            .filter(is_active=True)
            .order_by("nom")
        )

        # BLOG
        blog_categories = (
            BlogCategory.objects
            .filter(is_active=True)
            .order_by("name")
        )

        return {
            "cycles": cycles,
            "news_categories": news_categories,
            "blog_categories": blog_categories,
        }