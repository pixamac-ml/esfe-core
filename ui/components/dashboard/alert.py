from django_components import component


@component.register("alert")
class Alert(component.Component):
    template_name = "dashboard/alert.html"

    def get_context_data(
        self,
        title="",
        message="",
        tone="info",
        variant="default",
        dismissible=False,
        class_str="",
        icon="",
        **kwargs,
    ):
        return {
            "title": title,
            "message": message,
            "tone": tone,
            "variant": variant,
            "dismissible": dismissible,
            "class_str": class_str,
            "icon": icon,
            **kwargs,
        }
