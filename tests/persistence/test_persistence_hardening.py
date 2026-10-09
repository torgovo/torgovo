"""Persistence hardening matrix — security / optimization / reliability / concurrency.

Complements (does NOT duplicate) the phase test files:

* test_snapshot_restore.py — schema round-trips, throttle mechanics, writer isolation
* test_recovery.py        — dispatch matrix, orphan cleanup, exact .delay() kwargs
* test_stop_bot.py        — cross-process stop flag (request/scoped/clear/TTL)
* test_shutdown_signals.py — SIGTERM forced snapshot, handler chaining

This file pins the properties those suites leave uncovered:

SECURITY    hostile payload keys can never become engine attributes or
            rewrite identity; snapshots are strictly scoped by
            (bot_type, bot_id); a tampered DB row never mutates an engine.

OPTIMIZATION  a burst of monitor ticks collapses to ONE DB write;
            collect_state does zero queries (hot loop is pure);
            the heartbeat is a single UPDATE (no SELECT round-trip).

RELIABILITY a pre-write collect failure costs the snapshot (False, no
            write, stamp preserved); payloads stay plain-JSON
            serializable (Decimal leak would silently kill every save);
            the 15 s stale boundary is exact.

CONCURRENCY parallel snapshot_engine callers never raise and the
            check-then-act throttle stays bounded (≤ one write each).

Run:  .venv/bin/python -m pytest tests/persistence/test_persistence_hardening.py --tb=short -q
"""

import json
import threading
import time
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.trading import state as rt
from apps.trading.engines.grid_monitor import GridPositionMonitor
from tests.persistence.test_recovery import _POSITION, _grid_bot, _patch_dispatch, _stale_row
from tests.persistence.test_snapshot_restore import _base_payload, _stub_engine, _stub_gm

pytestmark = pytest.mark.django_db


# ===========================================================================
# SECURITY — payload isolation & hostile-key resistance
# ===========================================================================


class TestSecurity:
    def test_hostile_payload_keys_never_touch_engine(self):
        """apply_state is an allow-list: unknown keys are inert.

        A compromised/corrupt row must not be able to inject lifecycle or
        identity fields (user_id/status/worker/config) onto an engine —
        only the documented schema keys are ever written.
        """
        hostile = _base_payload(
            side="Sell",
            user_id=999,
            status="hacked",
            is_running=False,
            worker="evil-host:1",
            config={"bot_id": "ATTACKER", "bot_type": "evil"},
            bot_id="ATTACKER",
        )
        original_cfg = {"bot_id": "1001", "bot_type": "grid"}
        eng = _stub_engine(config=original_cfg, count=0)

        assert rt.apply_state(eng, hostile) is True
        # Known schema key IS applied (proves the payload was processed)...
        assert eng.current_side == "Sell"
        # ...but no hostile key ever became an engine attribute...
        for key in ("user_id", "status", "is_running", "worker", "bot_id"):
            assert not hasattr(eng, key), f"hostile key {key!r} leaked onto engine"
        # ...and identity is untouched, so restore stays scoped to the
        # original bot (payload cannot re-target where state lands).
        assert eng.config == original_cfg
        assert rt._engine_identity(eng) == ("grid", "1001")

    def test_snapshot_of_bot_a_never_restores_into_bot_b(self):
        """Rows are keyed exactly: another bot's payload can never load."""
        rt.save_snapshot("grid", "BOT-A", _base_payload(side="Buy", count=2))

        eng = _stub_engine(config={"bot_id": "BOT-B", "bot_type": "grid"})
        assert rt.restore_engine(eng) is False
        assert eng.current_side == "None"  # untouched
        assert eng.count == 0

    def test_same_bot_id_scoped_by_bot_type(self):
        """(bot_type, bot_id) is the key — same id, different type, no leak."""
        rt.save_snapshot("grid", "500", _base_payload(side="Buy", count=3))

        eng = _stub_engine(config={"bot_id": "500", "bot_type": "martingale"})
        assert rt.restore_engine(eng) is False
        assert eng.current_side == "None"
        assert eng.count == 0

    @pytest.mark.parametrize("bad_schema", [99, "abc", []])
    def test_tampered_schema_in_db_row_refused(self, bad_schema):
        """A row edited directly in the DB never mutates a fresh engine.

        Covers both refusal paths: a wrong-but-integral schema returns
        False from apply_state, an un-castable one raises inside
        restore_engine's try — either way: False, zero mutation.
        """
        # Written straight at the schema level — bypasses save_snapshot's
        # own (honest) schema stamping, i.e. simulates direct DB tampering.
        rt.upsert("grid", "600", {"schema": bad_schema, "count": 7})

        eng = _stub_engine(config={"bot_id": "600", "bot_type": "grid"}, count=0)
        assert rt.restore_engine(eng) is False
        assert eng.count == 0
        assert eng.current_side == "None"


# ===========================================================================
# OPTIMIZATION — hot-loop cost bounds
# ===========================================================================


class TestOptimization:
    def test_burst_of_20_ticks_collapses_to_one_db_write(self):
        """20 rapid monitor ticks == exactly 1 INSERT/UPDATE (5 s throttle)."""
        eng = _stub_engine()
        # Deterministic first-tick pass independent of host uptime.
        eng._snapshot_monotonic = time.monotonic() - (rt.SNAPSHOT_THROTTLE_S + 1)

        with CaptureQueriesContext(connection) as ctx:
            results = [rt.snapshot_engine(eng) for _ in range(20)]

        assert results[0] is True
        assert all(r is False for r in results[1:])
        writes = [
            q
            for q in ctx.captured_queries
            if "bot_runtime_state" in q["sql"]
            and q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE"))
        ]
        assert len(writes) == 1
        # First tick = one SELECT + write via update_or_create; the other 19
        # ticks must cost NOTHING against the table (not even a read).
        # SAVEPOINT/RELEASE noise from pytest-django's transaction wrapper
        # is Django machinery, not snapshot cost, so it is filtered out.
        reads = [
            q
            for q in ctx.captured_queries
            if "bot_runtime_state" in q["sql"] and q["sql"].lstrip().upper().startswith("SELECT")
        ]
        assert len(reads) == 1

    def test_collect_state_is_pure_zero_queries(self):
        """collect_state runs on every 1 s tick — it must stay DB-free."""
        eng = _stub_engine(grid_monitor=_stub_gm())
        with CaptureQueriesContext(connection) as ctx:
            payload = rt.collect_state(eng)
        assert len(ctx.captured_queries) == 0
        assert payload["schema"] == rt.SNAPSHOT_SCHEMA

    def test_heartbeat_is_single_update_no_select(self, user):
        """GridPositionMonitor._update_heartbeat = one UPDATE, no SELECT.

        Uses a duck-typed ``self`` — the method only reads ``bot_config``,
        so a full monitor construction would add nothing but weight.
        """
        from django.utils import timezone

        bot = _grid_bot(user, is_running=True)
        fake = SimpleNamespace(bot_config={"bot_id": str(bot.id), "bot_type": "grid"})

        with CaptureQueriesContext(connection) as ctx:
            GridPositionMonitor._update_heartbeat(fake)

        assert len(ctx.captured_queries) == 1
        assert ctx.captured_queries[0]["sql"].lstrip().upper().startswith("UPDATE")
        bot.refresh_from_db()
        assert bot.last_heartbeat is not None
        assert bot.last_heartbeat <= timezone.now()


# ===========================================================================
# RELIABILITY — failure isolation & boundary contracts
# ===========================================================================


class _Bomb:
    """Engine whose identity resolves but whose state reads explode.

    ``config`` lives on the class (found without __getattr__), so
    ``_engine_identity`` succeeds; every other attribute access raises a
    RuntimeError — the pre-write failure path ``snapshot_engine`` must
    swallow. An explicit ``_snapshot_monotonic`` instance attribute keeps
    the throttle check off the bomb.
    """

    config = {"bot_id": "777", "bot_type": "grid"}

    def __getattr__(self, name):
        raise RuntimeError(f"state read failed: {name}")


class TestReliability:
    def test_collect_failure_returns_false_without_writing(self):
        """Blow-up DURING collect: no write, no stamp consumed, no raise.

        Distinct from the writer-failure test (test_snapshot_restore) —
        this one fails BEFORE save_snapshot is ever entered, so the
        snapshot budget (stamp) stays available for the next tick.
        """
        eng = _Bomb()
        eng._snapshot_monotonic = 0.0
        with patch("apps.trading.state.save_snapshot") as save:
            ok = rt.snapshot_engine(eng, force=True)  # force -> past the throttle
        assert ok is False
        save.assert_not_called()
        assert eng._snapshot_monotonic == 0.0  # stamp untouched -> retried next tick

    def test_collect_state_is_plain_json_serializable(self):
        """JSONField writes with the plain encoder (no DjangoJSONEncoder).

        collect_state float()/int()-casts every numeric field — if a
        Decimal ever reaches the payload, save_snapshot raises at write
        time and every subsequent snapshot is lost silently. Decimal
        inputs here prove the casts are live.
        """
        eng = _stub_engine(
            last_trade_pnl=Decimal("1.50"),
            current_price=Decimal("42000.50"),
        )
        payload = rt.collect_state(eng)  # must not raise TypeError below
        text = json.dumps(payload)  # exactly what JSONField executes
        assert json.loads(text)["schema"] == rt.SNAPSHOT_SCHEMA
        assert payload["last_trade_pnl"] == 1.5
        assert isinstance(payload["price"], float)

    def test_stale_boundary_default_15s(self, user):
        """Recovery's stale cut is exact: 14 s is live, 16 s is dead.

        Pins RECOVERY_MIN_STALE_S=15 against the real staleness() filter —
        a boundary regression here means healthy sibling workers get
        stolen from (too eager) or crashed bots stay dark (too lax).
        """
        alive = _grid_bot(user, is_running=True, bot_name="alive")
        dead = _grid_bot(user, is_running=True, bot_name="dead")
        _stale_row("grid", str(alive.id), _POSITION, seconds_ago=14)
        _stale_row("grid", str(dead.id), _POSITION, seconds_ago=16)

        with _patch_dispatch() as mock_task:
            summary = rt.recover_running_bots()  # default RECOVERY_MIN_STALE_S

        assert summary["recovered"] == [f"grid/{dead.id}"]
        assert summary["errors"] == []
        mock_task.delay.assert_called_once_with(str(dead.id), "grid", restore_mode=True)


# ===========================================================================
# CONCURRENCY — parallel snapshot callers
# ===========================================================================


class TestConcurrency:
    def test_parallel_snapshot_engine_threads_safe(self):
        """8 concurrent ticks: no exception, writes bounded 1..8.

        The throttle is check-then-act, so more than one caller CAN pass
        before the stamp lands — the contract is "at most one write per
        caller, never a crash", not "exactly one write".
        """
        eng = _stub_engine()
        eng._snapshot_monotonic = time.monotonic() - (rt.SNAPSHOT_THROTTLE_S + 1)
        results, errors = [], []

        def worker():
            try:
                results.append(rt.snapshot_engine(eng))
            except Exception as exc:  # pragma: no cover - the contract itself
                errors.append(exc)

        with patch("apps.trading.state.save_snapshot") as save:
            threads = [threading.Thread(target=worker) for _ in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)

        assert errors == []
        assert all(not t.is_alive() for t in threads)
        assert len(results) == 8
        assert 1 <= save.call_count <= 8
        # Every True result corresponds to exactly one write — no torn state.
        assert sum(1 for r in results if r) == save.call_count
