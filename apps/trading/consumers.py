"""
WebSocket consumer for real-time bot management.
Authenticated via JWT access token in ?token= query parameter.
"""

import asyncio
import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

from apps.bots.models import SignalBot

logger = logging.getLogger("apps")


class BotConsumer(AsyncWebsocketConsumer):
    """
    Manages grid management loops via Django Channels (no manual threads).
    Authenticated: requires valid JWT access token as ?token= query param.
    User must own the bot they connect to.
    """

    async def connect(self):
        self.bot_id = self.scope["url_route"]["kwargs"]["bot_id"]
        self.bot_group = f"bot_{self.bot_id}"
        self.user = None

        authenticated, reason = await self._authenticate()
        if not authenticated:
            await self.close(code=4001)
            return

        ownership_ok, reason = await self._check_ownership()
        if not ownership_ok:
            await self.close(code=4003)
            return

        # Join channel group
        await self.channel_layer.group_add(self.bot_group, self.channel_name)
        await self.accept()

        # Start grid management in background
        await self.channel_layer.send(
            "bot-management",
            {
                "type": "start.management",
                "bot_id": self.bot_id,
            },
        )
        logger.info(f"BotConsumer connected: bot={self.bot_id} user={self.user.id}")

    async def disconnect(self, close_code):
        # Stop grid management for this bot
        await self.channel_layer.send(
            "bot-management",
            {
                "type": "stop.management",
                "bot_id": self.bot_id,
            },
        )
        # Leave channel group
        await self.channel_layer.group_discard(self.bot_group, self.channel_name)
        if self.user:
            logger.info(f"BotConsumer disconnected: bot={self.bot_id} user={self.user.id}")

    async def _authenticate(self):
        """
        Validate JWT access token from query string.
        Returns (True, None) or (False, reason_string).
        """
        token_str = self.scope.get("query_string", b"").decode()
        # Parse query string manually (no dependency on parse_qs)
        params = {}
        if token_str:
            for part in token_str.split("&"):
                if "=" in part:
                    key, val = part.split("=", 1)
                    params[key] = val

        raw_token = params.get("token", "")
        if not raw_token:
            return False, "Missing token"

        try:
            access_token = AccessToken(raw_token)
            user_id = access_token.payload.get("user_id")
            User = get_user_model()
            self.user = await User.objects.aget(id=user_id)
            return True, None
        except (TokenError, User.DoesNotExist, Exception) as exc:
            logger.warning(f"WebSocket auth failed: {exc}")
            return False, "Invalid token"

    async def _check_ownership(self):
        """
        Verify the authenticated user owns this bot.
        """
        try:
            bot = await SignalBot.objects.aget(id=self.bot_id)
            if bot.user_id != self.user.id:
                return False, "Forbidden"
            return True, None
        except SignalBot.DoesNotExist:
            return False, "Bot not found"

    async def bot_update(self, event):
        """
        Receive bot update from channel layer and forward to WebSocket client.
        """
        await self.send(
            text_data=json.dumps(
                {
                    "type": "bot_update",
                    "data": event.get("data", {}),
                }
            )
        )

    async def error_message(self, event):
        """
        Receive error message from channel layer and forward to WebSocket client.
        """
        await self.send(
            text_data=json.dumps(
                {
                    "type": "error",
                    "message": event.get("message", "An error occurred"),
                }
            )
        )


class MarketDataConsumer(AsyncWebsocketConsumer):
    """
    Stream real-time market data via CCXT WebSocket (ccxt.pro).

    URL: ``ws://host/ws/market/<exchange>/<symbol>/``

    Example: ``ws://host/ws/market/binance/BTC-USDT/``

    Sends ticker updates as JSON::

        {"type": "ticker", "symbol": "BTC/USDT", "bid": 50000.0,
         "ask": 50001.0, "last": 50000.5, "timestamp": 1712345678000}

    Also accepts client messages to subscribe additional symbols::

        {"action": "subscribe", "symbol": "ETH/USDT"}
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.exchange_name = ""
        self.symbols: set = set()
        self._exchange = None
        self._ticker_task = None

    async def connect(self):
        self.exchange_name = self.scope["url_route"]["kwargs"].get("exchange", "binance")
        initial_symbol = self.scope["url_route"]["kwargs"].get("symbol", "BTC/USDT")
        self.symbols.add(initial_symbol)

        await self.accept()

        try:
            import ccxt.pro as ccxt_pro

            exchange_class = getattr(ccxt_pro, self.exchange_name.lower(), None)
            if not exchange_class:
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "error",
                            "message": f"Exchange {self.exchange_name} not supported",
                        }
                    )
                )
                await self.close(code=4004)
                return

            self._exchange = exchange_class()
            self._ticker_task = asyncio.ensure_future(self._stream_tickers())
            logger.info(f"MarketDataConsumer connected: {self.exchange_name}/{initial_symbol}")
        except Exception as exc:
            logger.error(f"MarketDataConsumer init error: {exc}")
            await self.close(code=4000)

    async def disconnect(self, close_code):
        if self._ticker_task:
            self._ticker_task.cancel()
            self._ticker_task = None
        if self._exchange:
            await self._exchange.close()
        logger.info(f"MarketDataConsumer disconnected: {self.exchange_name}")

    async def receive(self, text_data=None, bytes_data=None):
        """Handle client messages: subscribe to additional symbols."""
        if not text_data:
            return
        try:
            msg = json.loads(text_data)
            action = msg.get("action", "")
            if action == "subscribe":
                symbol = msg.get("symbol", "")
                if symbol and "/" in symbol:
                    self.symbols.add(symbol)
                    await self.send(
                        text_data=json.dumps(
                            {
                                "type": "subscribed",
                                "symbol": symbol,
                            }
                        )
                    )
        except (json.JSONDecodeError, TypeError):
            pass

    async def _stream_tickers(self):
        """Continuously stream ticker updates for all subscribed symbols."""
        while True:
            try:
                for symbol in list(self.symbols):
                    ticker = await self._exchange.watch_ticker(symbol)
                    await self.send(
                        text_data=json.dumps(
                            {
                                "type": "ticker",
                                "symbol": ticker.get("symbol", symbol),
                                "bid": ticker.get("bid"),
                                "ask": ticker.get("ask"),
                                "last": ticker.get("last"),
                                "change": ticker.get("percentage"),
                                "baseVolume": ticker.get("baseVolume"),
                                "quoteVolume": ticker.get("quoteVolume"),
                                "timestamp": ticker.get("timestamp"),
                            }
                        )
                    )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning(f"MarketData ticker error: {exc}")
                await asyncio.sleep(5)
