# admissions/emails.py
"""
Fonctions d'envoi des notifications par email
"""

from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.utils import timezone

from core.models import Notification


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
        "dashboard_url": getattr(settings, "BASE_URL", "https://www.esfe-mali.org"),
    }

    template_name = "emails/notification_candidature.html"

    try:
        html_message = render_to_string(template_name, context)
    except Exception:
        html_message = f"""
        <html>
        <body>
            <h2>Bonjour {notification.recipient_name},</h2>
            <p>{notification.message}</p>
        </body>
        </html>
        """

    try:
        send_mail(
            subject=f"[EPSFe] {notification.title}",
            message=notification.message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[notification.recipient_email],
            html_message=html_message,
            fail_silently=False,
        )

        notification.email_sent = True
        notification.sent_at = timezone.now()
        notification.save(update_fields=["email_sent", "sent_at"])

        return True

    except Exception as e:
        print(f"Erreur envoi email: {e}")
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