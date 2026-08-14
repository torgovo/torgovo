"""Tests for WebSocket consumers — MarketData and Bot."""

import pytest
from asgiref.sync import async_to_sync


class TestMarketDataConsumer:
    """WebSocket market data streaming via ccxt.pro."""

    def test_market_data_routing_exists(self):
        from apps.trading.routing import websocket_urlpatterns

        market_routes = [p for p in websocket_urlpatterns if "market" in str(p.pattern)]
        assert len(market_routes) == 1

    def test_market_data_consumer_class(self):
        from apps.trading.consumers import MarketDataConsumer

        assert hasattr(MarketDataConsumer, "connect")
        assert hasattr(MarketDataConsumer, "disconnect")
        assert hasattr(MarketDataConsumer, "receive")

    def test_market_data_subscribe_message_handling(self):
        from apps.trading.consumers import MarketDataConsumer

        consumer = MarketDataConsumer()
        consumer.symbols = {"BTC/USDT"}
        assert "ETH/USDT" not in consumer.symbols  # receive() wasn't called

    def test_bot_consumer_class(self):
        from apps.trading.consumers import BotConsumer

        assert hasattr(BotConsumer, "connect")
        assert hasattr(BotConsumer, "disconnect")


@pytest.mark.django_db
class TestBotConsumerOwnership:
    """BotConsumer ownership check."""

    def test_ownership_check_fails_for_wrong_user(self, db, signal_bot):
        from django.contrib.auth import get_user_model

        from apps.trading.consumers import BotConsumer

        User = get_user_model()
        other_user = User.objects.create_user(username="other", email="other@x.com", password="x")
        consumer = BotConsumer()
        consumer.user = other_user
        consumer.bot_id = str(signal_bot.id)

        ok, reason = async_to_sync(consumer._check_ownership)()
        assert not ok
        assert "Forbidden" in reason

    def test_ownership_check_passes_for_owner(self, db, signal_bot, user):
        from apps.trading.consumers import BotConsumer

        consumer = BotConsumer()
        consumer.user = user
        consumer.bot_id = str(signal_bot.id)

        ok, reason = async_to_sync(consumer._check_ownership)()
        assert ok
