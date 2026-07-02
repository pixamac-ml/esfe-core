from django_components import component


@component.register("spinner")
class Spinner(component.Component):
    template_name = "atoms/spinner.html"

    def get_context_data(self, size="md", tone="current", **kwargs):
        sizes = {"sm": "w-4 h-4", "md": "w-6 h-6", "lg": "w-8 h-8"}
        return {
            "size_class": sizes.get(size, sizes["md"]),
            "tone": tone,
            **kwargs,
        }
