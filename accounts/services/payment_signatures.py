import base64
import hashlib
import re
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from accounts.models import (
    BranchCashMovement,
    PaymentSignatureSession,
    PayrollEntry,
    TeacherHonorariumEntry,
)
from accounts.services.accounting_documents import create_cash_movement, ensure_cash_movement_receipt
from accounts.services.financial_integrity import assert_financial_period_open
from accounts.services.manager_intelligence import (
    lock_branch_cash_balance,
    payroll_cash_reference,
)
from accounts.services.wallets import configured_wallet_for_category, consume_wallet_for_cash_movement, wallet_balance
from notifier.models import NotificationMessage
from notifier.services import NotificationBus


SESSION_MINUTES = 15
_DATA_IMAGE_RE = re.compile(r"^data:image/(?:png|jpeg|jpg|svg\+xml);base64,[A-Za-z0-9+/=\s]+$")


def _beneficiary_name(user):
    return user.get_full_name() or user.get_username()


def _entry_data(payment_type, entry):
    if payment_type == PaymentSignatureSession.TYPE_PAYROLL:
        return {
            "period_month": entry.period_month.isoformat(),
            "period_label": entry.period_month.strftime("%m/%Y"),
            "net_amount": int(entry.net_salary),
            "already_paid": int(entry.paid_amount),
            "remaining": int(entry.remaining_salary),
            "employee_name": _beneficiary_name(entry.employee),
            "employee_email": entry.employee.email or "",
            "label": "Salaire",
        }
    return {
        "period_month": entry.period_month.isoformat(),
        "period_label": entry.period_month.strftime("%m/%Y"),
        "net_amount": int(entry.net_amount),
        "already_paid": int(entry.paid_amount),
        "remaining": int(entry.remaining_amount),
        "employee_name": _beneficiary_name(entry.teacher),
        "employee_email": entry.teacher.email or "",
        "validated_hours": str(entry.validated_hours),
        "hourly_rate": int(entry.hourly_rate),
        "label": "Honoraire enseignant",
    }


def _active_for_entry(*, payment_type, entry):
    filters = {
        "branch": entry.branch,
        "payment_type": payment_type,
        "status__in": PaymentSignatureSession.ACTIVE_STATUSES,
    }
    filters["payroll_entry" if payment_type == PaymentSignatureSession.TYPE_PAYROLL else "honorarium_entry"] = entry
    return PaymentSignatureSession.objects.filter(**filters).order_by("-created_at").first()


def initiate_payment_signature(*, branch, payment_type, entry, amount, actor, base_url=""):
    """Create or reuse one active one-time signature link for an entry."""
    amount = int(amount or 0)
    if amount <= 0:
        raise ValidationError("Le montant de paiement doit etre positif.")
    remaining = entry.remaining_salary if payment_type == PaymentSignatureSession.TYPE_PAYROLL else entry.remaining_amount
    if amount > remaining:
        raise ValidationError("Le montant depasse le reste a payer.")
    expected_statuses = {PayrollEntry.STATUS_READY, PayrollEntry.STATUS_PARTIAL} if payment_type == PaymentSignatureSession.TYPE_PAYROLL else {TeacherHonorariumEntry.STATUS_READY, TeacherHonorariumEntry.STATUS_PARTIAL}
    if entry.status not in expected_statuses:
        raise ValidationError("La fiche doit etre disponible avant l'initiation du paiement.")

    existing = _active_for_entry(payment_type=payment_type, entry=entry)
    if existing:
        existing.status = PaymentSignatureSession.STATUS_CANCELLED if not existing.is_expired else PaymentSignatureSession.STATUS_EXPIRED
        existing.save(update_fields=["status", "updated_at"])

    raw_token, token_hash = PaymentSignatureSession.issue_token()
    session = PaymentSignatureSession.objects.create(
        branch=branch,
        payment_type=payment_type,
        payroll_entry=entry if payment_type == PaymentSignatureSession.TYPE_PAYROLL else None,
        honorarium_entry=entry if payment_type == PaymentSignatureSession.TYPE_HONORARIUM else None,
        beneficiary=entry.employee if payment_type == PaymentSignatureSession.TYPE_PAYROLL else entry.teacher,
        token_hash=token_hash,
        amount=amount,
        snapshot=_entry_data(payment_type, entry) | {"payment_amount": amount},
        status=PaymentSignatureSession.STATUS_AWAITING_SIGNATURE,
        expires_at=timezone.now() + timedelta(minutes=SESSION_MINUTES),
        created_by=actor,
    )
    session._raw_token = raw_token
    manager_link = (base_url.rstrip("/") + reverse("accounts:payment_signature_tablet", kwargs={"token": raw_token})) if base_url else reverse("accounts:payment_signature_tablet", kwargs={"token": raw_token})
    session._tablet_link = manager_link
    _notify_signature_requested(session, actor)
    return session, raw_token


def _notify_signature_requested(session, actor):
    recipient = session.beneficiary
    label = session.snapshot.get("label", "Paiement")
    body = f"Votre {label.lower()} de {session.amount:,} FCFA ({session.snapshot.get('period_label')}) attend votre signature sur tablette."
    channels = [NotificationMessage.CHANNEL_IN_APP, NotificationMessage.CHANNEL_WEBSOCKET]
    if recipient.email:
        channels.append(NotificationMessage.CHANNEL_EMAIL_TRANSACTIONAL)
    NotificationBus.notify(
        recipient=recipient,
        actor=actor,
        event_type="payment_signature_requested",
        title="Signature requise avant paiement",
        body=body,
        source_app="accounts",
        channels=tuple(channels),
        metadata={"payment_signature_session_id": session.pk, "amount": session.amount, "period_month": session.snapshot.get("period_month"), "signature_link": getattr(session, "_tablet_link", "")},
        legacy_source="payment_signature_session",
        legacy_object_id=str(session.pk),
    )


def get_session_for_token(raw_token):
    session = PaymentSignatureSession.objects.select_related("beneficiary", "branch", "created_by").filter(token_hash=PaymentSignatureSession.hash_token(raw_token)).first()
    if session and session.status in PaymentSignatureSession.ACTIVE_STATUSES and session.is_expired:
        session.status = PaymentSignatureSession.STATUS_EXPIRED
        session.save(update_fields=["status", "updated_at"])
    return session


def save_signature(*, session, signature_data, request):
    if session.status != PaymentSignatureSession.STATUS_AWAITING_SIGNATURE or session.is_expired:
        raise ValidationError("Ce lien de signature n'est plus utilisable.")
    if not signature_data or len(signature_data) > 350000 or not _DATA_IMAGE_RE.match(signature_data):
        raise ValidationError("La signature tablette est invalide ou trop volumineuse.")
    try:
        base64.b64decode(signature_data.split(",", 1)[1], validate=True)
    except (ValueError, UnicodeEncodeError):
        raise ValidationError("La signature tablette est invalide.")
    session.signature_data = signature_data
    session.signature_sha256 = hashlib.sha256(signature_data.encode("utf-8")).hexdigest()
    session.signed_at = timezone.now()
    session.signed_ip = request.META.get("REMOTE_ADDR")
    session.signed_user_agent = (request.META.get("HTTP_USER_AGENT") or "")[:300]
    session.status = PaymentSignatureSession.STATUS_SIGNED
    session.save(update_fields=["signature_data", "signature_sha256", "signed_at", "signed_ip", "signed_user_agent", "status", "updated_at"])
    manager = session.created_by
    if manager:
        NotificationBus.notify(
            recipient=manager,
            actor=session.beneficiary,
            event_type="payment_signature_received",
            title="Signature recue",
            body=f"{_beneficiary_name(session.beneficiary)} a signe le recapitulatif de {session.amount:,} FCFA. Le paiement peut etre approuve.",
            source_app="accounts",
            channels=(NotificationMessage.CHANNEL_IN_APP, NotificationMessage.CHANNEL_WEBSOCKET),
            metadata={"payment_signature_session_id": session.pk, "amount": session.amount},
            legacy_source="payment_signature_session",
            legacy_object_id=str(session.pk),
        )
    return session


def complete_payment(*, session_id, branch, approver):
    """Approve and book the payment exactly once after a beneficiary signature."""
    with transaction.atomic():
        _locked_branch, available_cash = lock_branch_cash_balance(branch)
        session = PaymentSignatureSession.objects.select_for_update().select_related("branch", "beneficiary").get(pk=session_id, branch=branch)
        if session.status == PaymentSignatureSession.STATUS_COMPLETED:
            return session, False
        if session.status != PaymentSignatureSession.STATUS_SIGNED or session.is_expired:
            raise ValidationError("La signature doit etre recue et encore valide avant l'approbation.")
        if session.payment_type == PaymentSignatureSession.TYPE_PAYROLL:
            entry = PayrollEntry.objects.select_for_update().select_related("employee").get(pk=session.payroll_entry_id, branch=branch)
            remaining = entry.remaining_salary
            source = BranchCashMovement.SOURCE_PAYROLL
            wallet_category = "salary"
            label = f"Salaire - {_beneficiary_name(entry.employee)}"
            source_reference = payroll_cash_reference(entry, entry.paid_amount + session.amount)
            period_month = entry.period_month
        else:
            entry = TeacherHonorariumEntry.objects.select_for_update().select_related("teacher").get(pk=session.honorarium_entry_id, branch=branch)
            remaining = entry.remaining_amount
            source = BranchCashMovement.SOURCE_HONORARIUM
            wallet_category = "honorarium"
            label = f"Honoraire - {_beneficiary_name(entry.teacher)}"
            source_reference = f"HON-{entry.pk}-{entry.paid_amount + session.amount}"
            period_month = entry.period_month
        assert_financial_period_open(branch, period_month)
        if session.amount > remaining or session.amount > available_cash:
            raise ValidationError("Le montant signe n'est plus disponible dans la fiche ou la caisse.")
        wallet = configured_wallet_for_category(branch, wallet_category)
        if wallet and session.amount > wallet_balance(wallet):
            raise ValidationError("La mini-caisse affectee est insuffisante.")
        entry.paid_amount += session.amount
        entry.updated_by = approver
        entry.save()
        movement = create_cash_movement(
            branch=branch, movement_type=BranchCashMovement.TYPE_OUT, source=source,
            amount=session.amount, label=label, movement_date=timezone.localdate(),
            source_reference=f"{source_reference}-SIG-{session.pk}",
            notes=f"Paiement signe et approuve {period_month:%Y-%m}.", created_by=approver,
        )
        if wallet:
            consume_wallet_for_cash_movement(wallet=wallet, cash_movement=movement, actor=approver, label=label)
        session.status = PaymentSignatureSession.STATUS_COMPLETED
        session.approved_by = approver
        session.approved_at = timezone.now()
        session.completed_at = timezone.now()
        session.cash_movement = movement
        session.save(update_fields=["status", "approved_by", "approved_at", "completed_at", "cash_movement", "updated_at"])
        # create_cash_movement generates the receipt before the session is
        # linked. Rebuild it now so the beneficiary signature is embedded in
        # the actual PDF, not only visible in the dashboard.
        if movement.receipt_pdf:
            movement.receipt_pdf.delete(save=False)
            movement.receipt_pdf = None
            movement.save(update_fields=["receipt_pdf"])
        ensure_cash_movement_receipt(movement)
    _notify_payment_completed(session)
    return session, True


def _notify_payment_completed(session):
    label = session.snapshot.get("label", "Paiement")
    body = f"Votre {label.lower()} de {session.amount:,} FCFA ({session.snapshot.get('period_label')}) a ete approuve et paye."
    channels = [NotificationMessage.CHANNEL_IN_APP, NotificationMessage.CHANNEL_WEBSOCKET]
    if session.beneficiary.email:
        channels.append(NotificationMessage.CHANNEL_EMAIL_TRANSACTIONAL)
    NotificationBus.notify(
        recipient=session.beneficiary, actor=session.approved_by, event_type="payment_completed",
        title="Paiement effectue", body=body, source_app="accounts", channels=tuple(channels),
        metadata={"payment_signature_session_id": session.pk, "amount": session.amount, "payment_amount": session.amount, "period_month": session.snapshot.get("period_month"), "receipt_number": getattr(session.cash_movement, "receipt_number", ""), "receipt_url": reverse("accounts:htmx_manager_cash_movement_receipt", kwargs={"pk": session.cash_movement_id}) if session.cash_movement_id else ""},
        legacy_source="payment_signature_session", legacy_object_id=str(session.pk),
    )
