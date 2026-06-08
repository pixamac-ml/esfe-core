from django.core.files.base import ContentFile

from core.pdf_documents import generate_pdf as generate_esfe_pdf


def build_donation_receipt(donation):
    pdf_bytes = generate_esfe_pdf("esfe_donation_receipt", {
        "receipt_number": donation.receipt_number or str(donation.id),
        "date": donation.date.strftime("%d %B %Y"),
        "donor_name": donation.donor_name,
        "amount": f"{donation.amount:,}".replace(",", " "),
        "motif": donation.get_motif_display() if hasattr(donation, "get_motif_display") else donation.motif,
        "payment_method": donation.get_payment_method_display() if hasattr(donation, "get_payment_method_display") else donation.payment_method,
        "payment_reference": getattr(donation, "payment_reference", ""),
        "branch_name": donation.branch.name if donation.branch_id else "",
        "description": donation.description or "",
    })
    return pdf_bytes


def ensure_donation_receipt(donation):
    if donation.receipt_pdf:
        return donation.receipt_pdf
    pdf_bytes = build_donation_receipt(donation)
    filename = f"don-{donation.receipt_number or donation.id}.pdf"
    donation.receipt_pdf.save(filename, ContentFile(pdf_bytes), save=True)
    return donation.receipt_pdf
