from communication.models import CommunicationNotification
from communication.services.event_bus import CommunicationEventBus
from communication.services.notifications import mark_notification_read


class NotificationService:
    @staticmethod
    def notify_user(
        *,
        recipient,
        actor=None,
        event_type,
        title,
        body="",
        source_app="core",
        priority=CommunicationNotification.PRIORITY_NORMAL,
        channels=None,
        metadata=None,
        legacy_source="",
        legacy_object_id="",
        dispatch_on_commit=True,
    ):
        resolved_channels = channels or (
            CommunicationNotification.CHANNEL_IN_APP,
            CommunicationNotification.CHANNEL_WEBSOCKET,
        )
        return CommunicationEventBus.emit(
            event_type=event_type,
            actor=actor,
            recipient=recipient,
            payload=metadata or {},
            source_app=source_app,
            title=title,
            body=body,
            priority=priority,
            channels=resolved_channels,
            notification_type=event_type,
            legacy_source=legacy_source,
            legacy_object_id=legacy_object_id,
            dispatch_on_commit=dispatch_on_commit,
        )

    @staticmethod
    def mark_as_read(notification):
        return mark_notification_read(notification)
