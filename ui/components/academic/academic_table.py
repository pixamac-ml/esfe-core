from django_components import component


@component.register("academic_table")
class AcademicTable(component.Component):
    """Tableau de données scolaire, wrapper autour de data_table."""

    template_name = "academic/academic_table.html"

    def get_context_data(
        self,
        id="academic-table",
        headers=None,
        rows=None,
        empty_title="Aucune donnée",
        empty_message="",
        empty_icon="inbox",
        selectable=False,
        loading=False,
        hx_target="",
        cell_edit_url="",
        class_str="",
        **kwargs,
    ):
        if isinstance(headers, str):
            headers = [{"label": h.strip()} for h in headers.split(",") if h.strip()]
        return {
            "id": id,
            "headers": headers or [],
            "rows": rows or [],
            "empty_title": empty_title,
            "empty_message": empty_message,
            "empty_icon": empty_icon,
            "selectable": selectable,
            "loading": loading,
            "hx_target": hx_target or f"#{id}",
            "cell_edit_url": cell_edit_url,
            "class_str": class_str,
            **kwargs,
        }
