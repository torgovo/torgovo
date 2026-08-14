import pytest
from rest_framework import status

# ==================== URL FIXTURES ====================


@pytest.fixture
def exchange_url():
    return "/api/trading/exchanges/"


@pytest.fixture
def credentials_url():
    return "/api/trading/credentials/"


@pytest.fixture
def pairs_url():
    return "/api/trading/pairs/"


@pytest.fixture
def status_url():
    return "/api/trading/status/"


@pytest.fixture
def strategy_config_url():
    return "/api/trading/strategy-configs/"


# ==================== AUTH TESTS ====================


class TestTradingAuth:
    def test_unauthenticated_blocked(self, api_client, exchange_url):
        response = api_client.get(exchange_url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_unauthenticated_post_blocked(self, api_client, credentials_url):
        response = api_client.post(credentials_url, {})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ==================== EXCHANGE VIEWSET TESTS ====================


@pytest.mark.django_db
class TestExchangeViewSet:
    def test_list_exchanges(self, auth_client, exchange_url, exchange):
        response = auth_client.get(exchange_url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["name"] == "binance"

    def test_list_exchanges_only_active(self, auth_client, exchange_url):
        from apps.exchanges.models import Exchange

        Exchange.objects.create(
            name="inactive_exchange",
            display_name="Inactive",
            is_active=False,
        )
        Exchange.objects.create(
            name="active_exchange",
            display_name="Active",
            is_active=True,
        )
        response = auth_client.get(exchange_url)
        assert response.status_code == status.HTTP_200_OK
        names = [e["name"] for e in response.data["results"]]
        assert "inactive_exchange" not in names
        assert "active_exchange" in names

    def test_retrieve_exchange(self, auth_client, exchange_url, exchange):
        response = auth_client.get(f"{exchange_url}{exchange.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "binance"

    def test_cannot_create_exchange(self, auth_client, exchange_url):
        response = auth_client.post(exchange_url, {"name": "new_exchange"}, format="json")
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


# ==================== EXCHANGE CREDENTIALS VIEWSET TESTS ====================


@pytest.mark.django_db
class TestExchangeCredentialsViewSet:
    def test_list_credentials_empty(self, auth_client, credentials_url):
        response = auth_client.get(credentials_url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["results"] == []

    def test_create_credentials(self, auth_client, credentials_url, valid_fernet_key):
        from django.test.utils import override_settings

        data = {
            "exchange_name": "binance",
            "api_key": "test-api-key-12345",
            "secret_key": "test-secret-key-54321",
            "is_testnet": True,
        }
        with override_settings(FERNET_KEY=valid_fernet_key):
            response = auth_client.post(credentials_url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert response.data["exchange_name"] == "binance"

    def test_list_credentials(self, auth_client, credentials_url, exchange_credentials):
        response = auth_client.get(credentials_url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["exchange_name"] == "binance"

    def test_other_user_cannot_see_credentials(
        self, auth_client, second_auth_client, credentials_url, exchange_credentials
    ):
        response = second_auth_client.get(credentials_url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["results"] == []

    def test_active_endpoint(self, auth_client, credentials_url, exchange_credentials):
        response = auth_client.get(f"{credentials_url}active/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 1

    def test_active_endpoint_filters_inactive(self, auth_client, credentials_url, valid_fernet_key):
        from django.test.utils import override_settings

        from apps.exchanges.models import ExchangeCredentials

        user = auth_client.handler._force_user
        with override_settings(FERNET_KEY=valid_fernet_key):
            ExchangeCredentials.objects.create(
                user=user,
                exchange_name="bybit",
                api_key="k",
                secret_key="s",
                is_active=False,
            )
        response = auth_client.get(f"{credentials_url}active/")
        assert response.status_code == status.HTTP_200_OK

    def test_update_credentials(self, auth_client, credentials_url, exchange_credentials):
        response = auth_client.patch(
            f"{credentials_url}{exchange_credentials.id}/",
            {"notes": "Updated notes"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["notes"] == "Updated notes"

    def test_delete_credentials(self, auth_client, credentials_url, exchange_credentials):
        response = auth_client.delete(f"{credentials_url}{exchange_credentials.id}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT


# ==================== TRADING PAIR VIEWSET TESTS ====================


@pytest.mark.django_db
class TestTradingPairViewSet:
    def test_list_pairs(self, auth_client, pairs_url, trading_pair):
        response = auth_client.get(pairs_url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["symbol"] == "BTC/USDT"

    def test_list_pairs_filter_by_exchange(self, auth_client, pairs_url):
        from apps.exchanges.models import TradingPair

        TradingPair.objects.create(
            exchange_name="binance",
            symbol="ETH/USDT",
            base_asset="ETH",
            quote_asset="USDT",
        )
        TradingPair.objects.create(
            exchange_name="bybit",
            symbol="SOL/USDT",
            base_asset="SOL",
            quote_asset="USDT",
        )
        response = auth_client.get(f"{pairs_url}?exchange=binance")
        assert response.status_code == status.HTTP_200_OK
        symbols = [p["symbol"] for p in response.data["results"]]
        assert "SOL/USDT" not in symbols
        assert "ETH/USDT" in symbols

    def test_popular_pairs(self, auth_client, pairs_url, trading_pair):
        response = auth_client.get(f"{pairs_url}popular/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 1

    def test_cannot_create_pair(self, auth_client, pairs_url):
        response = auth_client.post(pairs_url, {}, format="json")
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


# ==================== EXCHANGE STATUS VIEWSET TESTS ====================


@pytest.mark.django_db
class TestExchangeStatusViewSet:
    def test_list_status(self, auth_client, status_url, exchange_status):
        response = auth_client.get(status_url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["status"] == "online"

    def test_retrieve_status(self, auth_client, status_url, exchange_status):
        response = auth_client.get(f"{status_url}{exchange_status.id}/")
        assert response.status_code == status.HTTP_200_OK

    def test_cannot_create_status(self, auth_client, status_url):
        response = auth_client.post(status_url, {}, format="json")
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


# ==================== STRATEGY CONFIG VIEWSET TESTS ====================


@pytest.mark.django_db
class TestStrategyConfigViewSet:
    def test_list_strategy_configs(self, auth_client, strategy_config_url, strategy_config):
        response = auth_client.get(strategy_config_url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["name"] == "Grid Conservative"

    def test_list_only_active_configs(self, auth_client, strategy_config_url):
        from apps.trading.models import StrategyConfig

        StrategyConfig.objects.create(
            name="Inactive Config",
            strategy="grid",
            is_active=False,
        )
        StrategyConfig.objects.create(
            name="Active Config",
            strategy="martingale",
            is_active=True,
        )
        response = auth_client.get(strategy_config_url)
        assert response.status_code == status.HTTP_200_OK
        names = [c["name"] for c in response.data["results"]]
        assert "Inactive Config" not in names
        assert "Active Config" in names

    def test_cannot_create_strategy_config(self, auth_client, strategy_config_url):
        response = auth_client.post(strategy_config_url, {}, format="json")
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


# ==================== FUNCTION-BASED VIEW TESTS ====================


@pytest.mark.django_db
class TestListExchangesView:
    def test_list_exchanges_endpoint(self, auth_client, exchange):
        response = auth_client.get("/api/trading/exchanges/list/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] is True
        assert len(response.data["data"]) == 1
        assert response.data["data"][0]["name"] == "binance"

    def test_list_exchanges_unauthenticated(self, api_client):
        response = api_client.get("/api/trading/exchanges/list/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestGetExchangeSymbols:
    def test_get_symbols(self, auth_client, trading_pair):
        response = auth_client.get("/api/trading/exchanges/binance/symbols/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] is True
        assert "BTC/USDT" in response.data["symbols"]

    def test_get_symbols_unknown_exchange(self, auth_client):
        response = auth_client.get("/api/trading/exchanges/unknown/symbols/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] is True
        assert response.data["symbols"] == []


@pytest.mark.django_db
class TestGetExchangeRates:
    def test_get_rates_db_fallback(self, auth_client, exchange_rate):
        response = auth_client.get("/api/trading/rates/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] is True
        assert "rates" in response.data
        assert response.data["timestamp"] is not None

    def test_get_rates_unauthenticated(self, api_client):
        response = api_client.get("/api/trading/rates/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
