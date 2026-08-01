from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from branches.models import Branch
from formations.models import Programme
from inscriptions.models import Inscription


# ==================================================
# COUPON
# ==================================================

class Coupon(models.Model):
    """
    Coupon de réduction applicable sur le montant dû (Inscription.amount_due)
    d'une ou plusieurs formations (Programme).

    NB: un coupon ne modifie jamais un Payment directement. Il agit sur
    Inscription.amount_due, et chaque application est tracée de façon
    immuable via CouponRedemption + FinancialLog (voir payments.models),
    exactement comme PaymentCorrection le fait pour les corrections de
    paiement.
    """

    DISCOUNT_PERCENTAGE = "percentage"
    DISCOUNT_FIXED = "fixed_amount"

    DISCOUNT_TYPE_CHOICES = (
        (DISCOUNT_PERCENTAGE, "Pourcentage"),
        (DISCOUNT_FIXED, "Montant fixe (FCFA)"),
    )

    AVAILABILITY_ACTIVE = "active"
    AVAILABILITY_DISABLED = "disabled"
    AVAILABILITY_SCHEDULED = "scheduled"
    AVAILABILITY_EXPIRED = "expired"
    AVAILABILITY_EXHAUSTED = "exhausted"

    AVAILABILITY_LABELS = {
        AVAILABILITY_ACTIVE: "Actif",
        AVAILABILITY_DISABLED: "Désactivé",
        AVAILABILITY_SCHEDULED: "Programmé",
        AVAILABILITY_EXPIRED: "Expiré",
        AVAILABILITY_EXHAUSTED: "Épuisé",
    }

    code = models.CharField(
        max_length=32,
        unique=True,
        db_index=True,
        help_text="Code communiqué au candidat (ex: MASTER-DG-2026).",
    )

    label = models.CharField(
        max_length=150,
        help_text="Description interne (ex: 'Réduction DG - promo rentrée 2026').",
    )

    discount_type = models.CharField(
        max_length=20,
        choices=DISCOUNT_TYPE_CHOICES,
    )

    value = models.PositiveIntegerField(
        help_text="Pourcentage (1-100) si type=Pourcentage, sinon montant en FCFA.",
    )

    programmes = models.ManyToManyField(
        Programme,
        blank=True,
        related_name="coupons",
        help_text="Formations concernées. Laisser vide = applicable à toutes les formations.",
    )

    branches = models.ManyToManyField(
        Branch,
        blank=True,
        related_name="coupons",
        help_text="Annexes concernées. Laisser vide = applicable à toutes les annexes.",
    )

    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(null=True, blank=True)

    max_redemptions = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Nombre maximum d'utilisations au total. Vide = illimité.",
    )

    is_active = models.BooleanField(default=True, db_index=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="coupons_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["is_active"]),
            models.Index(fields=["valid_from", "valid_until"]),
        ]

    def __str__(self):
        return f"{self.code} ({self.get_discount_type_display()})"

    def clean(self):
        if self.discount_type == self.DISCOUNT_PERCENTAGE and not (1 <= self.value <= 100):
            raise ValidationError({"value": "Un pourcentage doit être compris entre 1 et 100."})

        if self.discount_type == self.DISCOUNT_FIXED and self.value <= 0:
            raise ValidationError({"value": "Le montant doit être supérieur à zéro."})

        if self.valid_until and self.valid_from and self.valid_until <= self.valid_from:
            raise ValidationError({"valid_until": "La date de fin doit être postérieure à la date de début."})

    def save(self, *args, **kwargs):
        if self.code:
            self.code = self.code.strip().upper()
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def redemptions_count(self):
        if hasattr(self, "usage_count"):
            return self.usage_count
        return self.redemptions.count()

    @property
    def availability_status(self):
        """Retourne l'état métier réel du coupon, pas seulement is_active."""
        now = timezone.now()

        if not self.is_active:
            return self.AVAILABILITY_DISABLED
        if now < self.valid_from:
            return self.AVAILABILITY_SCHEDULED
        if self.valid_until and now > self.valid_until:
            return self.AVAILABILITY_EXPIRED
        if self.max_redemptions is not None and self.redemptions_count >= self.max_redemptions:
            return self.AVAILABILITY_EXHAUSTED
        return self.AVAILABILITY_ACTIVE

    @property
    def availability_status_label(self):
        return self.AVAILABILITY_LABELS[self.availability_status]

    def is_currently_valid(self):
        return self.availability_status == self.AVAILABILITY_ACTIVE

    def applies_to(self, *, branch, programme):
        branch_ok = not self.branches.exists() or self.branches.filter(pk=branch.pk).exists()
        programme_ok = not self.programmes.exists() or self.programmes.filter(pk=programme.pk).exists()
        return branch_ok and programme_ok

    def compute_discount(self, base_amount):
        if self.discount_type == self.DISCOUNT_PERCENTAGE:
            discount = round(base_amount * self.value / 100)
        else:
            discount = self.value

        return min(discount, base_amount)


# ==================================================
# COUPON REDEMPTION (journal d'audit, immuable)
# ==================================================

class CouponRedemption(models.Model):

    coupon = models.ForeignKey(
        Coupon,
        on_delete=models.PROTECT,
        related_name="redemptions",
        db_index=True,
    )

    inscription = models.OneToOneField(
        Inscription,
        on_delete=models.PROTECT,
        related_name="coupon_redemption",
    )

    amount_before = models.PositiveBigIntegerField()
    amount_after = models.PositiveBigIntegerField()
    discount_amount = models.PositiveBigIntegerField()

    applied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="coupon_redemptions",
    )
    applied_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-applied_at"]
        indexes = [
            models.Index(fields=["coupon", "applied_at"]),
        ]

    def __str__(self):
        return (
            f"{self.coupon.code} appliqué sur {self.inscription.reference} "
            f"(-{self.discount_amount} FCFA)"
        )
