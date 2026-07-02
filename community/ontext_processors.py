"""
Context processors pour l'application community
"""

# DEPRECATED: le compteur officiel de notifications passe par communication/.
from notification_center.selectors import get_user_unread_count


def notifications_processor(request):
    """
    Ajoute le nombre de notifications non lues à toutes les pages
    """
    unread_count = 0

    if request.user.is_authenticated:
        unread_count = get_user_unread_count(request.user)

    return {
        "unread_notification_count": unread_count
    }
