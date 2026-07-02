from django_components import component


@component.register("mini_stat")
class MiniStat(component.Component):
    template_name = "dashboard/mini_stat.html"

    def get_context_data(self, label="", value="", icon="", color="muted", **kwargs):
        return {
            "label": label,
            "value": value,
            "icon": icon,
            "color": color,
            **kwargs,
        }
