from django_components import component
from django.utils.text import Truncator


@component.register("blog_article_card")
class BlogArticleCard(component.Component):
    template_name = "ui/components/blog/article_card.html"

    def get_context_data(self, article):
        """
        Composant purement visuel.
        Ne contient aucune logique métier.
        Reçoit un objet Article et prépare uniquement
        les données nécessaires à l'affichage.
        """

        featured_image = None

        # Si tu as un champ image principal
        if hasattr(article, "featured_image") and article.featured_image:
            featured_image = article.featured_image.url

        # Si tu utilises un modèle ArticleImage avec is_featured
        elif hasattr(article, "images"):
            image = article.images.filter(is_featured=True).first()
            if image and image.image:
                featured_image = image.image.url

        return {
            "article": article,
            "featured_image": featured_image,
            "category": article.category if article.category else None,
            "title": article.title,
            "excerpt": Truncator(article.excerpt).chars(180),
            "url": article.get_absolute_url(),
            "published_at": article.published_at,
            "comments_count": getattr(article, "comments_count", 0),
            "views_count": getattr(article, "views_count", 0),
        }
