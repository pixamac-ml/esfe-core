from django_components import component


@component.register("stat_card")
class StatCard(component.Component):
    template_name = "dashboard/stat_card.html"

    def get_context_data(
        self,
        label="",
        value="",
        icon="",
        trend=0,
        trend_label="",
        href="",
        tone="primary",
        **kwargs,
    ):
        return {
            "label": label,
            "value": value,
            "icon": icon,
            "trend": trend,
            "trend_label": trend_label,
            "href": href,
            "tone": tone,
            **kwargs,
        }
