from django_components import component


@component.register("article_share_bar")
class ArticleShareBar(component.Component):
    template_name = "blog/article_share_bar.html"

    def get_context_data(self, article, absolute_url):
        return {
            "article": article,
            "absolute_url": absolute_url
        }
