from django_components import component


@component.register("ui_core.dropdown_menu")
class DropdownMenu(component.Component):
    template_name = "ui_core/navigation/dropdown_menu.html"

    def get_context_data(
        self,
        id="ui-core-menu",
        label="Actions",
        items=None,
        align="right",
        disabled=False,
        **kwargs,
    ):
        return {
            "id": id,
            "label": label,
            "items": items or [],
            "align": align if align in {"left", "right"} else "right",
            "disabled": bool(disabled),
            **kwargs,
        }
