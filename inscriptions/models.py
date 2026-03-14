import uuid
import secrets

from django.db import models
from django.db.models import Sum
from django.urls import reverse
from django.core.exceptions import ValidationError
from django.utils import timezone

from admissions.models import Candidature


class Inscription(models.Model):
    """
    Inscription officielle après acceptation d’une candidature.

    RÈGLES FONDAMENTALES :

    - amount_due est FIGÉ lors de la création
    - amount_paid est CALCULÉ uniquement via Payment
    - Cette table est la SOURCE DE VÉRITÉ FINANCIÈRE
    - Une inscription ne peut exister que si la candidature est ACCEPTÉE
    """

    # ==================================================
    # LIEN MÉTIER
    # ==================================================

    candidature = models.OneToOneField(
        Candidature,
        on_delete=models.PROTECT,
        related_name="inscription"
    )

    # ==================================================
    # IDENTIFIANTS
    # ==================================================

    reference = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True
    )

    public_token = models.CharField(
        max_length=60,
        unique=True,
        editable=False,
        db_index=True
    )

    access_code = models.CharField(
        max_length=32,
        blank=True,
        editable=False,
        help_text="Code d’accès privé au dossier"
    )

    # ==================================================
    # STATUTS (MACHINE D'ÉTAT)
    # ==================================================

    STATUS_CREATED = "created"
    STATUS_AWAITING_PAYMENT = "awaiting_payment"
    STATUS_PARTIAL = "partial_paid"
    STATUS_ACTIVE = "active"
    STATUS_SUSPENDED = "suspended"
    STATUS_CANCELLED = "cancelled"
    STATUS_COMPLETED = "completed"
    STATUS_EXPIRED = "expired"

    STATUS_CHOICES = (
        (STATUS_CREATED, "Créée"),
        (STATUS_AWAITING_PAYMENT, "En attente paiement"),
        (STATUS_PARTIAL, "Paiement partiel"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_SUSPENDED, "Suspendue"),
        (STATUS_CANCELLED, "Annulée"),
        (STATUS_COMPLETED, "Terminée"),
        (STATUS_EXPIRED, "Expirée"),
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_CREATED,
        db_index=True
    )

    # ==================================================
    # FINANCES
    # ==================================================

    amount_due = models.PositiveBigIntegerField(
        help_text="Montant total à payer (FCFA)"
    )

    amount_paid = models.PositiveBigIntegerField(
        default=0,
        editable=False,
        help_text="Montant payé (calcul automatique)"
    )

    # ==================================================
    # MÉTADONNÉES
    # ==================================================

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    # ==================================================
    # REPRÉSENTATION
    # ==================================================

    def __str__(self):
        return f"Inscription {self.public_token}"

    # ==================================================
    # VALIDATION MÉTIER
    # ==================================================

    def clean(self):
        """
        Validation croisée métier.
        """

        if self.candidature.status != "accepted":
            raise ValidationError(
                "Impossible de créer une inscription pour une candidature non acceptée."
            )

        if self.amount_due <= 0:
            raise ValidationError(
                "Le montant dû doit être supérieur à zéro."
            )

    # ==================================================
    # SAVE SÉCURISÉ
    # ==================================================

    def save(self, *args, **kwargs):

        if not self.public_token:
            self.public_token = self.generate_public_token()

        if not self.access_code:
            self.access_code = self.generate_access_code()

        self.full_clean()

        super().save(*args, **kwargs)

    # ==================================================
    # GÉNÉRATEURS
    # ==================================================

    @staticmethod
    def generate_public_token():
        return f"ESFE-INS-{secrets.token_urlsafe(12)}"

    @staticmethod
    def generate_access_code():
        return secrets.token_hex(8)

    # ==================================================
    # URL PUBLIQUE
    # ==================================================

    def get_public_url(self):
        return reverse(
            "inscriptions:public_detail",
            kwargs={"token": self.public_token}
        )

    # ==================================================
    # MACHINE D'ÉTAT
    # ==================================================

    VALID_TRANSITIONS = {
        STATUS_CREATED: [STATUS_AWAITING_PAYMENT],
        STATUS_AWAITING_PAYMENT: [STATUS_PARTIAL, STATUS_ACTIVE, STATUS_EXPIRED],
        STATUS_PARTIAL: [STATUS_ACTIVE, STATUS_CANCELLED],
        STATUS_ACTIVE: [STATUS_SUSPENDED, STATUS_COMPLETED, STATUS_CANCELLED],
        STATUS_SUSPENDED: [STATUS_ACTIVE],
    }

    def change_status(self, new_status):

        allowed = self.VALID_TRANSITIONS.get(self.status, [])

        if new_status not in allowed:
            raise ValidationError(
                f"Transition interdite : {self.status} → {new_status}"
            )

        self.status = new_status
        self.save(update_fields=["status"])

    # ==================================================
    # LOGIQUE FINANCIÈRE DÉTERMINISTE
    # ==================================================

    def update_financial_state(self):
        """
        Recalcule l'état financier à partir des paiements validés.
        """

        total_paid = (
            self.payments
            .filter(status="validated")
            .aggregate(total=Sum("amount"))["total"]
            or 0
        )

        if total_paid < 0:
            total_paid = 0

        self.amount_paid = total_paid

        if total_paid == 0:
            self.status = self.STATUS_AWAITING_PAYMENT

        elif total_paid < self.amount_due:
            self.status = self.STATUS_PARTIAL

        else:
            self.status = self.STATUS_ACTIVE

        self.save(update_fields=["amount_paid", "status"])

    # ==================================================
    # PROPRIÉTÉS
    # ==================================================

    @property
    def balance(self):
        return max(self.amount_due - self.amount_paid, 0)

    @property
    def is_paid(self):
        return self.amount_paid >= self.amount_due

    @property
    def is_active(self):
        return self.status == self.STATUS_ACTIVE

    # ==================================================
    # ARCHIVAGE
    # ==================================================

    is_archived = models.BooleanField(
        default=False,
        db_index=True
    )

    archived_at = models.DateTimeField(
        null=True,
        blank=True
    )
    def archive(self):
        self.is_archived = True
        self.archived_at = timezone.now()
        self.save(update_fields=["is_archived", "archived_at"])

class StatusHistory(models.Model):

    inscription = models.ForeignKey(
        "Inscription",
        on_delete=models.CASCADE,
        related_name="history"
    )

    previous_status = models.CharField(max_length=20)

    new_status = models.CharField(max_length=20)

    comment = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.inscription.reference} : {self.previous_status} → {self.new_status}"