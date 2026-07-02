from django_components import component


@component.register("data_table")
class DataTable(component.Component):
    template_name = "dashboard/data_table.html"

    def get_context_data(
        self,
        id="data-table",
        headers=None,
        rows=None,
        empty_title="",
        empty_message="",
        empty_icon="info",
        selectable=False,
        loading=False,
        hx_target="",
        cell_edit_url="",
        **kwargs,
    ):
        return {
            "id": id,
            "headers": headers or [],
            "rows": rows or [],
            "empty_title": empty_title or "Aucune donnée",
            "empty_message": empty_message or "",
            "empty_icon": empty_icon,
            "selectable": selectable,
            "loading": loading,
            "hx_target": hx_target or f"#{id}",
            "cell_edit_url": cell_edit_url,
            **kwargs,
        }
