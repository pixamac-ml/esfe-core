from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from branches.models import Branch
from coupons.models import Coupon
from notifier.models import NotificationMessage
from notifier.services.audience import resolve_platform_users
from notifier.services.bus import NotificationBus

COUPON_RECIPIENT_ROLE_TOKENS = [
    "secretary",
    "finance_manager",
    "payment_agent",
    "admissions",
    "branch_manager",
]


def list_coupons():
    return (
        Coupon.objects.all()
        .prefetch_related("branches", "programmes", "redemptions")
        .order_by("-created_at")
    )


@transaction.atomic
def create_coupon(*, actor, form):
    data = form.cleaned_data
    coupon = Coupon(
        code=data["code"],
        label=data["label"],
        discount_type=data["discount_type"],
        value=data["value"],
        valid_from=data.get("valid_from") or timezone.now(),
        valid_until=data["valid_until"],
        max_redemptions=data.get("max_redemptions") or 1,
        created_by=actor,
    )
    coupon.save()
    coupon.branches.set(data.get("branches") or [])
    coupon.programmes.set(data.get("programmes") or [])

    _notify_coupon_created(actor=actor, coupon=coupon)

    return coupon


def toggle_coupon(*, actor, coupon_id):
    coupon = Coupon.objects.get(pk=coupon_id)
    coupon.is_active = not coupon.is_active
    coupon.save(update_fields=["is_active", "updated_at"])
    return coupon


def _notify_coupon_created(*, actor, coupon):
    branch_ids = list(coupon.branches.values_list("id", flat=True))
    if not branch_ids:
        branch_ids = list(Branch.objects.filter(is_active=True).values_list("id", flat=True))

    recipients = resolve_platform_users(
        audience_scope="scoped",
        branch_ids=branch_ids,
        role_tokens=COUPON_RECIPIENT_ROLE_TOKENS,
    )

    programme_names = ", ".join(p.title for p in coupon.programmes.all()) or "toutes les formations"
    title = f"Nouveau coupon disponible : {coupon.code}"
    body = (
        f"{coupon.label} — {coupon.get_discount_type_display()} de {coupon.value} "
        f"sur {programme_names}."
    )

    for recipient in recipients:
        NotificationBus.notify(
            recipient=recipient,
            actor=actor,
            event_type="coupon_created",
            title=title,
            body=body,
            source_app="coupons",
            channels=(NotificationMessage.CHANNEL_IN_APP, NotificationMessage.CHANNEL_WEBSOCKET),
            metadata={"coupon_id": coupon.id, "coupon_code": coupon.code},
        )
