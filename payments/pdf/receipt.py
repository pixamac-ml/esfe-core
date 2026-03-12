from io import BytesIO
import os

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle

from django.conf import settings

from payments.services.security import (
    generate_short_hash,
    generate_signature_timestamp
)


def render_pdf(*, payment, inscription, qr_image):

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)

    width, height = A4

    cand = inscription.candidature
    programme = cand.programme

    # ======================================================
    # WATERMARK LOGO (BACKGROUND INSTITUTIONNEL)
    # ======================================================

    watermark_path = os.path.join(
        settings.BASE_DIR,
        "static/institution/logo.png"
    )

    try:

        watermark = ImageReader(watermark_path)

        c.saveState()

        c.translate(width / 2, height / 2)
        c.rotate(25)

        c.setFillAlpha(0.08)

        c.drawImage(
            watermark,
            -120 * mm,
            -120 * mm,
            width=240 * mm,
            preserveAspectRatio=True,
            mask='auto'
        )

        c.restoreState()

    except Exception:
        pass

    # ======================================================
    # HEADER INSTITUTIONNEL
    # ======================================================

    c.setFillColorRGB(0.12, 0.32, 0.45)

    c.rect(
        0,
        height - 60,
        width,
        35,
        fill=1
    )

    c.setFillColorRGB(1, 1, 1)

    c.setFont("Helvetica-Bold", 15)

    c.drawCentredString(
        width / 2,
        height - 40,
        "ÉCOLE DE SANTÉ FÉLIX HOUPHOUËT-BOIGNY"
    )

    c.setFont("Helvetica", 9)

    c.drawCentredString(
        width / 2,
        height - 52,
        "Institution de formation paramédicale — Bamako, Mali"
    )

    # ======================================================
    # LOGO
    # ======================================================

    logo_path = os.path.join(
        settings.BASE_DIR,
        "static/institution/logo.png"
    )

    try:

        c.drawImage(
            logo_path,
            20 * mm,
            height - 55 * mm,
            width=25 * mm,
            mask='auto'
        )

    except Exception:
        pass

    # ======================================================
    # TITRE
    # ======================================================

    c.setFillColorRGB(0, 0, 0)

    c.setFont("Helvetica-Bold", 20)

    c.drawCentredString(
        width / 2,
        height - 95,
        "REÇU OFFICIEL DE PAIEMENT"
    )

    c.setStrokeColor(colors.grey)

    c.line(
        25 * mm,
        height - 105,
        width - 25 * mm,
        height - 105
    )

    # ======================================================
    # METADONNEES DU REÇU
    # ======================================================

    c.setFont("Helvetica", 10)

    start_y = height - 130

    c.drawString(
        25 * mm,
        start_y,
        f"Reçu N° : {payment.receipt_number}"
    )

    c.drawString(
        25 * mm,
        start_y - 10,
        f"Date : {payment.paid_at.strftime('%d/%m/%Y %H:%M')}"
    )

    c.drawString(
        25 * mm,
        start_y - 20,
        f"Référence transaction : {payment.reference or '-'}"
    )

    if getattr(payment, "accounting_reference", None):

        c.drawString(
            25 * mm,
            start_y - 30,
            f"Référence comptable : {payment.accounting_reference}"
        )

    # ======================================================
    # INFORMATIONS CANDIDAT
    # ======================================================

    c.setFont("Helvetica-Bold", 12)

    c.drawString(
        25 * mm,
        height - 200,
        "Informations du candidat"
    )

    c.setFont("Helvetica", 10)

    c.drawString(
        25 * mm,
        height - 215,
        f"Nom : {cand.last_name} {cand.first_name}"
    )

    c.drawString(
        25 * mm,
        height - 225,
        f"Téléphone : {cand.phone}"
    )

    c.drawString(
        25 * mm,
        height - 235,
        f"Email : {cand.email}"
    )

    # ======================================================
    # FORMATION
    # ======================================================

    c.setFont("Helvetica-Bold", 12)

    c.drawString(
        25 * mm,
        height - 260,
        "Formation"
    )

    c.setFont("Helvetica", 10)

    c.drawString(
        25 * mm,
        height - 275,
        f"Programme : {programme.title}"
    )

    c.drawString(
        25 * mm,
        height - 285,
        f"Cycle : {programme.cycle.name} — Filière : {programme.filiere.name}"
    )

    # ======================================================
    # TABLEAU COMPTABLE
    # ======================================================

    table_data = [
        ["Description", "Montant (FCFA)"],
        ["Frais d'inscription", f"{inscription.amount_due}"],
        ["Paiement effectué", f"{payment.amount}"],
        ["Total payé", f"{inscription.amount_paid}"],
        ["Solde restant", f"{inscription.balance}"],
    ]

    table = Table(
        table_data,
        colWidths=[95 * mm, 55 * mm]
    )

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e4f6f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),

        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),

        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),

        ("ALIGN", (1, 1), (-1, -1), "RIGHT")
    ]))

    table.wrapOn(c, width, height)

    table.drawOn(
        c,
        25 * mm,
        height - 380
    )

    # ======================================================
    # QR CODE
    # ======================================================

    qr_reader = ImageReader(qr_image)

    c.setStrokeColor(colors.grey)

    c.rect(
        width - 65 * mm,
        height - 330,
        45 * mm,
        45 * mm
    )

    c.drawImage(
        qr_reader,
        width - 60 * mm,
        height - 325,
        width=35 * mm,
        height=35 * mm
    )

    c.setFont("Helvetica", 8)

    c.drawCentredString(
        width - 43 * mm,
        height - 338,
        "Vérification du dossier"
    )

    # ======================================================
    # SIGNATURE ADMINISTRATIVE
    # ======================================================

    c.setFont("Helvetica", 10)

    c.drawString(
        25 * mm,
        120,
        "Signature administrative"
    )

    c.line(
        25 * mm,
        115,
        90 * mm,
        115
    )

    # ======================================================
    # CACHE NUMERIQUE
    # ======================================================

    hash_code = generate_short_hash(payment)

    timestamp = generate_signature_timestamp()

    c.setFont("Helvetica", 8)

    c.drawString(
        25 * mm,
        80,
        f"Cachet numérique : {hash_code}"
    )

    c.drawString(
        25 * mm,
        70,
        f"Généré le : {timestamp}"
    )

    # ======================================================
    # FOOTER
    # ======================================================

    c.setFont("Helvetica-Oblique", 8)

    c.drawCentredString(
        width / 2,
        40,
        "Document généré automatiquement par le système de gestion académique ESFé."
    )

    c.drawCentredString(
        width / 2,
        30,
        "Ce reçu constitue une preuve officielle de paiement."
    )

    c.showPage()

    c.save()

    buffer.seek(0)

    return buffer.getvalue()