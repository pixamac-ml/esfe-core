from django.db import models, transaction
from django.utils import timezone
from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.contrib.auth import get_user_model

from branches.models import Branch
from inscriptions.models import Inscription

from payments.services.receipt import generate_receipt_number
from payments.services.qrcode import generate_qr_image
from payments.utils.pdf import render_pdf

from students.services.create_student import create_student_after_first_payment
from students.services.email import (
    send_student_credentials_email,
    send_payment_confirmation_email
)

import secrets
import random
from datetime import timedelta

User = get_user_model()


# ==================================================
# PAYMENT AGENT
# ==================================================

class PaymentAgent(models.Model):

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        limit_choices_to={"is_staff": True},
        related_name="payment_agent_profile"
    )

    agent_code = models.CharField(
        max_length=8,
        unique=True,
        editable=False,
        db_index=True
    )

    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="payment_agents",
        db_index=True
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["user__last_name"]

        indexes = [
            models.Index(fields=["branch"]),
            models.Index(fields=["is_active"]),
        ]

    def save(self, *args, **kwargs):

        if not self.agent_code:
            self.agent_code = secrets.token_hex(3).upper()

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.agent_code})"


# ==================================================
# CASH PAYMENT SESSION
# ==================================================

class CashPaymentSession(models.Model):

    inscription = models.ForeignKey(
        Inscription,
        on_delete=models.CASCADE,
        related_name="cash_sessions",
        db_index=True
    )

    agent = models.ForeignKey(
        PaymentAgent,
        on_delete=models.PROTECT,
        related_name="cash_sessions",
        db_index=True
    )

    verification_code = models.CharField(max_length=6)

    expires_at = models.DateTimeField(db_index=True)

    is_used = models.BooleanField(default=False, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

        indexes = [
            models.Index(fields=["expires_at"]),
            models.Index(fields=["is_used"]),
            models.Index(fields=["agent", "created_at"]),
        ]

    def generate_code(self):

        self.verification_code = str(random.randint(100000, 999999))

        self.expires_at = timezone.now() + timedelta(minutes=5)

        self.save(update_fields=["verification_code", "expires_at"])

    def is_valid(self, code):

        return (
            not self.is_used
            and self.verification_code == code
            and timezone.now() <= self.expires_at
        )

    def __str__(self):
        return f"Session cash {self.inscription.reference}"


# ==================================================
# PAYMENT
# ==================================================

class Payment(models.Model):

    METHOD_CASH = "cash"
    METHOD_ORANGE = "orange_money"
    METHOD_BANK = "bank_transfer"

    METHOD_CHOICES = (
        (METHOD_CASH, "Espèces"),
        (METHOD_ORANGE, "Orange Money"),
        (METHOD_BANK, "Virement bancaire"),
    )

    STATUS_PENDING = "pending"
    STATUS_VALIDATED = "validated"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = (
        (STATUS_PENDING, "En attente"),
        (STATUS_VALIDATED, "Validé"),
        (STATUS_CANCELLED, "Annulé"),
    )

    inscription = models.ForeignKey(
        Inscription,
        on_delete=models.CASCADE,
        related_name="payments",
        db_index=True
    )

    agent = models.ForeignKey(
        PaymentAgent,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="payments"
    )

    cash_session = models.ForeignKey(
        CashPaymentSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
    )

    amount = models.PositiveBigIntegerField()

    method = models.CharField(
        max_length=30,
        choices=METHOD_CHOICES,
        db_index=True
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True
    )

    reference = models.CharField(
        max_length=100,
        blank=True,
        db_index=True
    )

    receipt_number = models.CharField(
        max_length=50,
        unique=True,
        null=True,
        blank=True
    )

    receipt_pdf = models.FileField(
        upload_to="payments/receipts/",
        null=True,
        blank=True
    )

    paid_at = models.DateTimeField(default=timezone.now, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:

        ordering = ["-paid_at"]

        indexes = [

            models.Index(fields=["paid_at"]),
            models.Index(fields=["status"]),
            models.Index(fields=["method"]),

            # dashboards financiers
            models.Index(fields=["status", "paid_at"]),
            models.Index(fields=["method", "paid_at"]),
            models.Index(fields=["inscription", "status"]),

        ]

    def __str__(self):
        return f"{self.amount} FCFA – {self.inscription.reference}"

    # ==================================================
    # VALIDATION MÉTIER
    # ==================================================

    def clean(self):

        if self.amount <= 0:
            raise ValidationError("Le montant doit être supérieur à zéro.")

        inscription = self.inscription

        if inscription.status in ["cancelled", "expired"]:
            raise ValidationError(
                "Impossible de payer une inscription annulée ou expirée."
            )

        if inscription.status == "completed":
            raise ValidationError(
                "L'inscription est déjà terminée."
            )

        total_paid = (
            inscription.payments
            .filter(status=self.STATUS_VALIDATED)
            .aggregate(total=Sum("amount"))["total"]
            or 0
        )

        if self.status == self.STATUS_VALIDATED:

            future_total = total_paid + self.amount

            # protection surpaiement extrême
            if future_total > inscription.amount_due * 2:
                raise ValidationError(
                    "Montant incohérent détecté."
                )

    # ==================================================
    # PIPELINE MÉTIER
    # ==================================================

    def save(self, *args, **kwargs):

        previous_status = None

        if self.pk:

            previous_status = (
                Payment.objects.only("status")
                .get(pk=self.pk)
                .status
            )

            if previous_status == self.STATUS_VALIDATED:
                raise ValueError(
                    "Un paiement validé ne peut plus être modifié."
                )

        if not self.reference:
            self.reference = f"PAY-{secrets.token_hex(4).upper()}"

        self.full_clean()

        with transaction.atomic():

            inscription = (
                Inscription.objects
                .select_for_update()
                .get(pk=self.inscription_id)
            )

            super().save(*args, **kwargs)

            just_validated = (
                self.status == self.STATUS_VALIDATED
                and previous_status != self.STATUS_VALIDATED
            )

            if not just_validated:
                return

            # ==================================================
            # MISE À JOUR FINANCIÈRE
            # ==================================================

            inscription.update_financial_state()

            # ==================================================
            # GÉNÉRATION REÇU
            # ==================================================

            if not self.receipt_number:

                self.receipt_number = generate_receipt_number(self)

                qr_image = generate_qr_image(
                    inscription.get_public_url()
                )

                pdf_bytes = render_pdf(
                    payment=self,
                    inscription=inscription,
                    qr_image=qr_image
                )

                self.receipt_pdf.save(
                    f"receipt-{self.receipt_number}.pdf",
                    ContentFile(pdf_bytes),
                    save=False
                )

                super().save(
                    update_fields=["receipt_number", "receipt_pdf"]
                )

        transaction.on_commit(
            lambda: self._post_commit_actions()
        )

    # ==================================================
    # ACTIONS APRÈS COMMIT
    # ==================================================

    def _post_commit_actions(self):

        result = create_student_after_first_payment(self.inscription)

        if result and result.get("created") and result.get("password"):

            send_student_credentials_email(
                student=result["student"],
                raw_password=result["password"]
            )

        else:

            send_payment_confirmation_email(payment=self)
