from django_components import component


@component.register("tabs")
class Tabs(component.Component):
    template_name = "dashboard/tabs.html"

    def get_context_data(self, tabs=None, active_tab="", name="tabs", **kwargs):
        return {
            "tabs": tabs or [],
            "active_tab": active_tab,
            "name": name,
            **kwargs,
        }
