# admissions/emails.py
"""Adaptateur de reprise email branche sur le noyau communication/."""

import logging

from communication.models import CommunicationNotification
from communication.services.dispatcher import NotificationDispatcher


logger = logging.getLogger(__name__)


def send_notification_email(notification_id):
    """
    Rejoue une notification email centralisee.
    """

    try:
        notification = CommunicationNotification.objects.get(
            pk=notification_id,
            channel=CommunicationNotification.CHANNEL_EMAIL_TRANSACTIONAL,
        )
    except CommunicationNotification.DoesNotExist:
        return False

    if notification.status in {
        CommunicationNotification.STATUS_SENT,
        CommunicationNotification.STATUS_DELIVERED,
        CommunicationNotification.STATUS_READ,
        CommunicationNotification.STATUS_SKIPPED,
    }:
        return False

    try:
        NotificationDispatcher.dispatch(notification)
        return True
    except Exception:
        logger.exception("Echec replay notification centralisee id=%s", notification_id)
        return False


def send_pending_notifications():
    """
    Rejoue toutes les notifications email centralisees en attente.
    """

    pending = CommunicationNotification.objects.filter(
        channel=CommunicationNotification.CHANNEL_EMAIL_TRANSACTIONAL,
        status__in=[
            CommunicationNotification.STATUS_PENDING,
            CommunicationNotification.STATUS_QUEUED,
            CommunicationNotification.STATUS_FAILED,
        ],
    ).order_by("created_at")
    sent_count = 0

    for notification in pending:
        if send_notification_email(notification.id):
            sent_count += 1

    return sent_count
