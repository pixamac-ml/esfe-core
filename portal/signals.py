"""Notifications pedagogiques pour le Directeur des Etudes (cf.
CAHIER_DES_CHARGES_DIRECTEUR_ETUDES.md, 2.4). Suit le meme pattern que
`academics/signals.py` (post_save -> NotificationService)."""
from django.db.models.signals import post_save
from django.dispatch import receiver

from communication.models import CommunicationNotification
from communication.services.notification_service import NotificationService
from portal.models import TeacherDocument, TransferRequest


def _directors_of_studies_for_branch(branch):
    from accounts.models import Profile

    return list(
        Profile.objects.select_related("user")
        .filter(position="director_of_studies", branch=branch, user__is_active=True)
        .values_list("user", flat=True)
    )


def _notify_directors(branch, *, event_type, title, body, legacy_source, legacy_object_id):
    from django.contrib.auth import get_user_model

    director_ids = _directors_of_studies_for_branch(branch)
    if not director_ids:
        return
    User = get_user_model()
    for director in User.objects.filter(pk__in=director_ids, is_active=True):
        NotificationService.notify_user(
            recipient=director,
            event_type=event_type,
            title=title,
            body=body,
            source_app="portal",
            priority=CommunicationNotification.PRIORITY_NORMAL,
            legacy_source=legacy_source,
            legacy_object_id=legacy_object_id,
        )


@receiver(post_save, sender=TeacherDocument)
def teacher_document_notify_pending(sender, instance, created, **kwargs):
    if not created or instance.is_verified:
        return
    teacher_label = instance.teacher.get_full_name() or instance.teacher.username
    _notify_directors(
        instance.branch,
        event_type="teacher_document_pending",
        title="Document enseignant en attente",
        body=f"{teacher_label} a transmis un document ({instance.get_document_type_display()}) en attente de verification.",
        legacy_source="teacher_document",
        legacy_object_id=str(instance.pk),
    )


@receiver(post_save, sender=TransferRequest)
def transfer_request_notify_created(sender, instance, created, **kwargs):
    if not created or instance.status != TransferRequest.STATUS_SUBMITTED:
        return
    student = instance.enrollment.student
    student_label = student.get_full_name() or student.username
    _notify_directors(
        instance.branch,
        event_type="transfer_request_created",
        title="Nouvelle demande de transfert",
        body=f"Une demande de transfert a ete creee pour {student_label} ({instance.source_class.display_name}).",
        legacy_source="transfer_request",
        legacy_object_id=str(instance.pk),
    )
