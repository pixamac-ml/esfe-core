from django_components import component


@component.register("ui_core.tabs")
class Tabs(component.Component):
    template_name = "ui_core/navigation/tabs.html"

    def get_context_data(
        self,
        id="ui-core-tabs",
        items=None,
        active="",
        density="comfortable",
        **kwargs,
    ):
        density = density if density in {"comfortable", "compact"} else "comfortable"
        items = items or []
        return {
            "id": id,
            "items": items,
            "active": active or (items[0].get("id", "") if items else ""),
            "density": density,
            **kwargs,
        }
