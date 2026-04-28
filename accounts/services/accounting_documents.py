from io import BytesIO

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle

from accounts.models import AccountingDocumentSequence, BranchCashMovement


PREFIX_BY_TYPE = {
    AccountingDocumentSequence.DOCUMENT_EXPENSE: "DEP",
    AccountingDocumentSequence.DOCUMENT_CASH: "CAI",
}


def _branch_code(branch):
    return (getattr(branch, "code", "") or "GEN").upper()


def next_accounting_reference(branch, document_type, *, document_date=None):
    document_date = document_date or timezone.localdate()
    year = document_date.year
    with transaction.atomic():
        sequence, _ = (
            AccountingDocumentSequence.objects
            .select_for_update()
            .get_or_create(
                branch=branch,
                document_type=document_type,
                year=year,
                defaults={"last_number": 0},
            )
        )
        sequence.last_number += 1
        sequence.save(update_fields=["last_number", "updated_at"])
    prefix = PREFIX_BY_TYPE[document_type]
    return f"{prefix}-{_branch_code(branch)}-{year}-{sequence.last_number:06d}"


def ensure_expense_reference(expense):
    if expense.reference:
        return expense.reference
    expense.reference = next_accounting_reference(
        expense.branch,
        AccountingDocumentSequence.DOCUMENT_EXPENSE,
        document_date=expense.expense_date,
    )
    expense.save(update_fields=["reference", "updated_at"])
    return expense.reference


def ensure_cash_movement_reference(movement):
    updates = []
    if not movement.reference:
        movement.reference = next_accounting_reference(
            movement.branch,
            AccountingDocumentSequence.DOCUMENT_CASH,
            document_date=movement.movement_date,
        )
        updates.append("reference")
    if not movement.receipt_number:
        movement.receipt_number = movement.reference
        updates.append("receipt_number")
    if updates:
        movement.save(update_fields=updates)
    return movement.reference


def _safe(value, fallback="-"):
    if value is None:
        return fallback
    text = str(value).strip()
    return text or fallback


def _money(value):
    return f"{value or 0:,} FCFA".replace(",", " ")


def render_cash_movement_receipt_pdf(movement):
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    margin = 16 * mm
    content_w = width - (2 * margin)
    top = height - margin

    pdf.setFillColor(colors.HexColor("#EEF4FB"))
    pdf.rect(0, 0, width, height, fill=1, stroke=0)
    pdf.setFillColor(colors.white)
    pdf.setStrokeColor(colors.HexColor("#D8E2EF"))
    pdf.roundRect(margin, margin, content_w, height - (2 * margin), 8, fill=1, stroke=1)

    x = margin + 10 * mm
    right = width - margin - 10 * mm
    y = top - 10 * mm

    pdf.setFillColor(colors.HexColor("#1D4F79"))
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(x, y, "PIECE DE CAISSE")
    pdf.setFont("Helvetica", 9)
    pdf.setFillColor(colors.HexColor("#4B5563"))
    pdf.drawString(x, y - 14, "Ecole de Sante Felix Houphouet-Boigny (ESFe)")

    pdf.setFont("Helvetica-Bold", 10)
    pdf.setFillColor(colors.HexColor("#1F2937"))
    pdf.drawRightString(right, y, _safe(movement.receipt_number or movement.reference))
    pdf.setFont("Helvetica", 9)
    pdf.drawRightString(right, y - 14, movement.created_at.strftime("%d/%m/%Y %H:%M"))
    y -= 34

    table_data = [
        ["Champ", "Valeur"],
        ["Annexe", _safe(movement.branch.name)],
        ["Reference comptable", _safe(movement.reference)],
        ["Type", movement.get_movement_type_display()],
        ["Source", movement.get_source_display()],
        ["Date operation", movement.movement_date.strftime("%d/%m/%Y")],
        ["Libelle", _safe(movement.label)],
        ["Montant", _money(movement.amount)],
        ["Agent", _safe(movement.created_by.get_full_name() if movement.created_by_id else "")],
        ["Observation", _safe(movement.notes)],
    ]
    table = Table(table_data, colWidths=[48 * mm, content_w - 68 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F2F7FC")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1D4F79")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#D6DFEA")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    table.wrapOn(pdf, content_w - 20 * mm, y)
    table.drawOn(pdf, x, y - 88 * mm)

    footer_y = margin + 18 * mm
    pdf.setStrokeColor(colors.HexColor("#D6DFEA"))
    pdf.line(x, footer_y + 10, right, footer_y + 10)
    pdf.setFillColor(colors.HexColor("#6B7280"))
    pdf.setFont("Helvetica", 8)
    pdf.drawString(x, footer_y, "Document genere automatiquement par ESFe.")
    pdf.drawRightString(right, footer_y, "Signature / cachet")
    pdf.line(right - 45 * mm, footer_y + 22, right, footer_y + 22)

    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()


def ensure_cash_movement_receipt(movement):
    ensure_cash_movement_reference(movement)
    if movement.receipt_pdf:
        return movement.receipt_pdf
    pdf_bytes = render_cash_movement_receipt_pdf(movement)
    movement.receipt_pdf.save(
        f"piece-caisse-{movement.receipt_number}.pdf",
        ContentFile(pdf_bytes),
        save=True,
    )
    return movement.receipt_pdf


def finalize_cash_movement_document(movement):
    ensure_cash_movement_reference(movement)
    ensure_cash_movement_receipt(movement)
    return movement


def create_cash_movement(**kwargs):
    movement = BranchCashMovement.objects.create(**kwargs)
    return finalize_cash_movement_document(movement)
