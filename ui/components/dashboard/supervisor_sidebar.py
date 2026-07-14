from django_components import component


@component.register("supervisor_sidebar")
class SupervisorSidebar(component.Component):
    template_name = "dashboard/supervisor_sidebar.html"

    def get_context_data(self, **kwargs):
        return kwargs
