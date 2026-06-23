"""Creation et envoi des convocations disciplinaires (surveillant general)."""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.utils import timezone

from branches.models import Branch
from students.models import Convocation


def _normalize_branch(branch: Branch | int | None) -> Branch:
    if branch is None:
        raise ValidationError("Une annexe est obligatoire.")
    if isinstance(branch, Branch):
        return branch
    return Branch.objects.get(pk=branch)


def create_convocation(
    *,
    target_type: str,
    branch,
    motif: str,
    channel: str,
    scheduled_date,
    scheduled_time,
    created_by,
    student=None,
    teacher=None,
    message: str = "",
    destinataire: str = "",
    student_case=None,
    teacher_case=None,
):
    """
    Persiste toujours la convocation. Seul le canal Email declenche un envoi reel (via
    NotificationService/Brevo) ; SMS/appel/courrier sont enregistres comme intention a
    traiter manuellement (aucune passerelle SMS/telephonie n'existe dans ce depot).
    """
    branch = _normalize_branch(branch)
    if target_type == Convocation.TARGET_STUDENT and student is None:
        raise ValidationError("Un etudiant est requis pour une convocation etudiant.")
    if target_type == Convocation.TARGET_TEACHER and teacher is None:
        raise ValidationError("Un enseignant est requis pour une convocation enseignant.")

    initial_status = (
        Convocation.STATUS_PLANNED if channel == Convocation.CHANNEL_EMAIL else Convocation.STATUS_MANUAL
    )

    convocation = Convocation.objects.create(
        target_type=target_type,
        student=student,
        teacher=teacher,
        student_case=student_case,
        teacher_case=teacher_case,
        branch=branch,
        destinataire=destinataire,
        motif=motif,
        channel=channel,
        scheduled_date=scheduled_date,
        scheduled_time=scheduled_time,
        message=message,
        status=initial_status,
        created_by=created_by,
    )

    if channel == Convocation.CHANNEL_EMAIL:
        _send_convocation_email(convocation)

    return convocation


def _send_convocation_email(convocation: Convocation) -> None:
    from communication.models import CommunicationNotification
    from communication.services.notification_service import NotificationService

    recipient = (
        convocation.student.user
        if convocation.target_type == Convocation.TARGET_STUDENT
        else convocation.teacher
    )
    if recipient is None:
        return

    title = "Convocation — ESFE"
    body = (
        f"Vous etes convoque(e) le {convocation.scheduled_date:%d/%m/%Y} a "
        f"{convocation.scheduled_time:%H:%M}.\nMotif : {convocation.motif}\n\n{convocation.message}"
    ).strip()

    try:
        NotificationService.notify_user(
            recipient=recipient,
            actor=convocation.created_by,
            event_type="supervisor_convocation",
            title=title,
            body=body,
            source_app="portal",
            channels=(
                CommunicationNotification.CHANNEL_EMAIL_TRANSACTIONAL,
                CommunicationNotification.CHANNEL_IN_APP,
                CommunicationNotification.CHANNEL_WEBSOCKET,
            ),
            metadata={"convocation_id": convocation.id, "motif": convocation.motif},
        )
    except Exception:
        convocation.status = Convocation.STATUS_MANUAL
        convocation.save(update_fields=["status"])
        return

    convocation.status = Convocation.STATUS_SENT
    convocation.sent_at = timezone.now()
    convocation.save(update_fields=["status", "sent_at"])
