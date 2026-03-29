# admissions/emails.py
"""
Fonctions d'envoi des notifications par email
"""

import logging

from urllib.parse import urljoin

from django.utils import timezone
from django.conf import settings

from core.emailing import send_templated_email
from core.models import Notification


logger = logging.getLogger(__name__)


def send_notification_email(notification_id):
    """
    Envoie un email de notification au candidat
    """

    try:
        notification = Notification.objects.get(pk=notification_id)
    except Notification.DoesNotExist:
        return False

    if notification.email_sent:
        return False

    context = {
        "recipient_name": notification.recipient_name,
        "message": notification.message,
        "candidate_reference": notification.related_candidature.id if notification.related_candidature else None,
        "programme_name": notification.related_candidature.programme.title if notification.related_candidature else None,
        "dashboard_url": urljoin(getattr(settings, "BASE_URL", "https://www.esfe-mali.org").rstrip("/") + "/", "candidature/"),
        "reference": notification.related_candidature.reference if notification.related_candidature else None,
    }

    template_name = "emails/notification_candidature.html"


    try:
        send_templated_email(
            subject=f"[ESFE] {notification.title}",
            recipient=notification.recipient_email,
            html_template=template_name,
            context=context,
            fail_silently=False,
        )

        notification.email_sent = True
        notification.sent_at = timezone.now()
        notification.save(update_fields=["email_sent", "sent_at"])

        return True

    except Exception:
        logger.exception("Echec envoi notification candidature id=%s", notification_id)
        return False


def send_pending_notifications():
    """
    Envoie toutes les notifications en attente
    """

    pending = Notification.objects.filter(email_sent=False)
    sent_count = 0

    for notification in pending:
        if send_notification_email(notification.id):
            sent_count += 1

    return sent_count