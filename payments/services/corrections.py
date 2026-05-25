from django.core.exceptions import ValidationError
from django.db import transaction

from payments.models import FinancialLog, Payment, PaymentCorrection
from payments.services.workflows import sync_payment_finance_history


def correct_validated_payment_amount(*, payment, new_amount, reason, actor=None):
    if payment.status != Payment.STATUS_VALIDATED:
        raise ValidationError("Seul un paiement valide peut etre corrige.")

    if new_amount <= 0:
        raise ValidationError("Le nouveau montant doit etre superieur a zero.")

    reason = (reason or "").strip()
    if len(reason) < 8:
        raise ValidationError("Le motif de correction doit etre explicite.")

    with transaction.atomic():
        locked_payment = (
            Payment.objects
            .select_for_update()
            .select_related("inscription__candidature__branch")
            .get(pk=payment.pk)
        )

        if locked_payment.status != Payment.STATUS_VALIDATED:
            raise ValidationError("Seul un paiement valide peut etre corrige.")

        old_amount = locked_payment.amount
        if old_amount == new_amount:
            raise ValidationError("Le nouveau montant est identique au montant actuel.")
        if new_amount > locked_payment.inscription.amount_due * 2:
            raise ValidationError("Montant incoherent detecte.")

        branch = locked_payment.inscription.candidature.branch
        correction = PaymentCorrection.objects.create(
            payment=locked_payment,
            old_amount=old_amount,
            new_amount=new_amount,
            delta_amount=new_amount - old_amount,
            reason=reason,
            corrected_by=actor if getattr(actor, "is_authenticated", False) else None,
        )

        Payment.objects.filter(pk=locked_payment.pk).update(amount=new_amount)
        locked_payment.amount = new_amount

        locked_payment.inscription.update_financial_state()
        movement = sync_payment_finance_history(payment=locked_payment, actor=actor)
        if movement:
            movement.refresh_from_db()

        FinancialLog.objects.create(
            branch=branch,
            payment=locked_payment,
            correction=correction,
            action=FinancialLog.ACTION_PAYMENT_CORRECTED,
            old_amount=old_amount,
            new_amount=new_amount,
            delta_amount=new_amount - old_amount,
            reason=reason,
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            metadata={
                "payment_reference": locked_payment.reference,
                "receipt_number": locked_payment.receipt_number or "",
                "inscription_id": locked_payment.inscription_id,
                "cash_movement_id": getattr(movement, "pk", None),
            },
        )

    locked_payment.refresh_from_db()
    return correction


def financial_logs_for_payment(payment):
    return (
        FinancialLog.objects
        .filter(payment=payment)
        .select_related("actor", "correction")
        .order_by("-created_at")
    )
