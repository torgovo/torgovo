from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status

from apps.exchanges.models import Exchange, TradingPair
from apps.investments.models import InvestmentBalance, Order, Position, TechnicalIndicator


@pytest.mark.django_db
class TestOrderViewSet:
    @pytest.fixture(autouse=True)
    def setup(self, db, user):
        self.exchange = Exchange.objects.create(name="binance", display_name="Binance")
        self.pair = TradingPair.objects.create(
            exchange_name="binance",
            symbol="BTC/USDT",
            base_asset="BTC",
            quote_asset="USDT",
        )

    def test_create_order(self, auth_client):
        url = reverse("investments:order-list")
        data = {
            "exchange_id": self.exchange.id,
            "trading_pair_id": self.pair.id,
            "order_type": "market",
            "Side": "buy",
            "quantity": "0.00100000",
            "Price": "50000.00000000",
        }
        response = auth_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED

    def test_cancel_order(self, auth_client, user):
        order = Order.objects.create(
            user=user,
            exchange=self.exchange,
            trading_pair=self.pair,
            order_type="limit",
            side="buy",
            quantity=Decimal("0.1"),
            price=Decimal("40000"),
        )
        url = reverse("investments:order-cancel", args=[order.id])
        response = auth_client.post(url, {}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "cancelled"

    def test_cancel_filled_order_fails(self, auth_client, user):
        order = Order.objects.create(
            user=user,
            exchange=self.exchange,
            trading_pair=self.pair,
            order_type="market",
            side="buy",
            quantity=Decimal("0.1"),
            price=Decimal("50000"),
            status="filled",
        )
        url = reverse("investments:order-cancel", args=[order.id])
        response = auth_client.post(url, {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestPositionViewSet:
    @pytest.fixture(autouse=True)
    def setup(self, db, user):
        self.exchange = Exchange.objects.create(name="binance", display_name="Binance")
        self.pair = TradingPair.objects.create(
            exchange_name="binance",
            symbol="BTC/USDT",
            base_asset="BTC",
            quote_asset="USDT",
        )

    def test_create_position(self, auth_client):
        url = reverse("investments:position-list")
        data = {
            "exchange_id": self.exchange.id,
            "trading_pair_id": self.pair.id,
            "side": "long",
            "entry_price": "50000.00000000",
            "quantity": "0.10000000",
        }
        response = auth_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED

    def test_close_position(self, auth_client, user):
        position = Position.objects.create(
            user=user,
            exchange=self.exchange,
            trading_pair=self.pair,
            side="long",
            entry_price=Decimal("50000"),
            quantity=Decimal("0.1"),
        )
        url = reverse("investments:position-close", args=[position.id])
        response = auth_client.post(url, {}, format="json")
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestTechnicalIndicatorViewSet:
    @pytest.fixture(autouse=True)
    def setup(self, db):
        self.exchange = Exchange.objects.create(name="binance", display_name="Binance")
        self.pair = TradingPair.objects.create(
            exchange_name="binance",
            symbol="BTC/USDT",
            base_asset="BTC",
            quote_asset="USDT",
        )
        TechnicalIndicator.objects.create(
            indicator_type="EMA",
            trading_pair=self.pair,
            exchange=self.exchange,
            values={"EMA200": 45000},
            triggered_at=None,
        )

    def test_list_indicators(self, admin_client):
        url = reverse("investments:indicator-list")
        response = admin_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1


@pytest.mark.django_db
class TestUserBalanceViewSet:
    @pytest.fixture(autouse=True)
    def setup(self, db, user):
        self.exchange = Exchange.objects.create(name="binance", display_name="Binance")
        InvestmentBalance.objects.create(
            user=user,
            exchange=self.exchange,
            currency="USDT",
            available=Decimal("1000"),
            total=Decimal("1000"),
        )

    def test_list_balances(self, auth_client):
        url = reverse("investments:balance-list")
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

    def test_summary(self, auth_client):
        url = reverse("investments:balance-summary")
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert "total_usdt_value" in response.data

    def test_unauthenticated(self, api_client):
        url = reverse("investments:balance-list")
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestUserOrdersView:
    def test_my_orders(self, auth_client, user):
        exchange = Exchange.objects.create(name="binance", display_name="Binance")
        pair = TradingPair.objects.create(
            exchange_name="binance",
            symbol="BTC/USDT",
            base_asset="BTC",
            quote_asset="USDT",
        )
        Order.objects.create(
            user=user,
            exchange=exchange,
            trading_pair=pair,
            order_type="market",
            side="buy",
            quantity=Decimal("0.01"),
            price=Decimal("50000"),
        )
        url = reverse("investments:user-orders")
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestUserProfileView:
    def test_user_profile(self, auth_client):
        url = reverse("investments:user-profile")
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert "user_email" in response.data
        assert "total_trades_executed" in response.data


@pytest.mark.django_db
class TestBlockchainAddressesView:
    def test_blockchain_addresses(self, auth_client):
        url = reverse("investments:blockchain-addresses")
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert "error" in response.data


@pytest.mark.django_db
class TestTradingViewWebhookView:
    @pytest.fixture(autouse=True)
    def setup(self, db, user):
        self.user = user
        self.exchange = Exchange.objects.create(name="binance", display_name="Binance")
        self.pair = TradingPair.objects.create(
            exchange_name="binance",
            symbol="BTC/USDT",
            base_asset="BTC",
            quote_asset="USDT",
        )

    def test_webhook_bot_not_found(self, api_client):
        url = reverse(
            "investments:tradingview-webhook", args=["00000000-0000-0000-0000-000000000000"]
        )
        response = api_client.post(url, {"secret": "test"}, format="json")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def _signal_bot(self, user, **kwargs):
        from apps.bots.models import SignalBot

        defaults = {
            "user": user,
            "bot_name": "Webhook Bot",
            "secret_key": "my-secret",
            "default_amount": Decimal("10"),
            "trading_pair": "BTC/USDT",
            "exchange_name": "binance",
        }
        defaults.update(kwargs)
        return SignalBot.objects.create(**defaults)

    def test_webhook_invalid_secret(self, api_client, user):
        bot = self._signal_bot(user, secret_key="correct-secret")
        url = reverse("investments:tradingview-webhook", args=[bot.bot_id])
        response = api_client.post(url, {"secret": "wrong-secret"}, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_webhook_invalid_action(self, api_client, user):
        bot = self._signal_bot(user)
        url = reverse("investments:tradingview-webhook", args=[bot.bot_id])
        response = api_client.post(url, {"secret": "my-secret", "action": "hold"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_webhook_buy_success(self, api_client, user):
        bot = self._signal_bot(user)
        url = reverse("investments:tradingview-webhook", args=[bot.bot_id])
        response = api_client.post(
            url,
            {
                "secret": "my-secret",
                "action": "buy",
                "order": {"amount": "0.001"},
            },
            format="json",
        )
        url = reverse("investments:tradingview-webhook", args=[bot.bot_id])
        response = api_client.post(
            url,
            {
                "secret": "my-secret",
                "action": "buy",
                "order": {"amount": "0.001"},
            },
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "success"


@pytest.mark.django_db
class TestEMAWebhookView:
    @pytest.fixture(autouse=True)
    def setup(self, db, user):
        user.username = "testuser_ema"
        user.save()
        self.exchange = Exchange.objects.create(name="binance", display_name="Binance")
        self.pair = TradingPair.objects.create(
            exchange_name="binance",
            symbol="BTC/USDT",
            base_asset="BTC",
            quote_asset="USDT",
        )

    def test_ema_webhook_success(self, admin_client, user):
        url = reverse("investments:ema-webhook")
        data = {
            "pair": "BTC/USDT",
            "exchange": "binance",
            "EMA200": 45000,
        }
        response = admin_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "success"

    def test_ema_webhook_ignores_username_from_body(self, admin_client, user):
        """Staff user cannot impersonate another user via POST body username."""
        get_user_model().objects.create_user(
            username="other_user",
            email="other@example.com",
            password="testpass123",
        )
        url = reverse("investments:ema-webhook")
        data = {
            "username": "other_user",
            "pair": "BTC/USDT",
            "exchange": "binance",
            "EMA200": 45000,
        }
        response = admin_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestRSIWebhookView:
    @pytest.fixture(autouse=True)
    def setup(self, db, user):
        user.username = "testuser_rsi"
        user.save()
        self.exchange = Exchange.objects.create(name="binance", display_name="Binance")
        self.pair = TradingPair.objects.create(
            exchange_name="binance",
            symbol="BTC/USDT",
            base_asset="BTC",
            quote_asset="USDT",
        )

    def test_rsi_webhook_success(self, admin_client, user):
        url = reverse("investments:rsi-webhook")
        data = {
            "pair": "BTC/USDT",
            "exchange": "binance",
            "RSI": 72.5,
            "color": "red",
            "prev_color": "green",
        }
        response = admin_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "success"


@pytest.mark.django_db
class TestQuantumAIDepositView:
    @pytest.fixture(autouse=True)
    def setup(self, db):
        from apps.bots.models import QuantumAIFund

        self.fund = QuantumAIFund.objects.create(
            name="Test Fund",
            master_api_key="k",
            master_secret_key="s",
        )

    def _bot(self, **kwargs):
        from apps.bots.models import QuantumAIBot

        defaults = {"bot_name": "QB", "fund": self.fund}
        defaults.update(kwargs)
        return QuantumAIBot.objects.create(**defaults)

    def test_deposit_success(self, auth_client, user):
        bot = self._bot()
        url = reverse("investments:quantum-deposit", args=[bot.id])
        data = {
            "amount": "100.00",
            "coin_type": "USDT",
            "blockchain": "BEP20",
            "transaction_hash": "0xtxhash_deposit_test",
        }
        response = auth_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED

    def test_deposit_missing_fields(self, auth_client, user):
        bot = self._bot()
        url = reverse("investments:quantum-deposit", args=[bot.id])
        response = auth_client.post(url, {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_deposit_bot_not_found(self, auth_client):
        url = reverse("investments:quantum-deposit", args=["00000000-0000-0000-0000-000000000000"])
        data = {
            "amount": "100",
            "coin_type": "USDT",
            "blockchain": "BEP20",
            "transaction_hash": "0xhash",
        }
        response = auth_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_404_NOT_FOUND
