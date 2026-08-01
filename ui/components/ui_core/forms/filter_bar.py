from django_components import component


@component.register("ui_core.filter_bar")
class FilterBar(component.Component):
    template_name = "ui_core/forms/filter_bar.html"

    def get_context_data(
        self,
        filters=None,
        action="",
        method="get",
        submit_label="Filtrer",
        reset_url="",
        target="",
        trigger="",
        indicator="",
        swap="outerHTML",
        sync="",
        density="comfortable",
        active_filters=None,
        **kwargs,
    ):
        density = density if density in {"comfortable", "compact"} else "comfortable"
        return {
            "filters": filters or [],
            "action": action,
            "method": method if str(method).lower() == "post" else "get",
            "submit_label": submit_label,
            "reset_url": reset_url,
            "target": target,
            "trigger": trigger,
            "indicator": indicator,
            "swap": swap if swap in {"innerHTML", "outerHTML"} else "outerHTML",
            "sync": sync,
            "density": density,
            "active_filters": active_filters or [],
            **kwargs,
        }
