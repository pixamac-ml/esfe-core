from django_components import component


@component.register("divider")
class Divider(component.Component):
    template_name = "atoms/divider.html"

    def get_context_data(self, label="", **kwargs):
        return {
            "label": label,
            **kwargs,
        }
