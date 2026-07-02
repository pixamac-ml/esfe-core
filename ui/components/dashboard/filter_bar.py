from django_components import component


@component.register("filter_bar")
class FilterBar(component.Component):
    template_name = "dashboard/filter_bar.html"

    def get_context_data(self, filters=None, id="filter-bar", hx_target="#data-table", class_str="", **kwargs):
        return {
            "filters": filters or [],
            "id": id,
            "hx_target": hx_target,
            "class_str": class_str,
            **kwargs,
        }
