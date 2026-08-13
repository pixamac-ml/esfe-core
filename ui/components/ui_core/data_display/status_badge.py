from django_components import component


@component.register("ui_core.status_badge")
class StatusBadge(component.Component):
    template_name = "ui_core/data_display/status_badge.html"

    def get_context_data(self, label="", tone="neutral", icon="", dot=False, **kwargs):
        tones = {"neutral", "primary", "success", "warning", "danger", "info"}
        return {
            "label": "Inconnu" if label is None or label == "" else label,
            "tone": tone if tone in tones else "neutral",
            "icon": icon,
            "dot": bool(dot),
            **kwargs,
        }
