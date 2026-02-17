from django_components import component


@component.register("news_hero")
class NewsHero(component.Component):
    template_name = "news/news_hero.html"

    def get_context_data(self, title, subtitle):
        return {
            "title": title,
            "subtitle": subtitle,
        }
