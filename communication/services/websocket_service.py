from communication.models import CommunicationNotification
from communication.realtime.payloads import build_notification_payload
from communication.realtime.service import send_notification_to_user


class WebsocketService:
    @staticmethod
    def notify_user(*, user, notification=None, payload=None):
        if not user:
            return None
        resolved_payload = payload
        if resolved_payload is None and notification is not None:
            resolved_payload = build_notification_payload(notification)
        if resolved_payload is None:
            resolved_payload = {
                "type": "communication.notification",
                "channel": CommunicationNotification.CHANNEL_WEBSOCKET,
            }
        send_notification_to_user(user.id, resolved_payload)
        return resolved_payload
