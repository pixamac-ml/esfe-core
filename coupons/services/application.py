from django.core.exceptions import ValidationError
from django.db import transaction

from coupons.models import Coupon, CouponRedemption
from coupons.services.validation import validate_coupon
from inscriptions.models import Inscription
from payments.models import FinancialLog


@transaction.atomic
def apply_coupon(code, inscription_id, actor, *, branch=None):
    """
    Applique un coupon à une inscription.

    Opération atomique et auditable :
      1. Verrouille l'inscription (select_for_update) pour éviter toute
         application concurrente pendant qu'un paiement est en cours.
      2. Revalide le coupon (defense in depth : la validation a pu être
         faite plusieurs secondes avant, sur un aperçu).
      3. Calcule la réduction, avec un plancher = montant déjà payé et
         validé (impossible de faire "rembourser" via un coupon).
      4. Met à jour Inscription.amount_due + recalcule son statut financier.
      5. Crée un CouponRedemption immuable + une entrée FinancialLog,
         exactement comme pour une PaymentCorrection.

    Retourne l'objet CouponRedemption créé.
    """

    inscription_queryset = (
        Inscription.objects
        .select_for_update()
        .select_related("candidature__branch", "candidature__programme")
    )
    if branch is not None:
        inscription_queryset = inscription_queryset.filter(candidature__branch=branch)
    inscription = inscription_queryset.get(pk=inscription_id)

    normalized_code = (code or "").strip().upper()
    if not normalized_code:
        raise ValidationError("Aucun code coupon fourni.")
    try:
        coupon = Coupon.objects.select_for_update().get(code=normalized_code)
    except Coupon.DoesNotExist:
        raise ValidationError("Ce code coupon n'existe pas.") from None
    validate_coupon(coupon, inscription)

    amount_before = inscription.amount_due
    discount = coupon.compute_discount(amount_before)

    # Le montant dû ne peut jamais descendre sous ce qui a déjà été
    # payé et validé : un coupon réduit une facture, il ne rembourse pas.
    floor = inscription.amount_paid
    amount_after = max(amount_before - discount, floor)
    actual_discount = amount_before - amount_after

    if actual_discount <= 0:
        raise ValidationError(
            "La réduction calculée est nulle : le montant déjà payé "
            "couvre au moins le montant après réduction."
        )

    inscription.amount_due = amount_after
    inscription.save(update_fields=["amount_due", "updated_at"])
    inscription.update_financial_state()

    redemption = CouponRedemption.objects.create(
        coupon=coupon,
        inscription=inscription,
        amount_before=amount_before,
        amount_after=amount_after,
        discount_amount=actual_discount,
        applied_by=actor,
    )

    FinancialLog.objects.create(
        branch=getattr(inscription.candidature, "branch", None),
        old_amount=amount_before,
        new_amount=amount_after,
        delta_amount=-actual_discount,
        action=FinancialLog.ACTION_COUPON_APPLIED,
        reason=f"Coupon {coupon.code} appliqué ({coupon.label})",
        actor=actor,
        metadata={
            "coupon_code": coupon.code,
            "coupon_id": coupon.id,
            "redemption_id": redemption.id,
            "inscription_id": inscription.id,
            "inscription_reference": str(inscription.reference),
            "branch_id": inscription.candidature.branch_id,
        },
    )

    return redemption
