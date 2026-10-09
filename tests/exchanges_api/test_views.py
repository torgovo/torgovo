from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework import status

from apps.exchanges import urls as legacy_exchange_urls
from apps.exchanges.models import Exchange, ExchangeCredentials, TradingPair
from apps.investments.models import ExchangeRate, ExchangeStatus
from apps.payments.models import BlockchainAddress
from apps.trading import views as trading_views


def test_legacy_exchange_urls_delegate_to_trading_source_of_truth():
    assert legacy_exchange_urls.list_exchanges is trading_views.list_exchanges
    assert legacy_exchange_urls.get_exchange_symbols is trading_views.get_exchange_symbols
    assert legacy_exchange_urls.get_exchange_rates is trading_views.get_exchange_rates


@pytest.mark.django_db
class TestExchangeCredentialsViewSet:
    def test_list_credentials_empty(self, auth_client):
        url = reverse("exchanges:credentials-list")
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 0

    def test_create_credential(self, auth_client, user):
        url = reverse("exchanges:credentials-list")
        data = {
            "exchange_name": "binance",
            "api_key": "test-api-key-12345",
            "secret_key": "test-secret-key-67890",
        }
        response = auth_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["exchange_name"] == "binance"
        assert response.data["user"] == user.id
        assert "api_key_display" in response.data
        assert "secret_key_display" in response.data

    def test_create_credential_with_passphrase(self, auth_client):
        url = reverse("exchanges:credentials-list")
        data = {
            "exchange_name": "okx",
            "api_key": "key-12345",
            "secret_key": "secret-67890",
            "passphrase": "pass-abc",
        }
        response = auth_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED

    def test_list_credentials_shows_own_only(self, auth_client, user):
        ExchangeCredentials.objects.create(
            user=user, exchange_name="binance", api_key="k1", secret_key="s1"
        )
        url = reverse("exchanges:credentials-list")
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

    def test_other_user_credentials_not_visible(self, auth_client, user, admin_user):
        ExchangeCredentials.objects.create(
            user=admin_user, exchange_name="binance", api_key="k2", secret_key="s2"
        )
        url = reverse("exchanges:credentials-list")
        response = auth_client.get(url)
        assert len(response.data["results"]) == 0

    def test_retrieve_credential(self, auth_client, user):
        cred = ExchangeCredentials.objects.create(
            user=user, exchange_name="binance", api_key="k", secret_key="s"
        )
        url = reverse("exchanges:credentials-detail", args=[cred.id])
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["exchange_name"] == "binance"

    def test_update_credential(self, auth_client, user):
        cred = ExchangeCredentials.objects.create(
            user=user, exchange_name="binance", api_key="k", secret_key="s", notes="original"
        )
        url = reverse("exchanges:credentials-detail", args=[cred.id])
        response = auth_client.patch(url, {"notes": "updated"}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["notes"] == "updated"

    def test_delete_credential(self, auth_client, user):
        cred = ExchangeCredentials.objects.create(
            user=user, exchange_name="binance", api_key="k", secret_key="s"
        )
        url = reverse("exchanges:credentials-detail", args=[cred.id])
        response = auth_client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_active_credentials_endpoint(self, auth_client, user):
        ExchangeCredentials.objects.create(
            user=user, exchange_name="binance", api_key="k1", secret_key="s1", is_active=True
        )
        ExchangeCredentials.objects.create(
            user=user, exchange_name="bybit", api_key="k2", secret_key="s2", is_active=False
        )
        url = reverse("exchanges:credentials-active")
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["exchange_name"] == "binance"

    def test_unauthenticated_access(self, api_client):
        url = reverse("exchanges:credentials-list")
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestTradingPairViewSet:
    @pytest.fixture(autouse=True)
    def setup(self, db):
        TradingPair.objects.create(
            exchange_name="binance",
            symbol="BTCUSDT",
            base_asset="BTC",
            quote_asset="USDT",
            is_active=True,
        )
        TradingPair.objects.create(
            exchange_name="binance",
            symbol="ETHUSDT",
            base_asset="ETH",
            quote_asset="USDT",
            is_active=True,
        )
        TradingPair.objects.create(
            exchange_name="bybit",
            symbol="BTCUSDT",
            base_asset="BTC",
            quote_asset="USDT",
            is_active=False,
        )

    def test_list_active_pairs(self, auth_client):
        url = reverse("exchanges:supported-pairs-list")
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 2

    def test_filter_by_exchange(self, auth_client):
        url = reverse("exchanges:supported-pairs-list")
        response = auth_client.get(f"{url}?exchange=binance")
        assert response.status_code == status.HTTP_200_OK

    def test_popular_pairs(self, auth_client):
        url = reverse("exchanges:supported-pairs-popular")
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK

    def test_unauthenticated(self, api_client):
        url = reverse("exchanges:supported-pairs-list")
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestExchangeStatusViewSet:
    @pytest.fixture(autouse=True)
    def setup(self, db):
        ExchangeStatus.objects.create(exchange_name="binance", status="online")
        ExchangeStatus.objects.create(exchange_name="bybit", status="maintenance")

    def test_list_statuses(self, auth_client):
        url = reverse("exchanges:status-list")
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 2

    def test_retrieve_status(self, auth_client):
        status_obj = ExchangeStatus.objects.first()
        url = reverse("exchanges:status-detail", args=[status_obj.id])
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["exchange_name"] == status_obj.exchange_name

    def test_trading_pairs_action(self, auth_client):
        status_obj = ExchangeStatus.objects.first()
        url = reverse("exchanges:status-trading-pairs", args=[status_obj.id])
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestBlockchainAddressViewSet:
    def test_list_addresses_empty(self, auth_client):
        url = reverse("exchanges:blockchain-addresses-list")
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 0

    def test_create_address(self, admin_client):
        url = reverse("exchanges:blockchain-addresses-list")
        data = {
            "coin_type": "USDT",
            "blockchain": "BEP20",
            "address": "0x1234567890abcdef1234567890abcdef12345678",
            "label": "My USDT Wallet",
        }
        response = admin_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["coin_type"] == "USDT"
        assert response.data["blockchain"] == "BEP20"

    def test_list_addresses_by_crypto(self, auth_client, user):
        BlockchainAddress.objects.create(
            coin_type="USDT",
            blockchain="BEP20",
            address="0x111",
            label="USDT Wallet",
        )
        BlockchainAddress.objects.create(
            coin_type="BTC",
            blockchain="Bitcoin",
            address="1abc",
            label="BTC Wallet",
        )
        url = reverse("exchanges:blockchain-addresses-cryptocurrency")
        response = auth_client.get(f"{url}?crypto=USDT")
        assert response.status_code == status.HTTP_200_OK

    def test_retrieve_address(self, auth_client):
        addr = BlockchainAddress.objects.create(
            coin_type="USDT",
            blockchain="ERC20",
            address="0x1234567890abcdef1234567890abcdef12345678",
        )
        url = reverse("exchanges:blockchain-addresses-detail", args=[addr.id])
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK

    def test_delete_address(self, admin_client):
        addr = BlockchainAddress.objects.create(
            coin_type="USDT",
            blockchain="TRC20",
            address="T1234567890abcdef1234567890abcdef",
        )
        url = reverse("exchanges:blockchain-addresses-detail", args=[addr.id])
        response = admin_client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.django_db
class TestListExchangesView:
    def test_list_exchanges(self, auth_client):
        Exchange.objects.create(name="binance", display_name="Binance", is_active=True)
        Exchange.objects.create(name="bybit", display_name="Bybit", is_active=True)
        url = reverse("exchanges:list_exchanges")
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] is True
        assert len(response.data["data"]) == 2

    def test_list_exchanges_only_active(self, auth_client):
        Exchange.objects.create(name="binance", display_name="Binance", is_active=True)
        Exchange.objects.create(name="offline_ex", display_name="Offline", is_active=False)
        url = reverse("exchanges:list_exchanges")
        response = auth_client.get(url)
        assert len(response.data["data"]) == 1
        assert response.data["data"][0]["name"] == "binance"

    def test_list_exchanges_unauthenticated(self, api_client):
        url = reverse("exchanges:list_exchanges")
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestGetExchangeSymbols:
    def test_get_symbols(self, auth_client):
        Exchange.objects.create(name="binance", display_name="Binance", is_active=True)
        TradingPair.objects.create(
            exchange_name="binance",
            symbol="BTCUSDT",
            base_asset="BTC",
            quote_asset="USDT",
            is_active=True,
        )
        url = reverse("exchanges:get_exchange_symbols", args=["binance"])
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] is True
        assert "BTCUSDT" in response.data["symbols"]

    def test_get_symbols_not_found(self, auth_client):
        url = reverse("exchanges:get_exchange_symbols", args=["nonexistent"])
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestGetExchangeRates:
    def test_get_rates_with_db_fallback(self, auth_client):
        ExchangeRate.objects.create(
            from_currency="BTC",
            to_currency="USDT",
            rate=Decimal("50000"),
            exchange_name="bybit",
            source="cached",
        )
        url = reverse("exchanges:get_exchange_rates")
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] is True
        assert "timestamp" in response.data

    def test_get_rates_unauthenticated(self, api_client):
        url = reverse("exchanges:get_exchange_rates")
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
