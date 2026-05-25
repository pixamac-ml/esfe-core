from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.urls import reverse

from accounts.models import BranchCashMovement
from communication.models import CommunicationNotification
from communication.services import EmailService, NotificationService
from communication.services.channel_policy import resolve_channel_policy


User = get_user_model()


def _payment_cash_reference(payment):
    if payment.reference:
        return payment.reference
    return f"PAY-{payment.pk}"


def sync_payment_finance_history(*, payment, actor=None):
    inscription = getattr(payment, "inscription", None)
    candidature = getattr(inscription, "candidature", None)
    branch = getattr(candidature, "branch", None)
    if not branch:
        return None

    reference = _payment_cash_reference(payment)
    movement, _created = BranchCashMovement.objects.get_or_create(
        branch=branch,
        source=BranchCashMovement.SOURCE_STUDENT_PAYMENT,
        source_reference=reference,
        defaults={
            "movement_type": BranchCashMovement.TYPE_IN,
            "amount": payment.amount,
            "label": f"Paiement etudiant - {candidature.full_name}",
            "movement_date": payment.paid_at.date(),
            "reference": payment.reference,
            "receipt_number": payment.receipt_number or "",
            "notes": f"Workflow FIRST_PAYMENT_VALIDATED pour paiement #{payment.pk}.",
            "created_by": actor,
        },
    )
    changed_fields = []
    if movement.receipt_number != (payment.receipt_number or ""):
        movement.receipt_number = payment.receipt_number or ""
        changed_fields.append("receipt_number")
    if payment.reference and movement.reference != payment.reference:
        movement.reference = payment.reference
        changed_fields.append("reference")
    if movement.amount != payment.amount:
        movement.amount = payment.amount
        changed_fields.append("amount")
    if movement.movement_date != payment.paid_at.date():
        movement.movement_date = payment.paid_at.date()
        changed_fields.append("movement_date")
    if changed_fields:
        movement.save(update_fields=changed_fields)
    return movement


def _notify_user(*, recipient, event_type, title, body, metadata):
    if not recipient:
        return None
    policy = resolve_channel_policy(
        event_type,
        default_channels=(CommunicationNotification.CHANNEL_IN_APP,),
        default_priority=CommunicationNotification.PRIORITY_NORMAL,
        metadata=metadata,
    )
    return NotificationService.notify_user(
        recipient=recipient,
        actor=None,
        event_type=event_type,
        title=title,
        body=body,
        source_app="payments",
        channels=policy["channels"],
        priority=policy["priority"],
        metadata=policy["metadata"],
        dispatch_on_commit=False,
    )


def _iter_staff_recipients(branch):
    if not branch:
        return User.objects.none()
    return (
        User.objects.filter(
            Q(profile__role="finance", profile__branch=branch)
            | Q(profile__position="branch_manager", profile__branch=branch)
        )
        .distinct()
        .select_related("profile")
    )


def _build_student_metadata(payment):
    inscription = payment.inscription
    candidature = inscription.candidature
    receipt_url = reverse("payments:receipt_detail", args=[payment.receipt_number]) if payment.receipt_number else ""
    receipt_pdf_url = reverse("payments:receipt_pdf", args=[payment.receipt_number]) if payment.receipt_number else ""
    login_url = getattr(settings, "STUDENT_LOGIN_URL", "/accounts/login/")
    return {
        "payment_id": payment.pk,
        "inscription_id": inscription.pk,
        "student_reference": getattr(inscription, "public_token", ""),
        "payment_reference": payment.reference,
        "receipt_number": payment.receipt_number or "",
        "receipt_url": receipt_url,
        "receipt_pdf_url": receipt_pdf_url,
        "login_url": login_url,
        "recipient_email": candidature.email,
    }


def _build_staff_metadata(payment):
    inscription = payment.inscription
    candidature = inscription.candidature
    return {
        "payment_id": payment.pk,
        "inscription_id": inscription.pk,
        "candidate_reference": candidature.reference,
        "candidate_name": candidature.full_name,
        "payment_reference": payment.reference,
        "receipt_number": payment.receipt_number or "",
        "amount": payment.amount,
        "branch": getattr(candidature.branch, "name", ""),
    }


def _send_receipt_available_email(*, payment, student_user):
    candidature = payment.inscription.candidature
    if not candidature.email:
        return None
    attachments = []
    if payment.receipt_pdf and getattr(payment.receipt_pdf, "path", ""):
        attachments.append(
            {
                "path": payment.receipt_pdf.path,
                "name": f"recu-{payment.receipt_number}.pdf",
                "mimetype": "application/pdf",
            }
        )
    return EmailService.send_transactional(
        subject="ESFE - Votre recu officiel est disponible",
        recipient=student_user,
        recipient_email=candidature.email,
        source_app="payments",
        event_type="receipt_generated",
        template_key="receipt_generated",
        context={
            "title": "Votre recu officiel est disponible",
            "message": (
                f"Votre premier paiement a ete valide. "
                f"Le recu {payment.receipt_number or ''} est maintenant disponible."
            ).strip(),
            "receipt_url": reverse("payments:receipt_detail", args=[payment.receipt_number]) if payment.receipt_number else "",
            "receipt_pdf_url": reverse("payments:receipt_pdf", args=[payment.receipt_number]) if payment.receipt_number else "",
            "receipt_number": payment.receipt_number or "",
            "candidate_name": candidature.full_name,
            "first_name": candidature.first_name,
            "reference": payment.reference,
            "support_email": getattr(settings, "DEFAULT_FROM_EMAIL", "contact@esfe-mali.org"),
        },
        metadata={
            "payment_id": payment.pk,
            "receipt_number": payment.receipt_number or "",
            "receipt_url": reverse("payments:receipt_detail", args=[payment.receipt_number]) if payment.receipt_number else "",
            "receipt_pdf_url": reverse("payments:receipt_pdf", args=[payment.receipt_number]) if payment.receipt_number else "",
        },
        attachments=attachments,
        fallback_text=(
            f"Votre recu {payment.receipt_number or ''} est disponible. "
            f"Consultez votre recu ici: "
            f"{reverse('payments:receipt_detail', args=[payment.receipt_number]) if payment.receipt_number else ''}"
        ).strip(),
        dispatch_on_commit=False,
        legacy_source="payments.workflow.first_payment_validated",
        legacy_object_id=str(payment.pk),
    )


def run_first_payment_validated_workflow(*, payment, student_result):
    inscription = payment.inscription
    candidature = inscription.candidature
    student = (student_result or {}).get("student")
    student_user = getattr(student, "user", None)
    is_first_validated_payment = (
        inscription.payments.filter(status=payment.STATUS_VALIDATED).count() == 1
    )

    sync_payment_finance_history(payment=payment)

    if not is_first_validated_payment or not student_user:
        return {
            "is_first_validated_payment": is_first_validated_payment,
            "student_user_id": getattr(student_user, "pk", None),
        }

    student_metadata = _build_student_metadata(payment)
    staff_metadata = _build_staff_metadata(payment)

    _notify_user(
        recipient=student_user,
        event_type="payment_validated",
        title="Paiement valide",
        body="Votre paiement a ete valide. Vos acces etudiant et votre recu vous sont envoyes par email.",
        metadata=student_metadata,
    )

    for staff_user in _iter_staff_recipients(candidature.branch):
        _notify_user(
            recipient=staff_user,
            event_type="first_payment_validated_staff",
            title="Premier paiement valide",
            body=(
                f"Le premier paiement de {candidature.full_name} a ete valide "
                f"pour {payment.amount} FCFA."
            ),
            metadata=staff_metadata,
        )

    _send_receipt_available_email(payment=payment, student_user=student_user)

    return {
        "is_first_validated_payment": True,
        "student_user_id": student_user.pk,
    }
