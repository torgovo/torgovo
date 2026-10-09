"""Phase 3 — snapshot / restore (crash-consistent persistence).

Covers CHG-3-1..4 (docs/persistence/CHANGES.md):

* ``apps.trading.state`` primitives — collect / apply / throttled save / restore
* ``GridPositionMonitor.snapshot_cb`` wiring (both monitor loops)
* ``BotEngine`` wiring — ctor binding, ``_snapshot_tick``, startBot force calls
* ``tasks.stop_bot`` durable STOPPED flush (step 4)

All stubs are pure in-memory (SimpleNamespace / MagicMock) — no adapter or
strategy I/O. DB tests rely on the project root ``user`` fixture + pytestmark.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.trading import state as rt
from apps.trading import tasks as trade_tasks
from apps.trading.engines.bot_engine import BotEngine
from apps.trading.engines.grid_monitor import GridPositionMonitor

pytestmark = pytest.mark.django_db


# ===========================================================================
# Stub builders — every call returns a FRESH object (no cross-test bleed)
# ===========================================================================


def _stub_engine(**overrides):
    """Minimal BotEngine stand-in — collect/apply only touch plain attrs."""
    eng = SimpleNamespace(
        config={"bot_id": "1001", "bot_type": "grid"},
        current_side="None",
        count=0,
        current_price=0.0,
        reason="",
        PrevReason="",
        last_trade_pnl=0.0,
        favor_lvl=[],
        against_lvl=[],
        Percentage=0.0,
        Unrealized_Pnl=0.0,
        signals_generated=0,
        orders_executed=0,
        EMA=0.0,
        RSI=0.0,
        PrevRSI=0.0,
        BB=None,
        RSI_color=None,
        RSI_prev_color=None,
        pair_config={"RSI_Lower": 30, "RSI_Upper": 70},
        grid_monitor=None,
        monitoring=False,
        bot_running=False,
        NoTrade=True,
        BuyTrade=False,
        SellTrade=False,
        EmaBuyCondition=False,
        EmaSellCondition=False,
        RsiBuyCondition=False,
        RsiSellCondition=False,
        BBBuyCondition=False,
        BBSellCondition=False,
        _sync_strategy=MagicMock(),
    )
    for key, value in overrides.items():
        setattr(eng, key, value)
    return eng


def _stub_gm(**overrides):
    """GridPositionMonitor mirror — the fields apply_state writes into gm.

    ``Percentage``/``Unrealized_Pnl`` are ALWAYS present: apply_state reads
    them back via ``engine.Percentage = gm.Percentage`` after the gm branch.
    """
    gm = SimpleNamespace(
        current_side="None",
        count=0,
        current_price=0.0,
        reason="",
        PrevReason="",
        last_trade_pnl=0.0,
        favor_lvl=[],
        against_lvl=[],
        Percentage=0.0,
        Unrealized_Pnl=0.0,
        monitoring=False,
        bot_running=False,
    )
    for key, value in overrides.items():
        setattr(gm, key, value)
    return gm


def _base_payload(**overrides):
    """Full schema-v1 payload (every key collect_state emits)."""
    payload = {
        "schema": rt.SNAPSHOT_SCHEMA,
        "ts": "2026-09-27T12:00:00+00:00",
        "side": "Buy",
        "count": 1,
        "price": 100.0,
        "reason": "RSI oversold",
        "prev_reason": "BB cross",
        "last_trade_pnl": 1.5,
        "favor_lvl": [99.0, 98.0],
        "against_lvl": [101.0, 102.0],
        "percentage": 2.5,
        "unrealized_pnl": 1.25,
        "signals_generated": 4,
        "orders_executed": 2,
        "indicators": {
            "EMA": 95.0,
            "RSI": 42.0,
            "PrevRSI": 20.0,
            "BB": "Closed Below Lower Band",
            "RSI_color": "white",
            "RSI_prev_color": "white",
        },
        "monitoring": True,
        "bot_running": True,
    }
    payload.update(overrides)
    return payload


def _engine_config(**overrides):
    """Fresh config per call — BotEngine.__init__ mutates the dict in place."""
    cfg = {
        "bot_id": "1001",
        "bot_type": "grid",
        "bot_name": "G",
        "symbol": "BTC/USDT",
        "user_id": None,
        "exchange_name": "binance",
        "parameters": {
            "symbol": "BTC/USDT",
            "RSI_Lower": 30,
            "RSI_Upper": 70,
        },
    }
    cfg.update(overrides)
    return cfg


# ===========================================================================
# 1. collect_state — pure serialization (schema v1 shape)
# ===========================================================================


class TestCollectState:
    def test_trade_state_and_iso_timestamp(self):
        eng = _stub_engine(
            current_side="Buy",
            count=1,
            current_price=100.0,
            reason="entry",
            PrevReason="prev",
        )
        payload = rt.collect_state(eng)
        assert payload["schema"] == rt.SNAPSHOT_SCHEMA == 1
        assert payload["side"] == "Buy"
        assert payload["count"] == 1
        assert payload["price"] == 100.0
        assert payload["reason"] == "entry"
        assert payload["prev_reason"] == "prev"
        datetime.fromisoformat(payload["ts"])  # must be valid ISO-8601

    def test_prefers_monitor_copies_for_levels_and_pnl(self):
        eng = _stub_engine(
            favor_lvl=[1.0],
            against_lvl=[2.0],
            grid_monitor=_stub_gm(
                favor_lvl=[9.0],
                against_lvl=[8.0],
                Percentage=3.5,
                Unrealized_Pnl=1.5,
                monitoring=True,
                bot_running=True,
            ),
        )
        payload = rt.collect_state(eng)
        # Monitor owns live levels while threads run — engine copies ignored.
        assert payload["favor_lvl"] == [9.0]
        assert payload["against_lvl"] == [8.0]
        assert payload["percentage"] == 3.5
        assert payload["unrealized_pnl"] == 1.5
        assert payload["monitoring"] is True
        assert payload["bot_running"] is True

    def test_without_monitor_levels_fall_back_but_pnl_stays_zero(self):
        eng = _stub_engine(
            favor_lvl=[1.0],
            against_lvl=[2.0],
            Percentage=7.0,
            monitoring=True,
            bot_running=True,
            grid_monitor=None,
        )
        payload = rt.collect_state(eng)
        assert payload["favor_lvl"] == [1.0]  # engine copy is the fallback
        assert payload["against_lvl"] == [2.0]
        # percentage / monitoring / bot_running are monitor-owned (gm-only):
        assert payload["percentage"] == 0.0
        assert payload["monitoring"] is False
        assert payload["bot_running"] is False

    def test_derived_condition_flags_excluded(self):
        payload = rt.collect_state(_stub_engine(NoTrade=True, BuyTrade=False, EmaBuyCondition=True))
        # Derived flags are recomputed by apply_state — never stored.
        for key in (
            "NoTrade",
            "BuyTrade",
            "SellTrade",
            "EmaBuyCondition",
            "RsiBuyCondition",
            "BBBuyCondition",
        ):
            assert key not in payload


# ===========================================================================
# 2. apply_state — restore + derived-flag recomputation
# ===========================================================================


class TestApplyState:
    def test_roundtrip_into_engine_and_monitor(self):
        payload = _base_payload()
        eng = _stub_engine(grid_monitor=_stub_gm())
        assert rt.apply_state(eng, payload) is True

        # Raw state
        assert eng.current_side == "Buy"
        assert eng.count == 1
        assert eng.current_price == 100.0
        assert eng.reason == "RSI oversold"
        assert eng.PrevReason == "BB cross"
        assert eng.favor_lvl == [99.0, 98.0]

        # Mirrored into the monitor (it owns the live monitoring copy)
        gm = eng.grid_monitor
        assert gm.current_side == "Buy"
        assert gm.count == 1
        assert gm.current_price == 100.0
        assert gm.favor_lvl == [99.0, 98.0]
        assert gm.Percentage == 2.5
        assert eng.Percentage == 2.5  # copied back out of the gm branch

        # Strategy resync hook fires
        eng._sync_strategy.assert_called_once_with()

    def test_recomputes_buy_flags(self):
        payload = _base_payload(
            side="Buy",
            count=1,
            price=100.0,
            indicators={
                "EMA": 90.0,
                "RSI": 40.0,
                "PrevRSI": 20.0,
                "BB": "Closed Below Lower Band",
                "RSI_color": "white",
                "RSI_prev_color": "white",
            },
        )
        eng = _stub_engine()
        assert rt.apply_state(eng, payload) is True
        assert eng.EmaBuyCondition is True  # 100 >= 90 != 0
        assert eng.RsiBuyCondition is True  # 20 <= 30 + white
        assert eng.BBBuyCondition is True
        assert eng.BuyTrade is True
        assert eng.NoTrade is False
        assert eng.EmaSellCondition is False

    def test_recomputes_sell_and_flat_flags(self):
        payload = _base_payload(
            side="Sell",
            count=0,
            price=110.0,
            indicators={
                "EMA": 120.0,
                "RSI": 75.0,
                "PrevRSI": 80.0,
                "BB": "Closed Above Upper Band",
                "RSI_color": "white",
                "RSI_prev_color": "white",
            },
        )
        eng = _stub_engine()
        assert rt.apply_state(eng, payload) is True
        assert eng.EmaSellCondition is True  # 110 <= 120 != 0
        assert eng.RsiSellCondition is True  # 80 >= 70 + white
        assert eng.BBSellCondition is True
        assert eng.SellTrade is False  # count is 0
        assert eng.NoTrade is False  # side is "Sell"
        assert eng.EmaBuyCondition is False

    def test_unknown_schema_refused_before_mutation(self):
        eng = _stub_engine(count=0)
        assert rt.apply_state(eng, {"schema": 99, "count": 5}) is False
        assert eng.count == 0  # nothing applied

    def test_empty_or_non_dict_payload_refused(self):
        eng = _stub_engine()
        assert rt.apply_state(eng, {}) is False
        assert rt.apply_state(eng, [1, 2]) is False
        eng._sync_strategy.assert_not_called()

    def test_partial_payload_only_touches_present_keys(self):
        eng = _stub_engine()  # grid_monitor=None
        assert rt.apply_state(eng, {"schema": 1, "count": 2}) is True
        assert eng.count == 2
        assert eng.current_side == "None"  # untouched (key absent)
        assert eng.NoTrade is False  # recomputed: count is now 2
        eng._sync_strategy.assert_called_once_with()

    def test_partial_payload_with_monitor_mirrors_count(self):
        eng = _stub_engine(grid_monitor=_stub_gm())
        assert rt.apply_state(eng, {"schema": 1, "count": 3}) is True
        assert eng.count == 3
        assert eng.grid_monitor.count == 3  # mirror block runs unconditionally

    def test_monitoring_and_bot_running_not_restored(self):
        # Threads must be started explicitly by Phase 4 recovery — never
        # revived by applying a payload.
        eng = _stub_engine(monitoring=False, bot_running=False, grid_monitor=_stub_gm())
        payload = _base_payload(monitoring=True, bot_running=True)
        assert rt.apply_state(eng, payload) is True
        assert eng.monitoring is False
        assert eng.bot_running is False
        assert eng.grid_monitor.monitoring is False
        assert eng.grid_monitor.bot_running is False

    def test_without_monitor_core_state_still_applies(self):
        eng = _stub_engine()  # grid_monitor=None — percentage has no home
        payload = _base_payload()
        assert rt.apply_state(eng, payload) is True
        assert eng.current_side == "Buy"
        assert eng.count == 1
        assert eng.current_price == 100.0
        assert eng.Percentage == 0.0  # P/L only flows through the gm branch
        eng._sync_strategy.assert_called_once_with()


# ===========================================================================
# 3. snapshot_engine — throttle / force / failure isolation (patched writer)
# ===========================================================================


class TestSnapshotThrottle:
    def test_first_tick_saves_then_throttles_then_force_bypasses(self):
        eng = _stub_engine()
        with patch("apps.trading.state.save_snapshot") as save:
            assert rt.snapshot_engine(eng) is True
            assert save.call_count == 1
            # Second regular tick inside the 5s window — no write.
            assert rt.snapshot_engine(eng) is False
            assert save.call_count == 1
            # force=True bypasses the throttle (lifecycle points).
            assert rt.snapshot_engine(eng, force=True) is True
            assert save.call_count == 2
        assert hasattr(eng, "_snapshot_monotonic")

    def test_missing_bot_id_skips_write(self):
        eng = _stub_engine(config={})  # not DB-tracked
        with patch("apps.trading.state.save_snapshot") as save:
            assert rt.snapshot_engine(eng) is False
        save.assert_not_called()

    def test_save_failure_never_raises_and_keeps_stale_stamp(self):
        eng = _stub_engine()
        eng._snapshot_monotonic = 123.0
        with patch(
            "apps.trading.state.save_snapshot",
            side_effect=RuntimeError("db down"),
        ):
            assert rt.snapshot_engine(eng, force=True) is False
        # Stamp advances ONLY on success — next tick retries immediately.
        assert eng._snapshot_monotonic == 123.0

    def test_identity_defaults_and_worker_stamp(self):
        eng = _stub_engine(config={"bot_id": 7})  # bot_type omitted -> grid
        with patch("apps.trading.state.save_snapshot") as save:
            assert rt.snapshot_engine(eng) is True
        args, kwargs = save.call_args
        assert args[0] == "grid"
        assert args[1] == "7"
        assert kwargs["worker"] == rt._worker_id()
        assert isinstance(args[2], dict)
        assert args[2]["schema"] == rt.SNAPSHOT_SCHEMA


# ===========================================================================
# 4. save_snapshot / restore_engine — real rows (status is never clobbered)
# ===========================================================================


class TestSnapshotPersistence:
    def test_save_creates_running_row_with_payload(self):
        payload = _base_payload()
        rt.save_snapshot("grid", "1001", payload)
        row = rt.get("grid", "1001")
        assert row is not None
        assert row.status == rt.RUNNING
        assert row.worker == ""  # model default when worker omitted
        assert row.state == payload
        assert row.heartbeat_at is not None

    def test_save_preserves_existing_status_and_worker(self):
        rt.upsert("grid", "1002", status=rt.STOPPING, worker="w1")
        rt.save_snapshot("grid", "1002", {"schema": 1})
        row = rt.get("grid", "1002")
        assert row.status == rt.STOPPING  # heartbeat-only write
        assert row.worker == "w1"
        assert row.state == {"schema": 1}

    def test_save_with_explicit_worker_updates_worker_only(self):
        rt.upsert("grid", "1003", status=rt.STOPPED, worker="w1")
        rt.save_snapshot("grid", "1003", {"schema": 1}, worker="w7")
        row = rt.get("grid", "1003")
        assert row.worker == "w7"
        assert row.status == rt.STOPPED  # status untouched by snapshots

    def test_save_then_restore_roundtrip(self):
        eng1 = _stub_engine(
            current_side="Buy",
            count=1,
            current_price=100.0,
            reason="e",
            EMA=90.0,
            PrevRSI=20.0,
            RSI_color="white",
            BB="Closed Below Lower Band",
            grid_monitor=_stub_gm(monitoring=True, bot_running=True),
        )
        rt.save_snapshot("grid", "1001", rt.collect_state(eng1), worker="w9")

        eng2 = _stub_engine()  # cold construction, all defaults
        assert rt.restore_engine(eng2) is True
        assert eng2.current_side == "Buy"
        assert eng2.count == 1
        assert eng2.current_price == 100.0
        assert eng2.reason == "e"
        assert eng2.EmaBuyCondition is True  # recomputed, not replayed
        assert eng2.BuyTrade is True

    def test_cold_start_returns_false(self):
        assert rt.restore_engine(_stub_engine(config={"bot_id": "9999"})) is False

    def test_corrupt_payload_returns_false_without_mutation(self):
        rt.upsert("grid", "1004", state={"schema": 1, "count": "not-a-number"})
        eng = _stub_engine(config={"bot_id": "1004"}, count=0)
        assert rt.restore_engine(eng) is False  # int() blew up -> swallowed
        assert eng.count == 0

    def test_restore_without_bot_id_returns_false(self):
        assert rt.restore_engine(_stub_engine(config={})) is False


# ===========================================================================
# 5. GridPositionMonitor.snapshot_cb wiring — both monitor loops
# ===========================================================================


def _monitor(bot_id=None, snapshot_cb=None, pair_config=None):
    """Real GridPositionMonitor with a fully mocked adapter."""
    adapter = MagicMock()
    adapter.get_current_price.return_value = 100.0
    adapter.fetch_open_orders.return_value = []
    return GridPositionMonitor(
        adapter,
        symbol="BTC/USDT",
        pair_config=pair_config if pair_config is not None else {},
        bot_config={"bot_id": bot_id} if bot_id else {},
        create_order_cb=MagicMock(return_value={"id": "o1"}),
        close_all_orders_cb=MagicMock(),
        snapshot_cb=snapshot_cb,
    )


class TestMonitorWiring:
    def test_snapshot_cb_defaults_to_none(self):
        assert _monitor()._snapshot_cb is None

    def test_snapshot_cb_stored_by_identity(self):
        cb = MagicMock()
        m = _monitor(snapshot_cb=cb)
        assert m._snapshot_cb is cb

    def test_grid_loop_takes_one_snapshot_tick_per_iteration(self):
        m = _monitor(snapshot_cb=MagicMock())
        m.monitoring = True
        # Iter 1: no stop -> snapshot tick; iter 2: stop -> break.
        calls = {"n": 0}

        def _remote():
            calls["n"] += 1
            return calls["n"] >= 2

        m._check_remote_stop = MagicMock(side_effect=_remote)
        m._update_heartbeat = MagicMock()
        with patch("apps.trading.engines.grid_monitor.time.sleep", lambda _s: None):
            m._monitor_grid_orders("Buy", 100.0, [], [], 1.0, 1.0)
        assert m._snapshot_cb.call_count == 1
        # Counter 1 < interval 60 -> no heartbeat write on the snapshot tick.
        m._update_heartbeat.assert_not_called()

    def test_loss_loop_takes_one_snapshot_tick_per_iteration(self):
        m = _monitor(snapshot_cb=MagicMock())
        m.monitoring = True
        m._check_remote_stop = MagicMock(return_value=False)
        m._check_loss_profit_percent = MagicMock(return_value=0.0)
        # is_set=False keeps the loop entered; wait=True breaks after 1 pass.
        m._stop_event = MagicMock()
        m._stop_event.is_set.return_value = False
        m._stop_event.wait.return_value = True
        with patch("apps.trading.engines.grid_monitor.time.sleep", lambda _s: None):
            m._monitor_loss_profit("Buy")
        assert m._snapshot_cb.call_count == 1


# ===========================================================================
# 6. BotEngine wiring — ctor binding, _snapshot_tick, startBot force calls
# ===========================================================================


def _make_engine(**cfg_over):
    """Real BotEngine with a mocked executor (DB-free construction)."""
    cfg = _engine_config(**cfg_over)
    with patch("apps.trading.engines.bot_engine.BotExecutor") as mock_cls:
        mock_cls.from_config.return_value = MagicMock()
        eng = BotEngine(cfg)
    # startBot path: ticker fetch must return a real dict (MagicMock keys
    # would produce a child mock as the price).
    eng.executor.adapter.fetch_ticker.return_value = {"last": 50000.0}
    # Entry eval is out of scope for wiring tests.
    eng.update_conditions = MagicMock()
    eng.strategy._evaluate_conditions = MagicMock(return_value={})
    eng.strategy._check_entry_conditions = MagicMock(return_value=None)
    return eng


class TestEngineWiring:
    def test_ctor_binds_snapshot_tick_to_engine(self):
        eng = _make_engine()
        cb = eng.grid_monitor._snapshot_cb
        assert cb is not None
        assert cb.__self__ is eng
        assert cb.__func__ is BotEngine._snapshot_tick

    def test_snapshot_tick_delegates_to_state_module(self):
        eng = _make_engine()
        with patch("apps.trading.state.snapshot_engine") as snap:
            snap.return_value = True
            assert eng._snapshot_tick() is True
            snap.assert_called_once_with(eng, force=False)
            snap.reset_mock()
            assert eng._snapshot_tick(force=True) is True
            snap.assert_called_once_with(eng, force=True)

    def test_startbot_normal_path_force_snapshots_after_eval(self):
        eng = _make_engine()
        with patch("apps.trading.state.snapshot_engine") as snap:
            eng.startBot()
        eng.update_conditions.assert_called_once_with()
        eng.strategy._evaluate_conditions.assert_called_once_with(50000.0)
        eng.strategy._check_entry_conditions.assert_called_once_with({}, 50000.0, "BTC/USDT:USDT")
        snap.assert_called_once_with(eng, force=True)
        assert eng.bot_running is True
        assert eng.current_side == "None"  # no signal -> no order placed

    def test_startbot_restore_mode_skips_entry_eval(self):
        eng = _make_engine(restore_mode=True)
        eng._start_monitoring_for_existing_position = MagicMock()
        with patch("apps.trading.state.snapshot_engine") as snap:
            eng.startBot()
        eng._start_monitoring_for_existing_position.assert_called_once_with()
        # Restore attaches to an open position — no new entry evaluation.
        eng.strategy._evaluate_conditions.assert_not_called()
        eng.strategy._check_entry_conditions.assert_not_called()
        snap.assert_called_once_with(eng, force=True)


# ===========================================================================
# 7. tasks.stop_bot — durable STOPPED flush (step 4)
# ===========================================================================


def _mid():
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


class TestStopBotFlush:
    def test_stop_flushes_stopped_status_and_durable_flags(self, user):
        bot = _grid_bot(user, is_running=True)
        bid = str(bot.id)
        rt.upsert(
            "grid",
            bid,
            state={"schema": 1, "count": 1},
            status=rt.RUNNING,
            worker="w1",
        )

        result = trade_tasks.stop_bot(bid, bot_type="grid")

        assert result == {"success": True, "status": "stopped"}
        row = rt.get("grid", bid)
        assert row is not None
        assert row.status == rt.STOPPED
        assert row.state == {"schema": 1, "count": 1}  # payload preserved
        bot.refresh_from_db()
        assert bot.is_running is False
        assert bot.stopped_at is not None

    def test_stop_without_runtime_row_still_succeeds(self, user):
        bot = _grid_bot(user, is_running=True)
        bid = str(bot.id)
        result = trade_tasks.stop_bot(bid, bot_type="grid")
        assert result == {"success": True, "status": "stopped"}
        # No orphan row is created for a bot that was never snapshotted.
        assert rt.get("grid", bid) is None
        bot.refresh_from_db()
        assert bot.is_running is False

    def test_status_flush_failure_does_not_fail_stop(self, user):
        bot = _grid_bot(user, is_running=True)
        bid = str(bot.id)
        rt.upsert("grid", bid, status=rt.RUNNING, worker="w1")
        with patch(
            "apps.trading.state.set_status",
            side_effect=RuntimeError("db down"),
        ):
            result = trade_tasks.stop_bot(bid, bot_type="grid")
        # Durable flags still landed; the row keeps its previous status.
        assert result == {"success": True, "status": "stopped"}
        row = rt.get("grid", bid)
        assert row.status == rt.RUNNING
        assert row.worker == "w1"
        bot.refresh_from_db()
        assert bot.is_running is False
        assert bot.stopped_at is not None
