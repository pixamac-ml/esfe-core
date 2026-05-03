from django_components import component


@component.register("supervision_panel")
class SupervisionPanel(component.Component):
    template_name = "informaticien/supervision_panel.html"

    def get_context_data(self, alerts):
        return {"alerts": alerts}
