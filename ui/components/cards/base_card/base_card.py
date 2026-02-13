from django_components import component

@component.register("base_card")
class BaseCard(component.Component):
    template_name = "cards/base_card/base_card.html"

    def get_context_data(self, **kwargs):
        return kwargs
