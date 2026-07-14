from django_components import component


@component.register("supervisor_topbar")
class SupervisorTopbar(component.Component):
    template_name = "dashboard/supervisor_topbar.html"

    def get_context_data(self, **kwargs):
        return kwargs
