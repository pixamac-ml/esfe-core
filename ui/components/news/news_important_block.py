from django_components import component


@component.register("news_important_block")
class NewsImportantBlock(component.Component):
    template_name = "news/news_important_block.html"

    def get_context_data(self, important_news):
        return {
            "important_news": important_news,
        }
