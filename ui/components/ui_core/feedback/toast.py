from django_components import component


@component.register("ui_core.toast")
class Toast(component.Component):
    template_name = "ui_core/feedback/toast.html"

    def get_context_data(self, message="", tone="info", visible=True, **kwargs):
        tones = {"info", "success", "warning", "danger"}
        return {
            "message": message,
            "tone": tone if tone in tones else "info",
            "visible": bool(visible),
            **kwargs,
        }
