from django.core.exceptions import ValidationError
from django.utils import timezone

from coupons.models import Coupon


def validate_coupon(coupon, inscription):
    """Valide une instance déjà chargée, notamment verrouillée en transaction."""
    if not coupon.is_active:
        raise ValidationError("Ce coupon a été désactivé.")

    now = timezone.now()

    if now < coupon.valid_from:
        raise ValidationError("Ce coupon n'est pas encore valide.")

    if coupon.valid_until and now > coupon.valid_until:
        raise ValidationError("Ce coupon a expiré.")

    if coupon.max_redemptions is not None and coupon.redemptions.count() >= coupon.max_redemptions:
        raise ValidationError("Ce coupon a atteint son nombre maximum d'utilisations.")

    programme = inscription.candidature.programme
    branch = inscription.candidature.branch
    if not coupon.applies_to(branch=branch, programme=programme):
        raise ValidationError(
            f"Ce coupon n'est pas applicable à la formation « {programme.title} » "
            f"dans cette annexe."
        )

    if hasattr(inscription, "coupon_redemption"):
        raise ValidationError("Un coupon a déjà été appliqué à cette inscription.")

    if inscription.status in [inscription.STATUS_CANCELLED, inscription.STATUS_EXPIRED]:
        raise ValidationError(
            "Impossible d'appliquer un coupon à une inscription annulée ou expirée."
        )

    if inscription.is_paid:
        raise ValidationError(
            "Cette inscription est déjà entièrement payée : aucune réduction n'est possible."
        )

    return coupon


def get_valid_coupon(code, inscription):
    """
    Valide un code coupon pour une inscription donnée.

    Lève ValidationError avec un message explicite en français si le
    coupon ne peut pas être appliqué. Retourne l'instance Coupon sinon.

    Cette fonction ne modifie rien : elle est appelée à la fois par
    l'aperçu ("combien ça ferait ?") et par l'application réelle.
    """

    code = (code or "").strip().upper()

    if not code:
        raise ValidationError("Aucun code coupon fourni.")

    try:
        coupon = Coupon.objects.get(code=code)
    except Coupon.DoesNotExist:
        raise ValidationError("Ce code coupon n'existe pas.")

    return validate_coupon(coupon, inscription)
