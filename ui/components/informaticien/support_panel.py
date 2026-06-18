from django_components import component


@component.register("support_panel")
class SupportPanel(component.Component):
    template_name = "informaticien/support_panel.html"

    def get_context_data(self, tickets, status_choices, status="", toast=None, tickets_page=None):
        return {
            "tickets": tickets,
            "status_choices": status_choices,
            "status": status,
            "toast": toast,
            "tickets_page": tickets_page,
        }
