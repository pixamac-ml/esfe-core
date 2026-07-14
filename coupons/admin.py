from django.contrib import admin
from django.utils.html import format_html

from coupons.models import Coupon, CouponRedemption


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):

    list_display = (
        "code",
        "label",
        "discount_type",
        "value",
        "is_active",
        "redemptions_display",
        "valid_from",
        "valid_until",
    )
    list_filter = ("discount_type", "is_active")
    search_fields = ("code", "label")
    filter_horizontal = ("programmes", "branches")
    readonly_fields = ("created_by", "created_at", "updated_at")

    def redemptions_display(self, obj):
        limit = obj.max_redemptions if obj.max_redemptions is not None else "∞"
        return format_html("{} / {}", obj.redemptions_count, limit)

    redemptions_display.short_description = "Utilisations"

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(CouponRedemption)
class CouponRedemptionAdmin(admin.ModelAdmin):
    """
    Journal d'audit en lecture seule : une réduction déjà appliquée ne
    doit jamais être modifiable depuis l'admin, uniquement consultable.
    """

    list_display = (
        "coupon",
        "inscription",
        "amount_before",
        "amount_after",
        "discount_amount",
        "applied_by",
        "applied_at",
    )
    list_filter = ("coupon",)
    search_fields = ("coupon__code", "inscription__reference")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
