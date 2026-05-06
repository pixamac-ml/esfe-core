from django.db import transaction

from communication.models import CommunicationEvent, CommunicationNotification
from communication.services.dispatcher import NotificationDispatcher, finalize_event_status
from communication.services.json_utils import make_json_safe
from communication.services.notifications import create_notification


class CommunicationEventBus:
    DEFAULT_CHANNELS = (
        CommunicationNotification.CHANNEL_IN_APP,
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
        priority=CommunicationNotification.PRIORITY_NORMAL,
        channels=None,
        notification_type=None,
        legacy_source="",
        legacy_object_id="",
        dispatch_on_commit=True,
    ):
        event = CommunicationEvent.objects.create(
            event_type=event_type,
            source_app=source_app,
            actor=actor,
            recipient=recipient,
            payload=make_json_safe(payload or {}),
            metadata=make_json_safe(metadata or {}),
        )

        created_notifications = []
        resolved_channels = tuple(channels or cls.DEFAULT_CHANNELS)
        resolved_notification_type = notification_type or event_type

        for channel in resolved_channels:
            notification = create_notification(
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
                status=CommunicationNotification.STATUS_QUEUED,
            )
            created_notifications.append(notification)

            if dispatch_on_commit:
                NotificationDispatcher.dispatch_on_commit(notification)
            else:
                NotificationDispatcher.dispatch(notification)

        if dispatch_on_commit:
            transaction.on_commit(lambda event_id=event.id: finalize_event_status(CommunicationEvent.objects.get(pk=event_id)))
        else:
            finalize_event_status(event)

        return event, created_notifications
