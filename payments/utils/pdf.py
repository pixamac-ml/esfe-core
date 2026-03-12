from io import BytesIO
import os

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.lib import colors

from django.conf import settings

from payments.services.security import (
    generate_short_hash,
    generate_signature_timestamp
)


# ======================================================
# PDF RECEIPT GENERATOR
# ======================================================

def render_pdf(*, payment, inscription, qr_image):

    buffer = BytesIO()

    c = canvas.Canvas(buffer, pagesize=A4)

    width, height = A4

    cand = inscription.candidature
    programme = cand.programme

    # ======================================================
    # LOGO INSTITUTION
    # ======================================================

    logo_path = os.path.join(
        settings.BASE_DIR,
        "static/institution/logo.png"
    )

    try:
        c.drawImage(
            logo_path,
            25 * mm,
            height - 35 * mm,
            width=28 * mm,
            preserveAspectRatio=True,
            mask="auto"
        )
    except Exception:
        pass

    # ======================================================
    # TITRE
    # ======================================================

    c.setFont("Helvetica-Bold", 18)
    c.drawString(
        60 * mm,
        height - 25 * mm,
        "REÇU OFFICIEL DE PAIEMENT"
    )

    c.setFont("Helvetica", 10)

    c.drawString(
        60 * mm,
        height - 33 * mm,
        "École de Santé Félix Houphouët-Boigny (ESFé)"
    )

    c.drawString(
        60 * mm,
        height - 39 * mm,
        "Institution de formation paramédicale - Bamako, Mali"
    )

    c.setStrokeColor(colors.grey)
    c.line(25 * mm, height - 45 * mm, width - 25 * mm, height - 45 * mm)

    # ======================================================
    # META REÇU
    # ======================================================

    c.setFont("Helvetica", 10)

    c.drawString(
        140 * mm,
        height - 30 * mm,
        f"Reçu N° : {payment.receipt_number}"
    )

    c.drawString(
        140 * mm,
        height - 36 * mm,
        f"Date : {payment.paid_at.strftime('%d/%m/%Y %H:%M')}"
    )

    c.drawString(
        140 * mm,
        height - 42 * mm,
        f"Référence paiement : {payment.reference or '-'}"
    )

    if hasattr(payment, "accounting_reference"):
        c.drawString(
            140 * mm,
            height - 48 * mm,
            f"Enregistrement comptable : {payment.accounting_reference}"
        )

    # ======================================================
    # CANDIDAT
    # ======================================================

    c.setFont("Helvetica-Bold", 12)

    c.drawString(
        25 * mm,
        height - 65 * mm,
        "Informations du candidat"
    )

    c.setFont("Helvetica", 10)

    c.drawString(
        25 * mm,
        height - 73 * mm,
        f"Nom : {cand.last_name} {cand.first_name}"
    )

    c.drawString(
        25 * mm,
        height - 80 * mm,
        f"Téléphone : {cand.phone}"
    )

    c.drawString(
        25 * mm,
        height - 87 * mm,
        f"Email : {cand.email}"
    )

    # ======================================================
    # FORMATION
    # ======================================================

    c.setFont("Helvetica-Bold", 12)

    c.drawString(
        25 * mm,
        height - 105 * mm,
        "Formation"
    )

    c.setFont("Helvetica", 10)

    c.drawString(
        25 * mm,
        height - 113 * mm,
        f"Programme : {programme.title}"
    )

    c.drawString(
        25 * mm,
        height - 120 * mm,
        f"Cycle : {programme.cycle.name} — Filière : {programme.filiere.name}"
    )

    # ======================================================
    # PAIEMENT
    # ======================================================

    c.setFont("Helvetica-Bold", 12)

    c.drawString(
        25 * mm,
        height - 140 * mm,
        "Détails du paiement"
    )

    c.setFont("Helvetica", 10)

    c.drawString(
        25 * mm,
        height - 148 * mm,
        f"Montant payé : {payment.amount} FCFA"
    )

    c.drawString(
        25 * mm,
        height - 155 * mm,
        f"Méthode : {payment.get_method_display()}"
    )

    c.drawString(
        25 * mm,
        height - 162 * mm,
        f"Statut : {payment.get_status_display()}"
    )

    # ======================================================
    # SITUATION FINANCIÈRE
    # ======================================================

    c.setFont("Helvetica-Bold", 12)

    c.drawString(
        25 * mm,
        height - 180 * mm,
        "Situation financière"
    )

    c.setFont("Helvetica", 10)

    c.drawString(
        25 * mm,
        height - 188 * mm,
        f"Total inscription : {inscription.amount_due} FCFA"
    )

    c.drawString(
        25 * mm,
        height - 195 * mm,
        f"Total payé : {inscription.amount_paid} FCFA"
    )

    c.drawString(
        25 * mm,
        height - 202 * mm,
        f"Solde restant : {inscription.balance} FCFA"
    )

    # ======================================================
    # QR CODE
    # ======================================================

    qr_reader = ImageReader(qr_image)

    c.drawImage(
        qr_reader,
        width - 60 * mm,
        height - 175 * mm,
        width=35 * mm,
        height=35 * mm,
        preserveAspectRatio=True
    )

    c.setFont("Helvetica", 8)

    c.drawString(
        width - 65 * mm,
        height - 180 * mm,
        "Vérification du dossier"
    )

    # ======================================================
    # SIGNATURE NUMÉRIQUE
    # ======================================================

    hash_code = generate_short_hash(payment)

    timestamp = generate_signature_timestamp()

    c.setFont("Helvetica", 8)

    c.drawString(
        25 * mm,
        30 * mm,
        f"Cachet numérique : {hash_code}"
    )

    c.drawString(
        25 * mm,
        24 * mm,
        f"Signature générée le : {timestamp}"
    )

    # ======================================================
    # SIGNATURE ADMIN
    # ======================================================

    c.setFont("Helvetica", 10)

    c.drawString(
        25 * mm,
        50 * mm,
        "Signature administrative"
    )

    c.line(25 * mm, 45 * mm, 80 * mm, 45 * mm)

    # ======================================================
    # FOOTER
    # ======================================================

    c.setFont("Helvetica-Oblique", 8)

    c.drawString(
        25 * mm,
        15 * mm,
        "Document généré automatiquement par le système de gestion académique ESFé."
    )

    c.showPage()
    c.save()

    buffer.seek(0)

    return buffer.getvalue()