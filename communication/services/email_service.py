from communication.models import CommunicationNotification
from communication.services.event_bus import CommunicationEventBus


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
        html_template="emails/base_communication.html",
        text_template=None,
        context=None,
        metadata=None,
        priority=CommunicationNotification.PRIORITY_NORMAL,
        dispatch_on_commit=True,
        legacy_source="",
        legacy_object_id="",
    ):
        payload = {
            "html_template": html_template,
            "text_template": text_template,
            "context": context or {},
            "recipient_email": recipient_email or getattr(recipient, "email", ""),
            **(metadata or {}),
        }
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
