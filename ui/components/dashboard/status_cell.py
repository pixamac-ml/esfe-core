from django_components import component


@component.register("status_cell")
class StatusCell(component.Component):
    template_name = "dashboard/status_cell.html"

    def get_context_data(self, label="", tone="neutral", icon="", **kwargs):
        return {
            "label": label,
            "tone": tone,
            "icon": icon,
            **kwargs,
        }
