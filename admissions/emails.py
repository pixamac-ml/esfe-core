# admissions/emails.py
"""Adaptateur de reprise email branche sur le noyau communication/."""

import logging

from notifier.models import NotificationMessage
from notifier.services import Dispatcher


logger = logging.getLogger(__name__)


def send_notification_email(notification_id):
    """
    Rejoue une notification email centralisee.
    """

    try:
        notification = NotificationMessage.objects.get(
            pk=notification_id,
            channel=NotificationMessage.CHANNEL_EMAIL_TRANSACTIONAL,
        )
    except NotificationMessage.DoesNotExist:
        return False

    if notification.status in {
        NotificationMessage.STATUS_SENT,
        NotificationMessage.STATUS_DELIVERED,
        NotificationMessage.STATUS_READ,
        NotificationMessage.STATUS_SKIPPED,
    }:
        return False

    try:
        Dispatcher.dispatch(notification)
        return True
    except Exception:
        logger.exception("Echec replay notification centralisee id=%s", notification_id)
        return False


def send_pending_notifications():
    """
    Rejoue toutes les notifications email centralisees en attente.
    """

    pending = NotificationMessage.objects.filter(
        channel=NotificationMessage.CHANNEL_EMAIL_TRANSACTIONAL,
        status__in=[
            NotificationMessage.STATUS_PENDING,
            NotificationMessage.STATUS_QUEUED,
            NotificationMessage.STATUS_FAILED,
        ],
    ).order_by("created_at")
    sent_count = 0

    for notification in pending:
        if send_notification_email(notification.id):
            sent_count += 1

    return sent_count
