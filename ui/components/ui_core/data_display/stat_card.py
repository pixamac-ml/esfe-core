from django_components import component


@component.register("ui_core.stat_card")
class StatCard(component.Component):
    template_name = "ui_core/data_display/stat_card.html"

    def get_context_data(
        self,
        label="",
        value="",
        icon="activity",
        tone="primary",
        trend=None,
        trend_label="",
        unit="",
        description="",
        period="",
        target=None,
        progress=None,
        compact=False,
        empty=False,
        href="",
        hx_get="",
        hx_target="",
        hx_push_url="",
        loading=False,
        **kwargs,
    ):
        tones = {"primary", "accent", "success", "warning", "danger", "info", "neutral"}
        return {
            "label": label,
            "value": value,
            "icon": icon or "activity",
            "tone": tone if tone in tones else "neutral",
            "trend": trend,
            "trend_label": trend_label,
            "unit": unit,
            "description": description,
            "period": period,
            "target": target,
            "progress": progress,
            "compact": bool(compact),
            "empty": bool(empty),
            "href": href,
            "hx_get": hx_get,
            "hx_target": hx_target,
            "hx_push_url": hx_push_url,
            "loading": bool(loading),
            **kwargs,
        }
