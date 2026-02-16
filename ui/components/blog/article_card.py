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

        return {
            "article": article,
            "featured_image": featured_image,
        }
