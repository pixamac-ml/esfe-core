from django_components import component


@component.register("esfe_shop_invoice")
class ShopInvoice(component.Component):
    template_name = "documents/shop_invoice/shop_invoice.html"

    def get_context_data(
        self,
        invoice_number="",
        date="",
        customer_name="",
        customer_email="",
        customer_phone="",
        branch_name="",
        items=None,
        total_amount="",
        payment_method="",
        payment_reference="",
        **kwargs,
    ):
        if items is None:
            items = []
        return {
            "title": "FACTURE D'ACHAT",
            "invoice_number": invoice_number,
            "date": date,
            "customer_name": customer_name,
            "customer_email": customer_email,
            "customer_phone": customer_phone,
            "branch_name": branch_name,
            "items": items,
            "total_amount": total_amount,
            "payment_method": payment_method,
            "payment_reference": payment_reference,
            **kwargs,
        }
