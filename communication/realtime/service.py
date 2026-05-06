from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def user_group_name(user_id):
    return f"communication_user_{user_id}"


def send_notification_to_user(user_id, payload):
    channel_layer = get_channel_layer()
    if not channel_layer:
        return
    async_to_sync(channel_layer.group_send)(
        user_group_name(user_id),
        {
            "type": "communication_notification",
            "payload": payload,
        },
    )
