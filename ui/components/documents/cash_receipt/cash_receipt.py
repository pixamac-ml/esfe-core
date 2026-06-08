from django_components import component


@component.register("esfe_cash_receipt")
class CashReceipt(component.Component):
    template_name = "documents/cash_receipt/cash_receipt.html"

    def get_context_data(
        self,
        receipt_number="",
        reference="",
        date="",
        branch_name="",
        movement_type="",
        source="",
        operation_date="",
        label="",
        amount="",
        agent="",
        notes="",
        **kwargs,
    ):
        return {
            "title": "PIÈCE DE CAISSE",
            "receipt_number": receipt_number,
            "reference": reference,
            "date": date,
            "branch_name": branch_name,
            "movement_type": movement_type,
            "source": source,
            "operation_date": operation_date,
            "label": label,
            "amount": amount,
            "agent": agent,
            "notes": notes,
            **kwargs,
        }
