"""Workflow OTP anti-fraude pour la correction d'une note EC apres cloture de session.

Meme principe que `accounts/services/sensitive_actions.py` (paiements) : la
saisie normale n'est jamais bloquee. C'est uniquement quand un informaticien
ou un gestionnaire tente de CORRIGER une note deja saisie dans une session
deja cloturee que ce workflow s'active : un code OTP est envoye au Directeur
des Etudes (a defaut a la direction executive) et la correction reelle n'est
appliquee qu'apres saisie du bon code dans le delai imparti (5 minutes).
"""
import hashlib
import secrets

from django.db import transaction
from django.utils import timezone

from academic_cycle.models import GradeModificationRequest
from academic_cycle.services.audit_service import log_action
from accounts.models import Profile
from communication.models import CommunicationNotification
from communication.services.email_service import EmailService
from communication.services.notification_service import NotificationService


class GradeModificationError(Exception):
    pass


def _hash_code(code):
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _generate_code():
    return f"{secrets.randbelow(1_000_000):06d}"


APPROVER_POSITIONS = ["director_of_studies", "executive_director", "deputy_executive_director"]


def _approvers_for_branch(branch):
    """Directeur des etudes de l'annexe en priorite, sinon direction executive (toute annexe)."""
    director_ids = list(
        Profile.objects.select_related("user")
        .filter(position="director_of_studies", branch=branch, user__is_active=True)
        .values_list("user", flat=True)
    )
    if director_ids:
        return director_ids
    return list(
        Profile.objects.select_related("user")
        .filter(position__in=["executive_director", "deputy_executive_director"], user__is_active=True)
        .values_list("user", flat=True)
    )


def request_grade_modification(*, branch, ec_grade, session_type, requested_score, requested_by, reason=""):
    """Cree la demande, genere l'OTP, et notifie le Directeur des Etudes. Ne modifie rien."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    approver_ids = _approvers_for_branch(branch)
    approvers = list(User.objects.filter(pk__in=approver_ids, is_active=True))
    if not approvers:
        raise GradeModificationError(
            "Aucun Directeur des Etudes ou direction executive actif n'est configure pour valider "
            "cette correction. Contactez l'administrateur du systeme."
        )

    previous_score = ec_grade.retake_score if session_type == GradeModificationRequest.SESSION_RETAKE else ec_grade.normal_score
    code = _generate_code()
    expires_at = timezone.now() + timezone.timedelta(minutes=GradeModificationRequest.OTP_VALIDITY_MINUTES)

    request_obj = GradeModificationRequest.objects.create(
        branch=branch,
        ec_grade=ec_grade,
        session_type=session_type,
        previous_score=previous_score,
        requested_score=requested_score,
        reason=reason,
        requested_by=requested_by,
        otp_code_hash=_hash_code(code),
        expires_at=expires_at,
    )

    session_label = "Rattrapage" if session_type == GradeModificationRequest.SESSION_RETAKE else "Normale"
    student = ec_grade.enrollment.student
    body = (
        f"L'informaticien {requested_by.get_full_name() or requested_by.username} de l'annexe "
        f"{branch} demande une correction de note deja cloturee :\n\n"
        f"Etudiant : {student.get_full_name() or student.username}\n"
        f"Matiere (EC) : {ec_grade.ec.title}\n"
        f"Session : {session_label}\n"
        f"Ancienne note : {previous_score if previous_score is not None else 'aucune'}\n"
        f"Note demandee : {requested_score}\n"
        f"Motif : {reason or 'non precise'}\n\n"
        f"Code de validation : {code}\n"
        f"Ce code expire dans {GradeModificationRequest.OTP_VALIDITY_MINUTES} minutes."
    )

    for approver in approvers:
        NotificationService.notify_user(
            recipient=approver,
            actor=requested_by,
            event_type="grade_modification_otp",
            title="Validation requise - Correction de note",
            body=body,
            source_app="academic_cycle",
            priority=CommunicationNotification.PRIORITY_HIGH,
            channels=(
                CommunicationNotification.CHANNEL_IN_APP,
                CommunicationNotification.CHANNEL_WEBSOCKET,
            ),
            metadata={
                "grade_modification_request_id": request_obj.pk,
                "branch_id": branch.pk,
            },
            legacy_source="grade_modification_request",
            legacy_object_id=str(request_obj.pk),
        )
        if approver.email:
            EmailService.send_transactional(
                subject=f"[ESFE] Validation requise - Correction de note - {branch}",
                recipient=approver,
                recipient_email=approver.email,
                actor=requested_by,
                source_app="academic_cycle",
                event_type="grade_modification_otp",
                body=body,
                legacy_source="grade_modification_request",
                legacy_object_id=str(request_obj.pk),
            )

    return request_obj


def confirm_grade_modification(*, request_id, code, approver, apply_callback):
    """Verifie le code OTP et applique la correction via apply_callback si valide.

    apply_callback(request_obj) -> dict (new_state) : fonction qui applique
    reellement la correction de note et retourne le nouvel etat pour l'audit.
    """
    error_message = None

    with transaction.atomic():
        request_obj = GradeModificationRequest.objects.select_for_update().get(pk=request_id)

        if request_obj.status != GradeModificationRequest.STATUS_PENDING:
            error_message = "Cette demande n'est plus en attente de validation."
        elif timezone.now() > request_obj.expires_at:
            request_obj.status = GradeModificationRequest.STATUS_EXPIRED
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

                request_obj.status = GradeModificationRequest.STATUS_APPROVED
                request_obj.approved_by = approver
                request_obj.resolved_at = timezone.now()
                request_obj.save(update_fields=["status", "approved_by", "resolved_at", "attempts"])

                log_action(
                    request_obj.requested_by,
                    "grade.modified_post_closure",
                    request_obj.ec_grade,
                    old_values={"score": str(request_obj.previous_score) if request_obj.previous_score is not None else None},
                    new_values=new_state or {"score": str(request_obj.requested_score)},
                    reason=request_obj.reason,
                    branch=request_obj.branch,
                )

    # L'exception est levee APRES la sortie du bloc atomic, pour que les mises
    # a jour deja faites (compteur d'essais, expiration) restent commitees
    # meme quand la demande est finalement rejetee.
    if error_message:
        raise GradeModificationError(error_message)

    return request_obj


def expire_stale_requests():
    """A appeler periodiquement (cron) pour marquer expirees les demandes oubliees."""
    stale = GradeModificationRequest.objects.filter(
        status=GradeModificationRequest.STATUS_PENDING,
        expires_at__lt=timezone.now(),
    )
    return stale.update(status=GradeModificationRequest.STATUS_EXPIRED, resolved_at=timezone.now())
