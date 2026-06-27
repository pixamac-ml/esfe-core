from django_components import component


@component.register("kpi_row")
class KpiRow(component.Component):
    template_name = "dashboard/kpi_row.html"

    def get_context_data(self, cards=None, columns=4, **kwargs):
        return {
            "cards": cards or [],
            "columns": min(columns, 6),
            **kwargs,
        }
