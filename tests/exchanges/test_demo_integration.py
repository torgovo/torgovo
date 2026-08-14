"""
Integration tests for exchange adapters against demo/testnet environments.

These tests validate that each adapter works correctly in demo mode.
They require appropriate environment variables to be set for each exchange.

Exchanges with official API sandboxes:
  - Binance: BINANCE_TESTNET_API_KEY / BINANCE_TESTNET_SECRET
  - Bybit:   BYBIT_TESTNET_API_KEY / BYBIT_TESTNET_SECRET
  - OKX:     OKX_DEMO_API_KEY / OKX_DEMO_SECRET / OKX_DEMO_PASSPHRASE
  - Alpaca:  ALPACA_PAPER_API_KEY / ALPACA_PAPER_SECRET

Exchanges WITHOUT API sandbox (MEXC, Coinbase):
  - Tested via MockAdapter (in-memory simulation)

Run like:
    BINANCE_TESTNET_API_KEY=x BYBIT_TESTNET_API_KEY=y
    pytest tests/exchanges/test_demo_integration.py -v
"""

import os

import pytest

from apps.exchanges.models import ExchangeCredentials
from apps.trading.exchanges import (
    AlpacaAdapter,
    BinanceAdapter,
    BybitAdapter,
    CoinbaseAdapter,
    MEXCAdapter,
    MockAdapter,
    OKXAdapter,
    get_adapter,
)

# =============================================================================
# Helpers
# =============================================================================

EXCHANGE_CREDENTIALS = {
    "binance": {
        "api_key": os.environ.get("BINANCE_TESTNET_API_KEY", ""),
        "secret_key": os.environ.get("BINANCE_TESTNET_SECRET", ""),
    },
    "bybit": {
        "api_key": os.environ.get("BYBIT_TESTNET_API_KEY", ""),
        "secret_key": os.environ.get("BYBIT_TESTNET_SECRET", ""),
    },
    "okx": {
        "api_key": os.environ.get("OKX_DEMO_API_KEY", ""),
        "secret_key": os.environ.get("OKX_DEMO_SECRET", ""),
        "passphrase": os.environ.get("OKX_DEMO_PASSPHRASE", ""),
    },
    "alpaca": {
        "api_key": os.environ.get("ALPACA_PAPER_API_KEY", ""),
        "secret_key": os.environ.get("ALPACA_PAPER_SECRET", ""),
    },
}

EXCHANGES_WITH_SANDBOX = [
    code for code, _ in ExchangeCredentials.EXCHANGE_CHOICES if code != "mexc"
]


def has_creds(name):
    creds = EXCHANGE_CREDENTIALS.get(name, {})
    return all(v for v in creds.values())


requires_creds = pytest.mark.skipif(
    not any(has_creds(name) for name in EXCHANGES_WITH_SANDBOX),
    reason="No demo API credentials provided. Set BINANCE_TESTNET_API_KEY, etc.",
)


# =============================================================================
# Smoke Tests — Can the adapters initialize in demo mode?
# =============================================================================


class TestAdapterInitialization:

    def test_binance_demo_init(self):
        adapter = BinanceAdapter(EXCHANGE_CREDENTIALS["binance"], demo_mode=True)
        assert adapter.demo_mode is True
        urls = adapter.exchange.urls
        api = urls.get("api", {})
        all_urls = " ".join(str(v) for v in (api.values() if isinstance(api, dict) else [api]))
        assert "demo" in all_urls, f"Binance demo URLs not set (got: {api})"

    def test_bybit_demo_init(self):
        adapter = BybitAdapter(EXCHANGE_CREDENTIALS["bybit"], demo_mode=True)
        assert adapter.demo_mode is True
        urls = adapter.exchange.urls
        api = urls.get("api", {})
        all_urls = str(api)
        assert "demo" in all_urls, f"Bybit demo URLs not set (got: {api})"

    def test_okx_demo_init(self):
        adapter = OKXAdapter(EXCHANGE_CREDENTIALS["okx"], demo_mode=True)
        assert adapter.demo_mode is True
        headers = adapter.exchange.headers or {}
        assert headers.get("x-simulated-trading") == "1", f"OKX demo header not set: {headers}"

    def test_alpaca_demo_init(self):
        adapter = AlpacaAdapter(EXCHANGE_CREDENTIALS["alpaca"], demo_mode=True)
        assert adapter.demo_mode is True
        urls = adapter.exchange.urls
        api = urls.get("api", {})
        all_urls = str(api)
        assert "paper" in all_urls or "sandbox" in all_urls, f"Alpaca paper URLs not set: {api}"

    def test_mexc_demo_raises(self):
        with pytest.raises((ValueError, TypeError)):
            MEXCAdapter({}, demo_mode=True)

    def test_coinbase_demo_raises(self):
        with pytest.raises((ValueError, TypeError)):
            CoinbaseAdapter({}, demo_mode=True)

    def test_get_adapter_mexc_fallback_to_mock(self):
        adapter = get_adapter("mexc", {"exchange_name": "mexc"}, demo_mode=True)
        assert isinstance(adapter, MockAdapter)

    def test_get_adapter_coinbase_fallback_to_mock(self):
        adapter = get_adapter("coinbase", {"exchange_name": "coinbase"}, demo_mode=True)
        assert isinstance(adapter, MockAdapter)

    def test_get_adapter_binance_no_fallback(self):
        adapter = get_adapter("binance", EXCHANGE_CREDENTIALS["binance"], demo_mode=True)
        assert isinstance(adapter, BinanceAdapter)


# =============================================================================
# MockAdapter Tests — Full feature parity (no credentials needed)
# =============================================================================


class TestMockAdapter:

    @pytest.fixture
    def adapter(self):
        return MockAdapter({"exchange_name": "mock_test", "initial_balance": 50000})

    def test_initial_balance(self, adapter):
        bal = adapter.fetch_balance()
        assert bal["free"]["USDT"] == 50000.0
        assert bal["total"]["USDT"] == 50000.0

    def test_fetch_ticker(self, adapter):
        ticker = adapter.fetch_ticker("BTC/USDT")
        assert ticker["symbol"] == "BTC/USDT"
        assert ticker["last"] > 0
        assert ticker["bid"] > 0
        assert ticker["ask"] > 0
        assert ticker["timestamp"] > 0

    def test_get_current_price(self, adapter):
        price = adapter.get_current_price("ETH/USDT")
        assert price > 0

    def test_fetch_ohlcv(self, adapter):
        candles = adapter.fetch_ohlcv("BTC/USDT", "1h", 10)
        assert len(candles) == 10
        for c in candles:
            assert c["timestamp"] > 0
            assert c["open"] > 0
            assert c["close"] > 0

    def test_fetch_order_book(self, adapter):
        ob = adapter.fetch_order_book("BTC/USDT", 5)
        assert len(ob["bids"]) == 5
        assert len(ob["asks"]) == 5
        for bid in ob["bids"]:
            assert len(bid) == 2

    def test_market_order_buy(self, adapter):
        bal_before = adapter.fetch_balance()
        order = adapter.create_market_order("BTC/USDT", "buy", 0.01)
        assert order["status"] == "closed"
        assert order["filled"] == 0.01
        assert order["side"] == "buy"
        bal_after = adapter.fetch_balance()
        assert bal_after["free"]["USDT"] < bal_before["free"]["USDT"]
        assert bal_after["free"]["BTC"] >= 0.0099  # minus fee

    def test_market_order_sell(self, adapter):
        adapter.create_market_order("BTC/USDT", "buy", 0.01)
        bal_before = adapter.fetch_balance()
        order = adapter.create_market_order("BTC/USDT", "sell", 0.005)
        assert order["status"] == "closed"
        bal_after = adapter.fetch_balance()
        assert bal_after["free"]["BTC"] < bal_before["free"]["BTC"]
        assert bal_after["free"]["USDT"] > bal_before["free"]["USDT"]

    def test_market_order_insufficient_funds(self, adapter):
        with pytest.raises(ValueError, match="Insufficient"):
            adapter.create_market_order("BTC/USDT", "buy", 1000)

    def test_limit_order(self, adapter):
        order = adapter.create_limit_order("BTC/USDT", "buy", 0.01, 50000)
        assert order["status"] == "open"
        assert order["remaining"] == 0.01
        open_orders = adapter.fetch_open_orders("BTC/USDT")
        assert any(o["id"] == order["id"] for o in open_orders)

    def test_cancel_limit_order(self, adapter):
        order = adapter.create_limit_order("BTC/USDT", "buy", 0.01, 50000)
        result = adapter.cancel_order(order["id"], "BTC/USDT")
        assert result["cancelled"] is True
        updated = adapter.fetch_order(order["id"], "BTC/USDT")
        assert updated["status"] == "canceled"

    def test_cancel_all_orders(self, adapter):
        adapter.create_limit_order("BTC/USDT", "buy", 0.01, 40000)
        adapter.create_limit_order("BTC/USDT", "buy", 0.02, 45000)
        cancelled = adapter.cancel_all_orders("BTC/USDT")
        assert len(cancelled) == 2
        remaining = adapter.fetch_open_orders("BTC/USDT")
        assert len(remaining) == 0

    def test_stop_loss_order(self, adapter):
        order = adapter.create_stop_loss_order("BTC/USDT", "sell", 0.01, 60000)
        assert order["status"] == "open"
        assert order["stop_price"] == 60000

    def test_take_profit_order(self, adapter):
        order = adapter.create_take_profit_order("BTC/USDT", "sell", 0.01, 70000)
        assert order["status"] == "open"
        assert order["take_profit_price"] == 70000

    def test_fetch_order_not_found(self, adapter):
        with pytest.raises(ValueError, match="not found"):
            adapter.fetch_order("nonexistent", "BTC/USDT")

    def test_fetch_positions_empty(self, adapter):
        positions = adapter.fetch_positions()
        assert positions == []

    def test_get_account_info(self, adapter):
        info = adapter.get_account_info()
        assert info["exchange"] == "mock_test"
        assert info["demo_mode"] is True
        assert "USDT" in info["balance"]["free"]

    def test_execute_order_market(self, adapter):
        signal = {"action": "buy", "symbol": "ETH/USDT", "amount": 0.1, "type": "market"}
        order = adapter.execute_order(signal)
        assert order["status"] == "closed"

    def test_execute_order_limit(self, adapter):
        signal = {
            "action": "buy",
            "symbol": "ETH/USDT",
            "amount": 0.1,
            "type": "limit",
            "price": 3000,
        }
        order = adapter.execute_order(signal)
        assert order["status"] == "open"

    def test_execute_order_stop_loss(self, adapter):
        signal = {"action": "sell", "symbol": "ETH/USDT", "amount": 0.1, "stop_price": 3000}
        order = adapter.execute_order(signal)
        assert order["status"] == "open"
        assert "stop_price" in order

    def test_execute_order_take_profit(self, adapter):
        signal = {"action": "sell", "symbol": "ETH/USDT", "amount": 0.1, "take_profit_price": 4000}
        order = adapter.execute_order(signal)
        assert order["status"] == "open"
        assert "take_profit_price" in order

    def test_execute_order_missing_fields(self, adapter):
        with pytest.raises(ValueError, match="'action', 'symbol', and 'amount'"):
            adapter.execute_order({"action": "buy"})

    def test_market_order_with_cost(self, adapter):
        order = adapter.create_market_order_with_cost("BTC/USDT", "buy", 500)
        assert order["status"] == "closed"
        assert order["cost"] > 0

    def test_format_symbol(self, adapter):
        assert adapter.format_symbol("BTC/USDT") == "BTC/USDT"

    def test_amount_to_precision(self, adapter):
        assert adapter.amount_to_precision("BTC/USDT", 0.123456789) == 0.12345679

    def test_price_to_precision(self, adapter):
        assert adapter.price_to_precision("BTC/USDT", 12345.6789) == 12345.68


# =============================================================================
# Live Demo Integration Tests (require credentials)
# =============================================================================


class TestBinanceDemoIntegration:

    @pytest.fixture
    def adapter(self):
        if not has_creds("binance"):
            pytest.skip("BINANCE_TESTNET_API_KEY / SECRET not set")
        return BinanceAdapter(EXCHANGE_CREDENTIALS["binance"], demo_mode=True)

    def test_fetch_ticker(self, adapter):
        ticker = adapter.fetch_ticker("BTC/USDT")
        assert ticker["last"] > 0
        assert ticker["symbol"] == "BTC/USDT"

    def test_fetch_balance(self, adapter):
        bal = adapter.fetch_balance()
        assert "total" in bal
        assert "free" in bal

    def test_fetch_ohlcv(self, adapter):
        candles = adapter.fetch_ohlcv("BTC/USDT", "1h", 5)
        assert len(candles) == 5

    def test_fetch_order_book(self, adapter):
        ob = adapter.fetch_order_book("BTC/USDT", 5)
        assert len(ob["bids"]) > 0

    def test_error_on_real_order(self, adapter):
        with pytest.raises(Exception):
            adapter.create_market_order("NONEXISTENT/FAKE", "buy", 0.001)


class TestBybitDemoIntegration:

    @pytest.fixture
    def adapter(self):
        if not has_creds("bybit"):
            pytest.skip("BYBIT_TESTNET_API_KEY / SECRET not set")
        return BybitAdapter(EXCHANGE_CREDENTIALS["bybit"], demo_mode=True)

    def test_fetch_ticker(self, adapter):
        ticker = adapter.fetch_ticker("BTC/USDT")
        assert ticker["last"] > 0

    def test_fetch_balance(self, adapter):
        bal = adapter.fetch_balance()
        assert "total" in bal

    def test_fetch_order_book(self, adapter):
        ob = adapter.fetch_order_book("BTC/USDT", 5)
        assert len(ob["bids"]) > 0


class TestOKXDemoIntegration:

    @pytest.fixture
    def adapter(self):
        if not has_creds("okx"):
            pytest.skip("OKX_DEMO_API_KEY / SECRET / PASSPHRASE not set")
        return OKXAdapter(EXCHANGE_CREDENTIALS["okx"], demo_mode=True)

    def test_fetch_ticker(self, adapter):
        ticker = adapter.fetch_ticker("BTC/USDT")
        assert ticker["last"] > 0

    def test_fetch_balance(self, adapter):
        bal = adapter.fetch_balance()
        assert "total" in bal

    def test_fetch_order_book(self, adapter):
        ob = adapter.fetch_order_book("BTC/USDT", 5)
        assert len(ob["bids"]) > 0


class TestAlpacaDemoIntegration:

    @pytest.fixture
    def adapter(self):
        if not has_creds("alpaca"):
            pytest.skip("ALPACA_PAPER_API_KEY / SECRET not set")
        return AlpacaAdapter(EXCHANGE_CREDENTIALS["alpaca"], demo_mode=True)

    def test_fetch_ticker(self, adapter):
        ticker = adapter.fetch_ticker("BTC/USDT")
        assert ticker.get("last", 0) > 0

    def test_fetch_balance(self, adapter):
        bal = adapter.fetch_balance()
        assert "total" in bal
