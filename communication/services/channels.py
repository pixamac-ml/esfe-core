from django.conf import settings

from communication.models import CommunicationNotification
from communication.providers.registry import get_email_provider
from communication.realtime.payloads import build_notification_payload
from communication.realtime.service import send_notification_to_user


def dispatch_email(notification: CommunicationNotification):
    provider = get_email_provider()
    return provider.send_notification(notification)


def dispatch_websocket(notification: CommunicationNotification):
    if not notification.recipient_id:
        return None
    payload = build_notification_payload(notification)
    send_notification_to_user(notification.recipient_id, payload)
    return {"status": "sent", "provider_message_id": ""}


def dispatch_in_app(notification: CommunicationNotification):
    return {"status": "delivered", "provider_message_id": ""}


def dispatch_notification(notification: CommunicationNotification):
    if notification.channel == CommunicationNotification.CHANNEL_IN_APP:
        return dispatch_in_app(notification)
    if notification.channel == CommunicationNotification.CHANNEL_WEBSOCKET:
        return dispatch_websocket(notification)
    if notification.channel in {
        CommunicationNotification.CHANNEL_EMAIL_TRANSACTIONAL,
        CommunicationNotification.CHANNEL_EMAIL_MARKETING,
    }:
        return dispatch_email(notification)
    if notification.channel == CommunicationNotification.CHANNEL_SMS_FUTURE:
        return {"status": "skipped", "provider_message_id": ""}
    return {"status": "skipped", "provider_message_id": ""}
