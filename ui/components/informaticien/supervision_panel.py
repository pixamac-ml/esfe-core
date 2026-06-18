from django_components import component


@component.register("supervision_panel")
class SupervisionPanel(component.Component):
    template_name = "informaticien/supervision_panel.html"

    def get_context_data(self, alerts, alerts_page=None):
        return {"alerts": alerts, "alerts_page": alerts_page}
