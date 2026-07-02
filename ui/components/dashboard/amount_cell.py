from django_components import component


@component.register("amount_cell")
class AmountCell(component.Component):
    template_name = "dashboard/amount_cell.html"

    def get_context_data(self, value="", currency="FCFA", tone="neutral", **kwargs):
        return {
            "value": value,
            "currency": currency,
            "tone": tone,
            **kwargs,
        }
