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


# ======================================================
# PDF RECEIPT GENERATOR
# ======================================================

def _safe_text(value, fallback="-"):
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def _fmt_amount(value):
    if value is None:
        return "-"
    return f"{value} FCFA"


def _draw_section_box(pdf, x, top_y, width, height, title):
    pdf.setStrokeColor(colors.HexColor("#D6DFEA"))
    pdf.setLineWidth(0.8)
    pdf.roundRect(x, top_y - height, width, height, 4, stroke=1, fill=0)

    pdf.setFillColor(colors.HexColor("#1D4F79"))
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(x + 8, top_y - 12, title)


def _draw_lines(pdf, x, start_y, lines, gap=10):
    pdf.setFillColor(colors.HexColor("#1F2937"))
    pdf.setFont("Helvetica", 9)
    current_y = start_y
    for line in lines:
        pdf.drawString(x, current_y, _safe_text(line))
        current_y -= gap

def render_pdf(*, payment, inscription, qr_image):

    buffer = BytesIO()

    c = canvas.Canvas(buffer, pagesize=A4)

    width, height = A4

    cand = inscription.candidature
    programme = cand.programme

    margin = 16 * mm
    card_x = margin
    card_y = margin
    card_w = width - (2 * margin)
    card_h = height - (2 * margin)

    c.setFillColor(colors.HexColor("#EEF4FB"))
    c.rect(0, 0, width, height, stroke=0, fill=1)

    c.setFillColor(colors.white)
    c.setStrokeColor(colors.HexColor("#D8E2EF"))
    c.roundRect(card_x, card_y, card_w, card_h, 8, stroke=1, fill=1)

    content_left = card_x + 10 * mm
    content_right = card_x + card_w - 10 * mm
    cursor_top = card_y + card_h - 8 * mm

    # ======================================================
    # [ HEADER ]
    # ======================================================

    logo_path = os.path.join(
        settings.BASE_DIR,
        "static/institution/logo.png"
    )

    try:
        c.drawImage(
            logo_path,
            content_left,
            cursor_top - 24 * mm,
            width=24 * mm,
            height=24 * mm,
            preserveAspectRatio=True,
            mask="auto"
        )
    except Exception:
        pass

    c.setFillColor(colors.HexColor("#1D4F79"))
    c.setFont("Helvetica-Bold", 16)
    c.drawString(content_left + 30 * mm, cursor_top - 6, "RECU OFFICIEL DE PAIEMENT")

    c.setFillColor(colors.HexColor("#4B5563"))
    c.setFont("Helvetica-Bold", 9.5)
    c.drawString(content_left + 30 * mm, cursor_top - 18, "Ecole de Sante Felix Houphouet-Boigny (ESFe)")
    c.setFont("Helvetica", 8.8)
    c.drawString(content_left + 30 * mm, cursor_top - 29, "Excellence - Discipline - Humanite")

    c.setStrokeColor(colors.HexColor("#C9D6E7"))
    c.setLineWidth(1)
    c.line(content_left, cursor_top - 34, content_right, cursor_top - 34)

    cursor_top -= 40

    # ======================================================
    # [ META ]
    # ======================================================

    meta_h = 16 * mm
    meta_w = 72 * mm
    meta_x = content_right - meta_w
    paid_at_text = payment.paid_at.strftime('%d/%m/%Y %H:%M') if getattr(payment, 'paid_at', None) else '-'

    _draw_section_box(c, meta_x, cursor_top, meta_w, meta_h, "META")
    _draw_lines(
        c,
        meta_x + 8,
        cursor_top - 22,
        [
            f"Recu : {_safe_text(payment.receipt_number)}",
            f"Ref : {_safe_text(payment.reference, _safe_text(payment.receipt_number))}",
            f"Date : {paid_at_text}",
        ],
        gap=9,
    )

    cursor_top -= meta_h + 6

    # ======================================================
    # [ INFOS STRUCTURE ]
    # ======================================================

    structure_h = 24 * mm
    _draw_section_box(c, content_left, cursor_top, card_w - 20 * mm, structure_h, "INFOS STRUCTURE")
    _draw_lines(
        c,
        content_left + 8,
        cursor_top - 22,
        [
            "Nom de l'etablissement : Ecole de Sante Felix Houphouet-Boigny (ESFe)",
            "Annexe / Campus : Campus principal",
            "Ville : Bamako",
            "Coordonnees : Non renseignees",
        ],
    )

    cursor_top -= structure_h + 6

    # ======================================================
    # [ INFOS CLIENT ]
    # ======================================================

    client_h = 23 * mm
    client_name = f"{_safe_text(getattr(cand, 'last_name', None), '')} {_safe_text(getattr(cand, 'first_name', None), '')}".strip() or "Non renseigne"
    _draw_section_box(c, content_left, cursor_top, card_w - 20 * mm, client_h, "INFOS CLIENT")
    _draw_lines(
        c,
        content_left + 8,
        cursor_top - 22,
        [
            f"Nom complet : {client_name}",
            f"Email : {_safe_text(getattr(cand, 'email', None), 'Non renseigne')}",
            f"Telephone : {_safe_text(getattr(cand, 'phone', None), 'Non renseigne')}",
        ],
    )

    cursor_top -= client_h + 6

    # ======================================================
    # [ INFOS AGENT ]
    # ======================================================

    agent_name = "Systeme ESFe"
    if getattr(payment, 'agent', None):
        if getattr(payment.agent, 'user', None):
            full_name = _safe_text(payment.agent.user.get_full_name(), "")
            if full_name:
                agent_name = full_name
        if agent_name == "Systeme ESFe":
            agent_name = _safe_text(getattr(payment.agent, 'agent_code', None), "Systeme ESFe")

    agent_h = 11 * mm
    _draw_section_box(c, content_left, cursor_top, card_w - 20 * mm, agent_h, "INFOS AGENT")
    _draw_lines(c, content_left + 8, cursor_top - 19, [f"Genere par : {agent_name}"], gap=9)

    cursor_top -= agent_h + 7

    # ======================================================
    # [ TABLEAU PRINCIPAL ]
    # ======================================================

    table_w = card_w - 20 * mm
    table_h = 46 * mm
    table_data = [
        ["Designation", "Detail", "Montant"],
        ["Paiement valide", _safe_text(getattr(programme, 'title', None), 'Inscription'), _fmt_amount(payment.amount)],
        ["Detail", f"{_safe_text(payment.get_method_display())} - {_safe_text(payment.get_status_display())}", "-"],
        ["Reference unique", _safe_text(payment.reference, _safe_text(payment.receipt_number)), "-"],
        ["Solde restant", "Situation actualisee de l'inscription", _fmt_amount(getattr(inscription, 'balance', None))],
    ]

    _draw_section_box(c, content_left, cursor_top, table_w, table_h, "TABLEAU PRINCIPAL")
    table = Table(table_data, colWidths=[70 * mm, 76 * mm, table_w - (146 * mm)])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F2F7FC")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1D4F79")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#D6DFEA")),
        ("ALIGN", (0, 0), (1, -1), "LEFT"),
        ("ALIGN", (2, 0), (2, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
    ]))
    table.wrapOn(c, table_w - 12, table_h - 16)
    table.drawOn(c, content_left + 6, cursor_top - table_h + 7)

    cursor_top -= table_h + 7

    # ======================================================
    # [ TOTAL ]
    # ======================================================

    total_h = 14 * mm
    total_w = 78 * mm
    total_x = content_right - total_w
    c.setFillColor(colors.HexColor("#F3F7FC"))
    c.setStrokeColor(colors.HexColor("#C8D8EA"))
    c.roundRect(total_x, cursor_top - total_h, total_w, total_h, 4, stroke=1, fill=1)
    c.setFillColor(colors.HexColor("#1D4F79"))
    c.setFont("Helvetica-Bold", 9)
    c.drawString(total_x + 8, cursor_top - 12, "TOTAL PAYE")
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(total_x + total_w - 8, cursor_top - 12, _fmt_amount(payment.amount))

    cursor_top -= total_h + 6

    # ======================================================
    # [ QR CODE ]
    # ======================================================

    qr_h = 34 * mm
    qr_w = 48 * mm
    qr_x = content_right - qr_w
    _draw_section_box(c, qr_x, cursor_top, qr_w, qr_h, "QR CODE")

    try:
        qr_reader = ImageReader(qr_image)
        c.drawImage(
            qr_reader,
            qr_x + 8,
            cursor_top - qr_h + 8,
            width=30 * mm,
            height=30 * mm,
            preserveAspectRatio=True,
            mask="auto"
        )
    except Exception:
        c.setFillColor(colors.HexColor("#94A3B8"))
        c.setFont("Helvetica", 8)
        c.drawString(qr_x + 8, cursor_top - 22, "QR indisponible")

    c.setFillColor(colors.HexColor("#6B7280"))
    c.setFont("Helvetica", 7.5)
    c.drawRightString(content_right, cursor_top - qr_h - 3, "Verification du dossier")

    # ======================================================
    # [ FOOTER ]
    # ======================================================

    hash_code = generate_short_hash(payment)

    timestamp = generate_signature_timestamp()

    footer_y = card_y + 8 * mm
    c.setStrokeColor(colors.HexColor("#D6DFEA"))
    c.setLineWidth(0.8)
    c.line(content_left, footer_y + 10, content_right, footer_y + 10)

    c.setFillColor(colors.HexColor("#6B7280"))
    c.setFont("Helvetica", 8)
    c.drawString(content_left, footer_y + 1, f"Cachet numerique : {hash_code}")
    c.drawString(content_left, footer_y - 8, f"Signature generee le : {timestamp}")

    c.setFont("Helvetica-Oblique", 8)
    c.drawRightString(content_right, footer_y + 1, "Merci pour votre confiance")
    c.drawRightString(content_right, footer_y - 8, "Document genere automatiquement - Copyright ESFe")

    c.showPage()
    c.save()

    buffer.seek(0)

    return buffer.getvalue()