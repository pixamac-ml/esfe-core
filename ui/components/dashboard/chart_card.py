import json

from django.core.serializers.json import DjangoJSONEncoder
from django_components import component


@component.register("chart_card")
class ChartCard(component.Component):
    template_name = "dashboard/chart_card.html"

    def get_context_data(
        self,
        title="",
        type="line",
        labels=None,
        datasets=None,
        height=250,
        options=None,
        **kwargs,
    ):
        chart_config = {
            "type": type,
            "data": {
                "labels": labels or [],
                "datasets": datasets or [],
            },
            "options": options or {},
        }
        return {
            "title": title,
            "type": type,
            "labels": labels or [],
            "datasets": datasets or [],
            "height": height,
            "chart_config_json": json.dumps(chart_config, cls=DjangoJSONEncoder),
            "chart_id": f"chart-{id(self)}",
            **kwargs,
        }
