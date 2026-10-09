from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from django.contrib.auth import get_user_model


def serializer_context():
    request = MagicMock()
    request.user = get_user_model()(id=1, username="test", email="test@test.com")
    return {"request": request}


@pytest.mark.django_db
class TestSignalBotSerializers:
    def test_signal_bot_serializer_fields(self, user, signal_bot_subscription):
        from apps.bots.models import SignalBot
        from apps.bots.serializers import SignalBotSerializer

        bot = SignalBot.objects.create(
            user=user,
            bot_name="Test",
            exchange_name="binance",
            trading_pair="BTC/USDT",
            default_amount=Decimal("0.01"),
            subscription=signal_bot_subscription,
        )
        serializer = SignalBotSerializer(instance=bot)
        expected_fields = {
            "id",
            "bot_name",
            "webhook_url",
            "secret_key",
            "exchange_name",
            "market_type",
            "trading_pair",
            "default_amount",
            "take_profit_percent",
            "stop_loss_percent",
            "is_active",
            "signals_used_this_month",
            "signal_limit",
            "last_triggered",
            "total_trades",
            "successful_trades",
            "total_profit_loss",
            "created_at",
            "updated_at",
            "success_rate",
            "last_error",
            "subscription",
        }
        assert set(serializer.data.keys()) == expected_fields
        assert serializer.data["success_rate"] == 0
        assert serializer.data["bot_name"] == "Test"

    def test_signal_bot_create_serializer_valid(self):
        from apps.bots.serializers import SignalBotCreateSerializer

        data = {
            "bot_name": "Test Bot",
            "exchange_name": "binance",
            "market_type": "spot",
            "trading_pair": "BTC/USDT",
            "default_amount": "0.01",
        }
        serializer = SignalBotCreateSerializer(data=data, context=serializer_context())
        assert serializer.is_valid(), serializer.errors
        assert serializer.validated_data["trading_pair"] == "BTC/USDT"

    def test_signal_bot_create_serializer_invalid_exchange(self):
        from apps.bots.serializers import SignalBotCreateSerializer

        data = {
            "bot_name": "Test",
            "exchange_name": "invalid_exchange",
            "market_type": "spot",
            "trading_pair": "BTC/USDT",
            "default_amount": "0.01",
        }
        serializer = SignalBotCreateSerializer(data=data, context=serializer_context())
        assert not serializer.is_valid()
        assert "exchange_name" in serializer.errors

    def test_signal_bot_create_serializer_invalid_pair_format(self):
        from apps.bots.serializers import SignalBotCreateSerializer

        data = {
            "bot_name": "Test",
            "exchange_name": "binance",
            "market_type": "spot",
            "trading_pair": "BTCUSDT",
            "default_amount": "0.01",
        }
        serializer = SignalBotCreateSerializer(data=data, context=serializer_context())
        assert not serializer.is_valid()
        assert "trading_pair" in serializer.errors

    def test_signal_bot_create_serializer_pair_uppercased(self):
        from apps.bots.serializers import SignalBotCreateSerializer

        data = {
            "bot_name": "Test",
            "exchange_name": "bybit",
            "market_type": "futures",
            "trading_pair": "eth/usdt",
            "default_amount": "0.1",
        }
        serializer = SignalBotCreateSerializer(data=data, context=serializer_context())
        assert serializer.is_valid(), serializer.errors
        assert serializer.validated_data["trading_pair"] == "ETH/USDT"

    def test_signal_bot_serializer_read_only_fields(self, user, signal_bot_subscription):
        from apps.bots.models import SignalBot
        from apps.bots.serializers import SignalBotSerializer

        bot = SignalBot.objects.create(
            user=user,
            bot_name="Test",
            exchange_name="binance",
            trading_pair="BTC/USDT",
            default_amount=Decimal("0.01"),
            subscription=signal_bot_subscription,
        )
        serializer = SignalBotSerializer(instance=bot)
        read_only = {
            "id",
            "webhook_url",
            "secret_key",
            "created_at",
            "updated_at",
            "last_triggered",
            "total_trades",
            "successful_trades",
            "total_profit_loss",
            "success_rate",
            "last_error",
        }
        for field in read_only:
            assert field in serializer.data


@pytest.mark.django_db
class TestGridBotSerializers:
    def test_grid_bot_serializer_fields(self, user, bot_subscription):
        from apps.bots.models import GridBot
        from apps.bots.serializers import GridBotSerializer

        bot = GridBot.objects.create(
            user=user,
            bot_name="Grid",
            exchange_name="binance",
            trading_pair="BTC/USDT",
            base_amount=Decimal("0.001"),
            favor_levels=5,
            against_levels=5,
            subscription=bot_subscription,
        )
        serializer = GridBotSerializer(instance=bot)
        assert "is_running" in serializer.data
        assert serializer.data["is_running"] is False
        assert "total_trades_executed" in serializer.data

    def test_grid_bot_create_serializer_valid(self):
        from apps.bots.serializers import GridBotCreateSerializer

        data = {
            "bot_name": "Grid Bot",
            "exchange_name": "binance",
            "trading_pair": "ETH/USDT",
            "initial_amount": "1000",
            "base_amount": "0.1",
            "favor_levels": 5,
            "against_levels": 5,
        }
        serializer = GridBotCreateSerializer(data=data, context=serializer_context())
        assert serializer.is_valid(), serializer.errors


@pytest.mark.django_db
class TestMartingaleBotSerializers:
    def test_martingale_bot_serializer_fields(self, user, bot_subscription):
        from apps.bots.models import MartingaleBot
        from apps.bots.serializers import MartingaleBotSerializer

        bot = MartingaleBot.objects.create(
            user=user,
            bot_name="Mart",
            exchange_name="binance",
            trading_pair="ETH/USDT",
            base_amount=Decimal("0.1"),
            favor_levels=3,
            against_levels=3,
            multiplier_factor=Decimal("2.0"),
            subscription=bot_subscription,
        )
        serializer = MartingaleBotSerializer(instance=bot)
        assert "multiplier_factor" in serializer.data
        assert "current_level" in serializer.data
        assert serializer.data["current_level"] == 0

    def test_martingale_bot_create_serializer_valid(self):
        from apps.bots.serializers import MartingaleBotCreateSerializer

        data = {
            "bot_name": "Mart Bot",
            "exchange_name": "bybit",
            "trading_pair": "SOL/USDT",
            "base_amount": "1",
            "favor_levels": 4,
            "against_levels": 4,
            "multiplier_factor": "2.5",
        }
        serializer = MartingaleBotCreateSerializer(data=data, context=serializer_context())
        assert serializer.is_valid(), serializer.errors


@pytest.mark.django_db
class TestQuantumAISerializers:
    def test_quantum_ai_fund_serializer(self, quantum_fund):
        from apps.bots.serializers import QuantumAIFundSerializer

        serializer = QuantumAIFundSerializer(instance=quantum_fund)
        assert "total_fund_value" in serializer.data
        assert "total_profit" in serializer.data
        assert "master_api_key" not in serializer.data

    def test_quantum_ai_investment_serializer(self, user, quantum_fund, bot_subscription):
        from apps.bots.models import InvestorPortfolio
        from apps.bots.serializers import InvestorPortfolioSerializer

        inv = InvestorPortfolio.objects.create(
            user=user,
            fund=quantum_fund,
            amount=Decimal("1000"),
            status="active",
            subscription=bot_subscription,
        )
        serializer = InvestorPortfolioSerializer(instance=inv)
        assert "user_share_amount" in serializer.data
        assert "share_percentage" in serializer.data
        assert "fund" in serializer.data

    def test_quantum_ai_investment_create_serializer(self, quantum_fund, bot_subscription):
        from apps.bots.serializers import InvestorPortfolioSerializer

        data = {
            "fund": str(quantum_fund.id),
            "amount": "1000",
            "subscription": str(bot_subscription.id),
        }
        serializer = InvestorPortfolioSerializer(data=data, context=serializer_context())
        assert serializer.is_valid(), serializer.errors


@pytest.mark.django_db
class TestPairConfigSerializer:
    def test_pair_config_serializer_fields(self, user, bot_subscription):
        from apps.bots.models import PairConfig
        from apps.bots.serializers import PairConfigSerializer

        config = PairConfig.objects.create(
            user=user,
            pair_symbol="BTC/USDT",
            bot_type="grid",
            subscription=bot_subscription,
        )
        serializer = PairConfigSerializer(instance=config)
        assert "pair_symbol" in serializer.data
        assert "bot_type" in serializer.data
        assert "RSI_Entry" in serializer.data
        assert "Order_Type" in serializer.data

    def test_pair_config_create_valid(self):
        from apps.bots.serializers import PairConfigSerializer

        data = {
            "pair_symbol": "ETH/USDT",
            "bot_type": "martingale",
            "Order_Type": "limit",
            "Stop_Loss": 5.0,
            "Take_Profit": 10.0,
        }
        serializer = PairConfigSerializer(data=data, context=serializer_context())
        assert serializer.is_valid(), serializer.errors


@pytest.mark.django_db
class TestOrderSerializer:
    def test_order_serializer_method_fields(self, user):
        from apps.bots.models import BotOrder
        from apps.bots.serializers import OrderSerializer

        order = BotOrder.objects.create(
            user=user,
            Pair="BTC/USDT",
            Side="buy",
            Price=45000.0,
            Quantity=Decimal("0.01"),
        )
        serializer = OrderSerializer(instance=order)
        assert "user_info" in serializer.data
        assert serializer.data["user_info"]["email"] == user.email
        assert "signal_bot_info" in serializer.data
        assert "grid_bot_info" in serializer.data
        assert "martingale_bot_info" in serializer.data
        assert "quantum_ai_info" in serializer.data

    def test_order_serializer_bot_info_null(self, user):
        from apps.bots.models import BotOrder
        from apps.bots.serializers import OrderSerializer

        order = BotOrder.objects.create(
            user=user,
            Pair="BTC/USDT",
            Side="buy",
            Price=45000.0,
            Quantity=Decimal("0.01"),
        )
        serializer = OrderSerializer(instance=order)
        assert serializer.data["signal_bot_info"] is None
        assert serializer.data["grid_bot_info"] is None


@pytest.mark.django_db
class TestIndicatorSerializer:
    def test_indicator_serializer_fields(self, user):
        from apps.bots.models import Indicator
        from apps.bots.serializers import IndicatorSerializer

        ind = Indicator.objects.create(
            user=user,
            Pair="BTC/USDT",
            EMA=200.0,
            RSI=65.0,
        )
        serializer = IndicatorSerializer(instance=ind)
        assert serializer.data["EMA"] == 200.0
        assert serializer.data["RSI"] == 65.0
        assert "Pair" in serializer.data

    def test_indicator_create_valid(self):
        from apps.bots.serializers import IndicatorSerializer

        data = {"Pair": "ETH/USDT", "EMA": 150.0, "RSI": 55.0}
        serializer = IndicatorSerializer(data=data, context=serializer_context())
        assert serializer.is_valid(), serializer.errors


@pytest.mark.django_db
class TestQuantumDepositSerializers:
    def test_deposit_wallet_serializer(self, quantum_wallet):
        from apps.bots.serializers import QuantumDepositWalletSerializer

        serializer = QuantumDepositWalletSerializer(instance=quantum_wallet)
        assert serializer.data["coin"] == "USDT"
        assert serializer.data["blockchain"] == "ERC20"
        assert serializer.data["is_active"] is True

    def test_deposit_serializer_fields(self, user, quantum_wallet):
        from apps.bots.models import QuantumDeposit
        from apps.bots.serializers import QuantumDepositSerializer

        dep = QuantumDeposit.objects.create(
            user=user,
            wallet=quantum_wallet,
            amount=Decimal("500"),
            transaction_hash="0xabc",
            screenshot="test.jpg",
        )
        serializer = QuantumDepositSerializer(instance=dep)
        assert serializer.data["status"] == "pending"
        assert "reviewed_by" in serializer.data
        assert "review_notes" in serializer.data
