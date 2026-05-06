from django.db import transaction
from django.utils import timezone

from communication.models import CommunicationDelivery, CommunicationNotification, CommunicationEvent
from communication.services.channels import dispatch_notification


class NotificationDispatcher:
    @classmethod
    def dispatch(cls, notification: CommunicationNotification):
        delivery = CommunicationDelivery.objects.create(
            notification=notification,
            channel=notification.channel,
            provider="internal",
            status=CommunicationNotification.STATUS_PENDING,
            attempt_count=1,
            payload_snapshot=notification.metadata,
        )

        try:
            raw_result = dispatch_notification(notification) or {}
            if hasattr(raw_result, "__dict__"):
                result = raw_result.__dict__
            else:
                result = raw_result
            status = result.get("status", CommunicationNotification.STATUS_SENT)
            provider = result.get("provider", delivery.provider)
            provider_message_id = result.get("provider_message_id", "")
            now = timezone.now()

            notification.status = status
            if status in {
                CommunicationNotification.STATUS_SENT,
                CommunicationNotification.STATUS_DELIVERED,
                CommunicationNotification.STATUS_READ,
            }:
                notification.sent_at = notification.sent_at or now
            if status == CommunicationNotification.STATUS_DELIVERED:
                notification.delivered_at = notification.delivered_at or now
            notification.save(update_fields=["status", "sent_at", "delivered_at", "updated_at"])

            delivery.provider = provider
            delivery.provider_message_id = provider_message_id
            delivery.status = status
            delivery.sent_at = notification.sent_at
            delivery.delivered_at = notification.delivered_at
            delivery.save(
                update_fields=[
                    "provider",
                    "provider_message_id",
                    "status",
                    "sent_at",
                    "delivered_at",
                    "updated_at",
                ]
            )
            return delivery
        except Exception as exc:
            notification.status = CommunicationNotification.STATUS_FAILED
            notification.save(update_fields=["status", "updated_at"])
            delivery.status = CommunicationNotification.STATUS_FAILED
            delivery.error_message = str(exc)
            delivery.save(update_fields=["status", "error_message", "updated_at"])
            raise

    @classmethod
    def dispatch_on_commit(cls, notification: CommunicationNotification):
        transaction.on_commit(lambda: cls.dispatch(notification))


def finalize_event_status(event: CommunicationEvent):
    notifications = list(event.notifications.all())
    if not notifications:
        event.status = CommunicationEvent.STATUS_PROCESSED
    elif all(item.status in {
        CommunicationNotification.STATUS_SENT,
        CommunicationNotification.STATUS_DELIVERED,
        CommunicationNotification.STATUS_READ,
        CommunicationNotification.STATUS_SKIPPED,
    } for item in notifications):
        event.status = CommunicationEvent.STATUS_PROCESSED
    elif any(item.status == CommunicationNotification.STATUS_FAILED for item in notifications):
        event.status = CommunicationEvent.STATUS_PARTIAL
    else:
        event.status = CommunicationEvent.STATUS_PENDING
    event.processed_at = timezone.now()
    event.save(update_fields=["status", "processed_at", "updated_at"])
