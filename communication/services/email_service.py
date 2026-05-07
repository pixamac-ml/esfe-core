from communication.models import CommunicationNotification
from communication.services.event_bus import CommunicationEventBus
from communication.services.json_utils import make_json_safe
from communication.services.template_registry import resolve_email_configuration


class EmailService:
    @staticmethod
    def send_transactional(
        *,
        subject,
        recipient=None,
        recipient_email="",
        actor=None,
        source_app="core",
        event_type="transactional_email",
        body="",
        html_template="",
        text_template=None,
        context=None,
        metadata=None,
        priority=CommunicationNotification.PRIORITY_NORMAL,
        dispatch_on_commit=True,
        legacy_source="",
        legacy_object_id="",
        attachments=None,
        fallback_text="",
        template_key="",
    ):
        resolved_email = resolve_email_configuration(
            event_type=template_key or event_type,
            title=subject,
            body=body,
            metadata={
                "html_template": html_template,
                "text_template": text_template,
                "context": context or {},
                "attachments": attachments or [],
                "fallback_text": fallback_text,
                "template_key": template_key or event_type,
                **(metadata or {}),
            },
        )
        payload = dict(metadata or {})
        payload.update(
            {
                "html_template": resolved_email["html_template"],
                "text_template": resolved_email["text_template"],
                "context": make_json_safe(resolved_email["context"]),
                "recipient_email": recipient_email or getattr(recipient, "email", ""),
                "attachments": make_json_safe(resolved_email["attachments"]),
                "fallback_text": resolved_email["fallback_text"],
                "template_key": resolved_email["template_key"],
            }
        )
        return CommunicationEventBus.emit(
            event_type=event_type,
            actor=actor,
            recipient=recipient,
            payload=payload,
            source_app=source_app,
            title=subject,
            body=body or payload["context"].get("message", ""),
            priority=priority,
            channels=(CommunicationNotification.CHANNEL_EMAIL_TRANSACTIONAL,),
            notification_type=event_type,
            legacy_source=legacy_source,
            legacy_object_id=legacy_object_id,
            dispatch_on_commit=dispatch_on_commit,
        )
