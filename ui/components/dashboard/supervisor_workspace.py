from django_components import component


@component.register("supervisor_workspace")
class SupervisorWorkspace(component.Component):
    template_name = "dashboard/supervisor_workspace.html"
