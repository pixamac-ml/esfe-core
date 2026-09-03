from __future__ import annotations

from django.db import transaction
from django.core.exceptions import ValidationError
from django.db.models import Count, Prefetch, Q, Sum
from django.utils import timezone

from branches.models import Branch
from coupons.models import Coupon, CouponRedemption
from notifier.models import NotificationMessage
from notifier.services.audience import resolve_platform_users
from notifier.services.bus import NotificationBus

COUPON_RECIPIENT_ROLE_TOKENS = [
    "secretary",
    "finance_manager",
    "payment_agent",
    "admissions",
    "branch_manager",
    "annex_manager",
]


def _scoped_coupons(*, branch_ids=None):
    queryset = Coupon.objects.all()
    if branch_ids is not None:
        queryset = queryset.filter(Q(branches__id__in=branch_ids) | Q(branches__isnull=True)).distinct()
    return queryset


def list_coupons(*, branch_ids=None):
    return (
        _scoped_coupons(branch_ids=branch_ids)
        .annotate(
            usage_count=Count("redemptions", distinct=True),
            discount_total=Sum("redemptions__discount_amount"),
        )
        .prefetch_related("branches", "programmes")
        .order_by("-created_at")
    )


def get_coupon_detail(coupon_id, *, branch_ids=None):
    redemptions = CouponRedemption.objects.select_related(
        "applied_by",
        "inscription__candidature__branch",
        "inscription__candidature__programme",
    ).order_by("-applied_at")
    return (
        _scoped_coupons(branch_ids=branch_ids)
        .select_related("created_by")
        .prefetch_related("branches", "programmes", Prefetch("redemptions", queryset=redemptions))
        .filter(pk=coupon_id)
        .first()
    )


@transaction.atomic
def create_coupon(*, actor, form, allowed_branch_ids=None):
    data = form.cleaned_data
    requested_branch_ids = set((data.get("branches") or []).values_list("id", flat=True))
    if allowed_branch_ids is not None:
        allowed_branch_ids = set(allowed_branch_ids)
        if not requested_branch_ids:
            requested_branch_ids = allowed_branch_ids
        if not requested_branch_ids.issubset(allowed_branch_ids):
            raise ValidationError("Une annexe du coupon est hors du contexte DG actif.")
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
    coupon.branches.set(requested_branch_ids)
    coupon.programmes.set(data.get("programmes") or [])

    _notify_coupon_created(actor=actor, coupon=coupon)

    return coupon


@transaction.atomic
def toggle_coupon(*, actor, coupon_id, allowed_branch_ids=None):
    coupon = _scoped_coupons(branch_ids=allowed_branch_ids).select_for_update().filter(pk=coupon_id).first()
    if coupon is None:
        return None
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
    reduction = (
        f"{coupon.value} %"
        if coupon.discount_type == Coupon.DISCOUNT_PERCENTAGE
        else f"{coupon.value} FCFA"
    )
    body = f"{coupon.label} — réduction de {reduction} sur {programme_names}."

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
