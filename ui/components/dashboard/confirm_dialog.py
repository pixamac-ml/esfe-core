from django_components import component


@component.register("confirm_dialog")
class ConfirmDialog(component.Component):
    template_name = "dashboard/confirm_dialog.html"

    def get_context_data(
        self,
        title="Confirmer",
        message="",
        confirm_label="Confirmer",
        cancel_label="Annuler",
        confirm_tone="danger",
        hx_post="",
        hx_target="",
        **kwargs,
    ):
        return {
            "title": title,
            "message": message,
            "confirm_label": confirm_label,
            "cancel_label": cancel_label,
            "confirm_tone": confirm_tone,
            "hx_post": hx_post,
            "hx_target": hx_target,
            **kwargs,
        }
