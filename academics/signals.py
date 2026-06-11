from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.urls import reverse

from academics.models import AcademicDiplomaAward
from communication.services.email_service import EmailService
from communication.services.notification_service import NotificationService


@receiver(pre_save, sender=AcademicDiplomaAward)
def diploma_award_track_status(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = sender.objects.get(pk=instance.pk)
            instance._old_status = old.status
        except sender.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None


@receiver(post_save, sender=AcademicDiplomaAward)
def diploma_award_notify(sender, instance, created, **kwargs):
    old_status = getattr(instance, "_old_status", None)
    if instance.status != AcademicDiplomaAward.STATUS_DELIVERED:
        return
    if old_status == AcademicDiplomaAward.STATUS_DELIVERED:
        return

    student = instance.student
    user = getattr(student, "user", None)
    if not user or not user.email:
        return

    diploma_url = reverse("academics:diploma_award_detail", args=[instance.id])
    diploma_name = instance.diploma.name if instance.diploma else str(instance.programme)

    EmailService.send_transactional(
        subject=f"Votre diplome {diploma_name} est disponible",
        recipient=user,
        event_type="diploma_ready",
        template_key="diploma_ready",
        context={
            "student_name": str(student),
            "diploma_name": diploma_name,
            "reference": instance.reference,
            "academic_year": instance.academic_year.name,
            "final_average": str(instance.final_average) if instance.final_average else "-",
            "mention": instance.mention,
            "diploma_url": diploma_url,
        },
        priority="high",
    )

    NotificationService.notify_user(
        recipient=user,
        actor=instance.delivered_by or instance.prepared_by,
        event_type="diploma_ready",
        title=f"Diplome disponible : {diploma_name}",
        body=f"Votre diplome {diploma_name} ({instance.reference}) a ete delivre. Consultez-le dans la section 'Mes diplomes' de votre portail.",
        source_app="academics",
        priority="high",
        legacy_source="academic_diploma_award",
        legacy_object_id=str(instance.id),
    )
