import threading
from unittest.mock import MagicMock, patch

import pytest

from apps.trading.engines.bot_engine import BotEngine

BASE_CONFIG = {
    "bot_name": "test_bot",
    "strategy": "quantum_ai",
    "symbol": "BTC/USDT",
    "exchange_name": "bybit",
    "api_key": "test_api_key",
    "secret_key": "test_secret_key",
    "passphrase": "",
    "is_testnet": True,
    "user_id": "1",
    "parameters": {
        "symbol": "BTC/USDT",
        "favor_levels": 3,
        "against_levels": 3,
        "favor_level_qty": 10.0,
        "against_level_qty": 10.0,
        "favor_level_difference": 0.5,
        "against_level_difference": 0.5,
        "Take_Profit": 3.0,
        "Stop_Loss": -2.0,
        "Amount_Type": "dollar",
        "Order_Type": "market",
        "SLTP_Type": "percentage",
        "quantity": 100.0,
        "RSI_Lower": 30,
        "RSI_Upper": 70,
        "EMA_RSI_Entry": "both",
        "RSI_Entry": "both",
        "BB_Entry": "both",
        "BB_Exit": "both",
        "RSI_Exit": "both",
        "BB_RSI_Exit": "both",
        "BB_RSI_Entry": "both",
        "EMA_BB_Entry": "both",
        "EMA_BB_Exit": "both",
        "EMA_BB_RSI_Entry": "both",
        "SL_Exit": "both",
    },
}


@pytest.fixture
def mock_exchange():
    exchange = MagicMock()

    exchange.fetch_ticker = MagicMock(
        return_value={
            "symbol": "BTC/USDT:USDT",
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
    )

    exchange.fetch_balance = MagicMock(
        return_value={
            "total": {"USDT": 10000},
            "free": {"USDT": 8000},
            "used": {"USDT": 2000},
        }
    )

    exchange.amount_to_precision = MagicMock(side_effect=lambda s, a: f"{a:.4f}")
    exchange.price_to_precision = MagicMock(side_effect=lambda s, p: f"{p:.2f}")

    exchange.create_order = MagicMock(
        return_value={
            "id": "order123",
            "info": {"orderId": "order123"},
            "symbol": "BTC/USDT:USDT",
            "side": "buy",
            "type": "market",
            "amount": 0.002,
            "price": 50000.0,
            "filled": 0.002,
            "remaining": 0.0,
            "cost": 100.0,
            "status": "closed",
            "timestamp": 1234567890000,
        }
    )

    exchange.create_market_buy_order_with_cost = MagicMock(
        return_value={
            "id": "cost_buy_1",
            "info": {"orderId": "cost_buy_1"},
            "symbol": "BTC/USDT:USDT",
            "side": "buy",
            "type": "market",
            "amount": 0.002,
            "price": 50000.0,
            "filled": 0.002,
            "remaining": 0.0,
            "cost": 100.0,
            "status": "closed",
            "timestamp": 1234567890000,
        }
    )

    exchange.create_market_sell_order_with_cost = MagicMock(
        return_value={
            "id": "cost_sell_1",
            "info": {"orderId": "cost_sell_1"},
            "symbol": "BTC/USDT:USDT",
            "side": "sell",
            "type": "market",
            "amount": 0.002,
            "price": 50000.0,
            "filled": 0.002,
            "remaining": 0.0,
            "cost": 100.0,
            "status": "closed",
            "timestamp": 1234567890000,
        }
    )

    exchange.fetch_open_orders = MagicMock(return_value=[])
    exchange.fetch_order = MagicMock(
        return_value={
            "id": "order123",
            "status": "closed",
            "symbol": "BTC/USDT:USDT",
            "side": "buy",
            "type": "market",
            "amount": 0.002,
            "price": 50000.0,
            "filled": 0.002,
            "remaining": 0.0,
            "cost": 100.0,
        }
    )

    exchange.fetch_positions = MagicMock(return_value=[])
    exchange.fetch_position = MagicMock(return_value=None)
    exchange.cancel_all_orders = MagicMock(return_value=[])
    exchange.create_market_order = MagicMock(
        return_value={
            "id": "market1",
            "symbol": "BTC/USDT:USDT",
            "side": "buy",
            "type": "market",
            "amount": 0.002,
            "price": 50000.0,
            "filled": 0.002,
            "cost": 100.0,
            "status": "closed",
        }
    )
    exchange.create_limit_order = MagicMock(
        return_value={
            "id": "limit1",
            "symbol": "BTC/USDT:USDT",
            "side": "buy",
            "type": "limit",
            "amount": 0.002,
            "price": 49000.0,
            "filled": 0.0,
            "cost": 0.0,
            "status": "open",
        }
    )

    return exchange


@pytest.fixture
def bot_engine(mock_exchange):
    with patch("apps.trading.engines.bot_engine.BotExecutor") as MockExecutor:
        mock_executor_instance = MagicMock()
        adapter = mock_executor_instance.adapter
        adapter.exchange = mock_exchange

        # Wire adapter methods to delegate to exchange mock
        adapter.format_symbol = MagicMock(side_effect=lambda s: s)
        adapter.fetch_ticker = MagicMock(side_effect=lambda s: mock_exchange.fetch_ticker(s))
        adapter.fetch_balance = MagicMock(side_effect=lambda: mock_exchange.fetch_balance())
        adapter.create_market_order_with_cost = MagicMock(
            side_effect=lambda symbol, side, cost, params=None: (
                mock_exchange.create_market_buy_order_with_cost(symbol, cost, params or {})
                if side == "buy"
                else mock_exchange.create_market_sell_order_with_cost(symbol, cost, params or {})
            )
        )

        def _limit_order(symbol, side, qty, price, params=None):
            return mock_exchange.create_limit_order(symbol, side, qty, price)

        adapter.create_limit_order = MagicMock(side_effect=_limit_order)
        adapter.create_market_order = MagicMock(
            side_effect=lambda symbol, side, qty, params=None: mock_exchange.create_market_order(
                symbol, side, qty, params or {}
            )
        )
        adapter.fetch_position = MagicMock(side_effect=lambda s: mock_exchange.fetch_position(s))
        adapter.fetch_positions = MagicMock(side_effect=lambda s: mock_exchange.fetch_positions(s))
        adapter.cancel_all_orders = MagicMock(
            side_effect=lambda s: mock_exchange.cancel_all_orders(s)
        )
        adapter.amount_to_precision = MagicMock(
            side_effect=lambda s, a: mock_exchange.amount_to_precision(s, a)
        )
        adapter.price_to_precision = MagicMock(
            side_effect=lambda s, p: mock_exchange.price_to_precision(s, p)
        )
        adapter.get_current_price = MagicMock(return_value=50000.0)

        MockExecutor.from_config.return_value = mock_executor_instance

        engine = BotEngine(BASE_CONFIG)

        engine.exchange = mock_exchange
        engine.lock = threading.Lock()

        return engine


class TestBotEngineInitialization:
    def test_initializes_with_config(self, bot_engine):
        assert bot_engine.bot_name == "test_bot"
        assert bot_engine.symbol == "BTC/USDT:USDT"
        assert bot_engine.pair_config["pair_symbol"] == "BTC/USDT"
        assert bot_engine.current_side == "None"
        assert bot_engine.count == 0
        assert bot_engine.bot_running is False
        assert bot_engine.monitoring is False
        assert bot_engine.signals_generated == 0
        assert bot_engine.orders_executed == 0

    def test_initial_indicator_state(self, bot_engine):
        assert bot_engine.EMA == 0.0
        assert bot_engine.BB is None
        assert bot_engine.TSI is None
        assert bot_engine.ADX is None
        assert bot_engine.RSI == 0.0
        assert bot_engine.PrevRSI == 0.0
        assert bot_engine.RSI_color is None
        assert bot_engine.RSI_prev_color is None

    def test_condition_flags_defaults(self, bot_engine):
        assert bot_engine.NoTrade is True
        assert bot_engine.BuyTrade is False
        assert bot_engine.SellTrade is False
        assert bot_engine.EmaBuyCondition is False
        assert bot_engine.EmaSellCondition is False

    def test_executor_created_from_config(self, mock_exchange):
        with patch("apps.trading.engines.bot_engine.BotExecutor.from_config") as mock_from_config:
            mock_executor = MagicMock()
            mock_executor.adapter.exchange = mock_exchange
            mock_from_config.return_value = mock_executor

            engine = BotEngine(BASE_CONFIG)

            mock_from_config.assert_called_once()
            assert engine.executor is not None

    def test_str_repr(self, bot_engine):
        assert str(bot_engine) == "BotEngine(test_bot)"
        assert repr(bot_engine) == "BotEngine(name=test_bot, symbol=BTC/USDT:USDT)"

    def test_default_bot_name(self, mock_exchange):
        with patch("apps.trading.engines.bot_engine.BotExecutor.from_config") as mock_from_config:
            mock_executor = MagicMock()
            mock_executor.adapter.exchange = mock_exchange
            mock_from_config.return_value = mock_executor

            engine = BotEngine({"symbol": "BTC/USDT", "parameters": {"symbol": "BTC/USDT"}})
            assert engine.bot_name == "unnamed"

    def test_symbol_without_slash(self, mock_exchange):
        with patch("apps.trading.engines.bot_engine.BotExecutor.from_config") as mock_from_config:
            mock_executor = MagicMock()
            mock_executor.adapter.exchange = mock_exchange
            mock_from_config.return_value = mock_executor

            engine = BotEngine({"symbol": "BTCUSDT", "parameters": {"symbol": "BTCUSDT"}})
            assert engine.symbol == "BTCUSDT:USDT"


class TestUpdateConditions:
    def test_update_conditions_fetches_price(self, bot_engine):
        bot_engine.exchange.fetch_ticker = MagicMock(return_value={"last": 51000.0})
        bot_engine.EMA = 50000.0

        bot_engine.update_conditions()

        assert bot_engine.current_price == 51000.0
        assert bot_engine.EmaBuyCondition is True
        assert bot_engine.EmaSellCondition is False

    def test_update_conditions_no_trade(self, bot_engine):
        bot_engine.exchange.fetch_ticker = MagicMock(return_value={"last": 50000.0})
        bot_engine.count = 0
        bot_engine.current_side = "None"

        bot_engine.update_conditions()

        assert bot_engine.NoTrade is True
        assert bot_engine.BuyTrade is False
        assert bot_engine.SellTrade is False

    def test_update_conditions_buy_trade(self, bot_engine):
        bot_engine.exchange.fetch_ticker = MagicMock(return_value={"last": 50000.0})
        bot_engine.count = 1
        bot_engine.current_side = "Buy"

        bot_engine.update_conditions()

        assert bot_engine.NoTrade is False
        assert bot_engine.BuyTrade is True
        assert bot_engine.SellTrade is False

    def test_update_conditions_rsi(self, bot_engine):
        bot_engine.exchange.fetch_ticker = MagicMock(return_value={"last": 50000.0})
        bot_engine.PrevRSI = 25
        bot_engine.RSI_color = "white"

        bot_engine.update_conditions()

        assert bot_engine.RsiBuyCondition is True
        assert bot_engine.RsiSellCondition is False

    def test_update_conditions_bb(self, bot_engine):
        bot_engine.exchange.fetch_ticker = MagicMock(return_value={"last": 50000.0})
        bot_engine.BB = "Crossing Down Band"

        bot_engine.update_conditions()

        assert bot_engine.BBBuyCondition is True
        assert bot_engine.BBSellCondition is False


class TestGetIndicatorData:
    def test_returns_formatted_string(self, bot_engine):
        bot_engine.current_price = 50000.0
        bot_engine.EMA = 49000.0
        bot_engine.BB = "Upper Band"
        bot_engine.RSI = 65.0
        bot_engine.PrevRSI = 60.0
        bot_engine.RSI_color = "green"
        bot_engine.RSI_prev_color = "white"

        result = bot_engine.get_indicator_data()

        assert "BTC/USDT:USDT" in result
        assert "50000" in result
        assert "49000" in result
        assert "Upper Band" in result
        assert "65.0" in result


class TestResetTradingState:
    def test_resets_all_state(self, bot_engine):
        bot_engine.monitoring = True
        bot_engine._stop_event = threading.Event()
        bot_engine.EMA = 50000.0
        bot_engine.BB = "Upper Band"
        bot_engine.RSI = 65.0
        bot_engine.current_side = "Buy"
        bot_engine.count = 1
        bot_engine.reason = "some reason"
        bot_engine.bot_running = True
        bot_engine.favor_lvl = [51000, 52000]
        bot_engine.against_lvl = [49000, 48000]

        bot_engine.exchange.fetch_ticker = MagicMock(return_value={"last": 50000.0})

        bot_engine.reset_trading_state()

        assert bot_engine.monitoring is False
        assert bot_engine.EMA == 0.0
        assert bot_engine.BB == ""
        assert bot_engine.RSI == 0.0
        assert bot_engine.current_side == "None"
        assert bot_engine.count == 0
        assert bot_engine.reason == ""
        assert bot_engine.bot_running is False
        assert bot_engine.favor_lvl == []
        assert bot_engine.against_lvl == []
        assert bot_engine.PrevReason == "some reason"


class TestStopBot:
    def test_stops_bot_and_clears_threads(self, bot_engine):
        bot_engine.grid_monitor.bot_running = True
        bot_engine.grid_monitor.monitoring = True
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = False
        bot_engine.grid_monitor.monitoring_threads = [mock_thread]

        bot_engine.stop_bot()

        assert bot_engine.grid_monitor.bot_running is False
        assert bot_engine.grid_monitor.monitoring is False
        assert bot_engine._stop_event.is_set()
        assert bot_engine.grid_monitor.monitoring_threads == []

    def test_wait_for_threads_joins_alive_threads(self, bot_engine):
        mock_thread = MagicMock()
        mock_thread.is_alive.side_effect = [True, False]
        bot_engine.grid_monitor.monitoring_threads = [mock_thread]

        bot_engine._wait_for_threads()

        mock_thread.join.assert_called_once_with(timeout=5.0)
        assert bot_engine.grid_monitor.monitoring_threads == []

    def test_wait_for_threads_hanging_logs_warning(self, bot_engine):
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = True
        mock_thread.name = "TestThread"
        bot_engine.grid_monitor.monitoring_threads = [mock_thread]

        with patch("apps.trading.engines.grid_monitor.logger") as mock_logger:
            bot_engine._wait_for_threads()

        mock_logger.warning.assert_called_once()
        assert "did not stop gracefully" in mock_logger.warning.call_args[0][0]


class TestStartBot:
    def test_start_bot_buy_case1_ema_rsi(self, bot_engine):
        bot_engine.exchange.fetch_ticker = MagicMock(return_value={"last": 50000.0})
        bot_engine.EMA = 49000.0
        bot_engine.PrevRSI = 25
        bot_engine.RSI_color = "white"

        bot_engine.calculated_grid_orders = MagicMock(return_value={"order": "test"})
        bot_engine.save_order = MagicMock()

        with patch.object(
            bot_engine,
            "prepare_order_data",
            return_value={
                "category": "futures",
                "symbol": "BTC/USDT:USDT",
                "Order_Type": "market",
                "side": "Buy",
                "qty": 0.002,
                "qty_dollar": 100.0,
                "price": 50000.0,
                "favor_levels": 3,
                "against_levels": 3,
                "favor_level_qty": 10.0,
                "against_level_qty": 10.0,
                "favor_level_difference": 0.5,
                "against_level_difference": 0.5,
            },
        ):
            with patch("apps.trading.engines.bot_engine.TelegramService"):
                bot_engine.startBot()

        assert bot_engine.count == 1
        assert bot_engine.current_side == "Buy"
        assert bot_engine.reason == "EMA + RSI BUY LONG (CASE1)"
        bot_engine.calculated_grid_orders.assert_called_once()
        bot_engine.save_order.assert_called_once_with(
            "BUY", "EMA + RSI BUY LONG (CASE1)", bot_engine.calculated_grid_orders.return_value
        )

    def test_start_bot_buy_case3_bb_rsi(self, bot_engine):
        bot_engine.exchange.fetch_ticker = MagicMock(return_value={"last": 50000.0})
        bot_engine.BB = "Closed Below Lower Band"
        bot_engine.EMA = 51000.0
        bot_engine.PrevRSI = 25
        bot_engine.RSI_color = "white"
        bot_engine.config["parameters"]["EMA_RSI_Entry"] = "none"
        bot_engine.config["parameters"]["EMA_BB_Entry"] = "none"
        bot_engine.config["parameters"]["BB_RSI_Entry"] = "both"

        bot_engine.update_conditions()
        bot_engine.calculated_grid_orders = MagicMock(return_value={})
        bot_engine.save_order = MagicMock()

        with patch("apps.trading.engines.bot_engine.TelegramService"):
            bot_engine.startBot()

        assert bot_engine.reason == "BOLLINGER BANDS + RSI BUY LONG (CASE3)"

    def test_start_bot_sell_case1_ema_rsi(self, bot_engine):
        bot_engine.exchange.fetch_ticker = MagicMock(return_value={"last": 50000.0})
        bot_engine.EMA = 51000.0
        bot_engine.PrevRSI = 75
        bot_engine.RSI_color = "white"
        bot_engine.config["parameters"]["RSI_Lower"] = 20
        bot_engine.config["parameters"]["RSI_Upper"] = 70

        bot_engine.update_conditions()
        bot_engine.calculated_grid_orders = MagicMock(return_value={})
        bot_engine.save_order = MagicMock()

        with patch("apps.trading.engines.bot_engine.TelegramService"):
            bot_engine.startBot()

        assert bot_engine.current_side == "Sell"

    def test_start_bot_already_in_trade_checks_tp(self, bot_engine):
        bot_engine.exchange.fetch_ticker = MagicMock(return_value={"last": 52000.0})
        bot_engine.count = 1
        bot_engine.current_side = "Buy"
        bot_engine.BB = "Crossing Up Band"
        bot_engine.close_all_orders = MagicMock(return_value={})

        with patch("apps.trading.engines.bot_engine.TelegramService"):
            bot_engine.startBot()

        bot_engine.close_all_orders.assert_called_once()

    def test_execute_once_returns_success(self, bot_engine):
        bot_engine.startBot = MagicMock()
        result = bot_engine.execute_once()
        assert result["success"] is True
        assert "signal" in result

    def test_execute_once_returns_error(self, bot_engine):
        bot_engine.startBot = MagicMock(side_effect=ValueError("test error"))
        result = bot_engine.execute_once()
        assert result["success"] is False
        assert result["error"] == "test error"


class TestPrepareOrderData:
    def test_dollar_type_calculates_coin_amount(self, bot_engine):
        bot_engine.current_price = 50000.0
        bot_engine.pair_config["Amount_Type"] = "dollar"
        bot_engine.pair_config["quantity"] = 100.0
        bot_engine.pair_config["favor_level_qty"] = 50.0
        bot_engine.pair_config["against_level_qty"] = 25.0

        data = bot_engine.prepare_order_data("Buy", 50000.0)

        assert data["qty_dollar"] == 100.0
        assert data["favor_level_qty_dollar"] == 50.0
        assert data["against_level_qty_dollar"] == 25.0

    def test_coin_type_keeps_raw_quantities(self, bot_engine):
        bot_engine.current_price = 50000.0
        bot_engine.pair_config["Amount_Type"] = "coin"
        bot_engine.pair_config["quantity"] = 0.002
        bot_engine.pair_config["favor_level_qty"] = 0.001
        bot_engine.pair_config["against_level_qty"] = 0.0005

        data = bot_engine.prepare_order_data("Sell", 50000.0)

        assert data["qty"] == 0.002
        assert data["favor_level_qty"] == 0.001
        assert data["against_level_qty"] == 0.0005
        assert data["qty_dollar"] is None


class TestCreateOrder:
    def test_create_market_order_dollar_type(self, bot_engine):
        bot_engine.pair_config["Amount_Type"] = "dollar"
        result = bot_engine.order_service.create_order("market", "buy", 100.0, None)
        bot_engine.exchange.create_market_buy_order_with_cost.assert_called_once_with(
            "BTC/USDT:USDT", 100.0, {}
        )
        assert result is not None

    def test_create_market_sell_order_dollar_type(self, bot_engine):
        bot_engine.pair_config["Amount_Type"] = "dollar"
        bot_engine.order_service.create_order("market", "sell", 100.0, None)
        bot_engine.exchange.create_market_sell_order_with_cost.assert_called_once_with(
            "BTC/USDT:USDT", 100.0, {}
        )

    def test_create_limit_order_dollar_type(self, bot_engine):
        bot_engine.pair_config["Amount_Type"] = "dollar"
        bot_engine.order_service.create_order("limit", "buy", 0.002, 50000.0)
        bot_engine.exchange.create_limit_order.assert_called_once_with(
            "BTC/USDT:USDT", "buy", 0.002, 50000.0
        )

    def test_create_market_order_coin_type(self, bot_engine):
        bot_engine.pair_config["Amount_Type"] = "coin"
        bot_engine.order_service.create_order("market", "sell", 0.002, 50000.0)
        bot_engine.exchange.create_market_order.assert_called_once_with(
            "BTC/USDT:USDT", "sell", 0.002, {}
        )

    def test_create_order_error_handling(self, bot_engine):
        bot_engine.executor.adapter.create_market_order = MagicMock(
            side_effect=Exception("API error")
        )
        bot_engine.pair_config["Amount_Type"] = "coin"
        result = bot_engine.order_service.create_order("market", "buy", 0.002, 50000.0)
        assert result is None


class TestFetchCurrentPrice:
    def test_fetches_and_stores_price(self, bot_engine):
        bot_engine.executor.adapter.get_current_price = MagicMock(return_value=51000.0)
        price = bot_engine.fetch_current_price()
        assert price == 51000.0
        assert bot_engine.current_price == 51000.0


class TestCloseOpenOrder:
    def test_close_open_order_short(self, bot_engine):
        bot_engine.executor.adapter.fetch_position = MagicMock(
            return_value={
                "contracts": 0.002,
                "unrealized_pnl": 10.0,
                "side": "short",
                "symbol": "BTC/USDT:USDT",
            }
        )
        bot_engine.executor.adapter.create_market_order = MagicMock(
            return_value={
                "id": "close1",
                "symbol": "BTC/USDT:USDT",
                "side": "buy",
                "type": "market",
                "amount": 0.002,
                "status": "closed",
            }
        )

        with patch.object(bot_engine, "save_order") as mock_save:
            result = bot_engine.close_open_order("Test close")

        assert result is not None
        assert result["id"] == "close1"
        bot_engine.executor.adapter.create_market_order.assert_called_once()
        mock_save.assert_called_once()

    def test_close_open_order_long(self, bot_engine):
        bot_engine.executor.adapter.fetch_position = MagicMock(
            return_value={
                "contracts": 0.002,
                "unrealized_pnl": 15.0,
                "side": "long",
                "symbol": "BTC/USDT:USDT",
            }
        )
        bot_engine.executor.adapter.create_market_order = MagicMock(
            return_value={
                "id": "close2",
                "symbol": "BTC/USDT:USDT",
                "side": "sell",
                "type": "market",
                "amount": 0.002,
                "status": "closed",
            }
        )

        with patch.object(bot_engine, "save_order"):
            result = bot_engine.close_open_order("Test close long")

        assert result["id"] == "close2"
        bot_engine.executor.adapter.create_market_order.assert_called_once()

    def test_close_open_order_no_position(self, bot_engine):
        bot_engine.executor.adapter.fetch_position = MagicMock(side_effect=Exception("No position"))
        result = bot_engine.close_open_order("Test")
        assert result is None

    def test_close_open_order_percentage_calculation(self, bot_engine):
        bot_engine.pair_config["SLTP_Type"] = "percentage"
        bot_engine.executor.adapter.fetch_position = MagicMock(
            return_value={
                "contracts": 0.002,
                "unrealized_pnl": 10.0,
                "side": "short",
                "symbol": "BTC/USDT:USDT",
            }
        )
        bot_engine.executor.adapter.create_market_order = MagicMock(return_value={"id": "c1"})

        with patch.object(bot_engine, "save_order"):
            bot_engine.close_open_order("Test")

        assert bot_engine.Unrealized_Pnl == 10.0
        assert bot_engine.Percentage > 0


class TestCloseAllOrders:
    def test_close_all_orders_calls_reset_and_cancel(self, bot_engine):
        bot_engine.close_open_order = MagicMock(return_value={"id": "close1"})
        bot_engine.executor.adapter.cancel_all_orders = MagicMock()

        result = bot_engine.close_all_orders("Test close all")

        bot_engine.executor.adapter.cancel_all_orders.assert_called_once()
        bot_engine.close_open_order.assert_called_once_with("Test close all")
        assert bot_engine.reason == "Test close all"
        assert result == {"id": "close1"}


class TestCalculateGrids:
    def test_calculate_grids_buy(self, bot_engine):
        bot_engine.current_price = 50000.0
        bot_engine.pair_config["favor_levels"] = 3
        bot_engine.pair_config["against_levels"] = 3
        bot_engine.pair_config["favor_level_difference"] = 0.5
        bot_engine.pair_config["against_level_difference"] = 0.5

        favor, against = bot_engine.calculate_grids("buy")

        assert len(favor) == 3
        assert len(against) == 3
        assert favor[0] > 50000.0
        assert against[0] < 50000.0

    def test_calculate_grids_sell(self, bot_engine):
        bot_engine.current_price = 50000.0
        bot_engine.pair_config["favor_levels"] = 2
        bot_engine.pair_config["against_levels"] = 2
        bot_engine.pair_config["favor_level_difference"] = 1.0
        bot_engine.pair_config["against_level_difference"] = 1.0

        favor, against = bot_engine.calculate_grids("sell")

        assert len(favor) == 2
        assert len(against) == 2
        assert favor[0] < 50000.0
        assert against[0] > 50000.0


class TestCalculatedGridOrders:
    def test_calculated_grid_orders_dollar_buy(self, bot_engine):
        bot_engine.pair_config["Amount_Type"] = "dollar"
        bot_engine.calculate_grids = MagicMock(
            return_value=([51000.0, 52000.0], [49000.0, 48000.0])
        )
        bot_engine.order_service.create_order = MagicMock(return_value={"id": "grid1"})
        bot_engine.monitor_grid_orders = MagicMock()
        bot_engine.monitor_lossProfit = MagicMock()

        data = {
            "symbol": "BTC/USDT:USDT",
            "Order_Type": "market",
            "side": "Buy",
            "qty": 0.002,
            "qty_dollar": 100.0,
            "price": 50000.0,
            "favor_levels": 3,
            "against_levels": 3,
            "favor_level_qty": 10.0,
            "against_level_qty": 10.0,
            "favor_level_difference": 0.5,
            "against_level_difference": 0.5,
        }

        bot_engine.calculated_grid_orders(data)

        assert bot_engine.grid_monitor.bot_running is True
        assert bot_engine.grid_monitor.monitoring is True
        assert bot_engine.signals_generated == 1
        bot_engine.exchange.create_market_buy_order_with_cost.assert_called_once_with(
            "BTC/USDT:USDT", 100.0, {}
        )

    def test_calculated_grid_orders_coin_sell(self, bot_engine):
        bot_engine.pair_config["Amount_Type"] = "coin"
        bot_engine.calculate_grids = MagicMock(return_value=([49000.0], [51000.0]))
        bot_engine.order_service.create_order = MagicMock(return_value={"id": "grid1"})
        bot_engine.monitor_grid_orders = MagicMock()
        bot_engine.monitor_lossProfit = MagicMock()

        data = {
            "symbol": "BTC/USDT:USDT",
            "Order_Type": "market",
            "side": "Sell",
            "qty": 0.002,
            "qty_dollar": None,
            "price": 50000.0,
            "favor_levels": 1,
            "against_levels": 1,
            "favor_level_qty": 0.001,
            "against_level_qty": 0.001,
            "favor_level_difference": 0.5,
            "against_level_difference": 0.5,
            "favor_level_qty_dollar": None,
            "against_level_qty_dollar": None,
        }

        bot_engine.calculated_grid_orders(data)

        assert bot_engine.signals_generated == 1
        bot_engine.order_service.create_order.assert_called()


class TestGetStatus:
    def test_get_status_returns_all_metrics(self, bot_engine):
        bot_engine.current_price = 50000.0
        bot_engine.current_side = "Buy"
        bot_engine.count = 1
        bot_engine.reason = "Test reason"
        bot_engine.Percentage = 2.5
        bot_engine.Unrealized_Pnl = 50.0
        bot_engine.signals_generated = 5
        bot_engine.orders_executed = 3
        bot_engine.favor_lvl = [51000.0]
        bot_engine.against_lvl = [49000.0]

        status = bot_engine.get_status()

        assert status["bot_name"] == "test_bot"
        assert status["symbol"] == "BTC/USDT:USDT"
        assert status["is_running"] is False
        assert status["current_side"] == "Buy"
        assert status["current_price"] == 50000.0
        assert status["count"] == 1
        assert status["reason"] == "Test reason"
        assert status["signals_generated"] == 5
        assert status["orders_executed"] == 3
        assert status["indicators"]["EMA"] == 0.0
        assert status["indicators"]["RSI"] == 0.0


class TestQtyHelper:
    def test_qty_dollar_type(self, bot_engine):
        bot_engine.pair_config["Amount_Type"] = "dollar"
        bot_engine.pair_config["quantity"] = 100.0
        bot_engine.pair_config["favor_level_qty"] = 50.0
        bot_engine.pair_config["against_level_qty"] = 25.0
        bot_engine.current_price = 50000.0

        qty, favor, against = bot_engine.order_service.qty(bot_engine.current_price)

        assert qty == 0.002
        assert favor == 0.001
        assert against == 0.0005

    def test_qty_coin_type(self, bot_engine):
        bot_engine.pair_config["Amount_Type"] = "coin"
        bot_engine.pair_config["quantity"] = 0.002
        bot_engine.pair_config["favor_level_qty"] = 0.001
        bot_engine.pair_config["against_level_qty"] = 0.0005
        bot_engine.current_price = 50000.0

        qty, favor, against = bot_engine.order_service.qty(bot_engine.current_price)

        assert qty == 0.002
        assert favor == 0.001
        assert against == 0.0005


class TestSaveOrder:
    def test_save_order_with_user_id(self, bot_engine):
        bot_engine.config["user_id"] = "1"
        bot_engine.symbol = "BTC/USDT:USDT"
        bot_engine.current_price = 50000.0
        bot_engine.EMA = 49500.0
        bot_engine.RSI = 45.0
        bot_engine.BB = "Crossing Down Band"

        with patch("apps.bots.models.BotOrder.objects.create") as mock_order:
            with patch("apps.bots.models.Indicator.objects.create") as mock_ind:
                with patch("django.contrib.auth.get_user_model") as mock_get_user:
                    mock_user = MagicMock()
                    mock_get_user.return_value.objects.get.return_value = mock_user
                    mock_indicator = MagicMock()
                    mock_ind.return_value = mock_indicator
                    mock_order.return_value = MagicMock()

                    result = bot_engine.save_order("Buy", "TEST ENTRY")

                    assert result is not None
                    mock_ind.assert_called_once()
                    mock_order.assert_called_once()
                    call_kwargs = mock_order.call_args[1]
                    assert call_kwargs["user"] is not None
                    assert call_kwargs["Side"] == "Buy"
                    assert call_kwargs["Description"].startswith("[test_bot] TEST ENTRY")
                    assert bot_engine.orders_executed == 1

    def test_save_order_without_user_id_quantum_ai(self, bot_engine):
        bot_engine.config["user_id"] = None
        bot_engine.config["bot_name"] = "QuantumBot1"
        bot_engine.symbol = "BTC/USDT:USDT"
        bot_engine.current_price = 50000.0

        with patch("apps.bots.models.BotOrder.objects.create") as mock_order:
            with patch("apps.bots.models.Indicator.objects.create") as mock_ind:
                mock_order.return_value = MagicMock()

                result = bot_engine.save_order("Sell", "QUANTUM AI ENTRY")

                assert result is not None
                mock_ind.assert_not_called()
                mock_order.assert_called_once()
                call_kwargs = mock_order.call_args[1]
                assert call_kwargs.get("user") is None
                assert "Indicators" not in call_kwargs
                assert "[QuantumBot1] QUANTUM AI ENTRY" in call_kwargs["Description"]

    def test_save_order_handles_db_error(self, bot_engine):
        bot_engine.config["user_id"] = "1"
        with patch("apps.bots.models.BotOrder.objects.create", side_effect=Exception("DB down")):
            with patch("apps.bots.models.Indicator.objects.create"):
                with patch("django.contrib.auth.get_user_model") as mock_get_user:
                    mock_get_user.return_value.objects.get.return_value = MagicMock()
                    result = bot_engine.save_order("Buy", "will fail")
                    assert result is None  # Should not raise

    def test_save_order_zero_orders_executed_on_failure(self, bot_engine):
        bot_engine.orders_executed = 5
        bot_engine.config["user_id"] = "1"
        with patch("apps.bots.models.BotOrder.objects.create", side_effect=Exception("fail")):
            with patch("django.contrib.auth.get_user_model") as mock_get_user:
                mock_get_user.return_value.objects.get.return_value = MagicMock()
                bot_engine.save_order("Buy", "fail")
                assert bot_engine.orders_executed == 5  # unchanged


class TestStrategySync:
    def test_strategy_initialized(self, bot_engine):
        assert bot_engine.strategy is not None
        assert bot_engine.strategy.name == "Quantum AI"

    def test_sync_strategy_updates_all_fields(self, bot_engine):
        bot_engine.EMA = 49500.0
        bot_engine.RSI = 35.0
        bot_engine.PrevRSI = 40.0
        bot_engine.RSI_color = "white"
        bot_engine.RSI_prev_color = "red"
        bot_engine.BB = "Crossing Down Band"
        bot_engine.current_price = 50000.0
        bot_engine.current_side = "Buy"
        bot_engine.count = 1

        bot_engine._sync_strategy()

        assert bot_engine.strategy.EMA == 49500.0
        assert bot_engine.strategy.RSI == 35.0
        assert bot_engine.strategy.PrevRSI == 40.0
        assert bot_engine.strategy.RSI_color == "white"
        assert bot_engine.strategy.RSI_prev_color == "red"
        assert bot_engine.strategy.BB == "Crossing Down Band"
        assert bot_engine.strategy.current_price == 50000.0
        assert bot_engine.strategy.current_side == "Buy"
        assert bot_engine.strategy.count == 1

    def test_sync_strategy_called_from_update_conditions(self, bot_engine):
        bot_engine.executor.adapter.fetch_ticker = MagicMock(return_value={"last": 50000.0})
        with patch.object(bot_engine, "_sync_strategy") as mock_sync:
            bot_engine.update_conditions()
            mock_sync.assert_called_once()

    def test_strategy_independent_instance_per_engine(self, bot_engine):
        with patch("apps.trading.engines.bot_engine.BotExecutor") as MockExecutor:
            MockExecutor.from_config.return_value = MagicMock()
            engine2 = BotEngine(BASE_CONFIG)
            assert engine2.strategy is not bot_engine.strategy
            assert engine2.strategy.name == bot_engine.strategy.name


class TestBotEngineErrorHandling:
    def test_adapter_init_failure_propagates(self):
        with patch(
            "apps.trading.engines.bot_engine.BotExecutor.from_config",
            side_effect=ValueError("Unsupported exchange"),
        ):
            with pytest.raises(ValueError, match="Unsupported exchange"):
                BotEngine(BASE_CONFIG)

    def test_adapter_connection_error_propagates(self):
        with patch(
            "apps.trading.engines.bot_engine.BotExecutor.from_config",
            side_effect=ConnectionError("Connection refused"),
        ):
            with pytest.raises(ConnectionError):
                BotEngine(BASE_CONFIG)

    def test_adapter_init_missing_credentials_raises(self):
        with patch(
            "apps.trading.engines.bot_engine.BotExecutor.from_config",
            side_effect=KeyError("api_key"),
        ):
            with pytest.raises(KeyError):
                BotEngine(BASE_CONFIG)

    def test_execute_once_catches_and_returns_error(self, bot_engine):
        bot_engine.startBot = MagicMock(side_effect=RuntimeError("Runtime failure"))
        result = bot_engine.execute_once()
        assert result["success"] is False
        assert result["error"] == "Runtime failure"

    def test_start_bot_telegram_failure_does_not_block(self, bot_engine):
        bot_engine.executor.adapter.fetch_ticker = MagicMock(return_value={"last": 50000.0})
        with patch(
            "apps.trading.engines.bot_engine.TelegramService.notify_bot_started",
            side_effect=Exception("Telegram down"),
        ):
            bot_engine.calculated_grid_orders = MagicMock(return_value={})
            bot_engine.save_order = MagicMock()
            with patch.object(
                bot_engine,
                "prepare_order_data",
                return_value={
                    "category": "futures",
                    "symbol": "BTC/USDT:USDT",
                    "Order_Type": "market",
                    "side": "Buy",
                    "qty": 0.002,
                    "qty_dollar": 100.0,
                    "price": 50000.0,
                    "favor_levels": 3,
                    "against_levels": 3,
                    "favor_level_qty": 10.0,
                    "against_level_qty": 10.0,
                    "favor_level_difference": 0.5,
                    "against_level_difference": 0.5,
                },
            ):
                bot_engine.startBot()
        assert bot_engine.bot_running


class TestBotEngineConfigHandling:
    def _make_minimal_config(self, **overrides):
        config = {
            "symbol": "BTC/USDT",
            "parameters": {"symbol": "BTC/USDT"},
        }
        config.update(overrides)
        return config

    def test_symbol_with_multiple_slashes(self, mock_exchange):
        with patch("apps.trading.engines.bot_engine.BotExecutor.from_config") as mock:
            mock_executor = MagicMock()
            mock_executor.adapter.exchange = mock_exchange
            mock.return_value = mock_executor
            engine = BotEngine(
                {"symbol": "BTC/USDT/SOMETHING", "parameters": {"symbol": "BTC/USDT/SOMETHING"}}
            )
            assert engine.symbol == "BTC/USDT/SOMETHING:USDT"

    def test_pair_config_extraction(self, mock_exchange):
        params = {"symbol": "BTC/USDT", "key": "value", "nested": {"a": 1}}
        with patch("apps.trading.engines.bot_engine.BotExecutor.from_config") as mock:
            mock_executor = MagicMock()
            mock_executor.adapter.exchange = mock_exchange
            mock.return_value = mock_executor
            engine = BotEngine({"symbol": "BTC/USDT", "parameters": params})
            assert engine.pair_config["pair_symbol"] == "BTC/USDT"
            assert engine.pair_config["key"] == "value"
            assert engine.pair_config["nested"] == {"a": 1}

    def test_pair_config_without_parameters_key(self, mock_exchange):
        with patch("apps.trading.engines.bot_engine.BotExecutor.from_config") as mock:
            mock_executor = MagicMock()
            mock_executor.adapter.exchange = mock_exchange
            mock.return_value = mock_executor
            engine = BotEngine({"symbol": "ETH/USDT", "parameters": {"symbol": "ETH/USDT"}})
            assert engine.pair_config == {"pair_symbol": "ETH/USDT", "symbol": "ETH/USDT"}

    def test_empty_symbol(self, mock_exchange):
        with patch("apps.trading.engines.bot_engine.BotExecutor.from_config") as mock:
            mock_executor = MagicMock()
            mock_executor.adapter.exchange = mock_exchange
            mock.return_value = mock_executor
            config = self._make_minimal_config(symbol="")
            engine = BotEngine(config)
            assert engine.symbol == ":USDT"

    def test_config_without_symbol_key(self, mock_exchange):
        with patch("apps.trading.engines.bot_engine.BotExecutor.from_config") as mock:
            mock_executor = MagicMock()
            mock_executor.adapter.exchange = mock_exchange
            mock.return_value = mock_executor
            engine = BotEngine({"parameters": {"symbol": "BTC/USDT"}})
            assert engine.symbol == ":USDT"
            assert engine.bot_name == "unnamed"

    def test_exchange_name_passed_to_executor(self, mock_exchange):
        with patch("apps.trading.engines.bot_engine.BotExecutor.from_config") as mock_from_config:
            mock_executor = MagicMock()
            mock_executor.adapter.exchange = mock_exchange
            mock_from_config.return_value = mock_executor
            BotEngine({**BASE_CONFIG, "exchange_name": "binance"})
            mock_from_config.assert_called_once()
            config_arg = mock_from_config.call_args[0][0]
            assert config_arg["exchange_name"] == "binance"

    def test_credentials_stripped_after_init(self, mock_exchange):
        with patch("apps.trading.engines.bot_engine.BotExecutor.from_config") as mock_from_config:
            mock_executor = MagicMock()
            mock_executor.adapter.exchange = mock_exchange
            mock_from_config.return_value = mock_executor
            config = {**BASE_CONFIG}
            engine = BotEngine(config)
            assert "api_key" not in engine.config
            assert "secret_key" not in engine.config
            assert "passphrase" not in engine.config
