from io import BytesIO

import logging

from django.contrib.auth.hashers import check_password, make_password
from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Case, IntegerField, Q, Sum, Value, When
from django.db.models.functions import Coalesce
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.dateparse import parse_date
from django.utils.text import slugify

from core.pdf_documents import generate_pdf as generate_esfe_pdf

from accounts.models import BranchCashMovement
from payments.models import PaymentAgent
from accounts.services.accounting_documents import create_cash_movement
from notifier.models import NotificationMessage
from notifier.services import NotificationBus
from accounts.dashboards.helpers import is_manager
from shop.models import (
    ShopOrder,
    ShopOrderEmailConfirmation,
    ShopOrderItem,
    ShopPayment,
    ShopProduct,
    ShopProductVariant,
    ShopSequence,
    ShopStockMovement,
)

SHOP_EMAIL_OTP_MINUTES = 10
SHOP_EMAIL_OTP_MAX_ATTEMPTS = 5
SHOP_EMAIL_OTP_RESEND_SECONDS = 60
SHOP_EMAIL_OTP_MAX_RESENDS = 3

User = get_user_model()
logger = logging.getLogger(__name__)

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


def get_branch_public_shop_identifier(branch):
    slug = (getattr(branch, "slug", "") or "").strip()
    if slug:
        return slug
    code = (getattr(branch, "code", "") or "").strip().lower()
    if code:
        return code
    return slugify(getattr(branch, "name", "") or "")


def _get_available_stock(product, variant=None):
    if variant is not None:
        return variant.current_stock
    return product.current_stock


def ensure_stock_available(*, product, quantity, variant=None):
    available_stock = _get_available_stock(product, variant)
    if quantity > available_stock:
        raise ValidationError(
            f"Stock insuffisant pour {product.name}. Disponible: {available_stock}, demande: {quantity}."
        )


def decrement_product_stock(order, *, user=None):
    if order.stock_movements.filter(movement_type=ShopStockMovement.TYPE_OUT).exists():
        return

    items = list(order.items.select_related("product", "variant"))
    locked_products = {
        product.pk: product
        for product in ShopProduct.objects.select_for_update().filter(pk__in={item.product_id for item in items})
    }
    locked_variants = {
        variant.pk: variant
        for variant in ShopProductVariant.objects.select_for_update().filter(
            pk__in={item.variant_id for item in items if item.variant_id}
        )
    }
    for item in items:
        product = locked_products[item.product_id]
        variant = locked_variants.get(item.variant_id)
        ensure_stock_available(product=product, variant=variant, quantity=item.quantity)
        ShopStockMovement.objects.create(
            branch=order.branch,
            product=product,
            variant=variant,
            movement_type=ShopStockMovement.TYPE_OUT,
            quantity=item.quantity,
            reference=next_shop_reference(order.branch, ShopSequence.TYPE_STOCK),
            order=order,
            notes=f"Sortie stock apres paiement valide pour {order.reference}.",
            created_by=user,
        )


def _get_branch_manager_recipients(branch):
    return (
        User.objects
        .filter(
            is_active=True,
            profile__branch=branch,
            groups__name="gestionnaire",
        )
        .distinct()
    )


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
        .annotate(
            stock_in=Coalesce(Sum("stock_movements__quantity", filter=Q(stock_movements__movement_type=ShopStockMovement.TYPE_IN)), Value(0), output_field=IntegerField()),
            stock_out=Coalesce(Sum("stock_movements__quantity", filter=Q(stock_movements__movement_type=ShopStockMovement.TYPE_OUT)), Value(0), output_field=IntegerField()),
            stock_adjustment=Coalesce(Sum("stock_movements__quantity", filter=Q(stock_movements__movement_type=ShopStockMovement.TYPE_ADJUSTMENT)), Value(0), output_field=IntegerField()),
        )
        .order_by("-is_required", "category", "name")
    )
    products = []
    for product in queryset:
        programme_ids = {programme.pk for programme in product.programmes.all()}
        if programme_ids and candidature.programme_id not in programme_ids:
            continue
        product.inventory_stock = product.stock_in - product.stock_out + product.stock_adjustment
        product.inventory_low = product.inventory_stock <= product.low_stock_threshold
        products.append(product)
    return products


def get_required_shop_context(user):
    student = getattr(user, "student_profile", None)
    if not student:
        return {"show_popup": False, "products": [], "open_orders": [], "required_missing_count": 0}
    inscription = student.inscription
    candidature = inscription.candidature
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
        "branch_public_identifier": get_branch_public_shop_identifier(candidature.branch),
    }


def create_student_required_order(user, product_ids, created_by=None):
    student = user.student_profile
    inscription = student.inscription
    candidature = inscription.candidature
    branch = inscription.candidature.branch
    products = list(
        ShopProduct.objects
        .filter(branch=branch, is_active=True, id__in=product_ids)
        .prefetch_related("variants")
    )
    if not products:
        return None
    with transaction.atomic():
        for product in products:
            ensure_stock_available(product=product, quantity=1)
        order = ShopOrder.objects.create(
            branch=branch,
            inscription=inscription,
            student=user,
            buyer_type=ShopOrder.BUYER_STUDENT,
            customer_name=candidature.full_name,
            customer_email=candidature.email,
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
        notify_shop_order_received(order=order, actor=created_by or user)
    return order


def _shop_email_otp():
    return "".join(get_random_string(1, allowed_chars="0123456789") for _ in range(6))


def _send_shop_email(*, required=False, **kwargs):
    """Email infrastructure must never turn a shop HTTP request into a 500."""
    try:
        return NotificationBus.send_email(**kwargs)
    except Exception as exc:
        logger.exception("Transactional shop email could not be sent")
        if required:
            raise ValidationError(
                "Impossible d'envoyer le code e-mail pour le moment. Vérifiez votre connexion ou réessayez plus tard."
            ) from exc
        return None


def request_student_remote_order_confirmation(*, student, product_id, quantity):
    if not getattr(student, "email", ""):
        raise ValidationError("Votre compte ne possède pas d'adresse e-mail. Contactez votre annexe.")
    available = {product.pk: product for product in get_recommended_products_for_student(student)}
    product = available.get(int(product_id))
    if not product:
        raise ValidationError("Cet article n'est pas disponible pour votre parcours.")
    if quantity < 1:
        raise ValidationError("La quantité doit être supérieure à zéro.")
    ensure_stock_available(product=product, quantity=quantity)
    now = timezone.now()
    with transaction.atomic():
        existing = (ShopOrderEmailConfirmation.objects.select_for_update().filter(student=student, product=product, status=ShopOrderEmailConfirmation.STATUS_PENDING, expires_at__gt=now).order_by("-created_at").first())
        if existing and existing.last_sent_at and (now - existing.last_sent_at).total_seconds() < SHOP_EMAIL_OTP_RESEND_SECONDS:
            raise ValidationError("Un code vient d'être envoyé. Attendez une minute avant de demander un nouvel envoi.")
        if existing and existing.resend_count >= SHOP_EMAIL_OTP_MAX_RESENDS:
            raise ValidationError("Nombre maximal de renvois atteint. Attendez l'expiration du code avant de recommencer.")
        code = _shop_email_otp()
        if existing:
            existing.quantity = quantity
            existing.otp_code_hash = make_password(code)
            existing.expires_at = now + timezone.timedelta(minutes=SHOP_EMAIL_OTP_MINUTES)
            existing.attempts = 0
            existing.resend_count += 1
            existing.last_sent_at = now
            existing.save()
            confirmation = existing
        else:
            confirmation = ShopOrderEmailConfirmation.objects.create(branch=product.branch, student=student, product=product, quantity=quantity, otp_code_hash=make_password(code), expires_at=now + timezone.timedelta(minutes=SHOP_EMAIL_OTP_MINUTES), last_sent_at=now)
    try:
        _send_shop_email(required=True, subject="Code de confirmation – commande Boutique ESFE", recipient=student, recipient_email=student.email, source_app="shop", event_type="shop_order_confirmation_otp", html_template="emails/base_communication.html", context={"title": "Confirmez votre commande Boutique", "message": f"Votre code est : {code}. Il expire dans {SHOP_EMAIL_OTP_MINUTES} minutes.", "recipient_name": student.get_full_name() or student.username}, metadata={"confirmation_id": confirmation.pk}, legacy_source="shop_order_confirmation", legacy_object_id=str(confirmation.pk))
    except ValidationError:
        confirmation.status = ShopOrderEmailConfirmation.STATUS_CANCELLED
        confirmation.save(update_fields=["status", "updated_at"])
        raise
    return confirmation, product


def confirm_student_remote_order(*, student, confirmation_id, code):
    with transaction.atomic():
        confirmation = ShopOrderEmailConfirmation.objects.select_for_update().select_related("product", "branch").filter(pk=confirmation_id, student=student).first()
        if not confirmation:
            raise ValidationError("Demande de commande introuvable.")
        if confirmation.status != ShopOrderEmailConfirmation.STATUS_PENDING:
            raise ValidationError("Cette demande n'est plus valide.")
        if timezone.now() >= confirmation.expires_at:
            confirmation.status = ShopOrderEmailConfirmation.STATUS_EXPIRED
            confirmation.save(update_fields=["status", "updated_at"])
            raise ValidationError("Le code a expiré. Demandez-en un nouveau.")
        confirmation.attempts += 1
        if confirmation.attempts > SHOP_EMAIL_OTP_MAX_ATTEMPTS or not check_password(code, confirmation.otp_code_hash):
            if confirmation.attempts >= SHOP_EMAIL_OTP_MAX_ATTEMPTS:
                confirmation.status = ShopOrderEmailConfirmation.STATUS_CANCELLED
            confirmation.save(update_fields=["attempts", "status", "updated_at"])
            raise ValidationError("Code incorrect." if confirmation.status == ShopOrderEmailConfirmation.STATUS_PENDING else "Trop de tentatives. Demandez un nouveau code.")
        product = ShopProduct.objects.select_for_update().get(pk=confirmation.product_id, branch=confirmation.branch, is_active=True)
        ensure_stock_available(product=product, quantity=confirmation.quantity)
        profile = student.student_profile
        order = ShopOrder.objects.create(branch=confirmation.branch, inscription=profile.inscription, student=student, buyer_type=ShopOrder.BUYER_STUDENT, customer_name=student.get_full_name() or student.username, customer_email=student.email, reference=next_shop_reference(confirmation.branch, ShopSequence.TYPE_ORDER), status=ShopOrder.STATUS_PENDING_PAYMENT, created_by=student)
        ShopOrderItem.objects.create(order=order, product=product, quantity=confirmation.quantity, unit_price=product.unit_price, is_required=product.is_required)
        order.refresh_total()
        confirmation.status = ShopOrderEmailConfirmation.STATUS_CONFIRMED
        confirmation.order = order
        confirmation.save(update_fields=["status", "order", "attempts", "updated_at"])
        notify_shop_order_received(order=order, actor=student)
    _send_shop_email(subject="Commande Boutique confirmée", recipient=student, recipient_email=student.email, source_app="shop", event_type="shop_order_confirmed_email", html_template="emails/base_communication.html", context={"title": "Commande enregistrée", "message": f"Votre commande {order.reference} est en attente de paiement. Présentez-vous à {order.branch.name} pour régler et retirer vos articles.", "recipient_name": order.buyer_display, "reference": order.reference, "amount": order.total_amount, "branch_name": order.branch.name}, legacy_source="shop_order", legacy_object_id=str(order.pk))
    return order


def create_counter_order(
    *,
    branch,
    product=None,
    quantity=None,
    lines=None,
    payment_method,
    created_by,
    student=None,
    customer_name="",
    customer_email="",
    customer_phone="",
    immediate_settlement=False,
):
    with transaction.atomic():
        lines = list(lines or [])
        if not lines:
            if product is None or quantity is None:
                raise ValidationError("Ajoutez au moins un article à la vente.")
            lines = [{"product": product, "quantity": quantity}]

        requested_quantities = {}
        for line in lines:
            line_product = line.get("product")
            line_quantity = line.get("quantity")
            if not line_product or not isinstance(line_quantity, int) or line_quantity < 1:
                raise ValidationError("Une ligne de vente est invalide.")
            requested_quantities[line_product.pk] = requested_quantities.get(line_product.pk, 0) + line_quantity

        # Locking the products before reading their movement ledgers prevents
        # two simultaneous counter sales from validating the same final unit.
        products = {
            item.pk: item
            for item in ShopProduct.objects.select_for_update().filter(
                branch=branch,
                is_active=True,
                pk__in=requested_quantities,
            )
        }
        if len(products) != len(requested_quantities):
            raise ValidationError("Un article de la vente est indisponible ou ne relève pas de cette annexe.")
        for product_id, requested_quantity in requested_quantities.items():
            ensure_stock_available(product=products[product_id], quantity=requested_quantity)

        order = ShopOrder.objects.create(
            branch=branch,
            inscription=getattr(getattr(student, "student_profile", None), "inscription", None),
            student=student,
            buyer_type=ShopOrder.BUYER_STUDENT if student else ShopOrder.BUYER_WALK_IN,
            customer_name=(student.get_full_name() or student.username) if student else customer_name,
            customer_email=getattr(student, "email", "") if student else customer_email,
            customer_phone=customer_phone,
            reference=next_shop_reference(branch, ShopSequence.TYPE_ORDER),
            status=ShopOrder.STATUS_PENDING_PAYMENT,
            created_by=created_by,
        )
        for product_id, requested_quantity in requested_quantities.items():
            sale_product = products[product_id]
            ShopOrderItem.objects.create(
                order=order,
                product=sale_product,
                quantity=requested_quantity,
                unit_price=sale_product.unit_price,
                is_required=sale_product.is_required,
            )
        order.refresh_total()
        collector = None
        auto_validate_payment = immediate_settlement
        if immediate_settlement and created_by is not None:
            collector = PaymentAgent.objects.filter(user=created_by, branch=branch, is_active=True).first()
        payment = create_shop_payment(
            order,
            order.total_amount,
            payment_method,
            created_by,
            auto_validate=auto_validate_payment,
            agent=collector if immediate_settlement else None,
        )
        notify_shop_order_received(order=order, actor=created_by)
    return order, payment


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

    student_name = order.buyer_display
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

        order = payment.order
        items = []
        for item in order.items.select_related("product", "variant"):
            label = item.product.name
            if item.variant:
                label = f"{label} ({item.variant.label})"
            items.append({
                "label": label,
                "quantity": str(item.quantity),
                "unit_price": f"{item.unit_price:,}".replace(",", " "),
                "total": f"{item.line_total:,} FCFA".replace(",", " "),
            })

        customer_name = order.buyer_display
        pdf_bytes = generate_esfe_pdf("esfe_shop_invoice", {
            "invoice_number": payment.receipt_number,
            "date": payment.paid_at.strftime("%d %B %Y"),
            "customer_name": customer_name,
            "customer_email": getattr(order, "customer_email", ""),
            "customer_phone": getattr(order, "customer_phone", ""),
            "branch_name": order.branch.name if order.branch_id else "",
            "items": items,
            "total_amount": f"{payment.amount:,}".replace(",", " "),
            "payment_method": payment.get_method_display(),
            "payment_reference": payment.reference or "",
        })
        payment.receipt_pdf.save(f"recu-boutique-{payment.receipt_number}.pdf", ContentFile(pdf_bytes), save=False)
        payment.save()

        order = payment.order
        order.refresh_total(save=False)
        order.status = ShopOrder.STATUS_PAID if order.balance <= 0 else ShopOrder.STATUS_PENDING_PAYMENT
        order.save(update_fields=["total_amount", "status", "updated_at"])
        if order.status == ShopOrder.STATUS_PAID:
            decrement_product_stock(order, user=user or payment.created_by)

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
        notify_shop_payment_validated(order=order, payment=payment, actor=user or payment.created_by)
    return payment


def create_shop_payment(order, amount, method, user=None, *, auto_validate=False, agent=None, cash_session=None):
    payment = ShopPayment.objects.create(
        order=order,
        amount=amount,
        method=method,
        status=ShopPayment.STATUS_PENDING,
        reference=next_shop_reference(order.branch, ShopSequence.TYPE_PAYMENT) if auto_validate else "",
        created_by=user,
        agent=agent,
        cash_session=cash_session,
    )
    if auto_validate:
        payment = validate_shop_payment(payment, user=user)
    return payment


def mark_order_ready(order, user):
    with transaction.atomic():
        order = ShopOrder.objects.select_for_update().get(pk=order.pk)
        if order.status != ShopOrder.STATUS_PAID:
            return order
        order.status = ShopOrder.STATUS_READY
        order.prepared_by = user
        order.prepared_at = timezone.now()
        order.save(update_fields=["status", "prepared_by", "prepared_at", "updated_at"])
        notify_shop_order_ready(order=order, actor=user)
    return order


def deliver_order(order, user):
    with transaction.atomic():
        order = ShopOrder.objects.select_for_update().prefetch_related("items", "items__product", "items__variant").get(pk=order.pk)
        if order.status not in {ShopOrder.STATUS_PAID, ShopOrder.STATUS_READY}:
            return order
        order.status = ShopOrder.STATUS_DELIVERED
        order.delivered_by = user
        order.delivered_at = timezone.now()
        order.save(update_fields=["status", "delivered_by", "delivered_at", "updated_at"])
        notify_shop_order_delivered(order=order, actor=user)
    return order


def get_manager_shop_context(
    branch,
    *,
    journal_query="",
    journal_date="",
    stock_query="",
    stock_state="",
    stock_category="",
):
    order_queryset = (
        ShopOrder.objects
        .filter(branch=branch)
        .select_related("student", "inscription")
        .prefetch_related("items", "items__product", "payments")
    )
    orders = (
        order_queryset
        .order_by(
            Case(
                When(status=ShopOrder.STATUS_PENDING_PAYMENT, then=Value(0)),
                When(status=ShopOrder.STATUS_PAID, then=Value(1)),
                When(status=ShopOrder.STATUS_READY, then=Value(2)),
                default=Value(3),
                output_field=IntegerField(),
            ),
            "-created_at",
        )[:30]
    )
    order_queues = {
        "pending": list(order_queryset.filter(status=ShopOrder.STATUS_PENDING_PAYMENT).order_by("created_at")[:30]),
        "paid": list(order_queryset.filter(status=ShopOrder.STATUS_PAID).order_by("created_at")[:30]),
        "ready": list(order_queryset.filter(status=ShopOrder.STATUS_READY).order_by("created_at")[:30]),
    }
    # Keep the stock ledger as the source of truth without making three
    # aggregate queries per catalogue item in the manager workspace.
    products = list(
        ShopProduct.objects
        .filter(branch=branch)
        .prefetch_related("variants")
        .annotate(
            stock_in=Coalesce(Sum("stock_movements__quantity", filter=Q(stock_movements__movement_type=ShopStockMovement.TYPE_IN)), Value(0), output_field=IntegerField()),
            stock_out=Coalesce(Sum("stock_movements__quantity", filter=Q(stock_movements__movement_type=ShopStockMovement.TYPE_OUT)), Value(0), output_field=IntegerField()),
            stock_adjustment=Coalesce(Sum("stock_movements__quantity", filter=Q(stock_movements__movement_type=ShopStockMovement.TYPE_ADJUSTMENT)), Value(0), output_field=IntegerField()),
        )
        .order_by("category", "name")
    )
    for product in products:
        product.inventory_stock = product.stock_in - product.stock_out + product.stock_adjustment
        product.inventory_low = product.inventory_stock <= product.low_stock_threshold

    # The counter always receives the complete active catalogue.  These
    # filters only narrow the inventory workspace and its table.
    stock_query = (stock_query or "").strip()
    stock_state = (stock_state or "").strip()
    stock_category = (stock_category or "").strip()
    catalogue_products = products
    if stock_query:
        needle = stock_query.casefold()
        catalogue_products = [
            product
            for product in catalogue_products
            if needle in product.name.casefold() or needle in product.get_category_display().casefold()
        ]
    if stock_category:
        catalogue_products = [product for product in catalogue_products if product.category == stock_category]
    if stock_state == "low":
        catalogue_products = [product for product in catalogue_products if product.inventory_low]
    elif stock_state == "available":
        catalogue_products = [product for product in catalogue_products if product.inventory_stock > product.low_stock_threshold]
    elif stock_state == "archived":
        catalogue_products = [product for product in catalogue_products if not product.is_active]
    elif stock_state == "active":
        catalogue_products = [product for product in catalogue_products if product.is_active]
    counter_catalog = [
        {
            "id": product.pk,
            "name": product.name,
            "category": product.category,
            "price": product.unit_price,
            "stock": product.inventory_stock,
            "available": product.inventory_stock > 0,
        }
        for product in products
        if product.is_active
    ]
    payments = ShopPayment.objects.filter(order__branch=branch, status=ShopPayment.STATUS_VALIDATED)
    today = timezone.localdate()
    month_sales = payments.filter(paid_at__date__gte=today.replace(day=1)).aggregate(total=Sum("amount"))["total"] or 0
    today_sales = payments.filter(paid_at__date=today).aggregate(total=Sum("amount"))["total"] or 0
    cash_entries_count = BranchCashMovement.objects.filter(
        branch=branch,
        source=BranchCashMovement.SOURCE_SHOP,
        movement_type=BranchCashMovement.TYPE_IN,
    ).count()
    journal_query = (journal_query or "").strip()
    journal_day = parse_date(journal_date) if journal_date else None
    payment_journal_queryset = ShopPayment.objects.filter(order__branch=branch)
    stock_journal_queryset = ShopStockMovement.objects.filter(branch=branch)
    if journal_query:
        payment_journal_queryset = payment_journal_queryset.filter(
            Q(reference__icontains=journal_query)
            | Q(order__reference__icontains=journal_query)
            | Q(order__customer_name__icontains=journal_query)
            | Q(order__student__first_name__icontains=journal_query)
            | Q(order__student__last_name__icontains=journal_query)
        )
        stock_journal_queryset = stock_journal_queryset.filter(
            Q(reference__icontains=journal_query)
            | Q(product__name__icontains=journal_query)
            | Q(notes__icontains=journal_query)
        )
    if journal_day:
        payment_journal_queryset = payment_journal_queryset.filter(paid_at__date=journal_day)
        stock_journal_queryset = stock_journal_queryset.filter(created_at__date=journal_day)
    recent_payments = list(
        payment_journal_queryset
        .select_related("order", "order__student", "created_by")
        .order_by("-paid_at")[:40]
    )
    recent_stock_movements = list(
        stock_journal_queryset
        .select_related("product", "created_by", "order")
        .order_by("-created_at")[:40]
    )
    return {
        "shop_products": products,
        "shop_catalogue_products": catalogue_products,
        "shop_counter_catalog": counter_catalog,
        "shop_orders": orders,
        "shop_order_queues": order_queues,
        "shop_recent_payments": recent_payments,
        "shop_recent_stock_movements": recent_stock_movements,
        "shop_journal_query": journal_query,
        "shop_journal_date": journal_day.isoformat() if journal_day else (journal_date or ""),
        "shop_stock_query": stock_query,
        "shop_stock_state": stock_state,
        "shop_stock_category": stock_category,
        "shop_stats": {
            "products": len(products),
            "required": sum(1 for product in products if product.is_required),
            "low_stock": sum(1 for product in products if product.inventory_low),
            "pending_orders": ShopOrder.objects.filter(branch=branch, status=ShopOrder.STATUS_PENDING_PAYMENT).count(),
            "paid_not_delivered": ShopOrder.objects.filter(branch=branch, status=ShopOrder.STATUS_PAID).count(),
            "ready_orders": ShopOrder.objects.filter(branch=branch, status=ShopOrder.STATUS_READY).count(),
            "month_sales": month_sales,
            "today_sales": today_sales,
            "today_sales_count": payments.filter(paid_at__date=today).count(),
            "cash_entries": cash_entries_count,
        },
    }


def notify_shop_order_received(*, order, actor=None):
    title = "Nouvelle commande boutique"
    body = (
        f"La commande {order.reference} a ete enregistree pour {order.buyer_display}. "
        f"Montant: {order.total_amount} FCFA."
    )
    for manager in _get_branch_manager_recipients(order.branch):
        NotificationBus.notify(
            recipient=manager,
            actor=actor,
            event_type="shop_order_received",
            title=title,
            body=body,
            source_app="shop",
            channels=(NotificationMessage.CHANNEL_IN_APP, NotificationMessage.CHANNEL_WEBSOCKET),
            metadata={"order_id": order.pk, "branch_id": order.branch_id},
            legacy_source="shop_order",
            legacy_object_id=str(order.pk),
        )


def notify_shop_payment_validated(*, order, payment, actor=None):
    title = "Achat boutique confirme"
    body = (
        f"Votre achat boutique {order.reference} a ete confirme pour un montant de {payment.amount} FCFA. "
        "Votre recu est disponible."
    )
    if order.student_id:
        NotificationBus.notify(
            recipient=order.student,
            actor=actor,
            event_type="shop_purchase_validated",
            title=title,
            body=body,
            source_app="shop",
            channels=(NotificationMessage.CHANNEL_IN_APP, NotificationMessage.CHANNEL_WEBSOCKET),
            metadata={
                "order_id": order.pk,
                "payment_id": payment.pk,
                "receipt_number": payment.receipt_number,
                "branch_id": order.branch_id,
            },
            legacy_source="shop_order",
            legacy_object_id=str(order.pk),
        )
    manager_body = (
        f"Paiement valide pour {order.reference}. Montant: {payment.amount} FCFA. "
        "La vente est entree en caisse et le stock a ete decremente."
    )
    for manager in _get_branch_manager_recipients(order.branch):
        if actor and manager.pk == actor.pk and is_manager(manager):
            continue
        NotificationBus.notify(
            recipient=manager,
            actor=actor,
            event_type="shop_payment_validated_manager",
            title="Paiement boutique valide",
            body=manager_body,
            source_app="shop",
            channels=(NotificationMessage.CHANNEL_IN_APP, NotificationMessage.CHANNEL_WEBSOCKET),
            metadata={"order_id": order.pk, "payment_id": payment.pk, "branch_id": order.branch_id},
            legacy_source="shop_order",
            legacy_object_id=str(order.pk),
        )
    if order.buyer_email:
        NotificationBus.send_email(
            subject=title,
            recipient=order.student if order.student_id else None,
            recipient_email=order.buyer_email,
            source_app="shop",
            event_type="shop_purchase_validated_email",
            html_template="emails/base_communication.html",
            context={
                "title": title,
                "message": body,
                "recipient_name": order.buyer_display,
                "reference": order.reference,
                "payment_reference": payment.reference,
                "amount": payment.amount,
                "branch_name": order.branch.name,
            },
            dispatch_on_commit=False,
            legacy_source="shop_order",
            legacy_object_id=str(order.pk),
        )


def notify_shop_order_ready(*, order, actor=None):
    title = "Commande boutique prete"
    body = f"Votre commande {order.reference} est prete. Vous pouvez passer pour le retrait."
    if order.student_id:
        NotificationBus.notify(
            recipient=order.student,
            actor=actor,
            event_type="shop_order_ready",
            title=title,
            body=body,
            source_app="shop",
            channels=(NotificationMessage.CHANNEL_IN_APP, NotificationMessage.CHANNEL_WEBSOCKET),
            metadata={"order_id": order.pk, "branch_id": order.branch_id},
            legacy_source="shop_order",
            legacy_object_id=str(order.pk),
        )
    if order.buyer_email:
        NotificationBus.send_email(
            subject=title,
            recipient=order.student if order.student_id else None,
            recipient_email=order.buyer_email,
            source_app="shop",
            event_type="shop_order_ready_email",
            html_template="emails/base_communication.html",
            context={"title": title, "message": body, "recipient_name": order.buyer_display, "reference": order.reference},
            legacy_source="shop_order",
            legacy_object_id=str(order.pk),
        )


def notify_shop_order_delivered(*, order, actor=None):
    title = "Commande boutique remise"
    body = f"La commande {order.reference} a ete remise avec succes."
    if order.student_id:
        NotificationBus.notify(
            recipient=order.student,
            actor=actor,
            event_type="shop_order_delivered",
            title=title,
            body=body,
            source_app="shop",
            channels=(NotificationMessage.CHANNEL_IN_APP, NotificationMessage.CHANNEL_WEBSOCKET),
            metadata={"order_id": order.pk, "branch_id": order.branch_id},
            legacy_source="shop_order",
            legacy_object_id=str(order.pk),
        )
