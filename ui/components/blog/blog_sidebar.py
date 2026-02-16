from django_components import component
from blog.models import Category


@component.register("blog_sidebar")
class BlogSidebar(component.Component):
    template_name = "blog/blog_sidebar.html"

    def get_context_data(self):
        categories = (
            Category.objects
            .filter(is_active=True)
            .prefetch_related("articles")
        )

        return {
            "categories": categories
        }
