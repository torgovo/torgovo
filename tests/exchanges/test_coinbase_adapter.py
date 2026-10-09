from unittest.mock import MagicMock, patch

import ccxt
import pytest

from apps.trading.exchanges.coinbase import CoinbaseAdapter

# ==============================================================================
# COINBASE TESTS
# ==============================================================================


@pytest.fixture
def mock_ccxt_coinbase():
    coinbase_class = ccxt.coinbase
    with patch("apps.trading.exchanges.coinbase.ccxt.coinbase") as mock_exchange_class:
        mock_exchange = MagicMock(spec=coinbase_class)
        mock_exchange.id = "coinbase"
        mock_exchange.options = {}
        mock_exchange.markets = {
            "BTC/USDT": {
                "limits": {"amount": {"min": 0.0001, "max": 1000}},
                "precision": {"amount": 4, "price": 2},
            },
        }
        mock_exchange.amount_to_precision = MagicMock(side_effect=lambda s, a: f"{a:.4f}")
        mock_exchange.price_to_precision = MagicMock(side_effect=lambda s, p: f"{p:.2f}")
        mock_exchange_class.return_value = mock_exchange
        yield mock_exchange_class


@pytest.fixture
def coinbase_adapter(mock_ccxt_coinbase):
    a = CoinbaseAdapter(
        credentials={"api_key": "ck", "secret_key": "csk", "passphrase": "cpass"},
        demo_mode=False,
    )
    a.exchange = mock_ccxt_coinbase.return_value
    return a


class TestCoinbaseAdapter:
    def test_exchange_name(self, coinbase_adapter):
        assert coinbase_adapter.exchange_name == "coinbase"

    def test_initialize_exchange_defaults(self, mock_ccxt_coinbase):
        CoinbaseAdapter(
            credentials={"api_key": "ak", "secret_key": "sk", "passphrase": "pass"},
            demo_mode=False,
        )
        config = mock_ccxt_coinbase.call_args[0][0]
        assert config["apiKey"] == "ak"
        assert config["secret"] == "sk"
        assert config["password"] == "pass"
        assert config["enableRateLimit"] is True

    def test_initialize_exchange_demo_mode(self, mock_ccxt_coinbase):
        mock_ccxt_coinbase.return_value.enable_demo_trading = MagicMock()
        a = CoinbaseAdapter(
            credentials={"api_key": "ak", "secret_key": "sk", "passphrase": "pass"},
            demo_mode=True,
        )
        a.exchange.enable_demo_trading.assert_called_once_with(True)

    def test_initialize_load_markets(self, mock_ccxt_coinbase):
        CoinbaseAdapter(
            credentials={"api_key": "ak", "secret_key": "sk", "passphrase": "pass"},
            demo_mode=False,
        )
        mock_ccxt_coinbase.return_value.load_markets.assert_called_once()

    def test_initialize_load_markets_failure(self, mock_ccxt_coinbase):
        mock_ccxt_coinbase.return_value.load_markets.side_effect = Exception("load fail")
        a = CoinbaseAdapter(
            credentials={"api_key": "ak", "secret_key": "sk", "passphrase": "pass"},
            demo_mode=False,
        )
        assert a.exchange is not None

    def test_str_repr(self, coinbase_adapter):
        assert str(coinbase_adapter) == "CoinbaseAdapter(demo=False)"
        assert repr(coinbase_adapter) == "CoinbaseAdapter(exchange=coinbase, demo=False)"

    def test_format_symbol_strips_futures_suffix(self, coinbase_adapter):
        assert coinbase_adapter.format_symbol("BTC/USDT:USDT") == "BTC/USDT"
        assert coinbase_adapter.format_symbol("BTC/USDT") == "BTC/USDT"


class TestCoinbaseLimitOrder:
    def test_create_limit_order_post_only(self, coinbase_adapter):
        coinbase_adapter._make_request = MagicMock(return_value={"id": "cb-1", "status": "open"})
        result = coinbase_adapter.create_limit_order("BTC/USDT", "buy", 1.0, 48000.0)
        assert result["id"] == "cb-1"
        args = coinbase_adapter._make_request.call_args[0]
        assert args[0] == "create_limit_order"
        assert args[1] == "BTC/USDT"
        assert args[2] == "buy"
        kwargs = coinbase_adapter._make_request.call_args[1]
        assert kwargs["params"]["post_only"] is True

    def test_create_limit_order_keeps_existing_params(self, coinbase_adapter):
        coinbase_adapter._make_request = MagicMock(return_value={"id": "cb-2"})
        coinbase_adapter.create_limit_order(
            "BTC/USDT", "sell", 1.0, 48000.0, params={"time_in_force": "GTC"}
        )
        kwargs = coinbase_adapter._make_request.call_args[1]
        assert kwargs["params"]["post_only"] is True
        assert kwargs["params"]["time_in_force"] == "GTC"


class TestCoinbaseStopLossOrder:
    def test_create_stop_loss_order(self, coinbase_adapter):
        coinbase_adapter.price_to_precision = MagicMock(return_value=48000.0)
        coinbase_adapter._make_request = MagicMock(return_value={"id": "cb-sl", "status": "open"})
        result = coinbase_adapter.create_stop_loss_order("BTC/USDT", "sell", 1.0, 48000.0)
        assert result["id"] == "cb-sl"
        args = coinbase_adapter._make_request.call_args[0]
        assert args[0] == "create_order"
        assert args[1] == "BTC/USDT"
        assert args[2] == "market"
        assert args[3] == "sell"
        assert args[4] == 1.0
        assert args[5] is None
        assert args[6] == {"stopPrice": 48000.0}

    def test_create_stop_loss_with_extra_params(self, coinbase_adapter):
        coinbase_adapter.price_to_precision = MagicMock(return_value=48000.0)
        coinbase_adapter._make_request = MagicMock(return_value={"id": "cb-sl2"})
        coinbase_adapter.create_stop_loss_order(
            "BTC/USDT", "sell", 1.0, 48000.0, params={"reduceOnly": True}
        )
        args = coinbase_adapter._make_request.call_args[0]
        assert args[6] == {"stopPrice": 48000.0, "reduceOnly": True}

    def test_create_stop_loss_formats_symbol(self, coinbase_adapter):
        coinbase_adapter.price_to_precision = MagicMock(return_value=48000.0)
        coinbase_adapter._make_request = MagicMock(return_value={})
        coinbase_adapter.create_stop_loss_order("BTC/USDT:USDT", "sell", 1.0, 48000.0)
        args = coinbase_adapter._make_request.call_args[0]
        assert args[1] == "BTC/USDT"


class TestCoinbaseTakeProfitOrder:
    def test_create_take_profit_order(self, coinbase_adapter):
        coinbase_adapter.price_to_precision = MagicMock(return_value=52000.0)
        coinbase_adapter._make_request = MagicMock(return_value={"id": "cb-tp", "status": "open"})
        result = coinbase_adapter.create_take_profit_order("BTC/USDT", "buy", 0.5, 52000.0)
        assert result["id"] == "cb-tp"
        args = coinbase_adapter._make_request.call_args[0]
        assert args[0] == "create_order"
        assert args[1] == "BTC/USDT"
        assert args[2] == "market"
        assert args[3] == "buy"
        assert args[5] is None
        assert args[6] == {"stopPrice": 52000.0}

    def test_create_take_profit_with_extra_params(self, coinbase_adapter):
        coinbase_adapter.price_to_precision = MagicMock(return_value=52000.0)
        coinbase_adapter._make_request = MagicMock(return_value={"id": "cb-tp2"})
        coinbase_adapter.create_take_profit_order(
            "BTC/USDT", "buy", 0.5, 52000.0, params={"reduceOnly": True}
        )
        args = coinbase_adapter._make_request.call_args[0]
        assert args[6] == {"stopPrice": 52000.0, "reduceOnly": True}


class TestCoinbasePositions:
    def test_fetch_positions_empty(self, coinbase_adapter):
        assert coinbase_adapter.fetch_positions("BTC/USDT") == []

    def test_close_position_long_sells(self, coinbase_adapter):
        coinbase_adapter.create_market_order = MagicMock(return_value={"id": "cb-close"})
        result = coinbase_adapter.close_position("BTC/USDT", "long", 1.0)
        assert result["id"] == "cb-close"
        coinbase_adapter.create_market_order.assert_called_once_with("BTC/USDT", "sell", 1.0)

    def test_close_position_short_buys(self, coinbase_adapter):
        coinbase_adapter.create_market_order = MagicMock(return_value={"id": "cb-close"})
        result = coinbase_adapter.close_position("BTC/USDT", "short", 1.0)
        assert result["id"] == "cb-close"
        coinbase_adapter.create_market_order.assert_called_once_with("BTC/USDT", "buy", 1.0)
