from django.db import transaction

from notifier.models import NotificationEvent, NotificationMessage
from notifier.services.dispatcher import Dispatcher, finalize_event_status
from notifier.services.json_utils import make_json_safe
from notifier.services.notifications import create_message, mark_message_read
from notifier.services.policy import resolve_channel_policy
from notifier.services.template_registry import resolve_email_configuration


class NotificationBus:
    DEFAULT_CHANNELS = (
        NotificationMessage.CHANNEL_IN_APP,
    )

    @classmethod
    def emit(
        cls,
        *,
        event_type,
        actor=None,
        recipient=None,
        payload=None,
        metadata=None,
        source_app="core",
        title="",
        body="",
        priority=NotificationMessage.PRIORITY_NORMAL,
        channels=None,
        notification_type=None,
        legacy_source="",
        legacy_object_id="",
        dispatch_on_commit=True,
    ):
        event = NotificationEvent.objects.create(
            event_type=event_type,
            source_app=source_app,
            actor=actor,
            recipient=recipient,
            payload=make_json_safe(payload or {}),
            metadata=make_json_safe(metadata or {}),
        )

        created_messages = []
        resolved_channels = tuple(channels or cls.DEFAULT_CHANNELS)
        resolved_notification_type = notification_type or event_type

        for channel in resolved_channels:
            message = create_message(
                event=event,
                recipient=recipient,
                actor=actor,
                title=title or event_type.replace("_", " ").title(),
                body=body,
                notification_type=resolved_notification_type,
                event_type=event_type,
                channel=channel,
                priority=priority,
                metadata=make_json_safe(payload or {}),
                legacy_source=legacy_source,
                legacy_object_id=legacy_object_id,
                status=NotificationMessage.STATUS_QUEUED,
            )
            created_messages.append(message)

            if dispatch_on_commit:
                Dispatcher.dispatch_on_commit(message)
            else:
                Dispatcher.dispatch(message)

        if dispatch_on_commit:
            transaction.on_commit(
                lambda event_id=event.id: finalize_event_status(
                    NotificationEvent.objects.get(pk=event_id)
                )
            )
        else:
            finalize_event_status(event)

        return event, created_messages

    @classmethod
    def notify(
        cls,
        *,
        recipient,
        actor=None,
        event_type,
        title,
        body="",
        source_app="core",
        priority=NotificationMessage.PRIORITY_NORMAL,
        channels=None,
        metadata=None,
        legacy_source="",
        legacy_object_id="",
        dispatch_on_commit=True,
    ):
        default_channels = (
            NotificationMessage.CHANNEL_IN_APP,
            NotificationMessage.CHANNEL_WEBSOCKET,
        )
        if channels is None:
            policy = resolve_channel_policy(
                event_type,
                default_channels=default_channels,
                default_priority=priority,
                metadata=metadata,
            )
            resolved_channels = policy["channels"]
            resolved_priority = policy["priority"]
            resolved_metadata = policy["metadata"]
        else:
            # Explicit channels are an intentional call-site override. This is
            # required for workflows that add email only when an address exists.
            resolved_channels = tuple(channels)
            resolved_priority = priority
            resolved_metadata = metadata or {}

        return cls.emit(
            event_type=event_type,
            actor=actor,
            recipient=recipient,
            payload=resolved_metadata,
            source_app=source_app,
            title=title,
            body=body,
            priority=resolved_priority,
            channels=resolved_channels,
            notification_type=event_type,
            legacy_source=legacy_source,
            legacy_object_id=legacy_object_id,
            dispatch_on_commit=dispatch_on_commit,
        )

    @classmethod
    def send_email(
        cls,
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
        priority=NotificationMessage.PRIORITY_NORMAL,
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
        return cls.emit(
            event_type=event_type,
            actor=actor,
            recipient=recipient,
            payload=payload,
            source_app=source_app,
            title=subject,
            body=body or payload["context"].get("message", ""),
            priority=priority,
            channels=(NotificationMessage.CHANNEL_EMAIL_TRANSACTIONAL,),
            notification_type=event_type,
            legacy_source=legacy_source,
            legacy_object_id=legacy_object_id,
            dispatch_on_commit=dispatch_on_commit,
        )

    @staticmethod
    def mark_as_read(message):
        return mark_message_read(message)
