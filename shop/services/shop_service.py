from io import BytesIO

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle

from accounts.models import BranchCashMovement
from accounts.services.accounting_documents import create_cash_movement
from shop.models import (
    ShopOrder,
    ShopOrderItem,
    ShopPayment,
    ShopProduct,
    ShopSequence,
    ShopStockMovement,
)


PREFIX_BY_SEQUENCE = {
    ShopSequence.TYPE_ORDER: "CMD",
    ShopSequence.TYPE_PAYMENT: "RVS",
    ShopSequence.TYPE_STOCK: "STK",
}


def _branch_code(branch):
    return (getattr(branch, "code", "") or "GEN").upper()


def next_shop_reference(branch, sequence_type, *, document_date=None):
    document_date = document_date or timezone.localdate()
    with transaction.atomic():
        sequence, _ = (
            ShopSequence.objects
            .select_for_update()
            .get_or_create(
                branch=branch,
                sequence_type=sequence_type,
                year=document_date.year,
                defaults={"last_number": 0},
            )
        )
        sequence.last_number += 1
        sequence.save(update_fields=["last_number", "updated_at"])
    return f"{PREFIX_BY_SEQUENCE[sequence_type]}-{_branch_code(branch)}-{document_date.year}-{sequence.last_number:06d}"


def get_recommended_products_for_student(user):
    student = getattr(user, "student_profile", None)
    if not student:
        return []
    inscription = student.inscription
    candidature = inscription.candidature
    queryset = (
        ShopProduct.objects
        .filter(branch=candidature.branch, is_active=True)
        .prefetch_related("variants", "programmes")
        .order_by("-is_required", "category", "name")
    )
    products = []
    for product in queryset:
        if product.programmes.exists() and not product.programmes.filter(pk=candidature.programme_id).exists():
            continue
        products.append(product)
    return products


def get_required_shop_context(user):
    student = getattr(user, "student_profile", None)
    if not student:
        return {"show_popup": False, "products": [], "open_orders": [], "required_missing_count": 0}
    products = get_recommended_products_for_student(user)
    required_products = [product for product in products if product.is_required]
    open_orders = list(
        ShopOrder.objects
        .filter(student=user)
        .exclude(status__in=[ShopOrder.STATUS_DELIVERED, ShopOrder.STATUS_CANCELLED])
        .prefetch_related("items", "items__product", "items__variant")
        .order_by("-created_at")[:5]
    )
    covered_product_ids = set()
    for order in open_orders:
        for item in order.items.all():
            if order.status in {ShopOrder.STATUS_PAID, ShopOrder.STATUS_READY, ShopOrder.STATUS_DELIVERED, ShopOrder.STATUS_PENDING_PAYMENT}:
                covered_product_ids.add(item.product_id)
    missing_required = [product for product in required_products if product.id not in covered_product_ids]
    return {
        "show_popup": bool(missing_required),
        "products": products,
        "required_products": required_products,
        "missing_required": missing_required,
        "open_orders": open_orders,
        "required_missing_count": len(missing_required),
    }


def create_student_required_order(user, product_ids, created_by=None):
    student = user.student_profile
    inscription = student.inscription
    branch = inscription.candidature.branch
    products = list(
        ShopProduct.objects
        .filter(branch=branch, is_active=True, id__in=product_ids)
        .prefetch_related("variants")
    )
    if not products:
        return None
    with transaction.atomic():
        order = ShopOrder.objects.create(
            branch=branch,
            inscription=inscription,
            student=user,
            reference=next_shop_reference(branch, ShopSequence.TYPE_ORDER),
            status=ShopOrder.STATUS_PENDING_PAYMENT,
            created_by=created_by or user,
        )
        for product in products:
            variant = product.variants.filter(is_active=True).first()
            unit_price = variant.final_price if variant else product.unit_price
            ShopOrderItem.objects.create(
                order=order,
                product=product,
                variant=variant,
                quantity=1,
                unit_price=unit_price,
                is_required=product.is_required,
            )
        order.refresh_total()
    return order


def render_shop_receipt_pdf(payment):
    order = payment.order
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    margin = 16 * mm
    content_w = width - (2 * margin)
    y = height - margin - 8 * mm
    x = margin + 8 * mm

    pdf.setFillColor(colors.HexColor("#EEF4FB"))
    pdf.rect(0, 0, width, height, fill=1, stroke=0)
    pdf.setFillColor(colors.white)
    pdf.setStrokeColor(colors.HexColor("#D8E2EF"))
    pdf.roundRect(margin, margin, content_w, height - (2 * margin), 8, fill=1, stroke=1)

    pdf.setFillColor(colors.HexColor("#1D4F79"))
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(x, y, "RECU BOUTIQUE ECOLE")
    pdf.setFont("Helvetica", 9)
    pdf.setFillColor(colors.HexColor("#4B5563"))
    pdf.drawString(x, y - 14, "Articles scolaires et fournitures ESFe")
    pdf.setFont("Helvetica-Bold", 10)
    pdf.setFillColor(colors.HexColor("#1F2937"))
    pdf.drawRightString(width - margin - 8 * mm, y, payment.receipt_number or payment.reference)
    y -= 34

    student_name = order.student.get_full_name() or order.student.username
    meta = [
        ["Commande", order.reference],
        ["Etudiant", student_name],
        ["Annexe", order.branch.name],
        ["Mode paiement", payment.get_method_display()],
        ["Date", payment.paid_at.strftime("%d/%m/%Y %H:%M")],
    ]
    table = Table([["Champ", "Valeur"], *meta], colWidths=[42 * mm, content_w - 58 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F2F7FC")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D6DFEA")),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    table.wrapOn(pdf, content_w, y)
    table.drawOn(pdf, x, y - 48 * mm)
    y -= 60 * mm

    rows = [["Article", "Qté", "PU", "Total"]]
    for item in order.items.select_related("product", "variant"):
        label = item.product.name
        if item.variant:
            label = f"{label} ({item.variant.label})"
        rows.append([label, str(item.quantity), f"{item.unit_price} FCFA", f"{item.line_total} FCFA"])
    rows.append(["TOTAL", "", "", f"{payment.amount} FCFA"])
    items_table = Table(rows, colWidths=[82 * mm, 18 * mm, 34 * mm, content_w - 150 * mm])
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F2F7FC")),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F8FAFC")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D6DFEA")),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    items_table.wrapOn(pdf, content_w, y)
    items_table.drawOn(pdf, x, y - (18 + len(rows) * 9) * mm)

    pdf.setFillColor(colors.HexColor("#6B7280"))
    pdf.setFont("Helvetica", 8)
    pdf.drawString(x, margin + 10 * mm, "Document genere automatiquement. A presenter lors du retrait des articles.")
    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()


def validate_shop_payment(payment, user=None):
    with transaction.atomic():
        payment = ShopPayment.objects.select_for_update().select_related("order", "order__branch").get(pk=payment.pk)
        if payment.status == ShopPayment.STATUS_VALIDATED:
            return payment
        if not payment.reference:
            payment.reference = next_shop_reference(payment.order.branch, ShopSequence.TYPE_PAYMENT)
        payment.status = ShopPayment.STATUS_VALIDATED
        payment.receipt_number = payment.reference
        payment.paid_at = timezone.now()
        pdf_bytes = render_shop_receipt_pdf(payment)
        payment.receipt_pdf.save(f"recu-boutique-{payment.receipt_number}.pdf", ContentFile(pdf_bytes), save=False)
        payment.save()

        order = payment.order
        order.refresh_total(save=False)
        order.status = ShopOrder.STATUS_PAID if order.balance <= 0 else ShopOrder.STATUS_PENDING_PAYMENT
        order.save(update_fields=["total_amount", "status", "updated_at"])

        create_cash_movement(
            branch=order.branch,
            movement_type=BranchCashMovement.TYPE_IN,
            source=BranchCashMovement.SOURCE_SHOP,
            amount=payment.amount,
            label=f"Vente boutique - {order.reference}",
            movement_date=payment.paid_at.date(),
            source_reference=payment.reference,
            notes=f"Encaissement boutique commande {order.reference}.",
            created_by=user or payment.created_by,
        )
    return payment


def create_shop_payment(order, amount, method, user=None, *, auto_validate=False):
    payment = ShopPayment.objects.create(
        order=order,
        amount=amount,
        method=method,
        status=ShopPayment.STATUS_PENDING,
        reference=next_shop_reference(order.branch, ShopSequence.TYPE_PAYMENT) if auto_validate else "",
        created_by=user,
    )
    if auto_validate:
        payment = validate_shop_payment(payment, user=user)
    return payment


def deliver_order(order, user):
    with transaction.atomic():
        order = ShopOrder.objects.select_for_update().prefetch_related("items", "items__product", "items__variant").get(pk=order.pk)
        if order.status not in {ShopOrder.STATUS_PAID, ShopOrder.STATUS_READY}:
            return order
        for item in order.items.all():
            ShopStockMovement.objects.create(
                branch=order.branch,
                product=item.product,
                variant=item.variant,
                movement_type=ShopStockMovement.TYPE_OUT,
                quantity=item.quantity,
                reference=next_shop_reference(order.branch, ShopSequence.TYPE_STOCK),
                order=order,
                notes=f"Remise commande {order.reference}.",
                created_by=user,
            )
        order.status = ShopOrder.STATUS_DELIVERED
        order.delivered_by = user
        order.delivered_at = timezone.now()
        order.save(update_fields=["status", "delivered_by", "delivered_at", "updated_at"])
    return order


def get_manager_shop_context(branch):
    orders = (
        ShopOrder.objects
        .filter(branch=branch)
        .select_related("student", "inscription")
        .prefetch_related("items", "items__product", "payments")
        .order_by("-created_at")[:30]
    )
    products = list(ShopProduct.objects.filter(branch=branch).prefetch_related("variants").order_by("category", "name"))
    payments = ShopPayment.objects.filter(order__branch=branch, status=ShopPayment.STATUS_VALIDATED)
    month_sales = payments.filter(
        paid_at__date__gte=timezone.localdate().replace(day=1)
    ).aggregate(total=Sum("amount"))["total"] or 0
    return {
        "shop_products": products,
        "shop_orders": orders,
        "shop_stats": {
            "products": len(products),
            "required": sum(1 for product in products if product.is_required),
            "low_stock": sum(1 for product in products if product.is_low_stock),
            "pending_orders": ShopOrder.objects.filter(branch=branch, status=ShopOrder.STATUS_PENDING_PAYMENT).count(),
            "paid_not_delivered": ShopOrder.objects.filter(branch=branch, status=ShopOrder.STATUS_PAID).count(),
            "month_sales": month_sales,
        },
    }
