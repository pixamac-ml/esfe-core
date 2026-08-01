from django_components import component


@component.register("ui_core.confirm_dialog")
class ConfirmDialog(component.Component):
    template_name = "ui_core/feedback/confirm_dialog.html"

    def get_context_data(
        self,
        id="ui-core-confirm",
        dialog_id=None,
        title="Confirmer l'action",
        message="",
        trigger_label="",
        confirm_label="Confirmer",
        cancel_label="Annuler",
        tone="danger",
        open=False,
        action_url="",
        target="",
        **kwargs,
    ):
        return {
            "dialog_id": dialog_id or id,
            "title": title,
            "message": message,
            "trigger_label": trigger_label,
            "confirm_label": confirm_label,
            "cancel_label": cancel_label,
            "tone": tone if tone in {"primary", "danger"} else "danger",
            "open": bool(open),
            "action_url": action_url,
            "target": target,
            **kwargs,
        }
