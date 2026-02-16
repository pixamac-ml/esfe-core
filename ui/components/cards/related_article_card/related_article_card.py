from django_components import component


@component.register("related_article_card")
class RelatedArticleCard(component.Component):
    template_name = "ui/cards/related_article_card/related_article_card.html"

    def get_context_data(self, article):
        return {"article": article}
