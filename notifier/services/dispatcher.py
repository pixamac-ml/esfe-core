from django.db import transaction
from django.utils import timezone

from notifier.models import DeliveryAttempt, NotificationMessage, NotificationEvent
from notifier.services.channels import dispatch_message


class Dispatcher:
    @classmethod
    def dispatch(cls, message):
        delivery = DeliveryAttempt.objects.create(
            message=message,
            channel=message.channel,
            provider="internal",
            status=NotificationMessage.STATUS_PENDING,
            attempt_count=1,
            payload_snapshot=message.metadata,
        )

        try:
            raw_result = dispatch_message(message) or {}
            result = raw_result.__dict__ if hasattr(raw_result, "__dict__") else raw_result
            status = result.get("status", NotificationMessage.STATUS_SENT)
            provider = result.get("provider", delivery.provider)
            provider_message_id = result.get("provider_message_id", "")
            now = timezone.now()

            message.status = status
            if status in {
                NotificationMessage.STATUS_SENT,
                NotificationMessage.STATUS_DELIVERED,
                NotificationMessage.STATUS_READ,
            }:
                message.sent_at = message.sent_at or now
            if status == NotificationMessage.STATUS_DELIVERED:
                message.delivered_at = message.delivered_at or now
            message.save(update_fields=["status", "sent_at", "delivered_at", "updated_at"])

            delivery.provider = provider
            delivery.provider_message_id = provider_message_id
            delivery.status = status
            delivery.sent_at = message.sent_at
            delivery.delivered_at = message.delivered_at
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
            message.status = NotificationMessage.STATUS_FAILED
            message.save(update_fields=["status", "updated_at"])
            delivery.status = NotificationMessage.STATUS_FAILED
            delivery.error_message = str(exc)
            delivery.save(update_fields=["status", "error_message", "updated_at"])
            raise

    @classmethod
    def dispatch_on_commit(cls, message):
        transaction.on_commit(lambda: cls.dispatch(message))


def finalize_event_status(event):
    messages = list(event.messages.all())
    if not messages:
        event.status = NotificationEvent.STATUS_PROCESSED
    elif all(
        item.status in {
            NotificationMessage.STATUS_SENT,
            NotificationMessage.STATUS_DELIVERED,
            NotificationMessage.STATUS_READ,
            NotificationMessage.STATUS_SKIPPED,
        }
        for item in messages
    ):
        event.status = NotificationEvent.STATUS_PROCESSED
    elif any(item.status == NotificationMessage.STATUS_FAILED for item in messages):
        event.status = NotificationEvent.STATUS_PARTIAL
    else:
        event.status = NotificationEvent.STATUS_PENDING
    event.processed_at = timezone.now()
    event.save(update_fields=["status", "processed_at", "updated_at"])
