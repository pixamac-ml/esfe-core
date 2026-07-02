from django_components import component


@component.register("panel")
class Panel(component.Component):
    template_name = "layout/panel.html"

    def get_context_data(self, padding="md", elevated=False, class_str="", **kwargs):
        paddings = {"none": "", "sm": "p-3", "md": "p-4", "lg": "p-6"}
        return {
            "padding_class": paddings.get(padding, paddings["md"]),
            "elevated": elevated,
            "class_str": class_str,
            **kwargs,
        }
