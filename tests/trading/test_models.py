from decimal import Decimal

import pytest


@pytest.mark.django_db
class TestExchangeModel:
    def test_create_exchange(self, exchange):
        assert exchange.name == "binance"
        assert exchange.display_name == "Binance"
        assert exchange.is_active is True
        assert exchange.supports_testnet is True
        assert exchange.supported_features == ["spot", "futures"]
        assert exchange.rate_limit_per_minute == 1200
        assert str(exchange) == "Binance"

    def test_exchange_defaults(self, db):
        from apps.exchanges.models import Exchange

        ex = Exchange.objects.create(
            name="test_exchange",
            display_name="Test Exchange",
        )
        assert ex.is_active is True
        assert ex.supports_testnet is True
        assert ex.supported_features == []
        assert ex.rate_limit_per_minute == 1200
        assert ex.fee_rates == {}

    def test_exchange_indexes(self):
        from apps.exchanges.models import Exchange

        index_fields = [idx.fields for idx in Exchange._meta.indexes]
        assert ["name"] in index_fields
        assert ["is_active"] in index_fields


@pytest.mark.django_db
class TestExchangeStatusModel:
    def test_create_exchange_status(self, exchange_status):
        assert exchange_status.exchange_name == "binance"
        assert exchange_status.status == "online"
        assert exchange_status.response_time_ms == 120
        assert exchange_status.last_check is not None
        assert str(exchange_status) == "binance - online"

    def test_exchange_status_choices(self, db):
        from apps.investments.models import ExchangeStatus

        for status_val in ["online", "degraded", "offline", "maintenance"]:
            es = ExchangeStatus.objects.create(
                exchange_name="bybit",
                status=status_val,
            )
            assert es.status == status_val

    def test_exchange_status_defaults(self, db):
        from apps.investments.models import ExchangeStatus

        es = ExchangeStatus.objects.create(exchange_name="okx")
        assert es.status == "online"
        assert es.error_message == ""
        assert es.api_limits == {}

    def test_exchange_status_str(self, db):
        from apps.investments.models import ExchangeStatus

        es = ExchangeStatus.objects.create(
            exchange_name="bybit",
            status="offline",
        )
        assert str(es) == "bybit - offline"


@pytest.mark.django_db
class TestTradingPairModel:
    def test_create_trading_pair(self, trading_pair):
        assert trading_pair.symbol == "BTC/USDT"
        assert trading_pair.base_asset == "BTC"
        assert trading_pair.quote_asset == "USDT"
        assert trading_pair.is_active is True
        assert Decimal(trading_pair.min_order_size) == Decimal("0.00000001")
        assert trading_pair.price_precision == 8
        assert trading_pair.maker_fee == Decimal("0.0010")
        assert str(trading_pair) == "BTC/USDT on binance"

    def test_trading_pair_unique_together(self, db):
        from apps.exchanges.models import TradingPair

        TradingPair.objects.create(
            exchange_name="binance",
            symbol="ETH/USDT",
            base_asset="ETH",
            quote_asset="USDT",
        )
        with pytest.raises(Exception):
            TradingPair.objects.create(
                exchange_name="binance",
                symbol="ETH/USDT",
                base_asset="ETH",
                quote_asset="USDT",
            )

    def test_trading_pair_different_exchange_allowed(self, db):
        from apps.exchanges.models import TradingPair

        tp1 = TradingPair.objects.create(
            exchange_name="binance",
            symbol="BTC/USDT",
            base_asset="BTC",
            quote_asset="USDT",
        )
        tp2 = TradingPair.objects.create(
            exchange_name="bybit",
            symbol="BTC/USDT",
            base_asset="BTC",
            quote_asset="USDT",
        )
        assert tp1.id != tp2.id


@pytest.mark.django_db
class TestSupportedBlockchainModel:
    def test_create_blockchain(self, supported_blockchain):
        assert supported_blockchain.name == "Ethereum"
        assert supported_blockchain.blockchain_code == "ERC20"
        assert supported_blockchain.native_coin == "ETH"
        assert supported_blockchain.is_active is True
        assert supported_blockchain.confirmation_blocks == 12
        assert supported_blockchain.transaction_fee_type == "dynamic"
        assert str(supported_blockchain) == "Ethereum (ERC20)"

    def test_blockchain_choices(self, db):
        from apps.investments.models import SupportedBlockchain

        for code in ["BEP20", "ERC20", "TRC20", "SOL", "APTOS"]:
            blockchain = SupportedBlockchain.objects.create(
                name=f"{code} Chain",
                blockchain_code=code,
                native_coin="COIN",
            )
            assert blockchain.blockchain_code == code

    def test_blockchain_defaults(self, db):
        from apps.investments.models import SupportedBlockchain

        bc = SupportedBlockchain.objects.create(
            name="Test Chain",
            blockchain_code="SOL",
            native_coin="SOL",
        )
        assert bc.is_active is True
        assert bc.confirmation_blocks == 12
        assert bc.transaction_fee_type == "dynamic"
        assert bc.explorer_url == ""


@pytest.mark.django_db
class TestExchangeRateModel:
    def test_create_exchange_rate(self, exchange_rate):
        assert exchange_rate.from_currency == "BTC"
        assert exchange_rate.to_currency == "USDT"
        assert exchange_rate.rate == Decimal("45000.00")
        assert exchange_rate.exchange_name == "aggregated"
        assert exchange_rate.source == "api"
        assert str(exchange_rate) == "1 BTC = 45000.00 USDT"

    def test_exchange_rate_unique_together(self, db):
        from apps.investments.models import ExchangeRate

        ExchangeRate.objects.create(
            from_currency="ETH",
            to_currency="USDT",
            rate=Decimal("3000"),
            exchange_name="aggregated",
        )
        with pytest.raises(Exception):
            ExchangeRate.objects.create(
                from_currency="ETH",
                to_currency="USDT",
                rate=Decimal("3100"),
                exchange_name="aggregated",
            )

    def test_exchange_rate_different_exchange_allowed(self, db):
        from apps.investments.models import ExchangeRate

        r1 = ExchangeRate.objects.create(
            from_currency="BTC",
            to_currency="USDT",
            rate=Decimal("45000"),
            exchange_name="aggregated",
        )
        r2 = ExchangeRate.objects.create(
            from_currency="BTC",
            to_currency="USDT",
            rate=Decimal("45100"),
            exchange_name="binance",
        )
        assert r1.id != r2.id

    def test_exchange_rate_timestamp(self, db):
        from apps.investments.models import ExchangeRate

        rate = ExchangeRate.objects.create(
            from_currency="SOL",
            to_currency="USDT",
            rate=Decimal("150.00"),
        )
        assert rate.timestamp is not None


@pytest.mark.django_db
class TestStrategyConfigModel:
    def test_create_strategy_config(self, strategy_config):
        assert strategy_config.name == "Grid Conservative"
        assert strategy_config.strategy == "grid"
        assert strategy_config.default_parameters == {"max_levels": 10, "spacing": 1.0}
        assert strategy_config.is_active is True
        assert "Grid Trading" in str(strategy_config)

    def test_strategy_choices(self, db):
        from apps.trading.models import StrategyConfig

        for strategy_code in ["quantum_ai", "grid", "martingale", "signal"]:
            sc = StrategyConfig.objects.create(
                name=f"{strategy_code} Config",
                strategy=strategy_code,
            )
            assert sc.strategy == strategy_code

    def test_strategy_config_defaults(self, db):
        from apps.trading.models import StrategyConfig

        sc = StrategyConfig.objects.create(
            name="Default Config",
            strategy="grid",
        )
        assert sc.default_parameters == {}
        assert sc.is_active is True
        assert sc.description == ""

    def test_strategy_config_soft_delete(self, db):
        from apps.trading.models import StrategyConfig

        sc = StrategyConfig.objects.create(
            name="Deletable",
            strategy="grid",
        )
        assert sc.is_deleted is False
        sc.delete()
        sc.refresh_from_db()
        assert sc.is_deleted is True
        assert sc.deleted_at is not None
