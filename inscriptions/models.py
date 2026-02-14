# inscriptions/models.py

import uuid
import secrets

from django.db import models
from django.db.models import Sum
from django.urls import reverse

from admissions.models import Candidature


class Inscription(models.Model):
    """
    Inscription officielle après acceptation d’une candidature.

    RÈGLES :
    - amount_due est FIGÉ lors de la création
    - amount_paid est CALCULÉ uniquement via Payment
    - Cette table est la SOURCE DE VÉRITÉ FINANCIÈRE
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
    # STATUT
    # ==================================================
    STATUS_CHOICES = (
        ("created", "Créée"),
        ("active", "Active"),
        ("suspended", "Suspendue"),
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="created",
        db_index=True
    )

    # ==================================================
    # FINANCES (FIGÉES)
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
    # SAVE SÉCURISÉ
    # ==================================================
    def save(self, *args, **kwargs):
        """
        Génération sécurisée des identifiants.
        Aucune logique financière ici.
        """

        if not self.public_token:
            self.public_token = self.generate_public_token()

        if not self.access_code:
            self.access_code = self.generate_access_code()

        super().save(*args, **kwargs)

    # ==================================================
    # GÉNÉRATEURS
    # ==================================================
    @staticmethod
    def generate_public_token():
        return f"ESFE-INS-{secrets.token_urlsafe(12)}"

    @staticmethod
    def generate_access_code():
        # Plus robuste que token_urlsafe(6)
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
    # LOGIQUE FINANCIÈRE DÉTERMINISTE
    # ==================================================
    def update_financial_state(self):
        """
        ⚠️ Doit être appelée UNIQUEMENT après validation d’un paiement.
        """

        total_paid = (
            self.payments
            .filter(status="validated")
            .aggregate(total=Sum("amount"))["total"]
            or 0
        )

        # Sécurité anti incohérence
        if total_paid < 0:
            total_paid = 0

        self.amount_paid = total_paid

        if total_paid >= self.amount_due:
            self.status = "active"
        else:
            self.status = "created"

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
