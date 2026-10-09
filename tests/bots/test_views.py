from decimal import Decimal

import pytest
from rest_framework import status

# ==================== HELPER FIXTURES ====================


@pytest.fixture
def signal_bot_url():
    return "/api/bots/signal-bots/"


@pytest.fixture
def grid_bot_url():
    return "/api/bots/grid-bots/"


@pytest.fixture
def martingale_bot_url():
    return "/api/bots/martingale-bots/"


@pytest.fixture
def quantum_fund_url():
    return "/api/bots/quantum-funds/"


@pytest.fixture
def quantum_investment_url():
    return "/api/bots/quantum-investments/"


@pytest.fixture
def pair_config_url():
    return "/api/bots/pair-configs/"


@pytest.fixture
def indicator_url():
    return "/api/bots/indicators/"


@pytest.fixture
def order_url():
    return "/api/bots/orders/"


@pytest.fixture
def telegram_plan_url():
    return "/api/bots/telegram-plans/"


@pytest.fixture
def telegram_sub_url():
    return "/api/bots/telegram-subscriptions/"


# ==================== AUTHENTICATION TESTS ====================


class TestAuth:
    def test_unauthenticated_blocked(self, api_client, signal_bot_url):
        response = api_client.get(signal_bot_url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_unauthenticated_post_blocked(self, api_client, signal_bot_url):
        response = api_client.post(signal_bot_url, {})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ==================== SIGNAL BOT VIEWSET TESTS ====================


@pytest.mark.django_db
class TestSignalBotViewSet:
    def test_list_signal_bots_empty(self, auth_client, signal_bot_url):
        response = auth_client.get(signal_bot_url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["results"] == []

    def test_create_signal_bot(self, auth_client, signal_bot_url, signal_bot_subscription):
        data = {
            "bot_name": "My Signal Bot",
            "exchange_name": "binance",
            "market_type": "spot",
            "trading_pair": "BTC/USDT",
            "default_amount": "0.01",
        }
        response = auth_client.post(signal_bot_url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert response.data["bot_name"] == "My Signal Bot"
        assert response.data["webhook_url"] is not None
        assert response.data["bot_id"] is not None  # via property

    def test_create_signal_bot_no_subscription(self, auth_client, signal_bot_url):
        data = {
            "bot_name": "No Sub Bot",
            "exchange_name": "binance",
            "market_type": "spot",
            "trading_pair": "BTC/USDT",
            "default_amount": "0.01",
        }
        response = auth_client.post(signal_bot_url, data, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_signal_bot_invalid_exchange(
        self, auth_client, signal_bot_url, signal_bot_subscription
    ):
        data = {
            "bot_name": "Bad Exchange",
            "exchange_name": "kraken",
            "market_type": "spot",
            "trading_pair": "BTC/USDT",
            "default_amount": "0.01",
        }
        response = auth_client.post(signal_bot_url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_retrieve_signal_bot(self, auth_client, signal_bot_url, signal_bot_subscription):
        from apps.bots.models import SignalBot

        bot = SignalBot.objects.create(
            user=auth_client.handler._force_user,
            bot_name="My Bot",
            exchange_name="binance",
            trading_pair="BTC/USDT",
            default_amount=Decimal("0.01"),
            subscription=signal_bot_subscription,
        )
        response = auth_client.get(f"{signal_bot_url}{bot.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["bot_name"] == "My Bot"

    def test_update_signal_bot(self, auth_client, signal_bot_url, signal_bot_subscription):
        from apps.bots.models import SignalBot

        user = auth_client.handler._force_user
        bot = SignalBot.objects.create(
            user=user,
            bot_name="Original",
            exchange_name="binance",
            trading_pair="BTC/USDT",
            default_amount=Decimal("0.01"),
            subscription=signal_bot_subscription,
        )
        response = auth_client.patch(
            f"{signal_bot_url}{bot.id}/", {"bot_name": "Updated"}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["bot_name"] == "Updated"

    def test_delete_signal_bot(self, auth_client, signal_bot_url, signal_bot_subscription):
        from apps.bots.models import SignalBot

        user = auth_client.handler._force_user
        bot = SignalBot.objects.create(
            user=user,
            bot_name="To Delete",
            exchange_name="binance",
            trading_pair="BTC/USDT",
            default_amount=Decimal("0.01"),
            subscription=signal_bot_subscription,
        )
        response = auth_client.delete(f"{signal_bot_url}{bot.id}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_other_user_cannot_access(
        self, auth_client, second_auth_client, signal_bot_url, signal_bot_subscription
    ):
        from apps.bots.models import SignalBot

        user = auth_client.handler._force_user
        bot = SignalBot.objects.create(
            user=user,
            bot_name="Private",
            exchange_name="binance",
            trading_pair="BTC/USDT",
            default_amount=Decimal("0.01"),
            subscription=signal_bot_subscription,
        )
        response = second_auth_client.get(f"{signal_bot_url}{bot.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_admin_sees_all(
        self, admin_client, auth_client, signal_bot_url, signal_bot_subscription
    ):
        from apps.bots.models import SignalBot

        user = auth_client.handler._force_user
        SignalBot.objects.create(
            user=user,
            bot_name="Admin Visible",
            exchange_name="binance",
            trading_pair="BTC/USDT",
            default_amount=Decimal("0.01"),
            subscription=signal_bot_subscription,
        )
        response = admin_client.get(signal_bot_url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

    def test_toggle_active(self, auth_client, signal_bot_url, signal_bot_subscription):
        from apps.bots.models import SignalBot

        user = auth_client.handler._force_user
        bot = SignalBot.objects.create(
            user=user,
            bot_name="Togglable",
            exchange_name="binance",
            trading_pair="BTC/USDT",
            default_amount=Decimal("0.01"),
            is_active=True,
            subscription=signal_bot_subscription,
        )
        response = auth_client.post(f"{signal_bot_url}{bot.id}/toggle_active/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["is_active"] is False

        response = auth_client.post(f"{signal_bot_url}{bot.id}/toggle_active/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["is_active"] is True

    def test_toggle_active_other_user_forbidden(
        self, auth_client, second_auth_client, signal_bot_url, signal_bot_subscription
    ):
        from apps.bots.models import SignalBot

        user = auth_client.handler._force_user
        bot = SignalBot.objects.create(
            user=user,
            bot_name="Private",
            exchange_name="binance",
            trading_pair="BTC/USDT",
            default_amount=Decimal("0.01"),
            subscription=signal_bot_subscription,
        )
        response = second_auth_client.post(f"{signal_bot_url}{bot.id}/toggle_active/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_admin_can_toggle_any(
        self, admin_client, auth_client, signal_bot_url, signal_bot_subscription
    ):
        from apps.bots.models import SignalBot

        user = auth_client.handler._force_user
        bot = SignalBot.objects.create(
            user=user,
            bot_name="Admin Toggle",
            exchange_name="binance",
            trading_pair="BTC/USDT",
            default_amount=Decimal("0.01"),
            subscription=signal_bot_subscription,
        )
        response = admin_client.post(f"{signal_bot_url}{bot.id}/toggle_active/")
        assert response.status_code == status.HTTP_200_OK


# ==================== GRID BOT VIEWSET TESTS ====================


@pytest.mark.django_db
class TestGridBotViewSet:
    def test_create_grid_bot(self, auth_client, grid_bot_url, bot_subscription):
        data = {
            "bot_name": "My Grid Bot",
            "exchange_name": "binance",
            "trading_pair": "BTC/USDT",
            "base_amount": "0.001",
            "favor_levels": 5,
            "against_levels": 5,
        }
        response = auth_client.post(grid_bot_url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert response.data["bot_name"] == "My Grid Bot"

    def test_create_grid_bot_no_subscription(self, auth_client, grid_bot_url):
        data = {
            "bot_name": "No Sub",
            "exchange_name": "binance",
            "trading_pair": "BTC/USDT",
            "base_amount": "0.001",
            "favor_levels": 3,
            "against_levels": 3,
        }
        response = auth_client.post(grid_bot_url, data, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_duplicate_grid_bot_fails(self, auth_client, grid_bot_url, bot_subscription):
        data = {
            "bot_name": "First",
            "exchange_name": "binance",
            "trading_pair": "BTC/USDT",
            "base_amount": "0.001",
            "favor_levels": 3,
            "against_levels": 3,
        }
        response = auth_client.post(grid_bot_url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED

        response = auth_client.post(grid_bot_url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "already have a Grid Bot" in str(response.data)

    def test_list_grid_bots(self, auth_client, grid_bot_url, bot_subscription):
        from apps.bots.models import GridBot

        user = auth_client.handler._force_user
        GridBot.objects.create(
            user=user,
            bot_name="G1",
            exchange_name="binance",
            trading_pair="BTC/USDT",
            base_amount=Decimal("0.001"),
            favor_levels=3,
            against_levels=3,
            subscription=bot_subscription,
        )
        response = auth_client.get(grid_bot_url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

    def test_start_grid_bot(self, auth_client, grid_bot_url, bot_subscription):
        from django.test.utils import override_settings

        from apps.bots.models import GridBot

        user = auth_client.handler._force_user
        bot = GridBot.objects.create(
            user=user,
            bot_name="Startable",
            exchange_name="binance",
            trading_pair="BTC/USDT",
            base_amount=Decimal("0.001"),
            favor_levels=3,
            against_levels=3,
            subscription=bot_subscription,
        )
        with override_settings(CELERY_TASK_ALWAYS_EAGER=False):
            response = auth_client.post(f"{grid_bot_url}{bot.id}/start/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] is True
        bot.refresh_from_db()
        assert bot.is_running is True
        assert bot.started_at is not None

    def test_stop_grid_bot(self, auth_client, grid_bot_url, bot_subscription):
        from apps.bots.models import GridBot

        user = auth_client.handler._force_user
        bot = GridBot.objects.create(
            user=user,
            bot_name="Stoppable",
            exchange_name="binance",
            trading_pair="BTC/USDT",
            base_amount=Decimal("0.001"),
            favor_levels=3,
            against_levels=3,
            is_running=True,
            subscription=bot_subscription,
        )
        response = auth_client.post(f"{grid_bot_url}{bot.id}/stop/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] is True
        bot.refresh_from_db()
        assert bot.is_running is False
        assert bot.stopped_at is not None

    def test_start_other_users_bot_forbidden(
        self, auth_client, second_auth_client, grid_bot_url, bot_subscription
    ):
        from apps.bots.models import GridBot

        user = auth_client.handler._force_user
        bot = GridBot.objects.create(
            user=user,
            bot_name="Private",
            exchange_name="binance",
            trading_pair="BTC/USDT",
            base_amount=Decimal("0.001"),
            favor_levels=3,
            against_levels=3,
            subscription=bot_subscription,
        )
        response = second_auth_client.post(f"{grid_bot_url}{bot.id}/start/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_admin_can_start_any(self, admin_client, auth_client, grid_bot_url, bot_subscription):
        from django.test.utils import override_settings

        from apps.bots.models import GridBot

        user = auth_client.handler._force_user
        bot = GridBot.objects.create(
            user=user,
            bot_name="Admin Start",
            exchange_name="binance",
            trading_pair="BTC/USDT",
            base_amount=Decimal("0.001"),
            favor_levels=3,
            against_levels=3,
            subscription=bot_subscription,
        )
        with override_settings(CELERY_TASK_ALWAYS_EAGER=False):
            response = admin_client.post(f"{grid_bot_url}{bot.id}/start/")
        assert response.status_code == status.HTTP_200_OK

    def test_update_grid_bot(self, auth_client, grid_bot_url, bot_subscription):
        from apps.bots.models import GridBot

        user = auth_client.handler._force_user
        bot = GridBot.objects.create(
            user=user,
            bot_name="Original",
            exchange_name="binance",
            trading_pair="BTC/USDT",
            base_amount=Decimal("0.001"),
            favor_levels=3,
            against_levels=3,
            subscription=bot_subscription,
        )
        response = auth_client.patch(
            f"{grid_bot_url}{bot.id}/", {"bot_name": "Updated"}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["bot_name"] == "Updated"

    def test_delete_grid_bot(self, auth_client, grid_bot_url, bot_subscription):
        from apps.bots.models import GridBot

        user = auth_client.handler._force_user
        bot = GridBot.objects.create(
            user=user,
            bot_name="To Delete",
            exchange_name="binance",
            trading_pair="BTC/USDT",
            base_amount=Decimal("0.001"),
            favor_levels=3,
            against_levels=3,
            subscription=bot_subscription,
        )
        response = auth_client.delete(f"{grid_bot_url}{bot.id}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_other_user_cannot_see_grid_bot(
        self, auth_client, second_auth_client, grid_bot_url, bot_subscription
    ):
        from apps.bots.models import GridBot

        user = auth_client.handler._force_user
        bot = GridBot.objects.create(
            user=user,
            bot_name="Hidden",
            exchange_name="binance",
            trading_pair="BTC/USDT",
            base_amount=Decimal("0.001"),
            favor_levels=3,
            against_levels=3,
            subscription=bot_subscription,
        )
        response = second_auth_client.get(f"{grid_bot_url}{bot.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND


# ==================== MARTINGALE BOT VIEWSET TESTS ====================


@pytest.mark.django_db
class TestMartingaleBotViewSet:
    def test_create_martingale_bot(
        self, auth_client, martingale_bot_url, martingale_bot_subscription
    ):
        data = {
            "bot_name": "My Martingale",
            "exchange_name": "bybit",
            "trading_pair": "ETH/USDT",
            "base_amount": "0.1",
            "favor_levels": 4,
            "against_levels": 4,
            "multiplier_factor": "2.0",
        }
        response = auth_client.post(martingale_bot_url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert response.data["bot_name"] == "My Martingale"

    def test_create_martingale_bot_no_subscription(self, auth_client, martingale_bot_url):
        data = {
            "bot_name": "No Sub",
            "exchange_name": "bybit",
            "trading_pair": "ETH/USDT",
            "base_amount": "0.1",
            "favor_levels": 3,
            "against_levels": 3,
        }
        response = auth_client.post(martingale_bot_url, data, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_duplicate_martingale_fails(
        self, auth_client, martingale_bot_url, martingale_bot_subscription
    ):
        data = {
            "bot_name": "First",
            "exchange_name": "bybit",
            "trading_pair": "ETH/USDT",
            "base_amount": "0.1",
            "favor_levels": 3,
            "against_levels": 3,
        }
        response = auth_client.post(martingale_bot_url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED

        response = auth_client.post(martingale_bot_url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_start_martingale_bot(
        self, auth_client, martingale_bot_url, martingale_bot_subscription
    ):
        from django.test.utils import override_settings

        from apps.bots.models import MartingaleBot

        user = auth_client.handler._force_user
        bot = MartingaleBot.objects.create(
            user=user,
            bot_name="MStart",
            exchange_name="bybit",
            trading_pair="ETH/USDT",
            base_amount=Decimal("0.1"),
            favor_levels=3,
            against_levels=3,
            subscription=martingale_bot_subscription,
        )
        with override_settings(CELERY_TASK_ALWAYS_EAGER=False):
            response = auth_client.post(f"{martingale_bot_url}{bot.id}/start/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] is True

    def test_stop_martingale_bot(
        self, auth_client, martingale_bot_url, martingale_bot_subscription
    ):
        from apps.bots.models import MartingaleBot

        user = auth_client.handler._force_user
        bot = MartingaleBot.objects.create(
            user=user,
            bot_name="MStop",
            exchange_name="bybit",
            trading_pair="ETH/USDT",
            base_amount=Decimal("0.1"),
            favor_levels=3,
            against_levels=3,
            is_running=True,
            subscription=martingale_bot_subscription,
        )
        response = auth_client.post(f"{martingale_bot_url}{bot.id}/stop/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] is True

    def test_martingale_permission_denied(
        self, second_auth_client, auth_client, martingale_bot_url, martingale_bot_subscription
    ):
        from apps.bots.models import MartingaleBot

        user = auth_client.handler._force_user
        bot = MartingaleBot.objects.create(
            user=user,
            bot_name="Private",
            exchange_name="bybit",
            trading_pair="ETH/USDT",
            base_amount=Decimal("0.1"),
            favor_levels=3,
            against_levels=3,
            subscription=martingale_bot_subscription,
        )
        response = second_auth_client.post(f"{martingale_bot_url}{bot.id}/start/")
        assert response.status_code == status.HTTP_404_NOT_FOUND


# ==================== QUANTUM AI FUND VIEWSET TESTS ====================


@pytest.mark.django_db
class TestQuantumAIFundViewSet:
    def test_admin_can_list_funds(self, admin_client, quantum_fund_url, quantum_fund):
        response = admin_client.get(quantum_fund_url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

    def test_regular_user_cannot_access_funds(self, auth_client, quantum_fund_url):
        response = auth_client.get(quantum_fund_url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_can_retrieve_fund(self, admin_client, quantum_fund_url, quantum_fund):
        response = admin_client.get(f"{quantum_fund_url}{quantum_fund.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Master Fund"


# ==================== QUANTUM AI INVESTMENT VIEWSET TESTS ====================


@pytest.mark.django_db
class TestQuantumInvestmentViewSet:
    def test_create_investment(
        self, auth_client, quantum_investment_url, quantum_ai_subscription, quantum_fund
    ):
        data = {
            "fund": str(quantum_fund.id),
            "amount": "1000",
            "subscription": str(quantum_ai_subscription.id),
        }
        response = auth_client.post(quantum_investment_url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert response.data["amount"] == "1000.00000000"

    def test_create_investment_no_subscription(
        self, auth_client, quantum_investment_url, quantum_fund
    ):
        data = {
            "fund": str(quantum_fund.id),
            "amount": "1000",
        }
        response = auth_client.post(quantum_investment_url, data, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_list_investments(
        self, auth_client, quantum_investment_url, quantum_ai_subscription, quantum_fund
    ):
        from apps.bots.models import InvestorPortfolio

        user = auth_client.handler._force_user
        InvestorPortfolio.objects.create(
            user=user,
            fund=quantum_fund,
            amount=Decimal("500"),
            status="active",
            subscription=quantum_ai_subscription,
        )
        response = auth_client.get(quantum_investment_url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

    def test_balance_endpoint(
        self, auth_client, quantum_investment_url, quantum_ai_subscription, quantum_fund
    ):
        from apps.bots.models import InvestorPortfolio

        user = auth_client.handler._force_user
        InvestorPortfolio.objects.create(
            user=user,
            fund=quantum_fund,
            amount=Decimal("1000"),
            accrued_profit=Decimal("50"),
            status="active",
            subscription=quantum_ai_subscription,
        )
        response = auth_client.get(f"{quantum_investment_url}balance/")
        assert response.status_code == status.HTTP_200_OK
        assert "total_invested" in response.data
        assert "total_profit" in response.data
        assert "current_balance" in response.data

    def test_admin_sees_all_investments(
        self,
        admin_client,
        auth_client,
        quantum_investment_url,
        quantum_ai_subscription,
        quantum_fund,
    ):
        from apps.bots.models import InvestorPortfolio

        user = auth_client.handler._force_user
        InvestorPortfolio.objects.create(
            user=user,
            fund=quantum_fund,
            amount=Decimal("500"),
            status="active",
            subscription=quantum_ai_subscription,
        )
        response = admin_client.get(quantum_investment_url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

    def test_other_user_cannot_see_investment(
        self,
        auth_client,
        second_auth_client,
        quantum_investment_url,
        quantum_ai_subscription,
        quantum_fund,
    ):
        from apps.bots.models import InvestorPortfolio

        user = auth_client.handler._force_user
        inv = InvestorPortfolio.objects.create(
            user=user,
            fund=quantum_fund,
            amount=Decimal("500"),
            status="active",
            subscription=quantum_ai_subscription,
        )
        response = second_auth_client.get(f"{quantum_investment_url}{inv.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND


# ==================== PAIR CONFIG VIEWSET TESTS ====================


@pytest.mark.django_db
class TestPairConfigViewSet:
    def test_create_pair_config(self, auth_client, pair_config_url, bot_subscription):
        data = {
            "pair_symbol": "BTC/USDT",
            "bot_type": "grid",
            "Order_Type": "limit",
            "Stop_Loss": 5.0,
            "Take_Profit": 10.0,
        }
        response = auth_client.post(pair_config_url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert response.data["pair_symbol"] == "BTC/USDT"

    def test_create_pair_config_no_subscription(self, auth_client, pair_config_url):
        data = {
            "pair_symbol": "BTC/USDT",
            "bot_type": "grid",
        }
        response = auth_client.post(pair_config_url, data, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_list_pair_configs(self, auth_client, pair_config_url, bot_subscription):
        from apps.bots.models import PairConfig

        user = auth_client.handler._force_user
        PairConfig.objects.create(
            user=user,
            pair_symbol="BTC/USDT",
            bot_type="grid",
            subscription=bot_subscription,
        )
        response = auth_client.get(pair_config_url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

    def test_update_pair_config(self, auth_client, pair_config_url, bot_subscription):
        from apps.bots.models import PairConfig

        user = auth_client.handler._force_user
        config = PairConfig.objects.create(
            user=user,
            pair_symbol="BTC/USDT",
            bot_type="grid",
            subscription=bot_subscription,
        )
        response = auth_client.patch(
            f"{pair_config_url}{config.id}/",
            {"Stop_Loss": 10.0},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK

    def test_admin_sees_all_pair_configs(
        self, admin_client, auth_client, pair_config_url, bot_subscription
    ):
        from apps.bots.models import PairConfig

        user = auth_client.handler._force_user
        PairConfig.objects.create(
            user=user,
            pair_symbol="BTC/USDT",
            bot_type="grid",
            subscription=bot_subscription,
        )
        response = admin_client.get(pair_config_url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) >= 1


# ==================== INDICATOR VIEWSET TESTS ====================


@pytest.mark.django_db
class TestIndicatorViewSet:
    def test_create_indicator(self, auth_client, indicator_url):
        data = {"Pair": "BTC/USDT", "EMA": 200.0, "RSI": 65.0}
        response = auth_client.post(indicator_url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert response.data["EMA"] == 200.0

    def test_list_indicators(self, auth_client, indicator_url):
        from apps.bots.models import Indicator

        user = auth_client.handler._force_user
        Indicator.objects.create(user=user, Pair="BTC/USDT", EMA=200.0)
        response = auth_client.get(indicator_url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

    def test_other_user_cannot_see_indicator(self, auth_client, second_auth_client, indicator_url):
        from apps.bots.models import Indicator

        user = auth_client.handler._force_user
        ind = Indicator.objects.create(user=user, Pair="BTC/USDT", EMA=200.0)
        response = second_auth_client.get(f"{indicator_url}{ind.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_admin_sees_all_indicators(self, admin_client, auth_client, indicator_url):
        from apps.bots.models import Indicator

        user = auth_client.handler._force_user
        Indicator.objects.create(user=user, Pair="BTC/USDT", EMA=200.0)
        response = admin_client.get(indicator_url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1


# ==================== ORDER VIEWSET TESTS ====================


@pytest.mark.django_db
class TestOrderViewSet:
    def test_list_orders(self, auth_client, order_url):
        from apps.bots.models import BotOrder

        user = auth_client.handler._force_user
        BotOrder.objects.create(
            user=user,
            Pair="BTC/USDT",
            Side="buy",
            Price=45000.0,
            Quantity=Decimal("0.01"),
        )
        response = auth_client.get(order_url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

    def test_recent_orders(self, auth_client, order_url):
        from apps.bots.models import BotOrder

        user = auth_client.handler._force_user
        BotOrder.objects.create(
            user=user,
            Pair="BTC/USDT",
            Side="buy",
            Price=45000.0,
            Quantity=Decimal("0.01"),
        )
        response = auth_client.get(f"{order_url}recent/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 1

    def test_other_user_cannot_see_orders(self, auth_client, second_auth_client, order_url):
        from apps.bots.models import BotOrder

        user = auth_client.handler._force_user
        order = BotOrder.objects.create(
            user=user,
            Pair="BTC/USDT",
            Side="buy",
            Price=45000.0,
            Quantity=Decimal("0.01"),
        )
        response = second_auth_client.get(f"{order_url}{order.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND


# ==================== TELEGRAM VIEWSET TESTS ====================


@pytest.mark.django_db
@pytest.mark.django_db
@pytest.mark.django_db
class TestGetOrCreateEngine:
    def test_returns_none_without_credentials(self, user):
        from apps.bots.views import get_or_create_engine

        result = get_or_create_engine(user, {"pair_symbol": "BTC/USDT"}, "binance")
        assert result is None
