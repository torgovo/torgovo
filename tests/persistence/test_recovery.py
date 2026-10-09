"""
Tests for Phase 4 — boot recovery (CHG-4-1..3).

Covers:
  * ``state.recover_running_bots`` — stale-row scan, dispatch decision
    matrix (position/idle/empty), orphan-row cleanup, heartbeat dedupe,
    error isolation (one bad candidate never blocks the next)
  * ``state._recovery_model`` / ``_payload_has_position`` unit contracts
  * ``apps._install_celery_recovery_hook`` — worker_ready-only wiring,
    weak=False, exception-swallowing receiver
  * ``TradingConfig.ready()`` — recovery hook installed only for Celery
    workers, never fatal
  * ``BotEngine.startBot(restore_mode=True)`` — restore applied BEFORE
    attach, payload visible on the engine, no entry eval

Run:  .venv/bin/python -m pytest tests/persistence/test_recovery.py -q
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.apps import apps as django_apps
from django.utils import timezone

from apps.bots.models import GridBot, MartingaleBot, QuantumAIBot
from apps.trading import apps as trading_apps
from apps.trading import state as rt
from apps.trading.models import BotRuntimeState
from tests.persistence.test_snapshot_restore import _make_engine

pytestmark = pytest.mark.django_db


# ── helpers ─────────────────────────────────────────────────────────────


def _grid_bot(user, **overrides):
    from decimal import Decimal

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


def _stale_row(bot_type, bot_id, state=None, seconds_ago=60):
    """Create a RUNNING row and age its heartbeat into the past."""
    row = rt.upsert(bot_type, bot_id, state)
    BotRuntimeState.objects.filter(pk=row.pk).update(
        heartbeat_at=timezone.now() - timedelta(seconds=seconds_ago)
    )
    row.refresh_from_db()
    return row


_POSITION = {"schema": 1, "side": "Buy", "count": 1, "price": 50000.0, "reason": "entry"}
_IDLE = {"schema": 1, "side": "None", "count": 0, "price": 50000.0}


def _patch_dispatch():
    """Patch the dispatch target state.py re-imports at call time."""
    return patch("apps.trading.tasks.run_trading_bot")


# ── recover_running_bots — dispatch matrix ──────────────────────────────


class TestRecoverRunningBots:
    def test_stale_position_bot_dispatches_restore(self, user):
        bot = _grid_bot(user, is_running=True)
        _stale_row("grid", str(bot.id), _POSITION)
        old_hb = timezone.now() - timedelta(seconds=60)

        with _patch_dispatch() as mock_task:
            summary = rt.recover_running_bots()

        assert summary["recovered"] == [f"grid/{bot.id}"]
        assert summary["errors"] == []
        mock_task.delay.assert_called_once_with(str(bot.id), "grid", restore_mode=True)
        # Heartbeats refreshed: row dedupes a sibling worker booting
        # seconds later; model heartbeat holds off the beat watchdog.
        row = BotRuntimeState.objects.get(bot_type="grid", bot_id=str(bot.id))
        assert row.status == rt.RUNNING
        assert row.heartbeat_at > old_hb + timedelta(seconds=30)
        bot.refresh_from_db()
        assert bot.last_heartbeat > old_hb + timedelta(seconds=30)

    def test_fresh_row_not_considered(self, user):
        bot = _grid_bot(user, is_running=True)
        rt.upsert("grid", str(bot.id), _POSITION)  # heartbeat = now

        with _patch_dispatch() as mock_task:
            summary = rt.recover_running_bots()

        mock_task.delay.assert_not_called()
        assert summary == {"recovered": [], "skipped": [], "errors": []}

    def test_idle_payload_skipped_no_dispatch(self, user):
        """Flat engines are owned by the check_stale_bots beat reaper."""
        bot = _grid_bot(user, is_running=True)
        _stale_row("grid", str(bot.id), _IDLE)

        with _patch_dispatch() as mock_task:
            summary = rt.recover_running_bots()

        mock_task.delay.assert_not_called()
        assert summary["recovered"] == [] and summary["errors"] == []
        assert summary["skipped"] == [f"grid/{bot.id}: no open position"]
        # Row left running — the beat reaper (not us) owns the flip.
        row = BotRuntimeState.objects.get(bot_type="grid", bot_id=str(bot.id))
        assert row.status == rt.RUNNING

    def test_empty_payload_dispatches_restore(self, user):
        """Crashed before the first snapshot — attach decides safely."""
        bot = _grid_bot(user, is_running=True)
        _stale_row("grid", str(bot.id), None)  # model default state = {}

        with _patch_dispatch() as mock_task:
            summary = rt.recover_running_bots()

        assert summary["recovered"] == [f"grid/{bot.id}"]
        mock_task.delay.assert_called_once()

    def test_deleted_bot_marks_row_stopped(self, user):
        _stale_row("grid", "999999", _POSITION)

        with _patch_dispatch() as mock_task:
            summary = rt.recover_running_bots()

        mock_task.delay.assert_not_called()
        assert summary["recovered"] == []
        assert len(summary["errors"]) == 1
        assert "bot missing" in summary["errors"][0]
        row = BotRuntimeState.objects.get(bot_type="grid", bot_id="999999")
        assert row.status == rt.STOPPED

    def test_model_not_running_marks_row_stopped(self, user):
        bot = _grid_bot(user, is_running=False)
        _stale_row("grid", str(bot.id), _POSITION)

        with _patch_dispatch() as mock_task:
            summary = rt.recover_running_bots()

        mock_task.delay.assert_not_called()
        assert summary["recovered"] == [] and summary["errors"] == []
        assert summary["skipped"] == [f"grid/{bot.id}: model not running (row -> stopped)"]
        row = BotRuntimeState.objects.get(bot_type="grid", bot_id=str(bot.id))
        assert row.status == rt.STOPPED

    def test_ineligible_bot_type_recorded_and_stopped(self, user):
        """SignalBot has no is_running/heartbeat — never dispatched."""
        _stale_row("signal", "42", _POSITION)

        with _patch_dispatch() as mock_task:
            summary = rt.recover_running_bots()

        mock_task.delay.assert_not_called()
        assert len(summary["errors"]) == 1
        assert "ineligible bot_type" in summary["errors"][0]
        row = BotRuntimeState.objects.get(bot_type="signal", bot_id="42")
        assert row.status == rt.STOPPED

    def test_min_stale_s_threshold(self, user):
        bot = _grid_bot(user, is_running=True)
        _stale_row("grid", str(bot.id), _POSITION, seconds_ago=30)

        with _patch_dispatch() as mock_task:
            summary = rt.recover_running_bots(min_stale_s=60)

        mock_task.delay.assert_not_called()
        assert summary == {"recovered": [], "skipped": [], "errors": []}

    def test_dispatch_failure_recorded_and_next_candidate_continues(self, user):
        """Broker down for candidate 1 must not block candidate 2."""
        bot_a = _grid_bot(user, is_running=True, bot_name="A")
        bot_b = _grid_bot(user, is_running=True, bot_name="B")
        _stale_row("grid", str(bot_a.id), _POSITION)
        _stale_row("grid", str(bot_b.id), _POSITION)

        with _patch_dispatch() as mock_task:
            mock_task.delay.side_effect = [RuntimeError("broker down"), None]
            summary = rt.recover_running_bots()

        assert len(summary["errors"]) == 1
        assert "RuntimeError" in summary["errors"][0]
        assert len(summary["recovered"]) == 1
        assert mock_task.delay.call_count == 2
        # Row iteration order is NOT creation order (queryset default
        # ordering) — assert both candidates were attempted exactly once:
        # one errored, the other recovered.
        attempted = {f"grid/{bot_a.id}", f"grid/{bot_b.id}"}
        outcome = set(summary["recovered"]) | {e.split(":")[0] for e in summary["errors"]}
        assert outcome == attempted

    def test_never_raises_on_broken_row(self, user):
        """A row whose save blows up is recorded, not fatal."""
        bot = _grid_bot(user, is_running=True)
        _stale_row("grid", str(bot.id), _POSITION)

        with (
            _patch_dispatch() as mock_task,
            patch.object(GridBot, "save", side_effect=RuntimeError("db down")),
        ):
            summary = rt.recover_running_bots()

        mock_task.delay.assert_not_called()
        assert len(summary["errors"]) == 1
        assert "RuntimeError" in summary["errors"][0]


# ── unit contracts ──────────────────────────────────────────────────────


class TestRecoveryUnitContracts:
    def test_recovery_model_map(self):
        assert rt._recovery_model("grid") is GridBot
        assert rt._recovery_model("martingale") is MartingaleBot
        assert rt._recovery_model("quantum_ai") is QuantumAIBot
        assert rt._recovery_model("signal") is None
        assert rt._recovery_model("custom") is None

    @pytest.mark.parametrize(
        "payload,expected",
        [
            # None/{} = unknown (crashed before first snapshot) -> dispatch
            (None, True),
            ({}, True),
            # explicitly flat -> skip (beat reaper owns idle bots)
            ({"side": "None", "count": 0}, False),
            ({"side": "", "count": 0}, False),
            # any side/count -> open position -> dispatch
            (_POSITION, True),
            ({"side": "Buy", "count": 2}, True),
        ],
    )
    def test_payload_has_position_matrix(self, payload, expected):
        assert rt._payload_has_position(payload) is expected

    def test_defaults_constant(self):
        assert rt.RECOVERY_MIN_STALE_S == 15.0
        assert rt._RECOVERY_MODEL_MAP == ("grid", "martingale", "quantum_ai")


# ── Celery hook (CHG-4-3) ───────────────────────────────────────────────


class TestRecoveryHookInstallation:
    @staticmethod
    def _capture_connect():
        from celery import signals

        captured = []

        def _recv(fn, **kwargs):
            captured.append((fn, kwargs))

        patcher = patch.object(signals.worker_ready, "connect", side_effect=_recv)
        return patcher, captured

    def test_connects_worker_ready_only_weak_false(self):
        patcher, captured = self._capture_connect()
        with patcher:
            trading_apps._install_celery_recovery_hook()

        assert len(captured) == 1  # NOT worker_process_init (per-child!)
        fn, kwargs = captured[0]
        assert kwargs.get("weak") is False
        assert callable(fn)

    def test_receiver_invokes_recover_running_bots(self):
        patcher, captured = self._capture_connect()
        with patcher:
            trading_apps._install_celery_recovery_hook()
        receiver = captured[0][0]

        with patch(
            "apps.trading.state.recover_running_bots",
            return_value={"recovered": ["grid/1"], "skipped": [], "errors": []},
        ) as recover:
            receiver()  # Celery calls it with signal/kwargs — signature is **kw

        recover.assert_called_once_with()

    def test_receiver_swallows_recovery_failure(self):
        patcher, captured = self._capture_connect()
        with patcher:
            trading_apps._install_celery_recovery_hook()
        receiver = captured[0][0]

        with patch(
            "apps.trading.state.recover_running_bots",
            side_effect=RuntimeError("boot boom"),
        ):
            receiver()  # must not raise — worker boot continues

    def test_ready_installs_recovery_hook_when_celery_worker(self):
        cfg = django_apps.get_app_config("trading")
        with (
            patch.object(trading_apps, "_is_celery_worker", return_value=True),
            patch.object(trading_apps, "_install_celery_shutdown_hooks"),
            patch.object(trading_apps, "_install_celery_recovery_hook") as hook,
        ):
            cfg.ready()
        hook.assert_called_once_with()

    def test_ready_noop_for_plain_processes(self):
        cfg = django_apps.get_app_config("trading")
        with (
            patch.object(trading_apps, "_is_celery_worker", return_value=False),
            patch.object(trading_apps, "_install_celery_recovery_hook") as hook,
        ):
            cfg.ready()
        hook.assert_not_called()

    def test_ready_survives_recovery_hook_failure(self):
        cfg = django_apps.get_app_config("trading")
        with (
            patch.object(trading_apps, "_is_celery_worker", return_value=True),
            patch.object(trading_apps, "_install_celery_shutdown_hooks"),
            patch.object(
                trading_apps, "_install_celery_recovery_hook", side_effect=RuntimeError("boom")
            ),
        ):
            cfg.ready()  # must not raise


# ── CHG-4-2 — startBot restore wiring ───────────────────────────────────


class TestStartBotRestoreWiring:
    def test_restore_engine_applied_before_attach(self):
        # Engine 1 "crashes" mid-trade, leaving a snapshot behind.
        eng1 = _make_engine()
        eng1.current_side = "Buy"
        eng1.count = 2
        eng1.current_price = 50000.0
        eng1.reason = "phase4-restore"
        rt.save_snapshot("grid", "1001", rt.collect_state(eng1))

        # Engine 2 boots in restore mode.
        eng2 = _make_engine(restore_mode=True)
        calls = []
        real_restore = rt.restore_engine
        eng2._start_monitoring_for_existing_position = MagicMock(
            side_effect=lambda: calls.append("attach")
        )
        with patch(
            "apps.trading.state.restore_engine",
            side_effect=lambda e: (calls.append("restore"), real_restore(e))[1],
        ) as restore_mock:
            eng2.startBot()

        assert calls == ["restore", "attach"]  # payload BEFORE attach
        restore_mock.assert_called_once_with(eng2)
        # Snapshot visible on the fresh engine (pre-attach truth).
        assert eng2.current_side == "Buy"
        assert eng2.count == 2
        assert eng2.reason == "phase4-restore"
        # Restore never evaluates a NEW entry.
        eng2.strategy._evaluate_conditions.assert_not_called()

    def test_restore_without_row_is_noop_cold_start(self):
        eng = _make_engine(restore_mode=True)
        eng._start_monitoring_for_existing_position = MagicMock()
        with patch("apps.trading.state.snapshot_engine"):
            eng.startBot()  # real restore_engine runs, finds no row -> False
        eng._start_monitoring_for_existing_position.assert_called_once_with()
        assert eng.bot_running is True
        eng.strategy._evaluate_conditions.assert_not_called()
