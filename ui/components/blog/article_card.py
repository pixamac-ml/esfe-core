from django_components import component


@component.register("blog_article_card")
class BlogArticleCard(component.Component):
    template_name = "blog/article_card.html"

    def get_context_data(self, article):

        featured_image = None

        if article.featured_image:
            featured_image = article.featured_image.url
        else:
            image = article.images.first()
            if image:
                featured_image = image.image.url

        # Calcul temps de lecture
        words = len(article.excerpt.split()) if article.excerpt else 0
        reading_time = max(1, round(words / 200))  # 200 mots/min

        return {
            "article": article,
            "featured_image": featured_image,
            "reading_time": reading_time,
        }