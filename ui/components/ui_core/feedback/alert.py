from django_components import component


@component.register("ui_core.alert")
class Alert(component.Component):
    template_name = "ui_core/feedback/alert.html"

    def get_context_data(self, title="", message="", tone="info", dismissible=False, **kwargs):
        tones = {"primary", "info", "success", "warning", "danger", "neutral"}
        return {
            "title": title,
            "message": message,
            "tone": tone if tone in tones else "neutral",
            "dismissible": bool(dismissible),
            **kwargs,
        }
