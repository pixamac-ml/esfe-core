from django_components import component


@component.register("data_table")
class DataTable(component.Component):
    template_name = "dashboard/data_table.html"

    def get_context_data(self, id="data-table", headers=None, rows=None, empty_title="", empty_message="", empty_icon="info", **kwargs):
        return {
            "id": id,
            "headers": headers or [],
            "rows": rows or [],
            "empty_title": empty_title or "Aucune donnée",
            "empty_message": empty_message or "",
            "empty_icon": empty_icon,
            **kwargs,
        }
