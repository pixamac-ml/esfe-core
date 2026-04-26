from community.models import Notification as CommunityNotification
from core.models import Notification as CoreNotification


def get_notifications_widget(user):
    student = getattr(user, "student_profile", None)
    if student is None:
        return {
            "items": [],
            "empty_message": "Aucune notification pour le moment.",
        }

    email = student.email
    items = list(
        CoreNotification.objects.filter(recipient_email=email)
        .order_by("-created_at")
        .values_list("title", flat=True)[:4]
    )
    if not items:
        items = list(
            CommunityNotification.objects.filter(user=user)
            .order_by("-created_at")
            .values_list("notification_type", flat=True)[:4]
        )

    return {
        "items": items,
        "empty_message": "Aucune notification pour le moment.",
    }
