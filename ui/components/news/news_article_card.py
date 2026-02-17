from django_components import component


@component.register("news_article_card")
class NewsArticleCard(component.Component):
    template_name = "news/news_article_card.html"

    def get_context_data(self, news):
        return {
            "news": news,
        }
