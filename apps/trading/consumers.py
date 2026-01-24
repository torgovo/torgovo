from channels.generic.websocket import AsyncWebsocketConsumer
import json

class BotConsumer(AsyncWebsocketConsumer):
    """
    Manages grid management loops via Django Channels (no manual threads)
    """
    async def connect(self):
        self.bot_id = self.scope['url_route']['kwargs']['bot_id']
        self.bot_group = f'bot_{self.bot_id}'
        
        # Join channel group
        await self.channel_layer.group_add(
            self.bot_group,
            self.channel_name
        )
        await self.accept()
        
        # Start grid management in background
        await self.channel_layer.send(
            'bot-management',
            {
                'type': 'start.management',
                'bot_id': self.bot_id
            }
        )
    
    async def disconnect(self, close_code):
        # Stop grid management
        await self.channel_layer.group_discard(
            self.bot_group,
            self.channel_name
        )