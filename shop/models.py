from django.conf import settings
from django.db import models
from django.utils import timezone

from branches.models import Branch
from formations.models import Programme
from inscriptions.models import Inscription


class ShopProduct(models.Model):
    CATEGORY_UNIFORM = "uniform"
    CATEGORY_BLOUSE = "blouse"
    CATEGORY_FABRIC = "fabric"
    CATEGORY_BADGE = "badge"
    CATEGORY_KIT = "kit"
    CATEGORY_OTHER = "other"

    CATEGORY_CHOICES = [
        (CATEGORY_UNIFORM, "Tenue"),
        (CATEGORY_BLOUSE, "Blouse"),
        (CATEGORY_FABRIC, "Tissu"),
        (CATEGORY_BADGE, "Badge"),
        (CATEGORY_KIT, "Kit"),
        (CATEGORY_OTHER, "Autre"),
    ]

    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="shop_products", db_index=True)
    name = models.CharField(max_length=180)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, db_index=True)
    description = models.TextField(blank=True)
    unit_price = models.PositiveBigIntegerField()
    is_required = models.BooleanField(default=False, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    low_stock_threshold = models.PositiveIntegerField(default=5)
    programmes = models.ManyToManyField(Programme, blank=True, related_name="shop_products")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "name"]
        indexes = [
            models.Index(fields=["branch", "category"]),
            models.Index(fields=["branch", "is_required", "is_active"]),
        ]

    def __str__(self):
        return f"{self.name} - {self.branch}"

    @property
    def current_stock(self):
        incoming = self.stock_movements.filter(movement_type=ShopStockMovement.TYPE_IN).aggregate(total=models.Sum("quantity"))["total"] or 0
        outgoing = self.stock_movements.filter(movement_type=ShopStockMovement.TYPE_OUT).aggregate(total=models.Sum("quantity"))["total"] or 0
        adjustment = self.stock_movements.filter(movement_type=ShopStockMovement.TYPE_ADJUSTMENT).aggregate(total=models.Sum("quantity"))["total"] or 0
        return incoming - outgoing + adjustment

    @property
    def is_low_stock(self):
        return self.current_stock <= self.low_stock_threshold


class ShopProductVariant(models.Model):
    product = models.ForeignKey(ShopProduct, on_delete=models.CASCADE, related_name="variants")
    label = models.CharField(max_length=80)
    extra_price = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["product", "label"]
        constraints = [
            models.UniqueConstraint(fields=["product", "label"], name="shop_unique_variant_per_product")
        ]

    def __str__(self):
        return f"{self.product.name} - {self.label}"

    @property
    def final_price(self):
        return max(self.product.unit_price + self.extra_price, 0)

    @property
    def current_stock(self):
        incoming = self.stock_movements.filter(movement_type=ShopStockMovement.TYPE_IN).aggregate(total=models.Sum("quantity"))["total"] or 0
        outgoing = self.stock_movements.filter(movement_type=ShopStockMovement.TYPE_OUT).aggregate(total=models.Sum("quantity"))["total"] or 0
        adjustment = self.stock_movements.filter(movement_type=ShopStockMovement.TYPE_ADJUSTMENT).aggregate(total=models.Sum("quantity"))["total"] or 0
        product_only = self.product.stock_movements.filter(variant__isnull=True).aggregate(total=models.Sum("quantity"))["total"] or 0
        return incoming - outgoing + adjustment + product_only


class ShopOrder(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_PENDING_PAYMENT = "pending_payment"
    STATUS_PAID = "paid"
    STATUS_READY = "ready"
    STATUS_DELIVERED = "delivered"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Brouillon"),
        (STATUS_PENDING_PAYMENT, "En attente paiement"),
        (STATUS_PAID, "Payee"),
        (STATUS_READY, "Prete a retirer"),
        (STATUS_DELIVERED, "Remise"),
        (STATUS_CANCELLED, "Annulee"),
    ]

    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="shop_orders", db_index=True)
    inscription = models.ForeignKey(Inscription, on_delete=models.PROTECT, related_name="shop_orders", db_index=True)
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="shop_orders")
    reference = models.CharField(max_length=80, blank=True, db_index=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)
    total_amount = models.PositiveBigIntegerField(default=0)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_shop_orders")
    delivered_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="delivered_shop_orders")
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["branch", "status"]),
            models.Index(fields=["student", "status"]),
        ]

    def __str__(self):
        return self.reference or f"Commande boutique #{self.pk}"

    def refresh_total(self, save=True):
        self.total_amount = sum(item.line_total for item in self.items.all())
        if save:
            self.save(update_fields=["total_amount", "updated_at"])
        return self.total_amount

    @property
    def paid_amount(self):
        return self.payments.filter(status=ShopPayment.STATUS_VALIDATED).aggregate(total=models.Sum("amount"))["total"] or 0

    @property
    def balance(self):
        return max(self.total_amount - self.paid_amount, 0)


class ShopOrderItem(models.Model):
    order = models.ForeignKey(ShopOrder, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(ShopProduct, on_delete=models.PROTECT, related_name="order_items")
    variant = models.ForeignKey(ShopProductVariant, on_delete=models.PROTECT, null=True, blank=True, related_name="order_items")
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.PositiveBigIntegerField()
    is_required = models.BooleanField(default=False)

    class Meta:
        ordering = ["id"]

    @property
    def line_total(self):
        return self.quantity * self.unit_price


class ShopPayment(models.Model):
    METHOD_CASH = "cash"
    METHOD_ORANGE = "orange_money"
    METHOD_BANK = "bank_transfer"

    METHOD_CHOICES = [
        (METHOD_CASH, "Especes"),
        (METHOD_ORANGE, "Orange Money"),
        (METHOD_BANK, "Virement bancaire"),
    ]

    STATUS_PENDING = "pending"
    STATUS_VALIDATED = "validated"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_PENDING, "En attente"),
        (STATUS_VALIDATED, "Valide"),
        (STATUS_CANCELLED, "Annule"),
    ]

    order = models.ForeignKey(ShopOrder, on_delete=models.PROTECT, related_name="payments")
    amount = models.PositiveBigIntegerField()
    method = models.CharField(max_length=30, choices=METHOD_CHOICES, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    reference = models.CharField(max_length=80, blank=True, db_index=True)
    receipt_number = models.CharField(max_length=80, blank=True, db_index=True)
    receipt_pdf = models.FileField(upload_to="shop/receipts/", null=True, blank=True)
    paid_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_shop_payments")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-paid_at"]
        indexes = [
            models.Index(fields=["order", "status"]),
            models.Index(fields=["status", "paid_at"]),
        ]

    def __str__(self):
        return f"{self.reference or self.pk} - {self.amount} FCFA"


class ShopStockMovement(models.Model):
    TYPE_IN = "in"
    TYPE_OUT = "out"
    TYPE_ADJUSTMENT = "adjustment"

    TYPE_CHOICES = [
        (TYPE_IN, "Entree"),
        (TYPE_OUT, "Sortie"),
        (TYPE_ADJUSTMENT, "Ajustement"),
    ]

    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="shop_stock_movements", db_index=True)
    product = models.ForeignKey(ShopProduct, on_delete=models.PROTECT, related_name="stock_movements")
    variant = models.ForeignKey(ShopProductVariant, on_delete=models.PROTECT, null=True, blank=True, related_name="stock_movements")
    movement_type = models.CharField(max_length=20, choices=TYPE_CHOICES, db_index=True)
    quantity = models.IntegerField()
    reference = models.CharField(max_length=80, blank=True, db_index=True)
    order = models.ForeignKey(ShopOrder, on_delete=models.SET_NULL, null=True, blank=True, related_name="stock_movements")
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_shop_stock_movements")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["branch", "product"]),
            models.Index(fields=["movement_type", "created_at"]),
        ]

    def __str__(self):
        return f"{self.product} {self.quantity}"


class ShopSequence(models.Model):
    TYPE_ORDER = "order"
    TYPE_PAYMENT = "payment"
    TYPE_STOCK = "stock"

    TYPE_CHOICES = [
        (TYPE_ORDER, "Commande"),
        (TYPE_PAYMENT, "Paiement"),
        (TYPE_STOCK, "Stock"),
    ]

    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="shop_sequences")
    sequence_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    year = models.PositiveSmallIntegerField()
    last_number = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["branch", "sequence_type", "year"], name="shop_unique_sequence_branch_type_year")
        ]
