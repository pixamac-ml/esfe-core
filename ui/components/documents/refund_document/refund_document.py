from django_components import component


@component.register("esfe_refund")
class RefundDocument(component.Component):
    template_name = "documents/refund_document/refund_document.html"

    def get_context_data(
        self,
        refund_number="",
        date="",
        recipient_name="",
        recipient_type="Client",
        original_receipt="",
        reason="",
        items=None,
        total_amount="",
        payment_method="",
        payment_reference="",
        **kwargs,
    ):
        if items is None:
            items = []
        return {
            "title": "REMBOURSEMENT",
            "refund_number": refund_number,
            "date": date,
            "recipient_name": recipient_name,
            "recipient_type": recipient_type,
            "original_receipt": original_receipt,
            "reason": reason,
            "items": items,
            "total_amount": total_amount,
            "payment_method": payment_method,
            "payment_reference": payment_reference,
            **kwargs,
        }
