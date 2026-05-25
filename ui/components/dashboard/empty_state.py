from django_components import component


@component.register("empty_state")
class EmptyState(component.Component):
    template_name = "dashboard/empty_state.html"

    def get_context_data(self, title="", message="", icon="info", compact=False, **kwargs):
        return {
            "title": title,
            "message": message,
            "icon": icon,
            "compact": compact,
            **kwargs,
        }

