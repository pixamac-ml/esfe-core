from django_components import component


@component.register("formation_finance")
class FormationFinance(component.Component):
    template_name = "formation_finance/formation_finance.html"

    def get_context_data(self, years_with_totals):
        return {
            "years_with_totals": years_with_totals,

        }
