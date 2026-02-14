# payments/models.py

from django.db import models, transaction
from django.utils import timezone
from django.core.files.base import ContentFile
from django.db.models import Sum

from inscriptions.models import Inscription
from payments.services.receipt import generate_receipt_number
from payments.services.qrcode import generate_qr_image
from payments.utils.pdf import render_pdf

from students.services.create_student import (
    create_student_after_first_payment
)
from students.services.email import (
    send_student_credentials_email,
    send_payment_confirmation_email
)

from django.contrib.auth import get_user_model
import secrets
from datetime import timedelta
import random

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
        editable=False
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

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
        related_name="cash_sessions"
    )

    agent = models.ForeignKey(
        PaymentAgent,
        on_delete=models.PROTECT,
        related_name="cash_sessions"
    )

    verification_code = models.CharField(max_length=6)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

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

    METHOD_CHOICES = (
        ("cash", "Espèces"),
        ("orange_money", "Orange Money"),
        ("bank_transfer", "Virement bancaire"),
    )

    STATUS_CHOICES = (
        ("pending", "En attente"),
        ("validated", "Validé"),
        ("cancelled", "Annulé"),
    )

    inscription = models.ForeignKey(
        Inscription,
        on_delete=models.CASCADE,
        related_name="payments"
    )

    agent = models.ForeignKey(
        PaymentAgent,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="payments"
    )

    amount = models.PositiveBigIntegerField(
        help_text="Montant payé en FCFA"
    )

    method = models.CharField(
        max_length=30,
        choices=METHOD_CHOICES,
        db_index=True
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        db_index=True
    )

    reference = models.CharField(
        max_length=100,
        blank=True
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

    paid_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-paid_at"]
        indexes = [
            models.Index(fields=["paid_at"]),
        ]

    def __str__(self):
        return f"{self.amount} FCFA – {self.inscription.reference}"

    # ==================================================
    # PIPELINE MÉTIER SÉCURISÉ
    # ==================================================
    def save(self, *args, **kwargs):

        previous_status = None

        if self.pk:
            previous_status = (
                Payment.objects.only("status")
                .get(pk=self.pk)
                .status
            )

            # 🔒 Empêcher rétrogradation d’un paiement validé
            if previous_status == "validated" and self.status != "validated":
                raise ValueError("Un paiement validé ne peut pas être modifié.")

        with transaction.atomic():

            super().save(*args, **kwargs)

            just_validated = (
                self.status == "validated"
                and previous_status != "validated"
            )

            if not just_validated:
                return

            # 1️⃣ Mise à jour financière inscription
            self.inscription.update_financial_state()

            # 2️⃣ Génération reçu UNIQUE
            if not self.receipt_number:

                self.receipt_number = generate_receipt_number(self)

                qr_image = generate_qr_image(
                    self.inscription.get_public_url()
                )

                pdf_bytes = render_pdf(
                    payment=self,
                    inscription=self.inscription,
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

        # ==========================================
        # ACTIONS POST-COMMIT SÉCURISÉES
        # ==========================================
        transaction.on_commit(
            lambda: self._post_commit_actions()
        )

    # ==================================================
    # POST-COMMIT
    # ==================================================
    def _post_commit_actions(self):

        result = create_student_after_first_payment(self.inscription)

        if result:
            send_student_credentials_email(
                student=result["student"],
                raw_password=result["password"]
            )
        else:
            send_payment_confirmation_email(payment=self)
