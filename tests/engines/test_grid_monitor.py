"""Behavior tests for GridPositionMonitor (apps/trading/engines/grid_monitor.py).

Covers thread lifecycle, price fetching, SL/TP decision branches,
exchange-native SL/TP placement, heartbeat persistence, and the
grid-level replacement loop after fills. Callbacks are injected as
mocks so no real exchange or Django model logic is needed for the
thread-driven tests.
"""

import threading
import time
from decimal import Decimal
from unittest import mock

import pytest

from apps.trading.engines.grid_monitor import GridPositionMonitor

_orig_sleep = time.sleep


def _fast_sleep(*_):
    _orig_sleep(0.001)


class _FakeEvent:
    """Replace threading.Event so wait() never blocks the test."""

    def __init__(self):
        self.flag = False

    def is_set(self):
        return self.flag

    def set(self):
        self.flag = True

    def wait(self, timeout=None):
        return self.flag


def _wait_until(pred, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(0.01)
    return False


def _make_monitor(
    adapter=None, pair_config=None, bot_config=None, create_order_cb=None, close_all_orders_cb=None
):
    adapter = adapter or mock.MagicMock()
    adapter.get_current_price.return_value = 100.0
    adapter.fetch_open_orders.return_value = []
    adapter.fetch_order.return_value = {"status": "new"}
    adapter.fetch_position.return_value = None
    return GridPositionMonitor(
        adapter,
        symbol="BTC/USDT",
        pair_config=pair_config or {},
        bot_config=bot_config or {},
        create_order_cb=create_order_cb or mock.Mock(return_value={"id": "o1"}),
        close_all_orders_cb=close_all_orders_cb or mock.Mock(),
    )


class TestLifecycle:
    def test_init_defaults(self):
        monitor = _make_monitor()
        assert monitor.monitoring is False
        assert monitor.bot_running is False
        assert monitor.monitoring_threads == []
        assert monitor.favor_lvl == []
        assert monitor.against_lvl == []
        assert monitor.current_side == "None"
        assert monitor.current_price == 0.0
        assert monitor._last_tp is None
        assert monitor._last_sl is None

    def test_fetch_current_price_updates_and_returns(self):
        monitor = _make_monitor()
        assert monitor.fetch_current_price() == 100.0
        assert monitor.current_price == 100.0

    def test_stop_all_clears_threads_and_resets_state(self):
        monitor = _make_monitor()

        def waiter():
            while not monitor._stop_event.is_set():
                time.sleep(0.001)

        t1 = threading.Thread(target=waiter, daemon=True)
        t2 = threading.Thread(target=waiter, daemon=True)
        monitor.monitoring = True
        monitor.bot_running = True
        monitor.monitoring_threads.extend([t1, t2])
        t1.start()
        t2.start()

        monitor.stop_all()

        assert monitor.monitoring is False
        assert monitor.bot_running is False
        assert monitor.monitoring_threads == []
        assert monitor._stop_event.is_set()
        assert not t1.is_alive()
        assert not t2.is_alive()

    def test_start_monitoring_spawns_both_threads(self):
        with mock.patch("apps.trading.engines.grid_monitor.time.sleep", _fast_sleep):
            monitor = _make_monitor()
            monitor.start_monitoring("buy", 50000, [50100], [49900], 0.01, 0.01)

            assert monitor.monitoring is True
            assert len(monitor.monitoring_threads) == 2
            assert all(t.is_alive() for t in monitor.monitoring_threads)
            assert all(t.daemon for t in monitor.monitoring_threads)

            monitor.stop_all()
            assert monitor.monitoring_threads == []
            assert all(not t.is_alive() for t in monitor.monitoring_threads)

    def test_start_restore_monitoring_marks_bot_running(self):
        with mock.patch("apps.trading.engines.grid_monitor.time.sleep", _fast_sleep):
            monitor = _make_monitor()
            monitor.start_restore_monitoring("buy", 50000, [50100], [49900], 0.01, 0.01)

            assert monitor.bot_running is True
            assert len(monitor.monitoring_threads) == 2
            monitor.stop_all()


class TestCheckLossProfitPercent:
    def test_percentage_mode_uses_notional(self):
        monitor = _make_monitor(pair_config={"SLTP_Type": "percentage"})
        monitor.adapter.fetch_position.return_value = {"notional": 100, "unrealizedPnl": -10}
        assert monitor._check_loss_profit_percent() == -100.0
        assert monitor.Percentage == -100.0
        assert monitor.Unrealized_Pnl == -10.0

    def test_zero_notional_falls_back_to_contracts(self):
        monitor = _make_monitor(pair_config={"SLTP_Type": "percentage"})
        monitor.current_price = 10.0
        monitor.adapter.fetch_position.return_value = {
            "notional": 0,
            "contracts": 10,
            "unrealizedPnl": 5,
        }
        assert monitor._check_loss_profit_percent() == 50.0

    def test_no_position_returns_zero(self):
        monitor = _make_monitor(pair_config={"SLTP_Type": "percentage"})
        monitor.adapter.fetch_position.return_value = None
        assert monitor._check_loss_profit_percent() == 0.0

    def test_dollars_mode_returns_pnl(self):
        monitor = _make_monitor(pair_config={"SLTP_Type": "dollars"})
        monitor.adapter.fetch_position.return_value = {"notional": 100, "unrealizedPnl": -10}
        assert monitor._check_loss_profit_percent() == -10.0

    def test_exception_resets_metrics_to_zero(self):
        monitor = _make_monitor(pair_config={"SLTP_Type": "percentage"})
        monitor.Percentage = 5.0
        monitor.Unrealized_Pnl = 3.0
        monitor.adapter.fetch_position.side_effect = RuntimeError("boom")
        assert monitor._check_loss_profit_percent() == 0.0
        assert monitor.Percentage == 0.0
        assert monitor.Unrealized_Pnl == 0.0


class TestPlaceSltpOrders:
    def test_dollar_quantity_long(self):
        monitor = _make_monitor(
            pair_config={
                "Amount_Type": "dollar",
                "quantity": 1000,
                "Stop_Loss": 10,
                "Take_Profit": 20,
            }
        )
        monitor.adapter.amount_to_precision.return_value = 10.0
        monitor.adapter.create_take_profit_order.return_value = {"retCode": 0}
        monitor.adapter.create_stop_loss_order.return_value = {"retCode": 0}

        monitor._place_sltp_orders("buy", 100)

        monitor.adapter.create_take_profit_order.assert_called_once_with(
            symbol="BTC/USDT",
            side="sell",
            amount=10.0,
            take_profit_price=102.0,
            params={"reduceOnly": True},
        )
        monitor.adapter.create_stop_loss_order.assert_called_once_with(
            symbol="BTC/USDT",
            side="sell",
            amount=10.0,
            stop_price=101.0,
            params={"reduceOnly": True},
        )
        assert monitor._last_tp == 20
        assert monitor._last_sl == 10

    def test_coin_quantity_uses_quantity(self):
        monitor = _make_monitor(
            pair_config={"Amount_Type": "base", "quantity": 5, "Stop_Loss": 10, "Take_Profit": 20}
        )
        monitor.adapter.amount_to_precision.return_value = 5.0
        monitor.adapter.create_take_profit_order.return_value = {"retCode": 0}
        monitor.adapter.create_stop_loss_order.return_value = {"retCode": 0}

        monitor._place_sltp_orders("buy", 100)

        monitor.adapter.create_take_profit_order.assert_called_once()
        assert monitor.adapter.create_take_profit_order.call_args[1]["amount"] == 5.0

    def test_position_contracts_override_config_size(self):
        monitor = _make_monitor(
            pair_config={
                "Amount_Type": "dollar",
                "quantity": 1000,
                "Stop_Loss": 10,
                "Take_Profit": 20,
            }
        )
        monitor.adapter.fetch_position.return_value = {"contracts": 2}
        monitor.adapter.create_take_profit_order.return_value = {"retCode": 0}
        monitor.adapter.create_stop_loss_order.return_value = {"retCode": 0}

        monitor._place_sltp_orders("buy", 100)

        assert monitor.adapter.create_take_profit_order.call_args[1]["amount"] == 2
        monitor.adapter.amount_to_precision.assert_not_called()

    def test_short_prices_inverted(self):
        monitor = _make_monitor(
            pair_config={"Amount_Type": "base", "quantity": 5, "Stop_Loss": 10, "Take_Profit": 20}
        )
        monitor.adapter.amount_to_precision.return_value = 5.0
        monitor.adapter.create_take_profit_order.return_value = {"retCode": 0}
        monitor.adapter.create_stop_loss_order.return_value = {"retCode": 0}

        monitor._place_sltp_orders("sell", 100)

        monitor.adapter.create_take_profit_order.assert_called_once_with(
            symbol="BTC/USDT",
            side="buy",
            amount=5.0,
            take_profit_price=98.0,
            params={"reduceOnly": True},
        )
        monitor.adapter.create_stop_loss_order.assert_called_once_with(
            symbol="BTC/USDT", side="buy", amount=5.0, stop_price=99.0, params={"reduceOnly": True}
        )

    def test_default_thresholds_skip_placement(self):
        monitor = _make_monitor(
            pair_config={
                "Amount_Type": "base",
                "quantity": 5,
                "Stop_Loss": -999,
                "Take_Profit": 999,
            }
        )
        monitor.adapter.amount_to_precision.return_value = 5.0

        monitor._place_sltp_orders("buy", 100)

        monitor.adapter.create_take_profit_order.assert_not_called()
        monitor.adapter.create_stop_loss_order.assert_not_called()

    def test_zero_size_skips_placement(self):
        monitor = _make_monitor(
            pair_config={"Amount_Type": "dollar", "quantity": 0, "Stop_Loss": 10, "Take_Profit": 20}
        )
        monitor.adapter.fetch_position.return_value = None

        monitor._place_sltp_orders("buy", 100)

        monitor.adapter.create_take_profit_order.assert_not_called()
        monitor.adapter.create_stop_loss_order.assert_not_called()

    def test_nonzero_retcode_warns_without_updating(self):
        monitor = _make_monitor(
            pair_config={"Amount_Type": "base", "quantity": 5, "Stop_Loss": 10, "Take_Profit": 20}
        )
        monitor.adapter.amount_to_precision.return_value = 5.0
        monitor.adapter.create_take_profit_order.return_value = {"retCode": 1, "retMsg": "rejected"}
        monitor.adapter.create_stop_loss_order.return_value = {"retCode": 0}

        monitor._place_sltp_orders("buy", 100)

        assert monitor._last_tp is None
        assert monitor._last_sl == 10

    def test_not_implemented_error_falls_back_to_polling(self):
        monitor = _make_monitor(
            pair_config={"Amount_Type": "base", "quantity": 5, "Stop_Loss": 10, "Take_Profit": 20}
        )
        monitor.adapter.amount_to_precision.return_value = 5.0
        monitor.adapter.create_take_profit_order.side_effect = NotImplementedError

        monitor._place_sltp_orders("buy", 100)

        assert monitor._last_tp is None


class TestMonitorLossProfit:
    def test_sl_hit_closes_position(self):
        monitor = _make_monitor(
            pair_config={
                "SLTP_Type": "percentage",
                "SL_Exit": "sl",
                "Stop_Loss": -5,
                "Take_Profit": 20,
            }
        )
        breached = {"notional": 100, "unrealizedPnl": -10}
        safe = {"notional": 100, "unrealizedPnl": 0}
        calls = {"n": 0}

        def fetch_position(symbol):
            calls["n"] += 1
            return breached if calls["n"] == 1 else safe

        monitor.adapter.fetch_position.side_effect = fetch_position
        monitor._stop_event = _FakeEvent()
        monitor.monitoring = True

        with mock.patch("apps.trading.engines.grid_monitor.time.sleep", _fast_sleep):
            thread = threading.Thread(
                target=monitor._monitor_loss_profit, args=("buy",), daemon=True
            )
            thread.start()
            ok = _wait_until(lambda: monitor._close_all_orders_cb.called)
            monitor.monitoring = False
            monitor._stop_event.set()
            thread.join(timeout=3.0)

        assert ok
        monitor._close_all_orders_cb.assert_called_once_with("SL hit Position and closed")

    def test_tp_hit_closes_position(self):
        monitor = _make_monitor(
            pair_config={
                "SLTP_Type": "percentage",
                "SL_Exit": "tp",
                "Stop_Loss": -999,
                "Take_Profit": 20,
            }
        )
        breached = {"notional": 100, "unrealizedPnl": 10}
        safe = {"notional": 100, "unrealizedPnl": 0}
        calls = {"n": 0}

        def fetch_position(symbol):
            calls["n"] += 1
            return breached if calls["n"] == 1 else safe

        monitor.adapter.fetch_position.side_effect = fetch_position
        monitor._stop_event = _FakeEvent()
        monitor.monitoring = True

        with mock.patch("apps.trading.engines.grid_monitor.time.sleep", _fast_sleep):
            thread = threading.Thread(
                target=monitor._monitor_loss_profit, args=("buy",), daemon=True
            )
            thread.start()
            ok = _wait_until(lambda: monitor._close_all_orders_cb.called)
            monitor.monitoring = False
            monitor._stop_event.set()
            thread.join(timeout=3.0)

        assert ok
        monitor._close_all_orders_cb.assert_called_once_with("TP hit Position and closed")

    def test_no_threshold_does_not_close(self):
        monitor = _make_monitor(
            pair_config={
                "SLTP_Type": "percentage",
                "SL_Exit": "none",
                "Stop_Loss": -999,
                "Take_Profit": 999,
            }
        )
        monitor.adapter.fetch_position.return_value = {"notional": 100, "unrealizedPnl": -50}
        monitor._stop_event = _FakeEvent()
        monitor.monitoring = True

        with mock.patch("apps.trading.engines.grid_monitor.time.sleep", _fast_sleep):
            thread = threading.Thread(
                target=monitor._monitor_loss_profit, args=("buy",), daemon=True
            )
            thread.start()
            _orig_sleep(0.05)
            monitor.monitoring = False
            monitor._stop_event.set()
            thread.join(timeout=3.0)

        monitor._close_all_orders_cb.assert_not_called()

    def test_stop_event_terminates_loop(self):
        monitor = _make_monitor(pair_config={"SLTP_Type": "percentage", "SL_Exit": "both"})
        event = _FakeEvent()
        event.set()
        monitor._stop_event = event
        monitor.monitoring = True

        with mock.patch("apps.trading.engines.grid_monitor.time.sleep", _fast_sleep):
            thread = threading.Thread(
                target=monitor._monitor_loss_profit, args=("buy",), daemon=True
            )
            thread.start()
            thread.join(timeout=3.0)

        assert not thread.is_alive()
        monitor._close_all_orders_cb.assert_not_called()


class TestMonitorGridOrders:
    def _run_grid_loop(
        self, monitor, side="buy", entry_price=50000, favor_levels=None, against_levels=None
    ):
        monitor.monitoring = True
        thread = threading.Thread(
            target=monitor._monitor_grid_orders,
            args=(side, entry_price, favor_levels or [], against_levels or [], 0.01, 0.01),
            daemon=True,
        )
        thread.start()
        return thread

    def _stop_grid_loop(self, monitor, thread):
        monitor.monitoring = False
        thread.join(timeout=3.0)
        assert not thread.is_alive()

    def test_filled_favor_level_replaced_at_entry(self):
        monitor = _make_monitor()
        monitor.adapter.fetch_open_orders.return_value = [
            {"price": "50100", "side": "sell", "id": "sell1"}
        ]

        def fetch_order(order_id, symbol):
            return {"status": "closed"} if order_id == "sell1" else {"status": "new"}

        monitor.adapter.fetch_order.side_effect = fetch_order

        thread = self._run_grid_loop(monitor)
        ok = _wait_until(lambda: monitor._create_order_cb.called)
        self._stop_grid_loop(monitor, thread)

        assert ok
        monitor._create_order_cb.assert_called_once_with("limit", "buy", 0.01, 50000.0)
        assert monitor.against_lvl == [50000.0]
        assert monitor.favor_lvl == []

    def test_filled_against_level_replaced_at_entry(self):
        monitor = _make_monitor()
        monitor.adapter.fetch_open_orders.return_value = [
            {"price": "49900", "side": "buy", "id": "buy1"}
        ]

        def fetch_order(order_id, symbol):
            return {"status": "closed"} if order_id == "buy1" else {"status": "new"}

        monitor.adapter.fetch_order.side_effect = fetch_order

        thread = self._run_grid_loop(monitor, side="buy")
        ok = _wait_until(lambda: monitor._create_order_cb.called)
        self._stop_grid_loop(monitor, thread)

        assert ok
        monitor._create_order_cb.assert_called_once_with("limit", "sell", 0.01, 50000.0)
        assert monitor.favor_lvl == [50000.0]
        assert monitor.against_lvl == []

    def test_unfilled_orders_do_not_reorder(self):
        monitor = _make_monitor()
        monitor.adapter.fetch_open_orders.return_value = [
            {"price": "50100", "side": "sell", "id": "sell1"}
        ]
        monitor.adapter.fetch_order.return_value = {"status": "new"}

        thread = self._run_grid_loop(monitor)
        _orig_sleep(0.05)
        self._stop_grid_loop(monitor, thread)

        monitor._create_order_cb.assert_not_called()

    def test_loop_exits_when_monitoring_stops(self):
        monitor = _make_monitor()

        with mock.patch("apps.trading.engines.grid_monitor.time.sleep", _fast_sleep):
            thread = self._run_grid_loop(monitor)
            _orig_sleep(0.02)
            self._stop_grid_loop(monitor, thread)

        assert not thread.is_alive()


@pytest.mark.django_db
class TestUpdateHeartbeat:
    def test_no_bot_id_is_noop(self):
        monitor = _make_monitor(bot_config={"bot_type": "grid"})
        monitor._update_heartbeat()

    def test_grid_bot_heartbeat_updated(self, user):
        from apps.bots.models import GridBot

        bot = GridBot.objects.create(
            user=user,
            bot_name="Grid",
            exchange_name="binance",
            trading_pair="BTC/USDT",
            base_amount=Decimal("100"),
            favor_levels=3,
            against_levels=3,
        )
        monitor = _make_monitor(bot_config={"bot_id": str(bot.id), "bot_type": "grid"})

        monitor._update_heartbeat()

        bot.refresh_from_db()
        assert bot.last_heartbeat is not None

    def test_martingale_bot_heartbeat_updated(self, user):
        from apps.bots.models import MartingaleBot

        bot = MartingaleBot.objects.create(
            user=user,
            bot_name="M",
            exchange_name="binance",
            trading_pair="BTC/USDT",
            base_amount=Decimal("100"),
            favor_levels=3,
            against_levels=3,
        )
        monitor = _make_monitor(bot_config={"bot_id": str(bot.id), "bot_type": "martingale"})

        monitor._update_heartbeat()

        bot.refresh_from_db()
        assert bot.last_heartbeat is not None

    def test_quantum_ai_bot_heartbeat_updated(self, quantum_fund):
        from apps.bots.models import QuantumAIBot

        bot = QuantumAIBot.objects.create(
            fund=quantum_fund, bot_name="Q", exchange_name="binance", trading_pair="BTC/USDT"
        )
        monitor = _make_monitor(bot_config={"bot_id": str(bot.id), "bot_type": "quantum_ai"})

        monitor._update_heartbeat()

        bot.refresh_from_db()
        assert bot.last_heartbeat is not None

    def test_invalid_bot_id_does_not_raise(self):
        monitor = _make_monitor(bot_config={"bot_id": "does-not-exist", "bot_type": "grid"})
        monitor._update_heartbeat()


@pytest.mark.django_db
class TestRefreshSltpIfChanged:
    def test_no_bot_id_returns(self):
        monitor = _make_monitor(bot_config={"bot_type": "grid"})
        monitor._refresh_sltp_if_changed()
        monitor.adapter.create_take_profit_order.assert_not_called()

    def test_unsupported_bot_type_returns(self, user):
        monitor = _make_monitor(bot_config={"bot_id": str(user.id), "bot_type": "quantum_ai"})
        monitor._refresh_sltp_if_changed()
        monitor.adapter.create_take_profit_order.assert_not_called()

    def test_no_change_skips_reapply(self, user):
        from apps.bots.models import GridBot

        bot = GridBot.objects.create(
            user=user,
            bot_name="Grid",
            exchange_name="binance",
            trading_pair="BTC/USDT",
            base_amount=Decimal("100"),
            favor_levels=3,
            against_levels=3,
            take_profit_percent=Decimal("20"),
            stop_loss_percent=Decimal("10"),
        )
        monitor = _make_monitor(bot_config={"bot_id": str(bot.id), "bot_type": "grid"})
        monitor._last_tp = 20.0
        monitor._last_sl = 10.0

        monitor._refresh_sltp_if_changed()

        monitor.adapter.create_take_profit_order.assert_not_called()

    def test_change_reapplies_sltp(self, user):
        from apps.bots.models import GridBot

        bot = GridBot.objects.create(
            user=user,
            bot_name="Grid",
            exchange_name="binance",
            trading_pair="BTC/USDT",
            base_amount=Decimal("100"),
            favor_levels=3,
            against_levels=3,
            take_profit_percent=Decimal("20"),
            stop_loss_percent=Decimal("10"),
        )
        monitor = _make_monitor(
            pair_config={"Amount_Type": "dollar", "quantity": 1000},
            bot_config={"bot_id": str(bot.id), "bot_type": "grid"},
        )
        monitor.current_side = "buy"
        monitor.current_price = 100.0
        monitor.adapter.amount_to_precision.return_value = 10.0
        monitor.adapter.create_take_profit_order.return_value = {"retCode": 0}
        monitor.adapter.create_stop_loss_order.return_value = {"retCode": 0}

        monitor._refresh_sltp_if_changed()

        assert monitor.pair_config["Take_Profit"] == 20.0
        assert monitor.pair_config["Stop_Loss"] == 10.0
        monitor.adapter.create_take_profit_order.assert_called_once()
        assert monitor.adapter.create_take_profit_order.call_args[1]["take_profit_price"] == 102.0
        monitor.adapter.create_stop_loss_order.assert_called_once()
        assert monitor.adapter.create_stop_loss_order.call_args[1]["stop_price"] == 101.0
        assert monitor._last_tp == 20
        assert monitor._last_sl == 10

    def test_invalid_bot_id_does_not_raise(self):
        monitor = _make_monitor(bot_config={"bot_id": "does-not-exist", "bot_type": "grid"})
        monitor._refresh_sltp_if_changed()
        monitor.adapter.create_take_profit_order.assert_not_called()
