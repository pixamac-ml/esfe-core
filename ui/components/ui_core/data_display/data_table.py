from django_components import component


@component.register("ui_core.data_table")
class DataTable(component.Component):
    template_name = "ui_core/data_display/data_table.html"

    def get_context_data(
        self,
        id="ui-core-table",
        table_id=None,
        caption="",
        headers=None,
        rows=None,
        loading=False,
        error="",
        permission_denied=False,
        density="comfortable",
        selectable=False,
        selected_count=0,
        result_count=None,
        page=1,
        page_count=1,
        empty_title="Aucune donnée",
        empty_message="",
        **kwargs,
    ):
        density = density if density in {"comfortable", "compact"} else "comfortable"
        return {
            "table_id": table_id or id,
            "caption": caption,
            "headers": headers or [],
            "rows": rows or [],
            "loading": bool(loading),
            "error": error,
            "permission_denied": bool(permission_denied),
            "density": density,
            "selectable": bool(selectable),
            "selected_count": max(int(selected_count or 0), 0),
            "result_count": len(rows or []) if result_count is None else max(int(result_count), 0),
            "page": max(int(page or 1), 1),
            "page_count": max(int(page_count or 1), 1),
            "empty_title": empty_title,
            "empty_message": empty_message,
            **kwargs,
        }
