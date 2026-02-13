from django_components import component

@component.register("accordion")
class Accordion(component.Component):
    template_name = "interactive/accordion/accordion.html"

    def get_context_data(self, title="", open=False):
        return {
            "title": title,
            "open": open,
        }
