from django_components import component


@component.register("status_badge")
class StatusBadge(component.Component):
    template_name = "dashboard/status_badge.html"

    def get_context_data(
        self,
        label="",
        tone="neutral",
        icon="",
        dot=False,
        dismissible=False,
        pulse=False,
        clickable=False,
        class_str="",
        **kwargs,
    ):
        return {
            "label": label,
            "tone": tone,
            "icon": icon,
            "dot": dot,
            "dismissible": dismissible,
            "pulse": pulse,
            "clickable": clickable,
            "class_str": class_str,
            **kwargs,
        }

