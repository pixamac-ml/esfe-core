from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import permission_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from coupons.forms import ApplyCouponForm
from coupons.services.application import apply_coupon
from inscriptions.models import Inscription


@staff_member_required
@permission_required("coupons.add_couponredemption", raise_exception=True)
@require_POST
def apply_coupon_view(request, inscription_id):
    """
    Applique un coupon à une inscription, depuis l'écran de gestion des
    paiements de la comptable.

    À brancher dans payments/urls.py ou superadmin/urls.py, par ex. :

        path(
            "inscriptions/<int:inscription_id>/coupon/appliquer/",
            apply_coupon_view,
            name="apply_coupon",
        ),

    Et dans le template de la fiche inscription, un petit formulaire
    POST-only (ApplyCouponForm) qui pointe vers cette URL.
    """

    inscription = get_object_or_404(Inscription, pk=inscription_id)
    form = ApplyCouponForm(request.POST)

    if not form.is_valid():
        messages.error(request, "Code coupon invalide.")
        return redirect(request.META.get("HTTP_REFERER", "/"))

    try:
        redemption = apply_coupon(
            code=form.cleaned_data["code"],
            inscription_id=inscription.id,
            actor=request.user,
        )
    except ValidationError as exc:
        messages.error(request, exc.messages[0] if hasattr(exc, "messages") else str(exc))
        return redirect(request.META.get("HTTP_REFERER", "/"))

    messages.success(
        request,
        f"Coupon {redemption.coupon.code} appliqué : "
        f"-{redemption.discount_amount} FCFA "
        f"(nouveau montant dû : {redemption.amount_after} FCFA).",
    )
    return redirect(request.META.get("HTTP_REFERER", "/"))
