import json

from django_components import component


@component.register("ui_core.chart_panel")
class ChartPanel(component.Component):
    template_name = "ui_core/data_display/chart_panel.html"

    def get_context_data(
        self,
        id="ui-core-chart",
        title="",
        description="",
        chart_type="line",
        labels=None,
        datasets=None,
        loading=False,
        error="",
        **kwargs,
    ):
        allowed_types = {"line", "bar", "doughnut"}
        config = {
            "type": chart_type if chart_type in allowed_types else "line",
            "data": {"labels": labels or [], "datasets": datasets or []},
        }
        return {
            "id": id,
            "title": title,
            "description": description,
            "chart_config": json.dumps(config, ensure_ascii=True),
            "loading": bool(loading),
            "error": error,
            "empty": not labels or not datasets,
            **kwargs,
        }
