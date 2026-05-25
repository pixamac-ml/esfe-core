from django_components import component


@component.register("status_badge")
class StatusBadge(component.Component):
    template_name = "dashboard/status_badge.html"

    def get_context_data(self, label="", tone="neutral", icon="", **kwargs):
        return {
            "label": label,
            "tone": tone,
            "icon": icon,
            **kwargs,
        }

