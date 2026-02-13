# payments/utils/pdf.py

from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader


def render_pdf(*, payment, inscription, qr_image):
    """
    Génère un reçu PDF officiel ESFE.
    Retourne les bytes du PDF.
    """

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # =========================
    # EN-TÊTE
    # =========================
    c.setFont("Helvetica-Bold", 16)
    c.drawString(30 * mm, height - 30 * mm, "REÇU DE PAIEMENT")

    c.setFont("Helvetica", 10)
    c.drawString(30 * mm, height - 38 * mm, "École Supérieure de Formation en Santé (ESFE)")
    c.drawString(30 * mm, height - 46 * mm, f"Reçu n° : {payment.receipt_number}")
    c.drawString(30 * mm, height - 53 * mm, f"Date : {payment.paid_at.strftime('%d/%m/%Y %H:%M')}")

    # =========================
    # CANDIDAT
    # =========================
    cand = inscription.candidature

    c.setFont("Helvetica-Bold", 12)
    c.drawString(30 * mm, height - 70 * mm, "Informations du candidat")

    c.setFont("Helvetica", 10)
    c.drawString(30 * mm, height - 78 * mm, f"Nom : {cand.last_name} {cand.first_name}")
    c.drawString(30 * mm, height - 85 * mm, f"Téléphone : {cand.phone}")
    c.drawString(30 * mm, height - 92 * mm, f"Email : {cand.email}")

    # =========================
    # FORMATION
    # =========================
    programme = cand.programme

    c.setFont("Helvetica-Bold", 12)
    c.drawString(30 * mm, height - 108 * mm, "Formation")

    c.setFont("Helvetica", 10)
    c.drawString(30 * mm, height - 116 * mm, programme.title)
    c.drawString(
        30 * mm,
        height - 123 * mm,
        f"{programme.cycle.name} — {programme.filiere.name}"
    )

    # =========================
    # PAIEMENT
    # =========================
    c.setFont("Helvetica-Bold", 12)
    c.drawString(30 * mm, height - 140 * mm, "Détails du paiement")

    c.setFont("Helvetica", 10)
    c.drawString(30 * mm, height - 148 * mm, f"Montant payé : {payment.amount} FCFA")
    c.drawString(30 * mm, height - 155 * mm, f"Méthode : {payment.get_method_display()}")

    # =========================
    # QR CODE
    # =========================
    qr_reader = ImageReader(qr_image)
    c.drawImage(
        qr_reader,
        width - 60 * mm,
        height - 165 * mm,
        width=30 * mm,
        height=30 * mm,
        preserveAspectRatio=True
    )

    c.setFont("Helvetica", 8)
    c.drawString(
        width - 65 * mm,
        height - 170 * mm,
        "Lien officiel d’inscription"
    )

    # =========================
    # PIED DE PAGE
    # =========================
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(
        30 * mm,
        20 * mm,
        "Document généré automatiquement par le système ESFE."
    )

    c.showPage()
    c.save()

    buffer.seek(0)
    return buffer.getvalue()
