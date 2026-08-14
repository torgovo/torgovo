from decimal import Decimal

import pytest

from apps.exchanges.models import Exchange, ExchangeCredentials, TradingPair
from apps.investments.models import ExchangeRate, ExchangeStatus, SupportedBlockchain


@pytest.mark.django_db
class TestExchangeModel:
    def test_create_exchange(self):
        exchange = Exchange.objects.create(
            name="binance",
            display_name="Binance",
            api_base_url="https://api.binance.com",
            is_active=True,
            supports_testnet=True,
            supported_features=["spot", "futures"],
            rate_limit_per_minute=1200,
            fee_rates={"maker": 0.001, "taker": 0.001},
        )
        assert exchange.name == "binance"
        assert exchange.display_name == "Binance"
        assert exchange.is_active is True
        assert exchange.supports_testnet is True
        assert str(exchange) == "Binance"
        assert exchange.supported_features == ["spot", "futures"]

    def test_exchange_unique_name(self, db):
        Exchange.objects.create(name="binance", display_name="Binance")
        with pytest.raises(Exception):
            Exchange.objects.create(name="binance", display_name="Binance2")

    def test_exchange_defaults(self):
        exchange = Exchange.objects.create(name="bybit", display_name="Bybit")
        assert exchange.is_active is True
        assert exchange.supports_testnet is True
        assert exchange.supported_features == []
        assert exchange.rate_limit_per_minute == 1200
        assert exchange.fee_rates == {}

    def test_exchange_indexes(self):
        assert Exchange._meta.indexes
        index_fields = [i.fields for i in Exchange._meta.indexes]
        assert ["name"] in index_fields
        assert ["is_active"] in index_fields


@pytest.mark.django_db
class TestExchangeCredentialsModel:
    def test_create_credentials(self, user):
        creds = ExchangeCredentials.objects.create(
            user=user,
            exchange_name="binance",
            api_key="raw-api-key-12345",
            secret_key="raw-secret-key-67890",
        )
        assert creds.user == user
        assert creds.exchange_name == "binance"
        assert creds.is_active is True
        assert creds.is_testnet is True
        assert creds.verification_status == "pending"
        assert creds.trading_enabled is True
        assert creds.withdrawal_enabled is False
        assert str(creds) == f"{user.email} - binance"

    def test_credentials_encrypt_on_create(self, user):
        creds = ExchangeCredentials.objects.create(
            user=user,
            exchange_name="bybit",
            api_key="my-api-key",
            secret_key="my-secret-key",
            passphrase="my-passphrase",
        )
        assert creds.api_key != "my-api-key"
        assert creds.secret_key != "my-secret-key"
        assert creds.passphrase != "my-passphrase"

    def test_get_decrypted_credentials(self, user):
        creds = ExchangeCredentials.objects.create(
            user=user,
            exchange_name="okx",
            api_key="raw-api-key",
            secret_key="raw-secret-key",
            passphrase="raw-passphrase",
        )
        decrypted = creds.get_decrypted_credentials()
        assert decrypted["api_key"] == "raw-api-key"
        assert decrypted["secret_key"] == "raw-secret-key"
        assert decrypted["passphrase"] == "raw-passphrase"
        assert decrypted["is_testnet"] is True

    def test_has_permission(self, user):
        creds = ExchangeCredentials.objects.create(
            user=user,
            exchange_name="mexc",
            api_key="k",
            secret_key="s",
            permissions={"spot": True, "futures": False},
        )
        assert creds.has_permission("spot") is True
        assert creds.has_permission("futures") is False
        assert creds.has_permission("margin") is False

    def test_credentials_unique_together(self, user):
        ExchangeCredentials.objects.create(
            user=user, exchange_name="binance", api_key="k1", secret_key="s1"
        )
        with pytest.raises(Exception):
            ExchangeCredentials.objects.create(
                user=user, exchange_name="binance", api_key="k2", secret_key="s2"
            )

    def test_soft_delete(self, user):
        creds = ExchangeCredentials.objects.create(
            user=user, exchange_name="alpaca", api_key="k", secret_key="s"
        )
        creds.delete()
        assert creds.is_deleted is True
        assert creds.deleted_at is not None


@pytest.mark.django_db
class TestExchangeStatusModel:
    def test_create_status(self):
        status = ExchangeStatus.objects.create(
            exchange_name="binance",
            status="online",
            response_time_ms=120,
            error_message="",
        )
        assert status.exchange_name == "binance"
        assert status.status == "online"
        assert status.response_time_ms == 120
        assert str(status) == "binance - online"

    def test_status_defaults(self):
        status = ExchangeStatus.objects.create(exchange_name="bybit")
        assert status.status == "online"
        assert status.api_limits == {}

    def test_status_choices(self):
        for choice in ["online", "degraded", "offline", "maintenance"]:
            status = ExchangeStatus.objects.create(exchange_name="test", status=choice)
            assert status.status == choice

    def test_status_timestamps(self):
        status = ExchangeStatus.objects.create(exchange_name="binance")
        assert status.last_check is not None


@pytest.mark.django_db
class TestTradingPairModel:
    def test_create_trading_pair(self):
        pair = TradingPair.objects.create(
            exchange_name="binance",
            symbol="BTCUSDT",
            base_asset="BTC",
            quote_asset="USDT",
            is_active=True,
        )
        assert pair.exchange_name == "binance"
        assert pair.symbol == "BTCUSDT"
        assert pair.base_asset == "BTC"
        assert pair.quote_asset == "USDT"
        assert pair.is_active is True
        assert str(pair) == "BTCUSDT on binance"

    def test_trading_pair_defaults(self):
        pair = TradingPair.objects.create(
            exchange_name="bybit",
            symbol="ETHUSDT",
            base_asset="ETH",
            quote_asset="USDT",
        )
        assert Decimal(pair.min_order_size) == Decimal("0.00000001")
        assert pair.max_order_size == Decimal("1000000")
        assert pair.price_precision == 8
        assert pair.quantity_precision == 8
        assert pair.maker_fee == Decimal("0.0010")
        assert pair.taker_fee == Decimal("0.0010")
        assert pair.min_notional == Decimal("10.0")

    def test_trading_pair_unique(self):
        TradingPair.objects.create(
            exchange_name="binance",
            symbol="BTCUSDT",
            base_asset="BTC",
            quote_asset="USDT",
        )
        with pytest.raises(Exception):
            TradingPair.objects.create(
                exchange_name="binance",
                symbol="BTCUSDT",
                base_asset="BTC",
                quote_asset="USDT",
            )


@pytest.mark.django_db
class TestSupportedBlockchainModel:
    def test_create_blockchain(self):
        bc = SupportedBlockchain.objects.create(
            name="Binance Smart Chain",
            blockchain_code="BEP20",
            native_coin="BNB",
            explorer_url="https://bscscan.com",
            confirmation_blocks=15,
            transaction_fee_type="dynamic",
        )
        assert bc.name == "Binance Smart Chain"
        assert bc.blockchain_code == "BEP20"
        assert bc.native_coin == "BNB"
        assert bc.is_active is True
        assert str(bc) == "Binance Smart Chain (BEP20)"

    def test_blockchain_unique(self):
        SupportedBlockchain.objects.create(
            name="Ethereum",
            blockchain_code="ERC20",
            native_coin="ETH",
        )
        with pytest.raises(Exception):
            SupportedBlockchain.objects.create(
                name="Ethereum2",
                blockchain_code="ERC20",
                native_coin="ETH",
            )


@pytest.mark.django_db
class TestExchangeRateModel:
    def test_create_exchange_rate(self):
        rate = ExchangeRate.objects.create(
            from_currency="BTC",
            to_currency="USDT",
            rate=Decimal("50000.00000000"),
            exchange_name="binance",
            source="api",
        )
        assert rate.from_currency == "BTC"
        assert rate.to_currency == "USDT"
        assert rate.rate == Decimal("50000.00000000")
        assert str(rate) == "1 BTC = 50000.00000000 USDT"

    def test_rate_unique_together(self):
        ExchangeRate.objects.create(
            from_currency="BTC",
            to_currency="USDT",
            rate=Decimal("50000"),
            exchange_name="binance",
        )
        with pytest.raises(Exception):
            ExchangeRate.objects.create(
                from_currency="BTC",
                to_currency="USDT",
                rate=Decimal("51000"),
                exchange_name="binance",
            )
