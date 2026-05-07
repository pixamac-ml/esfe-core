import logging

from django.conf import settings

from core.emailing import send_templated_email

from .base import BaseEmailProvider, ProviderResult
from communication.services.template_registry import resolve_email_configuration


logger = logging.getLogger(__name__)


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

        resolved_email = resolve_email_configuration(
            event_type=notification.event_type,
            title=notification.title,
            body=notification.body,
            metadata=notification.metadata,
        )
        context = {
            "notification": notification,
            **resolved_email["context"],
        }

        logger.info(
            "Envoi email transactionnel event=%s template=%s recipient=%s",
            notification.event_type,
            resolved_email["html_template"] or resolved_email["text_template"] or "fallback_text",
            recipient,
        )
        send_templated_email(
            subject=notification.title,
            recipient=recipient,
            text_template=resolved_email["text_template"],
            html_template=resolved_email["html_template"],
            context=context,
            attachments=resolved_email["attachments"],
            fallback_text=resolved_email["fallback_text"],
            fail_silently=False,
        )
        return ProviderResult(status="sent", provider=self.provider_name)
