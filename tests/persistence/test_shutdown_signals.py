"""Tests for Phase 6b — graceful shutdown signal registration & chaining.

Covers:
  * ``apps.trading.apps._is_celery_worker`` argv detection matrix
  * ``apps.trading.apps._install_celery_shutdown_hooks`` receiver wiring
  * ``execution._install_shutdown_handler`` idempotency / chain capture
  * ``execution._chain_to_previous_handler`` safety (SIG_DFL, SIG_IGN, self)
  * ``execution._shutdown_handler`` teardown + chain replay
"""

import signal
from unittest.mock import patch

import pytest
from django.apps import apps as django_apps

from apps.trading import apps as trading_apps
from apps.trading.engines import execution

# ── helpers ─────────────────────────────────────────────────────────────


@pytest.fixture
def restore_signal_handlers():
    """Snapshot SIGTERM/SIGINT so tests never leak a handler into the suite."""
    saved = {
        signal.SIGTERM: signal.getsignal(signal.SIGTERM),
        signal.SIGINT: signal.getsignal(signal.SIGINT),
    }
    saved_chain = dict(execution._prev_sig_handlers)
    yield
    for sig, handler in saved.items():
        signal.signal(sig, handler)
    execution._prev_sig_handlers.clear()
    execution._prev_sig_handlers.update(saved_chain)


@pytest.fixture
def isolated_running_engines():
    """Give the test an empty registry and put back whatever was there."""
    preexisting = dict(execution._running_engines)
    execution._running_engines.clear()
    yield execution._running_engines
    execution._running_engines.clear()
    execution._running_engines.update(preexisting)


# ── _is_celery_worker ───────────────────────────────────────────────────


class TestIsCeleryWorker:
    @pytest.mark.parametrize(
        "argv",
        [
            ["celery", "-A", "config", "worker", "-l", "info"],
            ["celery", "worker", "--pool=prefork"],
            ["/usr/local/bin/celery", "-A", "config", "worker"],
        ],
    )
    def test_detects_celery_worker_forms(self, argv):
        assert trading_apps._is_celery_worker(argv) is True

    @pytest.mark.parametrize(
        "argv",
        [["python", "-m", "celery", "worker", "-l", "info"]],
    )
    def test_detects_python_m_celery_worker(self, argv):
        assert trading_apps._is_celery_worker(argv) is True

    @pytest.mark.parametrize(
        "argv",
        [
            ["manage.py", "worker"],  # no such command, but is manage.py
            ["manage.py", "runserver"],
            ["celery", "-A", "config", "beat"],
            ["celery", "inspect", "ping"],
            ["python", "-m", "celery", "beat"],
            ["/home/u/.venv/bin/pytest", "tests/persistence"],
            [],
        ],
    )
    def test_rejects_non_worker_processes(self, argv):
        assert trading_apps._is_celery_worker(argv) is False

    def test_word_worker_in_arg_without_celery_is_not_worker(self):
        # "worker" present but neither a celery program nor `-m celery`
        assert trading_apps._is_celery_worker(["/bin/bash", "worker.sh"]) is False

    def test_none_uses_sys_argv_and_default_pytest_is_false(self):
        import sys

        assert trading_apps._is_celery_worker() == trading_apps._is_celery_worker(sys.argv)
        assert trading_apps._is_celery_worker() is False  # argv[0] is pytest


# ── _install_celery_shutdown_hooks ──────────────────────────────────────


class TestCeleryHookInstallation:
    def test_ready_wires_hooks_when_celery_worker(self, restore_signal_handlers):
        cfg = django_apps.get_app_config("trading")
        with (
            patch.object(trading_apps, "_is_celery_worker", return_value=True),
            patch.object(trading_apps, "_install_celery_shutdown_hooks") as hooks,
        ):
            cfg.ready()
        hooks.assert_called_once_with()

    def test_ready_is_noop_for_plain_processes(self, restore_signal_handlers):
        cfg = django_apps.get_app_config("trading")
        with (
            patch.object(trading_apps, "_is_celery_worker", return_value=False),
            patch.object(trading_apps, "_install_celery_shutdown_hooks") as hooks,
        ):
            cfg.ready()
        hooks.assert_not_called()

    def test_ready_survives_hook_failure(self, restore_signal_handlers):
        cfg = django_apps.get_app_config("trading")
        with (
            patch.object(trading_apps, "_is_celery_worker", return_value=True),
            patch.object(
                trading_apps, "_install_celery_shutdown_hooks", side_effect=RuntimeError("boom")
            ),
        ):
            cfg.ready()  # must not raise

    def test_hooks_connect_both_signals_weak_false(self, restore_signal_handlers):
        from celery import signals

        connected = []

        def _capture(fn, **kwargs):
            connected.append((fn, kwargs.get("weak")))

        with (
            patch.object(signals.worker_ready, "connect", side_effect=_capture),
            patch.object(signals.worker_process_init, "connect", side_effect=_capture),
        ):
            trading_apps._install_celery_shutdown_hooks()

        assert len(connected) == 2
        assert all(weak is False for _, weak in connected)

    def test_reinstall_receiver_installs_and_is_idempotent(self, restore_signal_handlers):
        """The receiver passed to both hooks must install our handler."""
        from celery import signals

        receivers = {}

        def _capture(fn, **kwargs):
            receivers["fn"] = fn

        with (
            patch.object(signals.worker_ready, "connect", side_effect=_capture),
            patch.object(signals.worker_process_init, "connect", side_effect=_capture),
        ):
            trading_apps._install_celery_shutdown_hooks()

        receiver = receivers["fn"]
        # Simulate Celery having just clobbered us with its own handler.
        # NOTE: must be a *real* Python callable — signal.getsignal() reports
        # SIG_IGN for MagicMock instances (CPython only round-trips functions).

        def celery_handler(signum, frame):
            pass

        signal.signal(signal.SIGTERM, celery_handler)
        signal.signal(signal.SIGINT, celery_handler)

        assert receiver() is None
        assert signal.getsignal(signal.SIGTERM) is execution._shutdown_handler
        assert signal.getsignal(signal.SIGINT) is execution._shutdown_handler
        # Celery's handler was captured for chaining, not discarded.
        assert execution._prev_sig_handlers[signal.SIGTERM] is celery_handler

        # Second fire must be a no-op that keeps the original chain.
        receiver()
        assert execution._prev_sig_handlers[signal.SIGTERM] is celery_handler


# ── _install_shutdown_handler ───────────────────────────────────────────


class TestInstallShutdownHandler:
    def test_installs_both_signals(self, restore_signal_handlers):
        assert execution._install_shutdown_handler() is True
        assert signal.getsignal(signal.SIGTERM) is execution._shutdown_handler
        assert signal.getsignal(signal.SIGINT) is execution._shutdown_handler

    def test_idempotent_keeps_first_chain(self, restore_signal_handlers):
        def prev(signum, frame):
            pass

        signal.signal(signal.SIGTERM, prev)
        execution._install_shutdown_handler()
        execution._install_shutdown_handler()  # second pass: already ours
        assert execution._prev_sig_handlers[signal.SIGTERM] is prev

    def test_reclaims_after_clobber_and_rechains(self, restore_signal_handlers):
        def first(signum, frame):
            pass

        def second(signum, frame):
            pass

        signal.signal(signal.SIGTERM, first)
        execution._install_shutdown_handler()
        signal.signal(signal.SIGTERM, second)  # e.g. Celery overwrites us
        execution._install_shutdown_handler()
        assert signal.getsignal(signal.SIGTERM) is execution._shutdown_handler
        assert execution._prev_sig_handlers[signal.SIGTERM] is second

    def test_single_signum_target(self, restore_signal_handlers):
        def other(signum, frame):
            pass

        signal.signal(signal.SIGINT, other)
        execution._install_shutdown_handler(signal.SIGTERM)
        assert signal.getsignal(signal.SIGTERM) is execution._shutdown_handler
        assert signal.getsignal(signal.SIGINT) is other
        assert signal.SIGINT not in execution._prev_sig_handlers

    def test_returns_false_when_not_main_thread(self, restore_signal_handlers):
        import threading

        results = []

        def _worker():
            results.append(execution._install_shutdown_handler())

        t = threading.Thread(target=_worker)
        t.start()
        t.join()
        assert results == [False]


# ── _chain_to_previous_handler ──────────────────────────────────────────


class TestChainToPreviousHandler:
    def test_calls_chained_handler(self):
        seen = []

        def prev(signum, frame):
            seen.append((signum, frame))

        execution._prev_sig_handlers[signal.SIGTERM] = prev
        try:
            execution._chain_to_previous_handler(signal.SIGTERM, "frame")
        finally:
            execution._prev_sig_handlers.pop(signal.SIGTERM, None)
        assert seen == [(signal.SIGTERM, "frame")]

    @pytest.mark.parametrize("prev", [signal.SIG_DFL, signal.SIG_IGN])
    def test_skips_signal_dfl_and_ign(self, prev):
        execution._prev_sig_handlers[signal.SIGTERM] = prev
        try:
            execution._chain_to_previous_handler(signal.SIGTERM, None)  # must not raise
        finally:
            execution._prev_sig_handlers.pop(signal.SIGTERM, None)

    def test_skips_missing_and_self(self):
        execution._chain_to_previous_handler(signal.SIGTERM, None)  # no entry
        execution._prev_sig_handlers[signal.SIGTERM] = execution._shutdown_handler
        try:
            execution._chain_to_previous_handler(signal.SIGTERM, None)
        finally:
            execution._prev_sig_handlers.pop(signal.SIGTERM, None)

    def test_exception_in_chained_handler_is_contained(self):
        calls = []

        def prev(signum, frame):
            calls.append(signum)
            raise RuntimeError("chain failed")

        execution._prev_sig_handlers[signal.SIGTERM] = prev
        try:
            execution._chain_to_previous_handler(signal.SIGTERM, None)  # must not raise
        finally:
            execution._prev_sig_handlers.pop(signal.SIGTERM, None)
        assert calls == [signal.SIGTERM]


# ── _shutdown_handler ───────────────────────────────────────────────────


class TestShutdownHandler:
    def test_stops_running_engines_then_chains(
        self, restore_signal_handlers, isolated_running_engines
    ):
        calls = []

        def _fake_stop(bot_id):
            calls.append(bot_id)

        isolated_running_engines["b-1"] = object()
        isolated_running_engines["b-2"] = object()
        prev_calls = []

        def prev(signum, frame):
            prev_calls.append((signum, frame))

        execution._prev_sig_handlers[signal.SIGTERM] = prev
        try:
            with patch.object(execution, "stop_bot", side_effect=_fake_stop):
                execution._shutdown_handler(signal.SIGTERM, "frame")
        finally:
            execution._prev_sig_handlers.pop(signal.SIGTERM, None)

        assert calls == ["b-1", "b-2"]
        assert prev_calls == [(signal.SIGTERM, "frame")]

    def test_no_engines_is_quiet_noop(self, restore_signal_handlers, isolated_running_engines):
        # isolated_running_engines guarantees the registry is empty here, so
        # the real (unpatched) stop_bot is never invoked.
        execution._shutdown_handler(signal.SIGINT, None)  # must not raise

    def test_reentrant_lock_safe_when_handler_interrupts_lock_holder(self):
        """Handler runs on the main thread that may already hold the lock.

        Pre-6b this was a plain ``threading.Lock`` → the process deadlocked
        inside its own shutdown path. RLock makes the nested acquire succeed.
        """
        with execution._running_engines_lock:
            with execution._running_engines_lock:  # nested — must not block
                pass
        assert execution._running_engines_lock.acquire(blocking=False)
        execution._running_engines_lock.release()


# ── CHG-3-5 — forced snapshot in the in-process shutdown path ───────────


class TestShutdownSnapshot:
    """SIGTERM/SIGINT must force a final BotRuntimeState snapshot first.

    Contract: snapshot BEFORE teardown, ``force=True`` (bypass the 5s
    throttle), per-engine containment (one bad engine never blocks the
    others, the stop loop, or the chained handler).
    """

    def test_snapshot_before_teardown_with_force(
        self, restore_signal_handlers, isolated_running_engines
    ):
        order = []
        isolated_running_engines["b-1"] = object()
        isolated_running_engines["b-2"] = object()

        def _fake_snapshot(engine, *, force=False, **kw):
            order.append(("snapshot", force))
            return True

        def _fake_stop(bot_id):
            order.append(("stop", bot_id))

        with (
            patch.object(execution, "stop_bot", side_effect=_fake_stop),
            patch("apps.trading.state.snapshot_engine", side_effect=_fake_snapshot),
        ):
            execution._shutdown_handler(signal.SIGTERM, None)  # must not raise

        kinds = [entry[0] for entry in order]
        # every snapshot precedes every stop (capture live state first)
        assert kinds == ["snapshot", "snapshot", "stop", "stop"]
        # every snapshot was forced (bypasses SNAPSHOT_THROTTLE_S)
        assert all(force for name, force in order if name == "snapshot")

    def test_snapshot_failure_never_blocks_stop_or_chain(
        self, restore_signal_handlers, isolated_running_engines
    ):
        stops, prev_calls = [], []
        isolated_running_engines["b-1"] = object()

        def prev(signum, frame):
            prev_calls.append(signum)

        execution._prev_sig_handlers[signal.SIGTERM] = prev
        try:
            with (
                patch.object(execution, "stop_bot", side_effect=stops.append),
                patch(
                    "apps.trading.state.snapshot_engine",
                    side_effect=RuntimeError("db down"),
                ),
            ):
                execution._shutdown_handler(signal.SIGTERM, None)  # must not raise
        finally:
            execution._prev_sig_handlers.pop(signal.SIGTERM, None)

        assert stops == ["b-1"]  # teardown still ran
        assert prev_calls == [signal.SIGTERM]  # chain still replayed

    def test_one_engine_failure_still_snapshots_the_rest_and_stops_all(
        self, restore_signal_handlers, isolated_running_engines
    ):
        snap_forces, stops = [], []
        isolated_running_engines["b-1"] = object()
        isolated_running_engines["b-2"] = object()

        def _boom_first(engine, *, force=False, **kw):
            snap_forces.append(force)
            if len(snap_forces) == 1:
                raise RuntimeError("boom")
            return True

        with (
            patch.object(execution, "stop_bot", side_effect=stops.append),
            patch("apps.trading.state.snapshot_engine", side_effect=_boom_first),
        ):
            execution._shutdown_handler(signal.SIGINT, None)  # must not raise

        assert snap_forces == [True, True]  # both attempted, both forced
        assert stops == ["b-1", "b-2"]  # teardown unaffected by the boom

    def test_identityless_engine_is_a_quiet_noop(
        self, restore_signal_handlers, isolated_running_engines
    ):
        """Bare engines (no config) hit the REAL snapshot path: identity
        check returns None before any DB work → False, no write, no raise.
        stop_bot stays mocked so a non-engine never goes through teardown.
        """
        stops = []
        isolated_running_engines["b-1"] = object()
        with patch.object(execution, "stop_bot", side_effect=stops.append):
            execution._shutdown_handler(signal.SIGTERM, None)  # real snapshot_engine
        assert stops == ["b-1"]
