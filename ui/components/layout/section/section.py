from django_components import component


@component.register("section")
class Section(component.Component):
    template_name = "layout/section/section.html"

    def get_context_data(self, variant="default", padding="lg", **kwargs):
        return {
            "variant": variant,
            "padding": padding,
            **kwargs
        }
