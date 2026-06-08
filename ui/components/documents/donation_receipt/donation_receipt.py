from django_components import component


@component.register("esfe_donation_receipt")
class DonationReceipt(component.Component):
    template_name = "documents/donation_receipt/donation_receipt.html"

    def get_context_data(
        self,
        receipt_number="",
        date="",
        donor_name="",
        amount="",
        motif="",
        payment_method="",
        payment_reference="",
        branch_name="",
        description="",
        **kwargs,
    ):
        return {
            "title": "REÇU DE DON",
            "receipt_number": receipt_number,
            "date": date,
            "donor_name": donor_name,
            "amount": amount,
            "motif": motif,
            "payment_method": payment_method,
            "payment_reference": payment_reference,
            "branch_name": branch_name,
            "description": description,
            **kwargs,
        }
