from django_components import component


@component.register("ui_core.timeline")
class Timeline(component.Component):
    template_name = "ui_core/data_display/timeline.html"

    def get_context_data(self, items=None, compact=False, empty_message="Aucune activité", **kwargs):
        return {
            "items": items or [],
            "compact": bool(compact),
            "empty_message": empty_message,
            **kwargs,
        }
