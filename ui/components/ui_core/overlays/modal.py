from django_components import component


@component.register("ui_core.modal")
class Modal(component.Component):
    template_name = "ui_core/overlays/modal.html"

    def get_context_data(
        self,
        id="ui-core-modal",
        modal_id=None,
        title="",
        trigger_label="",
        open=False,
        content_url="",
        size="md",
        has_form=False,
        **kwargs,
    ):
        size_map = {
            "compact": "max-w-lg",
            "md": "max-w-xl",
            "wide": "max-w-4xl",
            "full": "max-w-5xl",
        }
        return {
            "modal_id": modal_id or id,
            "title": title,
            "trigger_label": trigger_label,
            "open": bool(open),
            "content_url": content_url,
            "size_class": size_map.get(size, "max-w-xl"),
            "has_form": bool(has_form),
            **kwargs,
        }
