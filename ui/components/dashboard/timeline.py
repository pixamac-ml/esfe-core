from django_components import component


@component.register("timeline")
class Timeline(component.Component):
    template_name = "dashboard/timeline.html"

    def get_context_data(self, items=None, **kwargs):
        return {
            "items": items or [],
            **kwargs,
        }
