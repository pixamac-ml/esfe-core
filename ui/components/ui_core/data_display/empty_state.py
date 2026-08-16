from django_components import component


@component.register("ui_core.empty_state")
class EmptyState(component.Component):
    template_name = "ui_core/data_display/empty_state.html"

    def get_context_data(
        self,
        title="Aucune donnée",
        message="",
        icon="inbox",
        action_label="",
        action_url="",
        compact=False,
        **kwargs,
    ):
        return {
            "title": title,
            "message": message,
            "icon": icon or "inbox",
            "action_label": action_label,
            "action_url": action_url,
            "compact": bool(compact),
            **kwargs,
        }
