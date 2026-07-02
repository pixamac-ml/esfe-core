from notifier.models import NotificationMessage
from notifier.providers.registry import get_email_provider
from notifier.realtime.payloads import build_notification_payload
from notifier.realtime.service import send_to_user


def dispatch_email(message):
    provider = get_email_provider()
    return provider.send_notification(message)


def dispatch_websocket(message):
    if not message.recipient_id:
        return None
    payload = build_notification_payload(message)
    send_to_user(message.recipient_id, payload)
    return {"status": "sent", "provider_message_id": ""}


def dispatch_in_app(message):
    return {"status": "delivered", "provider_message_id": ""}


def dispatch_message(message):
    if message.channel == NotificationMessage.CHANNEL_IN_APP:
        return dispatch_in_app(message)
    if message.channel == NotificationMessage.CHANNEL_WEBSOCKET:
        return dispatch_websocket(message)
    if message.channel in {
        NotificationMessage.CHANNEL_EMAIL_TRANSACTIONAL,
        NotificationMessage.CHANNEL_EMAIL_MARKETING,
    }:
        return dispatch_email(message)
    if message.channel == NotificationMessage.CHANNEL_SMS_FUTURE:
        return {"status": "skipped", "provider_message_id": ""}
    return {"status": "skipped", "provider_message_id": ""}
