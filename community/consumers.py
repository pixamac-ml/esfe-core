import json

from channels.generic.websocket import AsyncWebsocketConsumer


class NotificationConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        user = self.scope["user"]

        # Si utilisateur non connecté on refuse
        if user.is_anonymous:
            await self.close()
            return

        # Groupe websocket par utilisateur
        self.group_name = f"user_{user.id}"

        # Inscription au groupe
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):

        user = self.scope["user"]

        if not user.is_anonymous:

            await self.channel_layer.group_discard(
                f"user_{user.id}",
                self.channel_name
            )

    async def receive(self, text_data=None, bytes_data=None):
        """
        Si un message arrive du navigateur
        """
        if not text_data:
            return

        data = json.loads(text_data)

        # Pour l'instant on ne gère rien
        print("Message reçu :", data)

    async def send_notification(self, event):
        """
        Envoi notification au navigateur
        """

        await self.send(
            text_data=json.dumps({
                "type": "notification",
                "message": event["message"],
                "url": event["url"],
                "notification_type": event.get("notification_type"),
                "vote_count": event.get("vote_count", 1),
                "unread_count": event.get("unread_count"),
            })
        )