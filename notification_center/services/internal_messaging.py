import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from academics.models import AcademicEnrollment
from notifier.models import MessageAttachment, NotificationMessage
from notifier.services import NotificationBus


COLLECTIVE_POSITIONS = {
    "director_of_studies",
    "executive_director",
    "deputy_executive_director",
    "branch_manager",
    "annex_manager",
    "finance_manager",
    "admissions",
    "secretary",
}


def can_send_collective_message(user):
    if user.is_superuser:
        return True
    profile = getattr(user, "profile", None)
    return bool(profile and profile.position in COLLECTIVE_POSITIONS)


def _branch_user_ids(branch):
    staff_ids = get_user_model().objects.filter(
        is_active=True, profile__branch=branch
    ).values_list("id", flat=True)
    student_ids = AcademicEnrollment.objects.filter(
        branch=branch,
        is_active=True,
        is_archived=False,
        student__is_active=True,
    ).values_list("student_id", flat=True)
    return set(staff_ids).union(student_ids)


def resolve_internal_message_recipients(
    *, sender, branch, direct_recipient_ids=None, audience="individual",
    class_ids=None, programme_ids=None, role_tokens=None,
):
    if branch is None:
        raise ValidationError("Aucune annexe n'est rattachée à ce compte.")
    direct_recipient_ids = {int(pk) for pk in (direct_recipient_ids or []) if str(pk).isdigit()}
    class_ids = {int(pk) for pk in (class_ids or []) if str(pk).isdigit()}
    programme_ids = {int(pk) for pk in (programme_ids or []) if str(pk).isdigit()}
    role_tokens = {str(value).strip() for value in (role_tokens or []) if str(value).strip()}
    is_collective = audience != "individual" or len(direct_recipient_ids) > 1
    if is_collective and not can_send_collective_message(sender):
        raise ValidationError("Ce compte n'est pas autorisé à cibler un groupe de destinataires.")

    scoped_ids = _branch_user_ids(branch)
    recipient_ids = direct_recipient_ids.intersection(scoped_ids)
    User = get_user_model()

    if audience == "staff":
        staff = User.objects.filter(is_active=True, profile__branch=branch)
        if role_tokens:
            staff = staff.filter(Q(profile__position__in=role_tokens) | Q(profile__role__in=role_tokens))
        recipient_ids.update(staff.values_list("id", flat=True))
    elif audience == "teachers":
        recipient_ids.update(User.objects.filter(
            is_active=True, profile__branch=branch, profile__position="teacher"
        ).values_list("id", flat=True))
    elif audience in {"students", "classes", "programmes"}:
        enrollments = AcademicEnrollment.objects.filter(
            branch=branch,
            is_active=True,
            is_archived=False,
            student__is_active=True,
        )
        if audience == "classes":
            if not class_ids:
                raise ValidationError("Sélectionnez au moins une classe.")
            enrollments = enrollments.filter(academic_class_id__in=class_ids)
        elif audience == "programmes":
            if not programme_ids:
                raise ValidationError("Sélectionnez au moins un programme.")
            enrollments = enrollments.filter(programme_id__in=programme_ids)
        recipient_ids.update(enrollments.values_list("student_id", flat=True))
    elif audience != "individual":
        raise ValidationError("Cible de messagerie inconnue.")

    recipient_ids.discard(sender.pk)
    recipients = User.objects.filter(id__in=recipient_ids, is_active=True).order_by(
        "first_name", "last_name", "username"
    )
    if not recipients.exists():
        raise ValidationError("Aucun destinataire actif ne correspond à cette sélection.")
    return recipients


@transaction.atomic
def send_internal_message(
    *, sender, branch, recipients, title, body, priority, audience="individual",
    attachment=None, parent_message=None,
):
    if priority not in dict(NotificationMessage.PRIORITY_CHOICES):
        raise ValidationError("Priorité de message invalide.")
    recipients = list(recipients)
    if not recipients:
        raise ValidationError("Sélectionnez au moins un destinataire.")
    batch_id = uuid.uuid4()
    thread_id = (
        parent_message.thread_id
        if parent_message is not None and parent_message.thread_id
        else uuid.uuid4()
    )
    created_in_app = []
    metadata = {
        "kind": "internal_message",
        "branch_id": branch.pk,
        "batch_id": str(batch_id),
        "thread_id": str(thread_id),
        "audience": audience,
        "recipient_count": len(recipients),
    }
    for recipient in recipients:
        _event, messages = NotificationBus.notify(
            recipient=recipient,
            actor=sender,
            event_type="internal_message",
            title=title.strip(),
            body=body.strip(),
            source_app="notification_center",
            priority=priority,
            channels=(NotificationMessage.CHANNEL_IN_APP, NotificationMessage.CHANNEL_WEBSOCKET),
            metadata=metadata,
        )
        for message in messages:
            message.batch_id = batch_id
            message.thread_id = thread_id
            message.parent_message = parent_message
            message.save(update_fields=["batch_id", "thread_id", "parent_message", "updated_at"])
            if message.channel == NotificationMessage.CHANNEL_IN_APP:
                created_in_app.append(message)
    if attachment:
        MessageAttachment.objects.create(
            batch_id=batch_id,
            uploaded_by=sender,
            file=attachment,
            original_name=attachment.name,
            content_type=getattr(attachment, "content_type", "") or "",
            size=getattr(attachment, "size", 0) or 0,
        )
    return {
        "batch_id": batch_id,
        "thread_id": thread_id,
        "messages": created_in_app,
        "recipient_count": len(created_in_app),
    }
