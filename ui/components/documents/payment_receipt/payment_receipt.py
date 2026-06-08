from django_components import component


@component.register("esfe_receipt")
class PaymentReceipt(component.Component):
    template_name = "documents/payment_receipt/payment_receipt.html"

    def get_context_data(
        self,
        receipt_number="",
        date="",
        academic_year="",
        student_name="",
        student_matricule="",
        programme="",
        level="",
        items=None,
        total_amount="",
        payment_method="",
        payment_reference="",
        legal_text="Ce reçu constitue une preuve officielle de paiement.",
        **kwargs,
    ):
        if items is None:
            items = []
        return {
            "title": "REÇU DE PAIEMENT",
            "receipt_number": receipt_number,
            "date": date,
            "academic_year": academic_year,
            "student_name": student_name,
            "student_matricule": student_matricule,
            "programme": programme,
            "level": level,
            "items": items,
            "total_amount": total_amount,
            "payment_method": payment_method,
            "payment_reference": payment_reference,
            "legal_text": legal_text,
            **kwargs,
        }
