from django.conf import settings

from core.emailing import send_templated_email

from .base import BaseEmailProvider, ProviderResult


class BrevoEmailProvider(BaseEmailProvider):
    provider_name = "brevo"

    def __init__(self):
        self.mode = getattr(settings, "COMMUNICATION_EMAIL_PROVIDER_MODE", "smtp")

    def send_notification(self, notification):
        recipient = (
            notification.metadata.get("recipient_email")
            or getattr(getattr(notification, "recipient", None), "email", "")
        )
        if not recipient:
            return ProviderResult(status="skipped", provider=self.provider_name)

        template_name = notification.metadata.get("html_template") or "emails/base_communication.html"
        context = {
            "title": notification.title,
            "message": notification.body,
            "notification": notification,
            **notification.metadata.get("context", {}),
        }

        # This keeps Brevo isolated behind a provider boundary. SMTP is the
        # default transport until API credentials/templates are wired in.
        send_templated_email(
            subject=notification.title,
            recipient=recipient,
            text_template=notification.metadata.get("text_template"),
            html_template=template_name,
            context=context,
            fail_silently=False,
        )
        return ProviderResult(status="sent", provider=self.provider_name)
