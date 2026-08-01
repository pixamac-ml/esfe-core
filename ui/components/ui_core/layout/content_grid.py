from django_components import component


@component.register("ui_core.content_grid")
class ContentGrid(component.Component):
    template_name = "ui_core/layout/content_grid.html"

    def get_context_data(self, columns=3, **kwargs):
        try:
            columns = int(columns)
        except (TypeError, ValueError):
            columns = 3
        return {"columns": min(max(columns, 1), 4), **kwargs}
