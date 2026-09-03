"""Notifications liées aux publications académiques officielles."""

from django.urls import reverse

from academics.models import AcademicEnrollment
from notifier.models import NotificationMessage
from notifier.services import NotificationBus


def notify_students_of_published_semester(*, semester, actor=None):
    """Crée une notification persistante par étudiant, sans doublon."""
    enrollments = AcademicEnrollment.objects.filter(
        academic_class=semester.academic_class,
        academic_year=semester.academic_class.academic_year,
        is_active=True,
    ).select_related("student")
    action_url = f"{reverse('accounts_portal:portal_student')}?section=academics"
    created = 0
    for enrollment in enrollments:
        recipient = enrollment.student
        legacy_object_id = f"semester:{semester.pk}:student:{recipient.pk}"
        if NotificationMessage.objects.filter(
            recipient=recipient,
            event_type="semester_results_published",
            legacy_source="academics.semester_publication",
            legacy_object_id=legacy_object_id,
            channel=NotificationMessage.CHANNEL_IN_APP,
        ).exists():
            continue
        NotificationBus.notify(
            recipient=recipient,
            actor=actor,
            event_type="semester_results_published",
            title="Résultats disponibles",
            body=(
                f"Les résultats du Semestre {semester.number} ont été publiés. "
                "Consultez vos résultats et votre relevé de notes."
            ),
            source_app="academics",
            priority=NotificationMessage.PRIORITY_HIGH,
            metadata={
                "action_url": action_url,
                "semester_id": semester.pk,
                "academic_class_id": semester.academic_class_id,
                "branch_id": semester.academic_class.branch_id,
            },
            legacy_source="academics.semester_publication",
            legacy_object_id=legacy_object_id,
        )
        created += 1
    return created
