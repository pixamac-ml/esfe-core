from django_components import component


@component.register("ui_core.app_shell")
class AppShell(component.Component):
    template_name = "ui_core/layout/app_shell.html"

    def get_context_data(self, title="ESFE", sidebar_open=True, **kwargs):
        return {"title": title, "sidebar_open": sidebar_open, **kwargs}
