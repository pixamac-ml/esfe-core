from django_components import component


@component.register("inscription_finance")
class InscriptionFinance(component.Component):
    template_name = "inscription_finance/inscription_finance.html"

    def get_context_data(
        self,
        inscription,
        payments,
        can_pay,
        has_pending_payment,
        payment_form,
    ):
        return {
            "inscription": inscription,
            "payments": payments,
            "can_pay": can_pay,
            "has_pending_payment": has_pending_payment,
            "payment_form": payment_form,
        }
