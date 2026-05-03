from django_components import component


@component.register("settings_panel")
class SettingsPanel(component.Component):
    template_name = "informaticien/settings_panel.html"

    def get_context_data(self, settings, toast=None):
        return {"settings": settings, "toast": toast}
