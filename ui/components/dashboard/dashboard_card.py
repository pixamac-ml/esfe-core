from django_components import component


@component.register("dashboard_card")
class DashboardCard(component.Component):
    template_name = "dashboard/dashboard_card.html"

    def get_context_data(self, padding="md", elevated=False, extra_class="", **kwargs):
        return {
            "padding": padding,
            "elevated": elevated,
            "extra_class": extra_class,
            **kwargs,
        }

