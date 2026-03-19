# courriers/consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user_id = self.scope['url_route']['kwargs']['user_id']
        self.room_group_name = f'user_{self.user_id}'

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()
        print(f'[WS] Connecté : user_{self.user_id}')

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        print(f'[WS] Déconnecté : user_{self.user_id} (code {close_code})')

    async def receive(self, text_data):
        """Reçoit les messages du client (ping keepalive)"""
        try:
            data = json.loads(text_data)
            if data.get('type') == 'ping':
                await self.send(text_data=json.dumps({'type': 'pong'}))
        except (json.JSONDecodeError, Exception):
            pass

    async def send_notification(self, event):
        """Handler appelé par channel_layer.group_send() depuis le backend"""
        await self.send(text_data=json.dumps({
            'type': event.get('notification_type', 'notification'),
            'message': event.get('message', ''),
            'data': event.get('data', {}),
        }))