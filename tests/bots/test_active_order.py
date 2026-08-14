"""Tests for the ActiveOrder model replacing GridBot JSONField."""

from decimal import Decimal

import pytest


@pytest.mark.django_db
class TestActiveOrderModel:
    """ActiveOrder model creation and relationships."""

    def test_active_order_created(self, db, user, bot_subscription):
        from apps.bots.models import ActiveOrder, GridBot

        bot = GridBot.objects.create(
            user=user,
            bot_name="Grid Test",
            exchange_name="binance",
            trading_pair="ETH/USDT",
            base_amount=Decimal("100"),
            favor_levels=3,
            against_levels=3,
            subscription=bot_subscription,
        )

        order = ActiveOrder.objects.create(
            grid_bot=bot,
            side="buy",
            quantity=Decimal("0.1"),
            price=Decimal("3000"),
            level_index=1,
            exchange_order_id="exch-123",
        )

        assert order.grid_bot == bot
        assert order.side == "buy"
        assert order.quantity == Decimal("0.1")
        assert order.status == "open"
        assert str(order) == f"{bot.bot_name} buy 0.1 @ 3000"

    def test_active_order_related_name(self, db, user, bot_subscription):
        from apps.bots.models import ActiveOrder, GridBot

        bot = GridBot.objects.create(
            user=user,
            bot_name="Grid Test 2",
            exchange_name="bybit",
            trading_pair="SOL/USDT",
            base_amount=Decimal("200"),
            favor_levels=3,
            against_levels=3,
            subscription=bot_subscription,
        )

        ActiveOrder.objects.create(
            grid_bot=bot,
            side="buy",
            quantity=Decimal("1"),
            level_index=1,
        )
        ActiveOrder.objects.create(
            grid_bot=bot,
            side="sell",
            quantity=Decimal("2"),
            level_index=2,
        )

        assert bot.active_orders_model.count() == 2

    def test_active_order_table_name(self):
        from apps.bots.models import ActiveOrder

        assert ActiveOrder._meta.db_table == "bots_active_orders"

    def test_active_order_indexes(self):
        from apps.bots.models import ActiveOrder

        indexes = {idx.fields[0] for idx in ActiveOrder._meta.indexes}
        assert "grid_bot" in indexes or any(
            "grid_bot" in idx.fields for idx in ActiveOrder._meta.indexes
        )
