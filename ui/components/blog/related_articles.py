from django_components import component
from blog.models import Article


@component.register("related_articles")
class RelatedArticles(component.Component):
    template_name = "blog/related_articles.html"

    def get_context_data(self, article):

        # Sécurité défensive : si pas d’article valide
        if not article or not article.category:
            return {"related_articles": []}

        related = (
            Article.published
            .filter(category=article.category)
            .exclude(pk=article.pk)
            .select_related("author", "category")
            .prefetch_related("images", "comments")
            .order_by("-published_at")[:3]
        )

        return {
            "related_articles": related
        }