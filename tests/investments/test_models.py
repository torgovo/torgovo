from decimal import Decimal

import pytest
from django.utils import timezone

from apps.exchanges.models import Exchange, TradingPair
from apps.investments.models import InvestmentBalance, Order, Position, TechnicalIndicator


@pytest.mark.django_db
class TestInvestmentOrderModel:
    def test_create_order(self, user):
        exchange = Exchange.objects.create(name="binance", display_name="Binance")
        pair = TradingPair.objects.create(
            exchange_name="binance",
            symbol="BTC/USDT",
            base_asset="BTC",
            quote_asset="USDT",
        )
        order = Order.objects.create(
            user=user,
            exchange=exchange,
            trading_pair=pair,
            order_type="market",
            side="buy",
            quantity=Decimal("0.00100000"),
            price=Decimal("50000.00000000"),
        )
        assert order.user == user
        assert order.order_type == "market"
        assert order.side == "buy"
        assert order.status == "pending"
        assert order.quantity == Decimal("0.00100000")
        assert str(order) == "buy 0.00100000 @ 50000.00000000"

    def test_save_syncs_aliases(self, user):
        exchange = Exchange.objects.create(name="binance", display_name="Binance")
        pair = TradingPair.objects.create(
            exchange_name="binance",
            symbol="BTC/USDT",
            base_asset="BTC",
            quote_asset="USDT",
        )
        order = Order.objects.create(
            user=user,
            exchange=exchange,
            trading_pair=pair,
            order_type="limit",
            side="sell",
            quantity=Decimal("1"),
            price=Decimal("100"),
            description="Test order",
        )
        assert order.side == "sell"
        assert order.description == "Test order"


@pytest.mark.django_db
class TestInvestmentPositionModel:
    def test_create_position(self, user):
        exchange = Exchange.objects.create(name="binance", display_name="Binance")
        pair = TradingPair.objects.create(
            exchange_name="binance",
            symbol="BTC/USDT",
            base_asset="BTC",
            quote_asset="USDT",
        )
        position = Position.objects.create(
            user=user,
            exchange=exchange,
            trading_pair=pair,
            side="long",
            entry_price=Decimal("50000.00000000"),
            quantity=Decimal("0.10000000"),
            leverage=1,
        )
        assert position.user == user
        assert position.side == "long"
        assert position.entry_price == Decimal("50000.00000000")
        assert position.leverage == 1
        assert position.unrealized_pnl == Decimal("0")
        assert str(position) == "long 0.10000000 @ 50000.00000000"


@pytest.mark.django_db
class TestTechnicalIndicatorModel:
    def test_create_indicator(self):
        exchange = Exchange.objects.create(name="binance", display_name="Binance")
        pair = TradingPair.objects.create(
            exchange_name="binance",
            symbol="BTC/USDT",
            base_asset="BTC",
            quote_asset="USDT",
        )
        indicator = TechnicalIndicator.objects.create(
            indicator_type="RSI",
            trading_pair=pair,
            exchange=exchange,
            values={"RSI": 72.5, "PrevRSI": 65.0},
            color="red",
            prev_color="green",
            triggered_at=timezone.now(),
        )
        assert indicator.indicator_type == "RSI"
        assert indicator.values == {"RSI": 72.5, "PrevRSI": 65.0}
        assert indicator.color == "red"
        assert str(indicator) == f"RSI \u2014 {pair}"


@pytest.mark.django_db
class TestUserBalanceModel:
    def test_create_balance(self, user):
        exchange = Exchange.objects.create(name="binance", display_name="Binance")
        balance = InvestmentBalance.objects.create(
            user=user,
            exchange=exchange,
            currency="USDT",
            available=Decimal("1000.00000000"),
            locked=Decimal("500.00000000"),
            total=Decimal("1500.00000000"),
        )
        assert balance.user == user
        assert balance.currency == "USDT"
        assert balance.available == Decimal("1000.00000000")
        assert balance.total == Decimal("1500.00000000")
        assert str(balance) == f"{user} \u2014 USDT: 1500.00000000"

    def test_unique_together(self, user):
        exchange = Exchange.objects.create(name="binance", display_name="Binance")
        InvestmentBalance.objects.create(
            user=user,
            exchange=exchange,
            currency="USDT",
            available=Decimal("100"),
            total=Decimal("100"),
        )
        with pytest.raises(Exception):
            InvestmentBalance.objects.create(
                user=user,
                exchange=exchange,
                currency="USDT",
                available=Decimal("200"),
                total=Decimal("200"),
            )
