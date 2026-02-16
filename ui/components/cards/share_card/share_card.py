from django_components import component


@component.register("share_card")
class ShareCard(component.Component):
    template_name = "ui/cards/share_card/share_card.html"

    def get_context_data(self, article):
        return {"article": article}
