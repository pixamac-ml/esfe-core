from django.db.models import Count, Q

from academics.models import AcademicClass
from coupons.models import Coupon


def active_coupons_for_branch(branch, *, limit=5):
    """Coupons utilisables dans au moins une formation active de l'annexe."""
    programme_ids = AcademicClass.objects.filter(
        branch=branch,
        is_active=True,
    ).values_list("programme_id", flat=True)

    candidates = (
        Coupon.objects.filter(is_active=True)
        .filter(Q(branches__isnull=True) | Q(branches=branch))
        .filter(Q(programmes__isnull=True) | Q(programmes__in=programme_ids))
        .annotate(usage_count=Count("redemptions", distinct=True))
        .prefetch_related("branches", "programmes")
        .distinct()
        .order_by("-created_at")
    )
    coupons = [coupon for coupon in candidates if coupon.is_currently_valid()]
    return coupons[:limit] if limit is not None else coupons
