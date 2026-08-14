"""
WebSocket URL routing for trading app.
"""

from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r"ws/bot/(?P<bot_id>[0-9a-f-]+)/$", consumers.BotConsumer.as_asgi()),
    re_path(
        r"ws/market/(?P<exchange>\w+)/(?P<symbol>[\w/-]+)/$",
        consumers.MarketDataConsumer.as_asgi(),
    ),
]
