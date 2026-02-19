from django_components import component
from blog.models import Article


@component.register("related_articles")
class RelatedArticles(component.Component):
    template_name = "blog/related_articles.html"

    def get_context_data(self, article):

        if not article.category:
            return {"related_articles": []}

        related = (
            Article.published
            .filter(category=article.category)
            .exclude(id=article.id)
            .select_related("author", "category")
            .order_by("-published_at")[:3]
        )

        return {
            "related_articles": related
        }
