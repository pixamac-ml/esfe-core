from django_components import component


@component.register("icon")
class Icon(component.Component):
    template_name = "atoms/icon.html"

    def get_context_data(self, name="", size=16, class_str="", **kwargs):
        return {
            "name": name,
            "size": size,
            "class_str": class_str,
            **kwargs,
        }
