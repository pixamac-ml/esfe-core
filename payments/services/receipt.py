# payments/services/receipt.py

from django.utils import timezone


def generate_receipt_number(payment):
    """
    Génère un numéro de reçu UNIQUE.

    Format :
    ESFE-2026-000001
    """

    year = timezone.now().year
    payment_id = payment.id or 0

    return f"ESFE-{year}-{payment_id:06d}"


from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4


def build_receipt_pdf(response, receipt, qr_image):
    c = canvas.Canvas(response, pagesize=A4)

    # QR CODE
    c.drawImage(
        qr_image,
        x=450,
        y=100,
        width=100,
        height=100
    )

    c.showPage()
    c.save()
