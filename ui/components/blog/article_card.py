from django_components import component


@component.register("blog_article_card")
class BlogArticleCard(component.Component):
    template_name = "ui/components/blog/article_card.html"

    def get_context_data(self, article):
        image = article.images.first() if hasattr(article, "images") else None

        return {
            "article": article,
            "featured_image": image.image.url if image and image.image else None,
        }
