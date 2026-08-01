from django_components import component


@component.register("ui_core.drawer")
class Drawer(component.Component):
    template_name = "ui_core/overlays/drawer.html"

    def get_context_data(
        self,
        id="ui-core-drawer",
        drawer_id=None,
        title="",
        trigger_label="",
        side="right",
        open=False,
        content_url="",
        has_form=False,
        size="md",
        **kwargs,
    ):
        size_map = {
            "sm": "max-w-sm",
            "compact": "max-w-sm",
            "md": "max-w-md",
            "lg": "max-w-lg",
            "xl": "max-w-xl",
            "wide": "max-w-4xl",
            "full": "max-w-5xl",
        }
        return {
            "drawer_id": drawer_id or id,
            "title": title,
            "trigger_label": trigger_label,
            "side": side if side in {"left", "right"} else "right",
            "open": bool(open),
            "content_url": content_url,
            "has_form": bool(has_form),
            "size_class": size_map.get(size, "max-w-md"),
            **kwargs,
        }
