import time
from unittest.mock import MagicMock, patch

import ccxt
import pytest

from apps.trading.exchanges.base_adapter import BaseAdapter


class _ConcreteAdapter(BaseAdapter):
    """Concrete implementation of BaseAdapter for testing."""

    @property
    def exchange_name(self) -> str:
        return "test_exchange"

    def _initialize_exchange(self) -> ccxt.Exchange:
        exchange = MagicMock(spec=ccxt.Exchange)
        exchange.id = "test_exchange"
        exchange.markets = {
            "BTC/USDT": {
                "limits": {
                    "amount": {"min": 0.001, "max": 1000},
                    "price": {"min": 0.01, "max": 1000000},
                },
                "precision": {"amount": 4, "price": 2},
            }
        }
        exchange.amount_to_precision = MagicMock(side_effect=lambda s, a: f"{a:.4f}")
        exchange.price_to_precision = MagicMock(side_effect=lambda s, p: f"{p:.2f}")
        return exchange


@pytest.fixture
def adapter():
    with patch.object(_ConcreteAdapter, "_initialize_exchange"):
        a = _ConcreteAdapter(credentials={"api_key": "test", "secret_key": "test"})
        a.exchange = MagicMock(spec=ccxt.Exchange)
        a.exchange.id = "test_exchange"
        a.exchange.markets = {
            "BTC/USDT": {
                "limits": {
                    "amount": {"min": 0.001, "max": 1000},
                    "price": {"min": 0.01, "max": 1000000},
                },
                "precision": {"amount": 4, "price": 2},
            }
        }
        a.exchange.amount_to_precision = MagicMock(side_effect=lambda s, a: f"{a:.4f}")
        a.exchange.price_to_precision = MagicMock(side_effect=lambda s, p: f"{p:.2f}")
        return a


class TestBaseAdapterInstantiation:
    def test_abstract_class_cannot_instantiate(self):
        with pytest.raises(TypeError):
            BaseAdapter(credentials={"api_key": "x", "secret_key": "y"})

    def test_concrete_adapter_instantiation(self):
        a = _ConcreteAdapter(credentials={"api_key": "test", "secret_key": "test"})
        assert a.credentials == {"api_key": "test", "secret_key": "test"}
        assert a.demo_mode is False
        assert a.rate_limit_delay == 0.05
        assert a.max_retries == 3
        assert a.retry_delay == 1
        assert a.request_count == 0
        assert a.last_request_time == 0

    def test_demo_mode_flag(self):
        a = _ConcreteAdapter(credentials={"api_key": "test", "secret_key": "test"}, demo_mode=True)
        assert a.demo_mode is True

    def test_abstract_methods_raise_not_implemented(self):
        class IncompleteAdapter(BaseAdapter):
            pass

        with pytest.raises(TypeError):
            IncompleteAdapter(credentials={"api_key": "x", "secret_key": "y"})

    def test_string_representations(self, adapter):
        assert str(adapter) == "_ConcreteAdapter(demo=False)"
        assert repr(adapter) == "_ConcreteAdapter(exchange=test_exchange, demo=False)"


class TestRateLimit:
    def test_rate_limit_enforces_delay(self, adapter):
        adapter.last_request_time = time.time()
        adapter.rate_limit_delay = 0.1
        start = time.time()
        adapter._rate_limit()
        elapsed = time.time() - start
        assert elapsed >= 0.08

    def test_rate_limit_no_delay_when_enough_time(self, adapter):
        adapter.last_request_time = time.time() - 10
        adapter.rate_limit_delay = 0.05
        start = time.time()
        adapter._rate_limit()
        elapsed = time.time() - start
        assert elapsed < 0.03

    def test_rate_limit_updates_last_request_time(self, adapter):
        adapter.last_request_time = 0
        adapter._rate_limit()
        assert adapter.last_request_time > 0


class TestMakeRequest:
    def test_successful_request(self, adapter):
        adapter.exchange.fetch_ticker = MagicMock(return_value={"last": 50000})
        result = adapter._make_request("fetch_ticker", "BTC/USDT")
        assert result == {"last": 50000}
        assert adapter.request_count == 1

    def test_network_error_retry_success(self, adapter):
        adapter.max_retries = 3
        adapter.retry_delay = 0.01
        mock = MagicMock()
        mock.side_effect = [ccxt.NetworkError("timeout"), {"last": 50000}]
        adapter.exchange.fetch_ticker = mock
        with patch("time.sleep"):
            result = adapter._make_request("fetch_ticker", "BTC/USDT")
        assert result == {"last": 50000}
        assert mock.call_count == 2

    def test_network_error_all_retries_fail(self, adapter):
        adapter.max_retries = 3
        adapter.retry_delay = 0.01
        adapter.exchange.fetch_ticker = MagicMock(side_effect=ccxt.NetworkError("timeout"))
        with patch("time.sleep"):
            with pytest.raises(ccxt.NetworkError):
                adapter._make_request("fetch_ticker", "BTC/USDT")
        assert adapter.exchange.fetch_ticker.call_count == 3

    def test_authentication_error_no_retry(self, adapter):
        adapter.max_retries = 3
        adapter.exchange.fetch_balance = MagicMock(side_effect=ccxt.AuthenticationError("bad key"))
        with pytest.raises(ccxt.AuthenticationError):
            adapter._make_request("fetch_balance")
        assert adapter.exchange.fetch_balance.call_count == 1

    def test_rate_limit_exceeded_retry(self, adapter):
        adapter.max_retries = 3
        adapter.retry_delay = 0.01
        mock = MagicMock()
        mock.side_effect = [ccxt.RateLimitExceeded("slow down"), {"last": 50000}]
        adapter.exchange.fetch_ticker = mock
        with patch("time.sleep"):
            result = adapter._make_request("fetch_ticker", "BTC/USDT")
        assert result == {"last": 50000}
        assert mock.call_count == 2

    def test_rate_limit_exceeded_all_fail(self, adapter):
        adapter.max_retries = 3
        adapter.retry_delay = 0.01
        adapter.exchange.fetch_ticker = MagicMock(side_effect=ccxt.RateLimitExceeded("slow down"))
        with patch("time.sleep"):
            with pytest.raises(ccxt.RateLimitExceeded):
                adapter._make_request("fetch_ticker", "BTC/USDT")

    def test_exchange_error_retry(self, adapter):
        adapter.max_retries = 3
        adapter.retry_delay = 0.01
        mock = MagicMock()
        mock.side_effect = [ccxt.ExchangeError("order failed"), {"id": "123"}]
        adapter.exchange.create_limit_order = mock
        with patch("time.sleep"):
            result = adapter._make_request("create_limit_order", "BTC/USDT", "buy", 1, 50000)
        assert result == {"id": "123"}

    def test_generic_exception_not_caught(self, adapter):
        adapter.exchange.fetch_ticker = MagicMock(side_effect=ValueError("unexpected"))
        with pytest.raises(ValueError):
            adapter._make_request("fetch_ticker", "BTC/USDT")

    def test_request_count_increments(self, adapter):
        adapter.exchange.fetch_ticker = MagicMock(return_value={"last": 1})
        adapter._make_request("fetch_ticker", "BTC/USDT")
        adapter._make_request("fetch_ticker", "BTC/USDT")
        adapter._make_request("fetch_ticker", "BTC/USDT")
        assert adapter.request_count == 3


class TestAmountToPrecision:
    def test_uses_exchange_method(self, adapter):
        result = adapter.amount_to_precision("BTC/USDT", 0.12345)
        assert result == 0.1235  # rounded to 4 decimal places

    def test_fallback_on_error(self, adapter):
        adapter.exchange.amount_to_precision = MagicMock(side_effect=Exception("fail"))
        result = adapter.amount_to_precision("BTC/USDT", 0.12345)
        assert result == 0.12345

    def test_calls_format_symbol(self, adapter):
        adapter.format_symbol = MagicMock(return_value="BTC/USDT")
        adapter.exchange.amount_to_precision = MagicMock(return_value="0.1234")
        adapter.amount_to_precision("BTC/USDT", 0.12345)
        adapter.format_symbol.assert_called_once_with("BTC/USDT")
        adapter.exchange.amount_to_precision.assert_called_once_with("BTC/USDT", 0.12345)


class TestPriceToPrecision:
    def test_uses_exchange_method(self, adapter):
        result = adapter.price_to_precision("BTC/USDT", 50000.123)
        assert result == 50000.12  # rounded to 2 decimal places

    def test_fallback_on_error(self, adapter):
        adapter.exchange.price_to_precision = MagicMock(side_effect=Exception("fail"))
        result = adapter.price_to_precision("BTC/USDT", 50000.123)
        assert result == 50000.123


class TestFormatSymbol:
    def test_default_returns_same(self, adapter):
        assert adapter.format_symbol("BTC/USDT") == "BTC/USDT"

    def test_subclass_can_override(self, adapter):
        adapter.format_symbol = MagicMock(return_value="BTCUSD")
        assert adapter.format_symbol("BTC/USDT") == "BTCUSD"


class TestFetchTicker:
    def test_returns_normalized_ticker(self, adapter):
        raw_ticker = {
            "symbol": "BTC/USDT",
            "last": 50000.0,
            "bid": 49900.0,
            "ask": 50100.0,
            "high": 51000.0,
            "low": 49000.0,
            "baseVolume": 1000.0,
            "quoteVolume": 50000000.0,
            "change": 200.0,
            "percentage": 0.4,
            "timestamp": 1234567890000,
        }
        adapter.exchange.fetch_ticker = MagicMock(return_value=raw_ticker)
        result = adapter.fetch_ticker("BTC/USDT")
        assert result["symbol"] == "BTC/USDT"
        assert result["last"] == 50000.0
        assert result["bid"] == 49900.0
        assert result["ask"] == 50100.0
        assert result["high"] == 51000.0
        assert result["low"] == 49000.0
        assert result["volume"] == 1000.0
        assert result["quote_volume"] == 50000000.0
        assert result["change_24h"] == 200.0
        assert result["percentage_24h"] == 0.4
        assert result["timestamp"] == 1234567890000

    def test_get_current_price(self, adapter):
        adapter.exchange.fetch_ticker = MagicMock(return_value={"last": 50000.0})
        assert adapter.get_current_price("BTC/USDT") == 50000.0


class TestFetchOHLCV:
    def test_returns_normalized_ohlcv(self, adapter):
        raw_ohlcv = [
            [1234567800000, 40000, 41000, 39000, 40500, 1000],
            [1234567880000, 40500, 41500, 39500, 41000, 1500],
        ]
        adapter.exchange.fetch_ohlcv = MagicMock(return_value=raw_ohlcv)
        result = adapter.fetch_ohlcv("BTC/USDT", "1h", 2)
        assert len(result) == 2
        assert result[0]["timestamp"] == 1234567800000
        assert result[0]["open"] == 40000.0
        assert result[0]["high"] == 41000.0
        assert result[0]["low"] == 39000.0
        assert result[0]["close"] == 40500.0
        assert result[0]["volume"] == 1000.0
        assert result[1]["timestamp"] == 1234567880000
        assert result[1]["close"] == 41000.0

    def test_calls_format_symbol(self, adapter):
        adapter.format_symbol = MagicMock(return_value="BTC/USDT")
        adapter.exchange.fetch_ohlcv = MagicMock(return_value=[])
        adapter.fetch_ohlcv("BTC/USDT", "1h", 10)
        adapter.format_symbol.assert_called_once_with("BTC/USDT")

    def test_passes_correct_args(self, adapter):
        adapter.exchange.fetch_ohlcv = MagicMock(return_value=[])
        adapter.fetch_ohlcv("BTC/USDT", "5m", 50)
        adapter.exchange.fetch_ohlcv.assert_called_once_with("BTC/USDT", "5m", limit=50)


class TestFetchOrderBook:
    def test_returns_standardized_orderbook(self, adapter):
        raw_book = {
            "bids": [[50000, 1.0], [49900, 2.0], [49800, 3.0], [49700, 4.0]],
            "asks": [[50100, 1.5], [50200, 2.5], [50300, 3.5], [50400, 4.5]],
            "timestamp": 1234567890000,
        }
        adapter.exchange.fetch_order_book = MagicMock(return_value=raw_book)
        result = adapter.fetch_order_book("BTC/USDT", 3)
        assert result["symbol"] == "BTC/USDT"
        assert len(result["bids"]) == 3
        assert len(result["asks"]) == 3
        assert result["bids"][0] == [50000, 1.0]
        assert result["asks"][0] == [50100, 1.5]
        assert result["timestamp"] == 1234567890000

    def test_calls_format_symbol(self, adapter):
        adapter.format_symbol = MagicMock(return_value="BTC/USDT")
        adapter.exchange.fetch_order_book = MagicMock(return_value={"bids": [], "asks": []})
        adapter.fetch_order_book("BTC/USDT", 10)
        adapter.format_symbol.assert_called_once_with("BTC/USDT")


class TestFetchBalance:
    def test_returns_standardized_balance(self, adapter):
        raw_balance = {
            "total": {"USDT": 10000, "BTC": 0.5},
            "free": {"USDT": 8000, "BTC": 0.3},
            "used": {"USDT": 2000, "BTC": 0.2},
        }
        adapter.exchange.fetch_balance = MagicMock(return_value=raw_balance)
        result = adapter.fetch_balance()
        assert result["total"] == {"USDT": 10000, "BTC": 0.5}
        assert result["free"] == {"USDT": 8000, "BTC": 0.3}
        assert result["used"] == {"USDT": 2000, "BTC": 0.2}
        assert "timestamp" in result


class TestGetAccountInfo:
    def test_returns_account_info_with_balance(self, adapter):
        adapter.exchange.fetch_balance = MagicMock(
            return_value={
                "total": {"USDT": 10000},
                "free": {"USDT": 8000},
                "used": {"USDT": 2000},
            }
        )
        result = adapter.get_account_info()
        assert result["exchange"] == "test_exchange"
        assert result["demo_mode"] is False
        assert result["balance"]["total"] == {"USDT": 10000}


class TestCreateLimitOrder:
    def test_creates_limit_order_successfully(self, adapter):
        raw_order = {
            "id": "order123",
            "clientOrderId": "client123",
            "symbol": "BTC/USDT",
            "side": "buy",
            "type": "limit",
            "amount": 1.0,
            "price": 50000.0,
            "filled": 0.0,
            "remaining": 1.0,
            "cost": 0.0,
            "status": "open",
            "timestamp": 1234567890000,
            "fee": {"cost": 0, "currency": "USDT"},
        }
        adapter.exchange.create_limit_order = MagicMock(return_value=raw_order)
        adapter.amount_to_precision = MagicMock(return_value=1.0)
        adapter.price_to_precision = MagicMock(return_value=50000.0)
        result = adapter.create_limit_order("BTC/USDT", "buy", 1.0, 50000.0)
        assert result["id"] == "order123"
        assert result["side"] == "buy"
        assert result["type"] == "limit"
        assert result["price"] == 50000.0
        adapter.exchange.create_limit_order.assert_called_once_with(
            "BTC/USDT", "buy", 1.0, 50000.0, params={}
        )

    def test_passes_params(self, adapter):
        raw_order = {
            "id": "o1",
            "symbol": "BTC/USDT",
            "side": "buy",
            "type": "limit",
            "amount": 1.0,
            "price": 50000.0,
            "filled": 0.0,
            "remaining": 1.0,
            "cost": 0.0,
            "status": "open",
            "timestamp": 0,
            "fee": {},
        }
        adapter.exchange.create_limit_order = MagicMock(return_value=raw_order)
        adapter.amount_to_precision = MagicMock(return_value=1.0)
        adapter.price_to_precision = MagicMock(return_value=50000.0)
        adapter.create_limit_order("BTC/USDT", "buy", 1.0, 50000.0, params={"timeInForce": "GTC"})
        call_kwargs = adapter.exchange.create_limit_order.call_args
        assert call_kwargs[0][0] == "BTC/USDT"
        assert call_kwargs[1]["params"]["timeInForce"] == "GTC"


class TestCreateMarketOrder:
    def test_creates_market_order_successfully(self, adapter):
        raw_order = {
            "id": "order456",
            "clientOrderId": "client456",
            "symbol": "BTC/USDT",
            "side": "sell",
            "type": "market",
            "amount": 0.5,
            "price": None,
            "filled": 0.5,
            "remaining": 0.0,
            "cost": 25000.0,
            "status": "closed",
            "timestamp": 1234567890000,
            "fee": {"cost": 10, "currency": "USDT"},
        }
        adapter.exchange.create_market_order = MagicMock(return_value=raw_order)
        adapter.amount_to_precision = MagicMock(return_value=0.5)
        result = adapter.create_market_order("BTC/USDT", "sell", 0.5)
        assert result["id"] == "order456"
        assert result["side"] == "sell"
        assert result["type"] == "market"
        assert result["filled"] == 0.5
        assert result["status"] == "closed"

    def test_uppercase_side_lowered(self, adapter):
        raw_order = {
            "id": "o1",
            "symbol": "BTC/USDT",
            "side": "buy",
            "type": "market",
            "amount": 1.0,
            "filled": 0.0,
            "remaining": 1.0,
            "cost": 0.0,
            "status": "open",
            "timestamp": 0,
            "fee": {},
        }
        adapter.exchange.create_market_order = MagicMock(return_value=raw_order)
        adapter.amount_to_precision = MagicMock(return_value=1.0)
        adapter.create_market_order("BTC/USDT", "BUY", 1.0)
        args = adapter.exchange.create_market_order.call_args[0]
        assert args[1] == "buy"


class TestNormalizeOrder:
    def test_normalize_order_all_fields(self, adapter):
        raw = {
            "id": "oid1",
            "clientOrderId": "coid1",
            "symbol": "BTC/USDT",
            "side": "buy",
            "type": "limit",
            "amount": 1.5,
            "price": 50000.0,
            "filled": 0.5,
            "remaining": 1.0,
            "cost": 25000.0,
            "status": "partially_filled",
            "timestamp": 1234567890000,
            "fee": {"cost": 5.0, "currency": "USDT"},
        }
        result = adapter._normalize_order(raw)
        assert result["id"] == "oid1"
        assert result["price"] == 50000.0
        assert result["filled"] == 0.5

    def test_normalize_order_missing_price(self, adapter):
        raw = {
            "id": "oid1",
            "amount": 1.0,
            "filled": 0.0,
            "remaining": 1.0,
            "cost": 0.0,
            "status": "open",
            "timestamp": 0,
            "fee": {},
        }
        result = adapter._normalize_order(raw)
        assert result["price"] is None


class TestFetchOrder:
    def test_fetches_and_normalizes(self, adapter):
        raw_order = {
            "id": "o1",
            "symbol": "BTC/USDT",
            "side": "buy",
            "type": "market",
            "amount": 1.0,
            "filled": 1.0,
            "remaining": 0.0,
            "cost": 50000.0,
            "status": "closed",
            "timestamp": 0,
            "fee": {},
        }
        adapter.exchange.fetch_order = MagicMock(return_value=raw_order)
        result = adapter.fetch_order("o1", "BTC/USDT")
        assert result["id"] == "o1"
        assert result["status"] == "closed"
        adapter.exchange.fetch_order.assert_called_once_with("o1", "BTC/USDT")

    def test_calls_format_symbol(self, adapter):
        adapter.format_symbol = MagicMock(return_value="BTC/USDT")
        adapter.exchange.fetch_order = MagicMock(
            return_value={
                "id": "o1",
                "amount": 1.0,
                "filled": 0.0,
                "remaining": 1.0,
                "cost": 0.0,
                "status": "open",
                "timestamp": 0,
                "fee": {},
            }
        )
        adapter.fetch_order("o1", "BTC/USDT")
        adapter.format_symbol.assert_called_once_with("BTC/USDT")


class TestFetchOpenOrders:
    def test_fetch_all_open_orders(self, adapter):
        raw_orders = [
            {
                "id": "o1",
                "symbol": "BTC/USDT",
                "side": "buy",
                "type": "limit",
                "amount": 1.0,
                "filled": 0.0,
                "remaining": 1.0,
                "cost": 0.0,
                "status": "open",
                "timestamp": 0,
                "fee": {},
            },
            {
                "id": "o2",
                "symbol": "BTC/USDT",
                "side": "sell",
                "type": "limit",
                "amount": 1.0,
                "filled": 0.0,
                "remaining": 1.0,
                "cost": 0.0,
                "status": "open",
                "timestamp": 0,
                "fee": {},
            },
        ]
        adapter.exchange.fetch_open_orders = MagicMock(return_value=raw_orders)
        result = adapter.fetch_open_orders()
        assert len(result) == 2
        assert result[0]["id"] == "o1"
        assert result[1]["id"] == "o2"

    def test_fetch_open_orders_by_symbol(self, adapter):
        adapter.exchange.fetch_open_orders = MagicMock(return_value=[])
        adapter.format_symbol = MagicMock(return_value="BTC/USDT")
        adapter.fetch_open_orders("BTC/USDT")
        adapter.exchange.fetch_open_orders.assert_called_once_with("BTC/USDT")


class TestCancelOrder:
    def test_cancel_order_returns_standardized(self, adapter):
        adapter.exchange.cancel_order = MagicMock(return_value={"result": True})
        adapter.format_symbol = MagicMock(return_value="BTC/USDT")
        result = adapter.cancel_order("o1", "BTC/USDT")
        assert result["id"] == "o1"
        assert result["symbol"] == "BTC/USDT"
        assert result["cancelled"] is True
        assert result["info"] == {"result": True}


class TestCancelAllOrders:
    def test_cancel_all_uses_exchange_method(self, adapter):
        adapter.exchange.cancel_all_orders = MagicMock(return_value=[{"id": "o1"}])
        adapter.format_symbol = MagicMock(return_value="BTC/USDT")
        result = adapter.cancel_all_orders("BTC/USDT")
        assert result == [{"id": "o1"}]

    def test_cancel_all_fallback_individual(self, adapter):
        adapter.exchange.cancel_all_orders = MagicMock(side_effect=Exception("not supported"))
        adapter.format_symbol = MagicMock(return_value="BTC/USDT")

        raw_orders = [
            {
                "id": "o1",
                "symbol": "BTC/USDT",
                "side": "buy",
                "type": "limit",
                "amount": 1.0,
                "filled": 0.0,
                "remaining": 1.0,
                "cost": 0.0,
                "status": "open",
                "timestamp": 0,
                "fee": {},
            },
            {
                "id": "o2",
                "symbol": "BTC/USDT",
                "side": "sell",
                "type": "limit",
                "amount": 1.0,
                "filled": 0.0,
                "remaining": 1.0,
                "cost": 0.0,
                "status": "open",
                "timestamp": 0,
                "fee": {},
            },
        ]
        adapter.exchange.fetch_open_orders = MagicMock(return_value=raw_orders)
        adapter.exchange.cancel_order = MagicMock()

        with patch.object(adapter, "cancel_order", wraps=adapter.cancel_order) as spy:
            result = adapter.cancel_all_orders("BTC/USDT")

        assert len(result) == 2
        assert spy.call_count == 2


class TestFetchMyTrades:
    def test_fetch_my_trades(self, adapter):
        raw_trades = [
            {
                "id": "t1",
                "symbol": "BTC/USDT",
                "side": "buy",
                "amount": 1.0,
                "price": 50000.0,
                "cost": 50000.0,
                "fee": {"cost": 10.0, "currency": "USDT"},
                "timestamp": 1234567890000,
            },
        ]
        adapter.exchange.fetch_my_trades = MagicMock(return_value=raw_trades)
        result = adapter._make_request("fetch_my_trades", "BTC/USDT")
        assert len(result) == 1
        assert result[0]["id"] == "t1"


class TestFetchPositions:
    def test_fetch_positions_filters_zero_contracts(self, adapter):
        raw_positions = [
            {
                "symbol": "BTC/USDT",
                "side": "long",
                "contracts": 1.0,
                "entryPrice": 50000,
                "markPrice": 51000,
                "unrealizedPnl": 1000,
                "leverage": 10,
                "liquidationPrice": 45000,
                "margin": 5000,
            },
            {
                "symbol": "ETH/USDT",
                "side": "long",
                "contracts": 0.0,
                "entryPrice": 3000,
                "markPrice": 3100,
                "unrealizedPnl": 0,
                "leverage": 5,
                "liquidationPrice": None,
                "margin": 0,
            },
        ]
        adapter.exchange.fetch_positions = MagicMock(return_value=raw_positions)
        adapter.format_symbol = MagicMock(return_value="BTC/USDT")
        result = adapter.fetch_positions("BTC/USDT")
        assert len(result) == 1
        assert result[0]["symbol"] == "BTC/USDT"
        assert result[0]["contracts"] == 1.0

    def test_fetch_positions_all(self, adapter):
        raw_positions = [
            {
                "symbol": "BTC/USDT",
                "side": "long",
                "contracts": 1.0,
                "entryPrice": 50000,
                "markPrice": 51000,
                "unrealizedPnl": 1000,
                "leverage": 10,
                "liquidationPrice": 45000,
                "margin": 5000,
            },
        ]
        adapter.exchange.fetch_positions = MagicMock(return_value=raw_positions)
        result = adapter.fetch_positions()
        assert len(result) == 1
        adapter.exchange.fetch_positions.assert_called_once_with()

    def test_normalize_position(self, adapter):
        raw = {
            "symbol": "BTC/USDT",
            "side": "long",
            "contracts": 2.5,
            "entryPrice": 50000,
            "markPrice": 51000,
            "unrealizedPnl": 2500,
            "leverage": 10,
            "liquidationPrice": 45000,
            "margin": 5000,
        }
        result = adapter._normalize_position(raw)
        assert result["symbol"] == "BTC/USDT"
        assert result["side"] == "long"
        assert result["contracts"] == 2.5
        assert result["leverage"] == 10
        assert result["liquidation_price"] == 45000.0

    def test_normalize_position_none_liquidation(self, adapter):
        raw = {
            "symbol": "ETH/USDT",
            "side": "short",
            "contracts": 5.0,
            "entryPrice": 3000,
            "markPrice": 2900,
            "unrealizedPnl": 500,
            "leverage": 5,
            "liquidationPrice": None,
            "margin": 3000,
        }
        result = adapter._normalize_position(raw)
        assert result["liquidation_price"] is None


class TestClosePosition:
    def test_close_long_position_sells(self, adapter):
        adapter.exchange.create_market_order = MagicMock(
            return_value={
                "id": "close1",
                "symbol": "BTC/USDT",
                "side": "sell",
                "type": "market",
                "amount": 1.0,
                "filled": 1.0,
                "remaining": 0.0,
                "cost": 50000.0,
                "status": "closed",
                "timestamp": 0,
                "fee": {},
            }
        )
        adapter.amount_to_precision = MagicMock(return_value=1.0)
        result = adapter.close_position("BTC/USDT", "long", 1.0)
        assert result["side"] == "sell"
        adapter.exchange.create_market_order.assert_called_once()
        call_kwargs = adapter.exchange.create_market_order.call_args[1]
        assert call_kwargs["params"] == {"reduceOnly": True}

    def test_close_short_position_buys(self, adapter):
        adapter.exchange.create_market_order = MagicMock(
            return_value={
                "id": "close2",
                "symbol": "BTC/USDT",
                "side": "buy",
                "type": "market",
                "amount": 1.0,
                "filled": 1.0,
                "remaining": 0.0,
                "cost": 49000.0,
                "status": "closed",
                "timestamp": 0,
                "fee": {},
            }
        )
        adapter.amount_to_precision = MagicMock(return_value=1.0)
        result = adapter.close_position("BTC/USDT", "short", 1.0)
        assert result["side"] == "buy"


class TestOrderStatusChecks:
    def test_is_order_filled_closed(self, adapter):
        assert adapter.is_order_filled({"status": "closed"}) is True

    def test_is_order_filled_filled(self, adapter):
        assert adapter.is_order_filled({"status": "filled"}) is True

    def test_is_order_filled_not_filled(self, adapter):
        assert adapter.is_order_filled({"status": "open"}) is False
        assert adapter.is_order_filled({"status": "cancelled"}) is False

    def test_is_order_open_open(self, adapter):
        assert adapter.is_order_open({"status": "open"}) is True

    def test_is_order_open_new(self, adapter):
        assert adapter.is_order_open({"status": "new"}) is True

    def test_is_order_open_partially_filled(self, adapter):
        assert adapter.is_order_open({"status": "partially_filled"}) is True

    def test_is_order_open_closed(self, adapter):
        assert adapter.is_order_open({"status": "closed"}) is False


class TestGetMinimumOrderAmount:
    def test_returns_min_from_markets(self, adapter):
        result = adapter.get_minimum_order_amount("BTC/USDT")
        assert result == 0.001

    def test_zero_for_unknown_symbol(self, adapter):
        result = adapter.get_minimum_order_amount("UNKNOWN/PAIR")
        assert result == 0.0

    def test_fallback_on_exception(self, adapter):
        adapter.exchange.markets = None
        result = adapter.get_minimum_order_amount("BTC/USDT")
        assert result == 0.0


class TestExecuteOrder:
    def test_execute_market_buy(self, adapter):
        adapter.exchange.create_market_order = MagicMock(
            return_value={
                "id": "m1",
                "symbol": "BTC/USDT",
                "side": "buy",
                "type": "market",
                "amount": 1.0,
                "filled": 1.0,
                "remaining": 0.0,
                "cost": 50000.0,
                "status": "closed",
                "timestamp": 0,
                "fee": {},
            }
        )
        adapter.amount_to_precision = MagicMock(return_value=1.0)
        signal = {"action": "buy", "symbol": "BTC/USDT", "amount": 1.0}
        result = adapter.execute_order(signal)
        assert result["id"] == "m1"

    def test_execute_market_sell(self, adapter):
        adapter.exchange.create_market_order = MagicMock(
            return_value={
                "id": "m2",
                "symbol": "BTC/USDT",
                "side": "sell",
                "type": "market",
                "amount": 1.0,
                "filled": 1.0,
                "remaining": 0.0,
                "cost": 49000.0,
                "status": "closed",
                "timestamp": 0,
                "fee": {},
            }
        )
        adapter.amount_to_precision = MagicMock(return_value=1.0)
        signal = {"action": "sell", "symbol": "BTC/USDT", "amount": 1.0}
        result = adapter.execute_order(signal)
        assert result["side"] == "sell"

    def test_execute_limit_order(self, adapter):
        adapter.exchange.create_limit_order = MagicMock(
            return_value={
                "id": "l1",
                "symbol": "BTC/USDT",
                "side": "buy",
                "type": "limit",
                "amount": 1.0,
                "price": 49000.0,
                "filled": 0.0,
                "remaining": 1.0,
                "cost": 0.0,
                "status": "open",
                "timestamp": 0,
                "fee": {},
            }
        )
        adapter.amount_to_precision = MagicMock(return_value=1.0)
        adapter.price_to_precision = MagicMock(return_value=49000.0)
        signal = {
            "action": "buy",
            "symbol": "BTC/USDT",
            "amount": 1.0,
            "price": 49000.0,
            "type": "limit",
        }
        result = adapter.execute_order(signal)
        assert result["type"] == "limit"
        assert result["price"] == 49000.0

    def test_execute_raises_on_missing_fields(self, adapter):
        with pytest.raises(ValueError, match="Signal must contain"):
            adapter.execute_order({"action": "buy", "symbol": "BTC/USDT"})
        with pytest.raises(ValueError, match="Signal must contain"):
            adapter.execute_order({"action": "buy", "amount": 1.0})

    def test_execute_uses_default_type_market(self, adapter):
        adapter.exchange.create_market_order = MagicMock(
            return_value={
                "id": "m3",
                "symbol": "BTC/USDT",
                "side": "buy",
                "type": "market",
                "amount": 1.0,
                "filled": 1.0,
                "remaining": 0.0,
                "cost": 50000.0,
                "status": "closed",
                "timestamp": 0,
                "fee": {},
            }
        )
        adapter.amount_to_precision = MagicMock(return_value=1.0)
        signal = {"action": "buy", "symbol": "BTC/USDT", "amount": 1.0}
        result = adapter.execute_order(signal)
        assert result["type"] == "market"


class TestFetchPosition:
    def test_fetch_position_success(self, adapter):
        adapter.exchange.fetch_position = MagicMock(
            return_value={
                "symbol": "BTC/USDT",
                "side": "long",
                "contracts": 1.0,
                "entryPrice": 50000.0,
                "markPrice": 51000.0,
                "unrealizedPnl": 1000.0,
                "leverage": 10,
                "liquidationPrice": 45000.0,
                "margin": 500.0,
            }
        )
        result = adapter.fetch_position("BTC/USDT")
        assert result["symbol"] == "BTC/USDT"
        assert result["side"] == "long"
        assert result["unrealized_pnl"] == 1000.0
        assert result["entry_price"] == 50000.0

    def test_fetch_position_not_supported_falls_back_to_fetch_positions(self, adapter):
        adapter.exchange.fetch_position = MagicMock()
        adapter.exchange.fetch_position = MagicMock(side_effect=ccxt.NotSupported("not supported"))
        adapter.exchange.fetch_positions = MagicMock(side_effect=lambda s: [])
        result = adapter.fetch_position("BTC/USDT")
        assert result["side"] is None
        assert result["contracts"] == 0

    def test_fetch_position_fallback_returns_first_position(self, adapter):
        adapter.exchange.fetch_position = MagicMock()
        adapter.exchange.fetch_position = MagicMock(side_effect=ccxt.NotSupported("not supported"))
        adapter.exchange.fetch_positions = MagicMock(
            side_effect=lambda s: [
                {
                    "symbol": "BTC/USDT",
                    "side": "short",
                    "contracts": 2.0,
                    "entryPrice": 51000.0,
                    "unrealizedPnl": -500.0,
                }
            ]
        )
        result = adapter.fetch_position("BTC/USDT")
        assert result["side"] == "short"
        assert result["contracts"] == 2.0
        assert result["unrealized_pnl"] == -500.0

    def test_fetch_position_no_position(self, adapter):
        adapter.exchange.fetch_position = MagicMock(
            return_value={
                "symbol": "BTC/USDT",
                "side": None,
                "contracts": 0,
                "entryPrice": 0,
                "unrealizedPnl": 0,
            }
        )
        result = adapter.fetch_position("BTC/USDT")
        assert result["contracts"] == 0
        assert result["unrealized_pnl"] == 0

    def test_fetch_position_attribute_error_fallback(self, adapter):
        del adapter.exchange.fetch_position
        adapter.exchange.fetch_positions = MagicMock(side_effect=lambda s: [])
        result = adapter.fetch_position("BTC/USDT")
        assert result["contracts"] == 0


class TestCreateMarketOrderWithCost:
    def test_create_market_buy_with_cost_success(self, adapter):
        adapter.exchange.create_market_buy_order_with_cost = MagicMock(
            return_value={
                "id": "cost1",
                "symbol": "BTC/USDT",
                "side": "buy",
                "type": "market",
                "amount": 0.002,
                "cost": 100.0,
                "filled": 0.002,
                "status": "closed",
                "timestamp": 0,
                "fee": {},
            }
        )
        result = adapter.create_market_order_with_cost("BTC/USDT", "buy", 100.0)
        assert result["id"] == "cost1"
        assert result["side"] == "buy"

    def test_create_market_sell_with_cost_success(self, adapter):
        adapter.exchange.create_market_sell_order_with_cost = MagicMock(
            return_value={
                "id": "cost2",
                "symbol": "BTC/USDT",
                "side": "sell",
                "type": "market",
                "amount": 0.002,
                "cost": 100.0,
                "filled": 0.002,
                "status": "closed",
                "timestamp": 0,
                "fee": {},
            }
        )
        result = adapter.create_market_order_with_cost("BTC/USDT", "sell", 100.0)
        assert result["id"] == "cost2"

    def test_create_market_order_with_cost_fallback(self, adapter):
        """When exchange doesn't support *with_cost, fall back to market order."""
        adapter.exchange.create_market_buy_order_with_cost = MagicMock()
        adapter.exchange.create_market_buy_order_with_cost = MagicMock(
            side_effect=ccxt.NotSupported("no cost orders")
        )
        adapter.exchange.create_market_order = MagicMock(
            return_value={
                "id": "m4",
                "symbol": "BTC/USDT",
                "side": "buy",
                "type": "market",
                "amount": 0.002,
                "cost": 100.0,
                "filled": 0.002,
                "status": "closed",
                "timestamp": 0,
                "fee": {},
            }
        )
        result = adapter.create_market_order_with_cost("BTC/USDT", "buy", 100.0)
        assert result["id"] == "m4"

    def test_create_market_order_with_cost_attribute_error_fallback(self, adapter):
        """If method doesn't exist at all, fall back."""
        if hasattr(adapter.exchange, "create_market_buy_order_with_cost"):
            del adapter.exchange.create_market_buy_order_with_cost
        adapter.exchange.create_market_order = MagicMock(
            return_value={
                "id": "m5",
                "symbol": "BTC/USDT",
                "side": "buy",
                "type": "market",
                "amount": 0.002,
                "filled": 0.002,
                "status": "closed",
                "timestamp": 0,
                "fee": {},
            }
        )
        result = adapter.create_market_order_with_cost("BTC/USDT", "buy", 100.0)
        assert result["id"] == "m5"
