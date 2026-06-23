"""Workflow OTP anti-fraude pour la modification d'operations financieres deja finalisees.

Regle metier : la creation d'une operation (paiement, fiche de paie, ...) n'est
jamais bloquee. C'est uniquement quand la gestionnaire tente de MODIFIER ou
ANNULER une operation deja validee/payee que ce workflow s'active : un code
OTP est envoye au DG et a la DGA, et la modification reelle n'est appliquee
qu'apres saisie du bon code dans le delai imparti (5 minutes).
"""
import hashlib
import secrets

from django.db import transaction
from django.utils import timezone

from accounts.models import FinancialAuditLog, Profile, SensitiveActionRequest
from communication.models import CommunicationNotification
from communication.services.email_service import EmailService
from communication.services.notification_service import NotificationService


class SensitiveActionError(Exception):
    pass


def _hash_code(code):
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _generate_code():
    return f"{secrets.randbelow(1_000_000):06d}"


DG_POSITIONS = ["executive_director", "deputy_executive_director"]


def _approvers_for_branch(branch):
    return list(
        Profile.objects.select_related("user")
        .filter(position__in=DG_POSITIONS, user__is_active=True)
        .values_list("user", flat=True)
    )


def request_sensitive_action(
    *,
    branch,
    action_type,
    target_model,
    target_id,
    previous_state,
    requested_state,
    requested_by,
    reason="",
):
    """Cree la demande, genere l'OTP, et notifie DG + DGA. Ne modifie rien."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    approver_ids = _approvers_for_branch(branch)
    approvers = list(User.objects.filter(pk__in=approver_ids, is_active=True))
    if not approvers:
        raise SensitiveActionError(
            "Aucun DG ou DGA actif n'est configure pour valider cette action. "
            "Contactez l'administrateur du systeme."
        )

    code = _generate_code()
    expires_at = timezone.now() + timezone.timedelta(minutes=SensitiveActionRequest.OTP_VALIDITY_MINUTES)

    request_obj = SensitiveActionRequest.objects.create(
        branch=branch,
        action_type=action_type,
        target_model=target_model,
        target_id=target_id,
        reason=reason,
        previous_state=previous_state,
        requested_state=requested_state,
        requested_by=requested_by,
        otp_code_hash=_hash_code(code),
        expires_at=expires_at,
    )

    action_label = dict(SensitiveActionRequest.ACTION_CHOICES).get(action_type, action_type)
    body = (
        f"La gestionnaire {requested_by.get_full_name() or requested_by.username} de l'annexe "
        f"{branch} demande : {action_label} sur {target_model} #{target_id}.\n\n"
        f"Etat actuel : {previous_state}\n"
        f"Etat demande : {requested_state}\n"
        f"Motif : {reason or 'non precise'}\n\n"
        f"Code de validation : {code}\n"
        f"Ce code expire dans {SensitiveActionRequest.OTP_VALIDITY_MINUTES} minutes."
    )

    for approver in approvers:
        NotificationService.notify_user(
            recipient=approver,
            actor=requested_by,
            event_type="sensitive_action_otp",
            title=f"Validation requise - {action_label}",
            body=body,
            source_app="accounts",
            priority=CommunicationNotification.PRIORITY_HIGH,
            channels=(
                CommunicationNotification.CHANNEL_IN_APP,
                CommunicationNotification.CHANNEL_WEBSOCKET,
            ),
            metadata={
                "sensitive_action_request_id": request_obj.pk,
                "branch_id": branch.pk,
                "action_type": action_type,
            },
            legacy_source="sensitive_action_request",
            legacy_object_id=str(request_obj.pk),
        )
        if approver.email:
            EmailService.send_transactional(
                subject=f"[ESFE] Validation requise - {action_label} - {branch}",
                recipient=approver,
                recipient_email=approver.email,
                actor=requested_by,
                source_app="accounts",
                event_type="sensitive_action_otp",
                body=body,
                legacy_source="sensitive_action_request",
                legacy_object_id=str(request_obj.pk),
            )

    return request_obj


def confirm_sensitive_action(*, request_id, code, approver, apply_callback):
    """Verifie le code OTP et applique la modification via apply_callback si valide.

    apply_callback(request_obj) -> dict (new_state) : fonction qui applique
    reellement la modification metier et retourne le nouvel etat pour l'audit.
    """
    error_message = None

    with transaction.atomic():
        request_obj = (
            SensitiveActionRequest.objects.select_for_update().get(pk=request_id)
        )

        if request_obj.status != SensitiveActionRequest.STATUS_PENDING:
            error_message = "Cette demande n'est plus en attente de validation."
        elif timezone.now() > request_obj.expires_at:
            request_obj.status = SensitiveActionRequest.STATUS_EXPIRED
            request_obj.resolved_at = timezone.now()
            request_obj.save(update_fields=["status", "resolved_at"])
            error_message = "Le code n'a pas ete entre a temps. Veuillez recommencer la demande."
        else:
            request_obj.attempts += 1
            if _hash_code(code) != request_obj.otp_code_hash:
                request_obj.save(update_fields=["attempts"])
                error_message = "Code de validation incorrect."
            else:
                new_state = apply_callback(request_obj)

                request_obj.status = SensitiveActionRequest.STATUS_APPROVED
                request_obj.approved_by = approver
                request_obj.resolved_at = timezone.now()
                request_obj.save(update_fields=["status", "approved_by", "resolved_at", "attempts"])

                FinancialAuditLog.objects.create(
                    branch=request_obj.branch,
                    action_type=request_obj.action_type,
                    target_model=request_obj.target_model,
                    target_id=request_obj.target_id,
                    previous_state=request_obj.previous_state,
                    new_state=new_state or request_obj.requested_state,
                    performed_by=request_obj.requested_by,
                    approved_by=approver,
                    sensitive_action_request=request_obj,
                )

    # Note : l'exception est levee APRES la sortie du bloc atomic, pour que les
    # mises a jour deja faites (compteur d'essais, expiration) restent commitees
    # meme quand la demande est finalement rejetee.
    if error_message:
        raise SensitiveActionError(error_message)

    return request_obj


def expire_stale_requests():
    """A appeler periodiquement (cron) pour marquer expirees les demandes oubliees."""
    stale = SensitiveActionRequest.objects.filter(
        status=SensitiveActionRequest.STATUS_PENDING,
        expires_at__lt=timezone.now(),
    )
    return stale.update(status=SensitiveActionRequest.STATUS_EXPIRED, resolved_at=timezone.now())
