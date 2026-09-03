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
        select="",
        density="comfortable",
        live_search_name="",
        live_search_delay=350,
        active_filters=None,
        hidden_fields=None,
        **kwargs,
    ):
        density = density if density in {"comfortable", "compact"} else "comfortable"
        try:
            live_search_delay = min(max(int(live_search_delay), 150), 1500)
        except (TypeError, ValueError):
            live_search_delay = 350
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
            "select": select,
            "density": density,
            "live_search_name": str(live_search_name or ""),
            "live_search_delay": live_search_delay,
            "active_filters": active_filters or [],
            "hidden_fields": hidden_fields or [],
            **kwargs,
        }
