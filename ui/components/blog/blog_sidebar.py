from django_components import component
from blog.models import Category
from django.db.models import Count


@component.register("blog_sidebar")
class BlogSidebar(component.Component):
    template_name = "blog/blog_sidebar.html"

    def get_context_data(self, categories=None):
        # Si categories est passé depuis la vue, on l'utilise
        # Sinon, on fait la requête ici (fallback)
        if categories is None:
            categories = (
                Category.objects
                .filter(is_active=True)
                .annotate(article_count=Count("articles"))
                .order_by("name")
            )

        return {
            "categories": categories
        }