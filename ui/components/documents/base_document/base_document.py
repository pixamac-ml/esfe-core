from django_components import component


@component.register("esfe_document_base")
class BaseDocument(component.Component):
    template_name = "documents/base_document/base_document.html"

    def get_context_data(
        self,
        title="DOCUMENT",
        document_type="",
        receipt_number="",
        date="",
        academic_year="",
        meta_lines=None,
        sections=None,
        total_label="Montant Total",
        total_amount="",
        payment_method="",
        payment_reference="",
        signature_label="Signature",
        stamp_label="Cachet de l'école",
        legal_text="Ce document constitue une preuve officielle.",
        footer_extra="",
        **kwargs,
    ):
        if meta_lines is None:
            meta_lines = []
        if sections is None:
            sections = []
        return {
            "title": title,
            "document_type": document_type,
            "receipt_number": receipt_number,
            "date": date,
            "academic_year": academic_year,
            "meta_lines": meta_lines,
            "sections": sections,
            "total_label": total_label,
            "total_amount": total_amount,
            "payment_method": payment_method,
            "payment_reference": payment_reference,
            "signature_label": signature_label,
            "stamp_label": stamp_label,
            "legal_text": legal_text,
            "footer_extra": footer_extra,
            **kwargs,
        }
