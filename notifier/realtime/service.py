from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
import uuid


def user_group_name(user_id):
    return f"notifier_user_{user_id}"


def session_group_name(identifier):
    normalized = uuid.UUID(str(identifier)).hex
    return f"notifier_session_{normalized}"


def send_to_user(user_id, payload):
    channel_layer = get_channel_layer()
    if not channel_layer:
        return
    async_to_sync(channel_layer.group_send)(
        user_group_name(user_id),
        {
            "type": "notification_message",
            "payload": payload,
        },
    )
