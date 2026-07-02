from django_components import component


@component.register("toolbar")
class Toolbar(component.Component):
    template_name = "dashboard/toolbar.html"

    def get_context_data(
        self,
        total_count=0,
        count_label="résultat",
        class_str="",
        **kwargs,
    ):
        return {
            "total_count": total_count,
            "count_label": count_label,
            "class_str": class_str,
            **kwargs,
        }
