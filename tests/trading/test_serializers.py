import pytest


@pytest.mark.django_db
class TestExchangeSerializer:
    def test_exchange_serializer_fields(self, exchange):
        from apps.trading.serializers import ExchangeSerializer

        serializer = ExchangeSerializer(instance=exchange)
        expected = {
            "id",
            "name",
            "display_name",
            "api_base_url",
            "websocket_url",
            "is_active",
            "supports_testnet",
            "supported_features",
            "rate_limit_per_minute",
            "fee_rates",
            "created_at",
            "updated_at",
        }
        assert set(serializer.data.keys()) == expected
        assert serializer.data["name"] == "binance"
        assert serializer.data["is_active"] is True

    def test_exchange_serializer_read_only(self):
        from apps.trading.serializers import ExchangeSerializer

        serializer = ExchangeSerializer()
        read_only = {"id", "created_at", "updated_at"}
        for field in read_only:
            assert serializer.get_fields()[field].read_only is True


@pytest.mark.django_db
class TestExchangeCredentialsSerializer:
    def test_credentials_serializer_fields(self, exchange_credentials):
        from apps.trading.serializers import ExchangeCredentialsSerializer

        serializer = ExchangeCredentialsSerializer(instance=exchange_credentials)
        assert "api_key_display" in serializer.data
        assert "secret_key_display" in serializer.data
        assert serializer.data["api_key_display"] == "****"
        assert serializer.data["secret_key_display"] == "****"
        assert "user_email" in serializer.data
        assert "exchange_name" in serializer.data

    def test_credentials_create_serializer_valid(self):
        from apps.trading.serializers import ExchangeCredentialsCreateSerializer

        data = {
            "exchange_name": "binance",
            "api_key": "my-api-key",
            "secret_key": "my-secret-key",
            "is_testnet": True,
        }
        serializer = ExchangeCredentialsCreateSerializer(data=data)
        assert serializer.is_valid(), serializer.errors
        assert serializer.validated_data["exchange_name"] == "binance"


@pytest.mark.django_db
class TestTradingPairSerializer:
    def test_trading_pair_serializer_fields(self, trading_pair):
        from apps.trading.serializers import TradingPairSerializer

        serializer = TradingPairSerializer(instance=trading_pair)
        expected = {
            "id",
            "exchange_name",
            "symbol",
            "base_asset",
            "quote_asset",
            "is_active",
            "min_order_size",
            "max_order_size",
            "price_precision",
            "quantity_precision",
            "maker_fee",
            "taker_fee",
            "min_notional",
            "created_at",
            "updated_at",
        }
        assert set(serializer.data.keys()) == expected
        assert serializer.data["symbol"] == "BTC/USDT"

    def test_trading_pair_serializer_read_only(self):
        from apps.trading.serializers import TradingPairSerializer

        serializer = TradingPairSerializer()
        read_only = {"id", "created_at", "updated_at"}
        for field in read_only:
            assert serializer.get_fields()[field].read_only is True


@pytest.mark.django_db
class TestExchangeStatusSerializer:
    def test_status_serializer_fields(self, exchange_status):
        from apps.trading.serializers import ExchangeStatusSerializer

        serializer = ExchangeStatusSerializer(instance=exchange_status)
        assert "exchange_name" in serializer.data
        assert "status" in serializer.data
        assert "response_time_ms" in serializer.data
        assert serializer.data["status"] == "online"

    def test_status_serializer_read_only(self):
        from apps.trading.serializers import ExchangeStatusSerializer

        serializer = ExchangeStatusSerializer()
        read_only = {"id", "created_at", "updated_at"}
        for field in read_only:
            assert serializer.get_fields()[field].read_only is True


@pytest.mark.django_db
class TestSupportedBlockchainSerializer:
    def test_blockchain_serializer_fields(self, supported_blockchain):
        from apps.trading.serializers import SupportedBlockchainSerializer

        serializer = SupportedBlockchainSerializer(instance=supported_blockchain)
        assert serializer.data["name"] == "Ethereum"
        assert serializer.data["blockchain_code"] == "ERC20"
        assert "explorer_url" in serializer.data

    def test_blockchain_serializer_read_only(self):
        from apps.trading.serializers import SupportedBlockchainSerializer

        serializer = SupportedBlockchainSerializer()
        read_only = {"id", "created_at", "updated_at"}
        for field in read_only:
            assert serializer.get_fields()[field].read_only is True


@pytest.mark.django_db
class TestExchangeRateSerializer:
    def test_rate_serializer_fields(self, exchange_rate):
        from apps.trading.serializers import ExchangeRateSerializer

        serializer = ExchangeRateSerializer(instance=exchange_rate)
        assert serializer.data["from_currency"] == "BTC"
        assert serializer.data["to_currency"] == "USDT"
        assert serializer.data["rate"] == "45000.00000000"
        assert "timestamp" in serializer.data

    def test_rate_serializer_read_only(self):
        from apps.trading.serializers import ExchangeRateSerializer

        serializer = ExchangeRateSerializer()
        read_only = {"id", "timestamp", "created_at", "updated_at"}
        for field in read_only:
            assert serializer.get_fields()[field].read_only is True


@pytest.mark.django_db
class TestStrategyConfigSerializer:
    def test_strategy_config_serializer_fields(self, strategy_config):
        from apps.trading.serializers import StrategyConfigSerializer

        serializer = StrategyConfigSerializer(instance=strategy_config)
        assert serializer.data["name"] == "Grid Conservative"
        assert serializer.data["strategy"] == "grid"
        assert "strategy_display" in serializer.data
        assert serializer.data["strategy_display"] == "Grid Trading"

    def test_strategy_config_read_only(self):
        from apps.trading.serializers import StrategyConfigSerializer

        serializer = StrategyConfigSerializer()
        read_only = {"id", "created_at", "updated_at"}
        for field in read_only:
            assert serializer.get_fields()[field].read_only is True
