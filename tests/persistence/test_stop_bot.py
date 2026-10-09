"""Phase 6a — cross-process bot stop.

Covers the three cooperating layers added by CHG-6a-1..9:

* ``apps.trading.engines.execution`` stop-request primitives (Redis flag)
* ``GridPositionMonitor._check_remote_stop`` polling + teardown callback
* ``apps.trading.tasks.stop_bot`` — flag + in-process teardown + durable DB

See docs/persistence/CHANGES.md.
"""

import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from apps.trading import tasks as trade_tasks
from apps.trading.engines import execution
from apps.trading.engines.grid_monitor import GridPositionMonitor

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_stop_flags():
    """LocMemCache is process-global — keep stop flags from leaking between tests."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


def _mid() -> str:
    """Unique bot id per test so flags can never collide."""
    return str(uuid.uuid4())


def _grid_bot(user, **overrides):
    from apps.bots.models import GridBot

    defaults = dict(
        user=user,
        bot_name="Grid Bot",
        exchange_name="binance",
        trading_pair="BTC/USDT",
        base_amount=Decimal("100"),
        favor_levels=3,
        against_levels=3,
    )
    defaults.update(overrides)
    return GridBot.objects.create(**defaults)


def _signal_bot(user, **overrides):
    from apps.bots.models import SignalBot

    defaults = dict(
        user=user,
        bot_name="Signal Bot",
        exchange_name="binance",
        trading_pair="BTC/USDT",
        bot_id=f"sig-{uuid.uuid4().hex[:10]}",
        default_amount=Decimal("100"),
    )
    defaults.update(overrides)
    return SignalBot.objects.create(**defaults)


def _monitor(bot_id=None, stop_cb=None, **kwargs) -> GridPositionMonitor:
    bot_config = {"bot_id": bot_id} if bot_id else {}
    return GridPositionMonitor(
        MagicMock(),
        symbol="BTC/USDT",
        pair_config=kwargs.get("pair_config", {}),
        bot_config=bot_config,
        create_order_cb=MagicMock(return_value={"id": "o1"}),
        close_all_orders_cb=MagicMock(),
        stop_cb=stop_cb,
    )


# ---------------------------------------------------------------------------
# CHG-6a-1/3 — execution stop-request primitives
# ---------------------------------------------------------------------------


class TestStopRequestPrimitives:
    def test_request_stop_sets_flag(self):
        bot_id = _mid()
        assert execution.stop_requested(bot_id) is False

        execution.request_stop(bot_id)

        assert execution.stop_requested(bot_id) is True

    def test_stop_requested_is_scoped_to_bot(self):
        a, b = _mid(), _mid()
        execution.request_stop(a)

        assert execution.stop_requested(a) is True
        assert execution.stop_requested(b) is False

    def test_clear_stop_request_removes_flag(self):
        bot_id = _mid()
        execution.request_stop(bot_id)
        execution.clear_stop_request(bot_id)

        assert execution.stop_requested(bot_id) is False

    def test_stop_flag_has_ttl(self):
        bot_id = _mid()
        with patch("apps.trading.engines.execution.cache") as mock_cache:
            execution.request_stop(bot_id)

        mock_cache.set.assert_called_once_with(f"bot:stop_req:{bot_id}", 1, execution._STOP_REQ_TTL)
        assert execution._STOP_REQ_TTL == 600

    def test_request_stop_survives_cache_failure(self):
        """A Redis outage must never abort the caller's stop flow."""
        with patch("apps.trading.engines.execution.cache.set", side_effect=RuntimeError("down")):
            execution.request_stop(_mid())  # must not raise

    def test_stop_requested_fails_open_on_cache_failure(self):
        """A Redis blip must not silently kill a healthy bot's monitors."""
        with patch("apps.trading.engines.execution.cache.get", side_effect=RuntimeError("down")):
            assert execution.stop_requested(_mid()) is False

    def test_clear_stop_request_survives_cache_failure(self):
        with patch("apps.trading.engines.execution.cache.delete", side_effect=RuntimeError("down")):
            execution.clear_stop_request(_mid())  # must not raise

    def test_key_format(self):
        assert execution._stop_req_key("abc") == "bot:stop_req:abc"


# ---------------------------------------------------------------------------
# CHG-6a-4/5/6 — GridPositionMonitor polling
# ---------------------------------------------------------------------------


class TestCheckRemoteStop:
    def test_no_flag_returns_false_and_keeps_monitoring(self):
        monitor = _monitor(bot_id=_mid())
        monitor.monitoring = True
        monitor.bot_running = True

        assert monitor._check_remote_stop() is False
        assert monitor.monitoring is True
        assert monitor.bot_running is True
        assert monitor._stop_event.is_set() is False

    def test_missing_bot_id_returns_false(self):
        monitor = _monitor(bot_id=None)
        monitor.monitoring = True
        assert monitor._check_remote_stop() is False
        assert monitor.monitoring is True

    def test_flag_present_tears_down_and_calls_callback(self):
        bot_id = _mid()
        cb = MagicMock()
        monitor = _monitor(bot_id=bot_id, stop_cb=cb)
        monitor.monitoring = True
        monitor.bot_running = True

        execution.request_stop(bot_id)

        assert monitor._check_remote_stop() is True
        assert monitor.monitoring is False
        assert monitor.bot_running is False
        assert monitor._stop_event.is_set() is True
        cb.assert_called_once_with()

    def test_flag_present_without_callback(self):
        bot_id = _mid()
        monitor = _monitor(bot_id=bot_id, stop_cb=None)
        monitor.monitoring = True
        execution.request_stop(bot_id)

        assert monitor._check_remote_stop() is True
        assert monitor.monitoring is False

    def test_fails_open_when_cache_lookup_raises(self):
        monitor = _monitor(bot_id=_mid(), stop_cb=MagicMock())
        monitor.monitoring = True

        with patch(
            "apps.trading.engines.execution.stop_requested",
            side_effect=RuntimeError("redis down"),
        ):
            assert monitor._check_remote_stop() is False

        assert monitor.monitoring is True  # untouched
        assert monitor._stop_event.is_set() is False

    def test_callback_exception_is_swallowed(self):
        """A broken stop_cb must not propagate out of the monitor loop."""
        bot_id = _mid()
        cb = MagicMock(side_effect=RuntimeError("boom"))
        monitor = _monitor(bot_id=bot_id, stop_cb=cb)
        monitor.monitoring = True
        execution.request_stop(bot_id)

        assert monitor._check_remote_stop() is True
        assert monitor.monitoring is False
        cb.assert_called_once_with()

    def test_poll_is_first_statement_of_both_loops(self):
        """Guards the 1s/5s stop latency contract (CHG-6a-6)."""
        import inspect

        from apps.trading.engines import grid_monitor as gm

        grid_src = inspect.getsource(gm.GridPositionMonitor._monitor_grid_orders)
        sltp_src = inspect.getsource(gm.GridPositionMonitor._monitor_loss_profit)
        assert "if self._check_remote_stop():" in grid_src
        assert "if self._check_remote_stop():" in sltp_src
        # ...and it must run before any other work in the try block.
        assert grid_src.index("if self._check_remote_stop():") < grid_src.index(
            "self._heartbeat_counter += 1"
        )
        assert sltp_src.index("if self._check_remote_stop():") < sltp_src.index(
            "self._heartbeat_counter += 1"
        )


# ---------------------------------------------------------------------------
# CHG-6a-9 — tasks.stop_bot
# ---------------------------------------------------------------------------


class TestTaskStopBot:
    def test_sets_cross_process_flag(self, user):
        bot = _grid_bot(user, is_running=True)

        result = trade_tasks.stop_bot(str(bot.id), bot_type="grid")

        assert result == {"success": True, "status": "stopped"}
        assert execution.stop_requested(str(bot.id)) is True

    def test_in_process_engine_is_torn_down(self, user):
        """The engine registry is released even though it was never running."""
        bot = _grid_bot(user, is_running=True)
        engine = MagicMock()
        execution._running_engines[str(bot.id)] = engine

        with (
            patch("apps.trading.engines.execution.save_bot_state"),
            patch(
                "apps.trading.engines.execution._collect_engine_state",
                return_value={},
            ),
        ):
            trade_tasks.stop_bot(str(bot.id), bot_type="grid")

        assert str(bot.id) not in execution._running_engines
        engine.stop_bot.assert_called_once_with()

    def test_running_set_is_cleared(self, user):
        bot = _grid_bot(user, is_running=True)
        assert execution._mark_bot_starting(str(bot.id)) is True

        trade_tasks.stop_bot(str(bot.id), bot_type="grid")

        assert not execution._is_bot_running(str(bot.id))

    def test_db_flags_written(self, user):
        bot = _grid_bot(user, is_running=True)

        trade_tasks.stop_bot(str(bot.id), bot_type="grid")

        bot.refresh_from_db()
        assert bot.is_running is False
        assert bot.stopped_at is not None

    def test_survives_engine_teardown_failure(self, user):
        """Step 2 blowing up must not lose step 1 (flag) or step 3 (DB)."""
        bot = _grid_bot(user, is_running=True)

        with patch(
            "apps.trading.engines.execution.stop_bot",
            side_effect=RuntimeError("engine exploded"),
        ):
            result = trade_tasks.stop_bot(str(bot.id), bot_type="grid")

        assert result == {"success": True, "status": "stopped"}
        assert execution.stop_requested(str(bot.id)) is True
        bot.refresh_from_db()
        assert bot.is_running is False

    def test_signal_bot_without_running_columns(self, user):
        """SignalBot has neither is_running nor stopped_at — must not raise."""
        bot = _signal_bot(user)

        result = trade_tasks.stop_bot(str(bot.id), bot_type="signal")

        assert result == {"success": True, "status": "stopped"}

    def test_not_found(self):
        missing = "11111111-1111-1111-1111-111111111111"
        result = trade_tasks.stop_bot(missing, bot_type="grid")

        assert result == {"success": False, "error": f"Bot not found: {missing}"}

    def test_return_shape_is_stable(self, user):
        """tests/engines/test_trading_tasks.py asserts this exact dict."""
        bot = _grid_bot(user, is_running=True)
        result = trade_tasks.stop_bot(str(bot.id), bot_type="grid")

        assert set(result.keys()) == {"success", "status"}
        assert result == {"success": True, "status": "stopped"}

    def test_request_stop_runs_before_teardown(self, user):
        """The flag must be published first so another worker starts early."""
        bot = _grid_bot(user, is_running=True)
        order = []

        with (
            patch(
                "apps.trading.engines.execution.request_stop",
                side_effect=lambda bid: order.append("flag"),
            ),
            patch(
                "apps.trading.engines.execution.stop_bot",
                side_effect=lambda *a, **k: order.append("teardown"),
            ),
        ):
            trade_tasks.stop_bot(str(bot.id), bot_type="grid")

        assert order == ["flag", "teardown"]


# ---------------------------------------------------------------------------
# CHG-6a-3 — start clears a stale flag
# ---------------------------------------------------------------------------


class TestStartClearsStaleStopFlag:
    def test_run_bot_clears_stale_flag(self):
        """A restart within TTL must not be killed by the previous stop."""
        bot_id = _mid()
        execution.request_stop(bot_id)
        assert execution.stop_requested(bot_id) is True

        execution.clear_stop_request(bot_id)

        assert execution.stop_requested(bot_id) is False

    def test_clear_is_invoked_by_run_bot(self):
        """Structural guard: run_bot must clear the flag before any engine work."""
        import inspect

        src = inspect.getsource(execution.run_bot)
        assert "clear_stop_request(bot_id)" in src
        # ...and before the bot-type dispatch that builds the engine config.
        assert src.index("clear_stop_request(bot_id)") < src.index('if bot_type == "quantum_ai":')
