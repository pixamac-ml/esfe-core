from django.contrib import admin

from shop.models import (
    ShopOrder,
    ShopOrderItem,
    ShopPayment,
    ShopProduct,
    ShopProductVariant,
    ShopSequence,
    ShopStockMovement,
)


class ShopProductVariantInline(admin.TabularInline):
    model = ShopProductVariant
    extra = 0


@admin.register(ShopProduct)
class ShopProductAdmin(admin.ModelAdmin):
    list_display = ("name", "branch", "category", "unit_price", "is_required", "is_active", "current_stock")
    list_filter = ("branch", "category", "is_required", "is_active")
    search_fields = ("name", "description")
    filter_horizontal = ("programmes",)
    inlines = [ShopProductVariantInline]


@admin.register(ShopProductVariant)
class ShopProductVariantAdmin(admin.ModelAdmin):
    list_display = ("product", "label", "extra_price", "is_active")
    list_filter = ("product__branch", "is_active")
    search_fields = ("product__name", "label")
    autocomplete_fields = ("product",)


class ShopOrderItemInline(admin.TabularInline):
    model = ShopOrderItem
    extra = 0


@admin.register(ShopOrder)
class ShopOrderAdmin(admin.ModelAdmin):
    list_display = ("reference", "student", "branch", "status", "total_amount", "created_at")
    list_filter = ("branch", "status", "created_at")
    search_fields = ("reference", "student__username", "student__first_name", "student__last_name")
    autocomplete_fields = ("branch", "inscription", "student", "created_by", "delivered_by")
    inlines = [ShopOrderItemInline]


@admin.register(ShopPayment)
class ShopPaymentAdmin(admin.ModelAdmin):
    list_display = ("reference", "receipt_number", "order", "amount", "method", "status", "paid_at")
    list_filter = ("method", "status", "paid_at")
    search_fields = ("reference", "receipt_number", "order__reference")
    autocomplete_fields = ("order", "created_by")


@admin.register(ShopStockMovement)
class ShopStockMovementAdmin(admin.ModelAdmin):
    list_display = ("reference", "product", "variant", "branch", "movement_type", "quantity", "created_at")
    list_filter = ("branch", "movement_type", "created_at")
    search_fields = ("reference", "product__name", "notes")
    autocomplete_fields = ("branch", "product", "variant", "order", "created_by")


@admin.register(ShopSequence)
class ShopSequenceAdmin(admin.ModelAdmin):
    list_display = ("branch", "sequence_type", "year", "last_number", "updated_at")
    list_filter = ("branch", "sequence_type", "year")
