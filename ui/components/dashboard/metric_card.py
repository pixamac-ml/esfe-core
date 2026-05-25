from django_components import component


@component.register("metric_card")
class MetricCard(component.Component):
    template_name = "dashboard/metric_card.html"

    def get_context_data(self, label="", value="", icon="", hint="", **kwargs):
        return {
            "label": label,
            "value": value,
            "icon": icon,
            "hint": hint,
            **kwargs,
        }

