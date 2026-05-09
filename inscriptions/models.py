import secrets
import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone

from admissions.models import Candidature


class Inscription(models.Model):
    """
    Inscription officielle apres acceptation d'une candidature.
    """

    candidature = models.OneToOneField(
        Candidature,
        on_delete=models.PROTECT,
        related_name="inscription",
        db_index=True,
    )
    academic_class = models.ForeignKey(
        "academics.AcademicClass",
        on_delete=models.PROTECT,
        related_name="inscriptions",
        null=True,
        blank=True,
    )
    academic_level = models.CharField(
        max_length=10,
        blank=True,
        help_text="Niveau academique positionne administrativement.",
    )

    reference = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
    )
    public_token = models.CharField(
        max_length=60,
        unique=True,
        editable=False,
        db_index=True,
    )
    access_code = models.CharField(
        max_length=32,
        blank=True,
        editable=False,
        help_text="Code d’accès privé au dossier",
    )

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
        db_index=True,
    )

    amount_due = models.PositiveBigIntegerField(
        help_text="Montant total à payer (FCFA)",
    )
    amount_paid = models.PositiveBigIntegerField(
        default=0,
        editable=False,
        help_text="Montant payé (calcul automatique)",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    is_archived = models.BooleanField(
        default=False,
        db_index=True,
    )
    archived_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["is_archived"]),
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["status", "amount_paid"]),
        ]

    def __str__(self):
        return f"Inscription {self.public_token}"

    def clean(self):
        errors = {}

        if self.candidature.status not in ["accepted", "accepted_with_reserve"]:
            errors["candidature"] = "Impossible de creer une inscription pour une candidature non acceptee."

        if self.amount_due <= 0:
            errors["amount_due"] = "Le montant du doit etre superieur a zero."

        if self.academic_class_id:
            if not self.academic_class.is_active:
                errors["academic_class"] = "La classe academique selectionnee doit etre active."
            elif self.academic_class.programme_id != self.candidature.programme_id:
                errors["academic_class"] = "La classe academique ne correspond pas au programme."
            elif self.academic_class.branch_id != self.candidature.branch_id:
                errors["academic_class"] = "La classe academique ne correspond pas a l'annexe."
            else:
                from academics.services.academic_years import resolve_academic_year_reference

                candidature_year = resolve_academic_year_reference(self.candidature.academic_year)
                if candidature_year["status"] != "resolved":
                    errors["academic_class"] = (
                        "L'annee academique de la candidature n'est pas configuree correctement."
                    )
                elif self.academic_class.academic_year_id != candidature_year["academic_year"].id:
                    errors["academic_class"] = "La classe academique ne correspond pas a l'annee academique."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.academic_class_id and not self.academic_level:
            self.academic_level = self.academic_class.level

        if not self.public_token:
            self.public_token = self.generate_public_token()

        if not self.access_code:
            self.access_code = self.generate_access_code()

        self.full_clean()
        super().save(*args, **kwargs)

    @staticmethod
    def generate_public_token():
        return f"ESFE-INS-{secrets.token_urlsafe(12)}"

    @staticmethod
    def generate_access_code():
        return secrets.token_hex(8)

    def get_public_url(self):
        return reverse(
            "inscriptions:public_detail",
            kwargs={"token": self.public_token},
        )

    VALID_TRANSITIONS = {
        STATUS_CREATED: [STATUS_AWAITING_PAYMENT],
        STATUS_AWAITING_PAYMENT: [
            STATUS_PARTIAL,
            STATUS_ACTIVE,
            STATUS_EXPIRED,
        ],
        STATUS_PARTIAL: [
            STATUS_ACTIVE,
            STATUS_CANCELLED,
        ],
        STATUS_ACTIVE: [
            STATUS_SUSPENDED,
            STATUS_COMPLETED,
            STATUS_CANCELLED,
        ],
        STATUS_SUSPENDED: [STATUS_ACTIVE],
    }

    def change_status(self, new_status):
        allowed = self.VALID_TRANSITIONS.get(self.status, [])
        if new_status not in allowed:
            raise ValidationError(f"Transition interdite : {self.status} -> {new_status}")

        previous = self.status
        self.status = new_status
        self.save(update_fields=["status"])

        StatusHistory.objects.create(
            inscription=self,
            previous_status=previous,
            new_status=new_status,
        )

    def update_financial_state(self):
        total_paid = (
            self.payments
            .filter(status="validated")
            .aggregate(total=Sum("amount"))["total"]
            or 0
        )

        self.amount_paid = total_paid

        if total_paid == 0:
            self.status = self.STATUS_AWAITING_PAYMENT
        elif total_paid < self.amount_due:
            self.status = self.STATUS_PARTIAL
        else:
            self.status = self.STATUS_ACTIVE

        self.save(update_fields=["amount_paid", "status"])

    @property
    def balance(self):
        return max(self.amount_due - self.amount_paid, 0)

    @property
    def is_paid(self):
        return self.amount_paid >= self.amount_due

    @property
    def is_active(self):
        return self.status == self.STATUS_ACTIVE

    def archive(self):
        self.is_archived = True
        self.archived_at = timezone.now()
        self.save(update_fields=["is_archived", "archived_at"])


class StatusHistory(models.Model):
    inscription = models.ForeignKey(
        Inscription,
        on_delete=models.CASCADE,
        related_name="history",
    )
    previous_status = models.CharField(
        max_length=20,
    )
    new_status = models.CharField(
        max_length=20,
    )
    comment = models.TextField(
        blank=True,
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["inscription", "created_at"]),
        ]

    def __str__(self):
        return f"{self.inscription.reference} : {self.previous_status} -> {self.new_status}"
