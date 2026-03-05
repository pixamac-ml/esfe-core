"""
Context processors pour l'application community
"""


def notifications_processor(request):
    """
    Ajoute le nombre de notifications non lues à toutes les pages
    """
    from community.models import Notification

    unread_count = 0

    if request.user.is_authenticated:
        unread_count = Notification.objects.filter(
            user=request.user,
            is_read=False
        ).count()

    return {
        "unread_notification_count": unread_count
    }