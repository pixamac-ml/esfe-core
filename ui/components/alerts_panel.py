from django_components import component


@component.register("alerts_panel")
class AlertsPanel(component.Component):
    template_name = "components/alerts_panel.html"

    def get_context_data(self, alerts=None, class_watchlist=None, **kwargs):
        return {
            "alerts": alerts or [],
            "class_watchlist": class_watchlist or [],
        }
