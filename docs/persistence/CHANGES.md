# Persistence Work — Change Log & Revert Guide

**Purpose:** every change made during the crash-consistency / persistence effort is
recorded here with the file touched, what changed, and the exact revert step, so any
change can be undone independently.

**Scope:** ALL DONE (2026-09-26..28): 6a cross-process stop + 6b SIGTERM
registration → Phases 1 → 2 → 3 → 4 → 5 (see CHG-1-*, CHG-2-*, CHG-3-*) →
CHG-3-5 shutdown snapshot → 7 final docs. This file remains the master revert
guide.

---

## Baseline (revert reference)

| Item | Value |
|---|---|
| Branch | `main` |
| HEAD | `6752b71306922b0cade0d455dd64e962f5a47015` ("Add frontend integration brief (root prompt + docs copy)") |
| Dirty-file snapshot | `/tmp/opencode/torgovo2_baseline_status.txt` (138 lines: 101 modified + 36 untracked + 1) |
| Test command | `.venv/bin/python -m pytest --tb=short -q` |
| Lint command | `/usr/bin/flake8` |

> **WARNING — do NOT revert with `git checkout -- <file>`.**
> `apps/trading/engines/bot_engine.py`, `apps/trading/engines/execution.py` and
> `apps/trading/tasks.py` were **already modified before this effort began** (they
> appear in the baseline snapshot). A file-level `git checkout` would silently throw
> away unrelated pre-existing work. Only revert using the per-edit reverse snippets
> below. `apps/trading/engines/grid_monitor.py` was clean at baseline, so a
> file-level revert *is* safe for that one file only.

### Legend

- **ID** — stable identifier for the change.
- **Revert** — exact reverse edit (replace `NEW` with `OLD`), safe to apply standalone.

---

## Phase 6a — cross-process bot stop (DONE 2026-09-26)

### CHG-6a-1 — Stop-request primitives in `execution.py`

- **File:** `apps/trading/engines/execution.py`
- **Location:** inserted immediately above `def stop_bot(...)` — constants/helpers at
  lines ~636–693.
- **What:** added `_STOP_REQ_TTL = 600`, `_stop_req_key(bot_id)`,
  `request_stop(bot_id)`, `stop_requested(bot_id)`, `clear_stop_request(bot_id)`.
  `request_stop` / `clear_stop_request` swallow Redis errors so a cache outage never
  aborts a stop; `stop_requested` **fails open (returns `False`)** so a Redis blip can
  never silently kill a healthy bot's monitor threads.
- **Why:** the stop task frequently runs on a *different* Celery worker than the one
  holding the engine, so the in-process `_running_engines` lookup cannot reach it.
- **Revert:** delete the whole `# ── Cross-process stop signalling (Phase 6a) ──`
  block (from the banner comment through the end of `clear_stop_request`).

### CHG-6a-2 — `engine_found` in `execution.stop_bot` return

- **File:** `apps/trading/engines/execution.py`
- **Location:** `stop_bot()` return, line 738.
- **What:** `return {"success": True, "bot_id": bot_id}` →
  `return {"success": True, "bot_id": bot_id, "engine_found": engine is not None}`.
- **Why:** lets the caller distinguish "threads actually joined here" from "engine
  lives on another worker, only the Redis flag can reach it".
- **Revert:** restore the original two-key return.
- **Test:** `tests/engines/test_bot_executor.py::TestStopBot` (only asserts
  `result["success"]`, so the added key is non-breaking).

### CHG-6a-3 — Clear stale stop flag on start

- **File:** `apps/trading/engines/execution.py`
- **Location:** `run_bot()`, line 452 — immediately after the `restore_mode and not
  _try_redis_lock(bot_id)` guard.
- **What:** calls `clear_stop_request(bot_id)`.
- **Why:** without it, restarting a bot within 10 minutes of a stop would be killed
  instantly by the previous session's flag on the first monitor-loop poll.
- **Revert:** delete the three lines (comment + call + blank line).

### CHG-6a-4 — `stop_cb` hook on `GridPositionMonitor`

- **File:** `apps/trading/engines/grid_monitor.py`
- **Location:** `__init__` signature (line 42) and body (line 55).
- **What:** new keyword-only arg `stop_cb: Optional[Callable] = None` stored as
  `self._stop_cb`; fires when a cross-process stop is detected.
- **Why:** the monitor runs inside a thread and must not join threads itself, so the
  owning engine supplies a callback for registry cleanup.
- **Revert:** remove the parameter from the signature and the `self._stop_cb = stop_cb`
  assignment (plus its comment).

### CHG-6a-5 — `_check_remote_stop()` poll

- **File:** `apps/trading/engines/grid_monitor.py`
- **Location:** new method under a new `# CROSS-PROCESS STOP (Phase 6a)` banner,
  lines ~182–230 (between `_update_heartbeat` and the `FETCH PRICE` section).
- **What:** reads the Redis stop flag; on detection sets `monitoring = False`,
  `bot_running = False`, `_stop_event.set()` (both loops read at least one of these)
  and invokes `self._stop_cb`. Never raises — a Redis failure returns `False` and
  leaves monitoring untouched.
- **Revert:** delete the whole `# CROSS-PROCESS STOP` section.

### CHG-6a-6 — Poll wired into both monitor loops

- **File:** `apps/trading/engines/grid_monitor.py`
- **Location:** `_monitor_grid_orders` loop head (line 328) and
  `_monitor_loss_profit` loop head (line 576).
- **What:** `if self._check_remote_stop(): break` as the first statement in each
  `try` block.
- **Why:** gives worst-case stop latency of one loop sleep — **~1 s (grid)** and
  **~5 s (SL/TP)**.
- **Revert:** remove the two `if self._check_remote_stop(): break` blocks (each is
  a two-line insert plus one comment line).

### CHG-6a-7 — `stop_cb` wired from `BotEngine`

- **File:** `apps/trading/engines/bot_engine.py`
- **Location:** `GridPositionMonitor(...)` construction, line 114.
- **What:** passes `stop_cb=self._on_remote_stop`.
- **Revert:** delete the argument and its two comment lines.

### CHG-6a-8 — `_notify_stopped()` helper extracted + `_on_remote_stop()`

- **File:** `apps/trading/engines/bot_engine.py`
- **Location:** lines ~338–392 (replaces the inline Telegram block in `stop_bot`).
- **What:**
  - `stop_bot()`'s trailing Telegram `try/except` block moved verbatim into a new
    `_notify_stopped()` method; `stop_bot()` now ends with `self._notify_stopped()`.
    **Behaviour is unchanged** — this is a pure extraction so the new callback can
    reuse it.
  - New `_on_remote_stop()`: sets engine-level `monitoring`/`bot_running`/`_stop_event`,
    then `_mark_bot_stopped(bot_id)` + pops `_running_engines[bot_id]` under
    `_running_engines_lock`, then notifies Telegram. **Never joins threads** — it
    executes inside a monitor thread.
- **Why:** releases the in-process registries so a restart is not blocked by the
  "already running in this process" guard. DB flags are deliberately *not* written
  here — the worker that received `tasks.stop_bot` owns them.
- **Revert:** move the Telegram `try/except` back into `stop_bot()` and delete
  `_notify_stopped()` and `_on_remote_stop()`.

### CHG-6a-9 — `tasks.stop_bot` now stops the engine

- **File:** `apps/trading/tasks.py`
- **Location:** `stop_bot()`, lines ~85–140.
- **What:** three-step body replaces the flag-only version:
  1. `execution.request_stop(bot_id)` (cross-process, first, so teardown overlaps
     the DB write),
  2. `execution.stop_bot(bot_id, bot_type=bot_type)` inside its own `try` (in-process
     fast path),
  3. guarded DB write using `hasattr` for `is_running` / `stopped_at`.
- **Why:** the old implementation only flipped DB flags, leaving monitor threads
  running → next start failed with "already running in this process".
- **Side effects fixed:** `bot_type="signal"` used to raise (SignalBot has neither
  column) — the `hasattr` guard now skips it cleanly.
- **Return shape preserved exactly** as `{"success": True, "status": "stopped"}` /
  `{"success": False, "error": ...}` because `tests/engines/test_trading_tasks.py:267,277`
  assert dict equality.
- **Revert:** restore the original body (fetch bot → set `is_running=False` /
  `stopped_at=timezone.now()` → `save(update_fields=["is_running","stopped_at"])`).

---

### CHG-6a-10 — Phase 6a test suite

- **Files (new):**
  - `tests/persistence/__init__.py`
  - `tests/persistence/test_stop_bot.py` (26 tests)
  - `tests/engines/test_bot_engine.py` → new class `TestRemoteStopCallback` (6 tests)
- **What:** covers all three cooperating layers:
  1. `TestStopRequestPrimitives` (8) — flag set/scoped/clear, TTL=600 asserted via
     `cache.set` call args, cache failures in `request_stop` / `stop_requested`
     (fails open) / `clear_stop_request`, key format.
  2. `TestCheckRemoteStop` (7) — no flag / missing `bot_id` / flag tears down
     `monitoring`+`bot_running`+`_stop_event` and fires `stop_cb` once / no
     callback / lookup raises (fails open, state untouched) / callback raises
     (swallowed) / structural guard that the poll precedes `_heartbeat_counter`
     in **both** loops.
  3. `TestTaskStopBot` (8) — flag published, engine registry popped, running set
     cleared, DB flags written, survives `execution.stop_bot` raising,
     `signal` bot_type no longer raises, not-found, exact return shape,
     **ordering** (`request_stop` before `execution.stop_bot`).
  4. `TestStartClearsStaleStopFlag` (2) — flag cleared on start; structural guard
     that `run_bot` calls `clear_stop_request` before the bot-type dispatch.
  5. `TestRemoteStopCallback` (6) — monitor constructed with `stop_cb=`, registry
     cleanup + flags, never joins threads, `_notify_stopped` internally guarded,
     raising notify contained by `_check_remote_stop`, no-`bot_id` path.
- **Gotchas encoded in tests:**
  - `SignalBot` requires `default_amount` (NOT NULL) — `_signal_bot()` sets it.
  - `LocMemCache` is process-global → autouse `_clean_stop_flags` fixture calls
    `cache.clear()` around each test; per-test unique UUID bot ids.
  - `execution.save_bot_state` / `_collect_engine_state` patched in the
    registry-teardown test (they run unguarded inside `execution.stop_bot`).
- **Revert:** `rm -rf tests/persistence/` and delete the `TestRemoteStopCallback`
  block from `tests/engines/test_bot_engine.py`.

---

## Phase 6b — SIGTERM/SIGINT registration (DONE 2026-09-26)

**Problem:** the graceful-shutdown handler in `execution.py` self-registered only when
`RUN_MAIN` (runserver) or `SERVER_SOFTWARE` (gunicorn) matched. In a **Celery worker**
neither matched → no handler was ever installed → SIGTERM hard-killed the process with
no `_running_engines` teardown and no thread joins.

**Boot-order fact (verified against Celery 5.3.4) that drives the whole design:**

```
WorkController.__init__ (celery/worker/worker.py:87)
    -> loader.init_worker() -> import_default_modules()
    -> DjangoFixup.validate_models() -> django.setup() -> TradingConfig.ready()   ← FIRST
Worker.start -> blueprint.start -> Worker.on_start (celery/apps/worker.py:121)
    -> install_platform_tweaks (celery/apps/worker.py:~138)
    -> signal(SIGTERM, celery._handle_request)                                    ← SECOND (overwrites us)
```

So registering in `ready()` alone is broken — Celery clobbers it afterwards. The
re-install points must fire **after** `install_platform_tweaks`:
`worker_ready` (`celery/apps/worker.py:174`, main process) and `worker_process_init`
(`celery/concurrency/prefork.py:79`, every pool child / `celery/concurrency/solo.py:20`).
`celeryd_after_setup` fires *before* → too early.

**Three competing registration sites exist in the repo:**

| Site | Behaviour |
|---|---|
| `apps/trading/engines/execution.py` graceful-shutdown block | gated on `RUN_MAIN` / gunicorn |
| `config/wsgi.py:20-28` | own handler doing `sys.exit(0)`; runs after `get_wsgi_application()` → **wins under gunicorn** |
| `core/shutdown.py:33-41` | **DEAD — never imported anywhere.** Do not rely on it. |

### CHG-6b-1 — `_running_engines_lock` → `threading.RLock()`

- **File:** `apps/trading/engines/execution.py`
- **Location:** module level (~line 30).
- **What:** `threading.Lock()` → `threading.RLock()` (+ comment).
- **Why:** signal handlers run on the **main thread**, which may already hold the lock
  inside `run_bot` / `stop_bot` (real under `--pool=solo`, `--pool=threads` and
  `CELERY_TASK_ALWAYS_EAGER`). A plain `Lock` would self-deadlock the process inside
  its own shutdown path. RLock is a drop-in for every existing `with lock:` use
  (`execution.py` :491/:568/:704, `bot_engine.py` :389).
- **Design deviation (documented deliberately):** the original plan was a
  non-blocking `acquire(False)` fallback in the handler. Rejected — it silently
  skips teardown whenever the lock is contended. RLock is simpler and correct.
  Verified there is **no** `.locked()` and no `acquire(False)` caller anywhere.
  `_running_bots_lock` stays a plain `Lock` (the handler never touches it).
- **Revert:** `_running_engines_lock = threading.RLock()` →
  `_running_engines_lock = threading.Lock()` (drop the comment).
- **Test:** `tests/persistence/test_shutdown_signals.py::TestShutdownHandler::test_reentrant_lock_safe_when_handler_interrupts_lock_holder`.

### CHG-6b-2 — `apps/trading/apps.py`: Celery-aware re-install hooks

- **File:** `apps/trading/apps.py` (was 13 lines, `ready()` = `pass`).
- **What:** new module docstring (boot-order rationale), `_is_celery_worker(argv=None)`,
  `_install_celery_shutdown_hooks()`, and `TradingConfig.ready()` calling the latter
  **only** when `_is_celery_worker()` is True.
  - `_is_celery_worker` — stdlib only (`os`/`sys`): requires the literal arg `worker`
    AND (`basename(argv[0])` startswith `celery` OR `-m celery`). Matches
    `celery -A config worker` and `python -m celery worker`; rejects `manage.py`,
    `celery beat`, `celery inspect`, pytest (so tests never touch signal handlers).
  - `_install_celery_shutdown_hooks` — **function-local** `from celery import signals`
    + `from apps.trading.engines.execution import _install_shutdown_handler`, so
    `celery` is imported only in the one process that needs it. Connects
    `worker_ready` and `worker_process_init` to one receiver with **`weak=False`**
    (module-level functions would otherwise be GC'd before the signal fires).
    The receiver calls `_install_shutdown_handler()` (idempotent) and logs a
    warning if it returns False (not main thread).
  - `ready()` wraps the call in `try/except Exception` + `logger.exception` — signal
    wiring must never take a worker down.
- **Design deviations (documented deliberately):**
  1. **The legacy `RUN_MAIN` / gunicorn gate was NOT moved into `ready()`.** Moving it
     would change ordering vs `config/wsgi.py` (which registers *after*
     `get_wsgi_application()`). It stays at module level in `execution.py` so runserver
     and gunicorn behaviour is byte-for-byte unchanged; `ready()` adds only the Celery
     path.
  2. **`_is_celery_worker` lives in `apps.py`, not `execution.py`** — pure stdlib, so
     `apps.py` does not need to import `execution` at module level (it is imported
     lazily inside the hook installer instead).
- **Why:** the only way to get a handler installed in a Celery worker is to install it
  *after* Celery claims the signal.
- **Revert:** restore `apps/trading/apps.py` to:
  ```python
  from django.apps import AppConfig

  class TradingConfig(AppConfig):
      default_auto_field = "django.db.models.BigAutoField"
      name = "apps.trading"
      verbose_name = "Trading"

      def ready(self):
          """Import signals when app is ready."""
          pass
  ```
  (`git show 6752b71306922b0cade0d455dd64e962f5a47015:apps/trading/apps.py` is the
  pre-effort version — this file was **clean at baseline**, so a file-level
  `git checkout -- apps/trading/apps.py` is also safe.)
- **Test:** `tests/persistence/test_shutdown_signals.py::TestIsCeleryWorker` (9) +
  `::TestCeleryHookInstallation` (5).

### CHG-6b-3 — `execution.py`: idempotent install + handler chaining

- **File:** `apps/trading/engines/execution.py`
- **Location:** the `# ── Graceful shutdown (Phase 6b) ──` block, immediately after the
  module-level imports (line numbers below the old `:614` shifted ≈ +70 lines).
- **What:** replaced the old inline `signal.signal(...)` registration with:
  - `import signal as _signal`, `import os as _os` (`noqa: E402`, top-of-block) —
    the old bare `import os` / `import signal` mid-file are gone.
  - `_prev_sig_handlers: dict` — the captured "previous" handler per signal.
  - `_install_shutdown_handler(signum=None) -> bool` — reads
    `signal.getsignal(sig)`; if it is already `_shutdown_handler`, **skips** (keeps
    the first chain); otherwise installs ours and records the previous one.
    Wrapped in `try/except (AttributeError, ValueError, OSError, RuntimeError)` →
    returns `False` on non-main-thread / platform-missing signal numbers instead of
    raising.
  - `_chain_to_previous_handler(signum, frame)` — replays the captured handler.
    Skips when absent, when it is `SIG_DFL`/`SIG_IGN`, or when it **is**
    `_shutdown_handler` (prevents self-recursion). Everything in
    `try/except Exception` + `logger.exception`.
  - `_shutdown_handler` now ends with `_chain_to_previous_handler(signum, frame)`.
  - Legacy gate preserved verbatim:
    `if _os.environ.get("RUN_MAIN") or "gunicorn" in (_os.environ.get("SERVER_SOFTWARE", "")): _install_shutdown_handler()`
    with a comment noting Celery workers deliberately do **not** match it.
- **Why:** (a) Celery overwrites the signal later, so installation must be repeatable
  and must *chain* rather than discard Celery's handler; (b) under runserver the
  previous handler was `default_int_handler`, which the old code swallowed — Ctrl-C
  died silently; under gunicorn it is `sys.exit(0)`; under Celery it is warm shutdown.
  All three now still run.
- **Revert:** delete the `# ── Graceful shutdown (Phase 6b) ──` block and restore the
  original inline registration:
  ```python
  # ── Graceful shutdown ──
  import signal
  import os


  def _shutdown_handler(signum, frame):
      """Stop all running bot engines cleanly on SIGTERM/SIGINT."""
      logger.warning("Received signal %s, stopping all running bots...", signum)
      with _running_engines_lock:
          engine_ids = list(_running_engines.keys())
          for bot_id in engine_ids:
              try:
                  stop_bot(bot_id)
              except Exception:
                  logger.exception("Error stopping bot %s during shutdown", bot_id)
      logger.info("Stopped %d running bot(s)", len(engine_ids))
      raise SystemExit(0)


  if os.environ.get("RUN_MAIN") or "gunicorn" in os.environ.get("SERVER_SOFTWARE", ""):
      signal.signal(signal.SIGTERM, _shutdown_handler)
      signal.signal(signal.SIGINT, _shutdown_handler)
  ```
  (adapted to the file's actual pre-6b body — the two `with _running_engines_lock:`
  sub-blocks are unchanged by this edit; only the surrounding plumbing differs).
  **Do not use `git checkout --`** — see the Baseline warning.
- **Test:** `tests/persistence/test_shutdown_signals.py::TestInstallShutdownHandler` (5)
  + `::TestChainToPreviousHandler` (5) + `::TestShutdownHandler` (3).

### CHG-6b-4 — test-state leak fix in `tests/engines/test_bot_executor.py`

- **File:** `tests/engines/test_bot_executor.py`
- **What:** import `_running_engines` alongside the existing `_running_bots`, and add a
  module-level **autouse** fixture `_isolate_running_registries` that snapshots
  `_running_engines` + `_running_bots` and restores them after each test.
- **Root cause:** `TestRunBotFunction` drives the **real** `run_bot("q1"/"g1"/"m1"/"s1", …)`
  with a mocked `BotEngine`. `run_bot` registers the engine
  (`execution.py:496`) and flags the bot starting, but only `stop_bot()` clears them —
  and those tests never call it. Four ids leaked into module-level state for the rest
  of the session. This is a **pre-existing** test-hygiene bug that only became visible
  once Phase 6b's test observed `_running_engines`.
- **Why:** without it, `test_stops_running_engines_then_chains` failed in the full run
  (`['q1','g1',…,'b-1','b-2'] == ['b-1','b-2']`) while passing in isolation — an
  order-dependent flake.
- **Revert:** delete the `_isolate_running_engines` fixture and the `_running_engines`
  import name from the `from apps.trading.engines.execution import (…)` tuple.

### CHG-6b-5 — Phase 6b test suite

- **File (new):** `tests/persistence/test_shutdown_signals.py` (31 tests).
- **Coverage:**
  1. `TestIsCeleryWorker` (9) — celery/`python -m celery` worker forms accepted;
     `manage.py`, `celery beat`, `celery inspect`, `runserver`, pytest, empty argv
     rejected; `"worker"` in argv without a celery program rejected;
     no-arg form matches `sys.argv` and is `False` under pytest.
  2. `TestCeleryHookInstallation` (5) — `ready()` calls the installer iff
     `_is_celery_worker()`; `ready()` survives a hook failure; both receivers
     connected with `weak=False`; the receiver really reinstalls after a simulated
     Celery clobber and captures Celery's handler for chaining; second fire is a
     no-op that keeps the first chain.
  3. `TestInstallShutdownHandler` (5) — installs SIGTERM+SIGINT; idempotent (keeps the
     first chain); reclaims after an external clobber and rechains; single-signum
     target leaves the other signal alone; returns `False` off the main thread.
  4. `TestChainToPreviousHandler` (5) — calls the chained handler with the original
     args; skips `SIG_DFL` / `SIG_IGN` / missing / self; exception in the chained
     handler is logged and contained.
  5. `TestShutdownHandler` (3) — stops every registered engine then chains;
     empty registry is a quiet no-op; RLock reentrancy.
- **Gotchas encoded in tests:**
  - **`signal.getsignal()` reports `SIG_IGN` for `MagicMock` instances** (CPython only
    round-trips real Python callables) → all "previous handler" doubles are plain
    `def` closures, never `MagicMock`.
  - The `restore_signal_handlers` fixture snapshots/restores SIGTERM+SIGINT **and**
    `_prev_sig_handlers`, so no test leaks a handler into the rest of the suite.
  - `isolated_running_engines` fixture gives the handler tests an empty registry so the
    real (unpatched) `stop_bot` is never invoked.
  - `django_apps.get_app_config("trading")` is used instead of constructing
    `TradingConfig(...)` manually.
- **Revert:** `rm tests/persistence/test_shutdown_signals.py` (+ CHG-6b-4 revert).

---

## Phase 1 — Trade record integrity (DONE 2026-09-27)

Goal: every `BotOrder` row can (a) show a real fill price, (b) name its owning
bot, (c) say whether the trade is open or closed, (d) carry the entry reason and
the realized P/L of the trade it closes — the raw material Phases 3–5 rebuild
state from.

### CHG-1-1 — `BotOrder` additive columns + migration `0017`

- **File:** `apps/bots/models.py` — `BotOrder`, inserted **after `Details`,
  before `created_at`** (never touches an existing column).
- **Added:** `STATUS_CHOICES = [("open","Open"),("closed","Closed")]` and
  `bot_type` (`CharField(20, null, blank, db_index)`),
  `bot_id` (`CharField(64, null, blank, db_index)`),
  `Reason` (`CharField(255, null, blank)`),
  `Status` (`CharField(10, choices, **default="closed"**)`),
  `Realized_PnL` (`DecimalField(20,8, null, blank)`) — all with help_texts.
- **Default `"closed"` is a safety property:** pre-Phase-1 rows can never be
  mistaken for live trades after a restart.
- **Migration:** `apps/bots/migrations/0017_botorder_trade_integrity.py`
  (5 × `AddField`, dependency `bots.0016_rename_quantumaiinvestment_investorportfolio`).
  Auto-generated name was `0017_botorder_realized_pnl_botorder_reason_and_more`;
  renamed while nothing depended on it. Additive only — verified by inspection.
- **Revert:** delete the `# --- Phase 1 (persistence)` block from `BotOrder`
  (from `STATUS_CHOICES = [("open", "Open"), …` through the `Realized_PnL` field)
  **and** `rm apps/bots/migrations/0017_botorder_trade_integrity.py`.
  If it was ever applied to Postgres: `python manage.py migrate bots 0016`.
  (Never edit/replace 0015/0016 — already untracked at baseline.)
- **Test:** `python manage.py makemigrations --check --dry-run` → *No changes
  detected*; `pytest tests/engines/test_order_service.py::TestTradeIntegrity`.

### CHG-1-2 — price resolution + bot linkage in `order_service.py`

- **File:** `apps/trading/engines/order_service.py`
- **Module level (after the logger, before `class BotOrderService`):**
  - `_FILL_PRICE_KEYS = ("average", "fillPrice", "avgPrice", "price", "entryPrice")`
  - `_BOT_FK_MAP = {"grid": (…GridBot, "grid_bot"), "martingale": (…MartingaleBot, "martingale_bot"), "signal": (…SignalBot, "signal_bot")}`
    — **`quantum_ai` deliberately absent**: `BotOrder.quantum_ai_investment`
    points at `InvestorPortfolio`, not `QuantumAIBot`; pk-wiring it would corrupt rows.
  - `_extract_fill_price(details) -> float | None` — reads the exchange
    response (non-dict/0/garbage → `None`).
  - `_resolve_price(explicit, details, bot_config) -> float` — precedence
    explicit → exchange fill → `bot_config["current_price"]` → `0.0`.
    **Root-cause fix:** `bot_config["current_price"]` is *never written* by the
    engine (it is a read-only engine attribute), so `Price` was persisted as 0
    for every order before this change.
- **New method `BotOrderService._link_bot_fk(order_kwargs)`** (inserted under the
  `# SAVE ORDER (DB persistence)` header, *before* `save_order`): best-effort
  polymorphic FK wiring — importlib lookup by `bot_type`, `filter(id=…).first()`,
  **all exceptions logged + swallowed** so a broken link never loses a trade row
  (falls back to `bot_id`/`bot_type`).
- **`save_order` signature** →
  `(self, side, description, details=None, indicators=None, *, price=None, reason=None, status=None, pnl=None)`
  — new params are **keyword-only** ⇒ existing positional callers unchanged.
- **`order_kwargs` gains:** `bot_type` (`bot_config["bot_type"] or None`),
  `bot_id` (`str(...) or None`), `Reason`, `Status` (`status or "closed"`),
  `Realized_PnL`; `Price` now = `_resolve_price(...)`.
  Call order: build kwargs → `self._link_bot_fk(order_kwargs)` → user/indicators → `BotOrder.objects.create(**order_kwargs)`.
- **Revert:** delete `_FILL_PRICE_KEYS`, `_BOT_FK_MAP`, `_extract_fill_price`,
  `_resolve_price`, `_link_bot_fk`; restore `current_price = self.bot_config.get("current_price", 0) or 0`;
  drop the 5 new `order_kwargs` keys; restore signature `(..., indicators=None)`.
- **Test:** `pytest tests/engines/test_order_service.py::TestTradeIntegrity`
  (13: price units + precedence, exchange-beats-config, config fallback, zero,
  defaults, open+reason, exit+pnl, bot_id/bot_type, grid FK wired, quantum
  unlinked, broken id safe) **and** `tests/engines/test_order_service.py::TestSaveOrder`
  (regression: `Price == 50000.0` fallback still holds).

### CHG-1-3 — `BotEngine.save_order` forwards the new kwargs

- **File:** `apps/trading/engines/bot_engine.py` (`def save_order`, ~:634)
- **Change:** signature `(self, side, description, details=None)` →
  `(..., details=None, *, reason=None, status=None, pnl=None, price=None)`;
  forwards all four + `indicators=self._get_indicators()` to
  `self.order_service.save_order(...)`. `details` **stays the 3rd positional**
  so `save_order("Buy", "TEST ENTRY")` (tests at 992/1013/1029/1038) still works.
- **Revert:** drop the 4 keyword params from the signature and the 4 forwarded
  kwargs (`reason=…, status=…, pnl=…, price=…`) from the `order_service.save_order` call.
- **Test:** `pytest "tests/engines/test_bot_engine.py::TestSaveOrderTradeIntegrity"`
  (4 passed: forwards, legacy-positional defaults, close path, close_all path).

### CHG-1-4 — call sites mark live / closed + reason

- **File:** `apps/trading/engines/bot_engine.py` (4 call sites)
  1. **strategy entry (:447)** `self.save_order(side.upper(), signal.reason, detail, reason=signal.reason, status="open")`
  2. **manual buy (:522)** `await sync_to_async(self.save_order)("BUY", "CUSTOM BUY ORDER", details=detail, reason="Custom BUY", status="open")`
  3. **manual sell (:545)** same with `"SELL"`, `"Custom SELL"`.
  4. **`close_open_order` (:689)** `self.save_order(result["side"], description, result["detail"], status="closed", pnl=result["pnl"])`
- `close_all_orders` (:700) delegates to `close_open_order` → **no edit needed**
  (a test now pins that).
- **Revert:** strip the kwargs from those 4 calls (the `details=detail` form used
  by the manual paths can go back to a bare 3rd positional argument).
- **Test:** `test_start_bot_buy_case1_ema_rsi` (updated assert, see CHG-1-5),
  `TestCloseOpenOrder` + `TestSaveOrderTradeIntegrity::test_close_open_order_marks_closed_with_realized_pnl`.
- **Note:** close records write `result["side"]` = the *position* side
  (`"short"`/`"long"`) — pre-existing behaviour, pinned on purpose.

### CHG-1-4b — `_log_trade` (webhook/execution path) writes linkage

- **File:** `apps/trading/engines/execution.py` (`_log_trade`, ~:339)
- **Change:** extracts `bot_id`/`bot_config.get("bot_type")` and adds to the
  existing `BotOrder.objects.create(...)`: `bot_id=str(bot_id) if bot_id else None`,
  `bot_type=bot_type or None`, `Reason=signal.reason`, `Status="open"`.
  (`Price=signal.price or order.get("price", 0)` was already real here — this is
  the second of the only **two** `BotOrder.objects.create` sites in `apps/`.)
- **Revert:** delete those 4 kwargs from the create call (and the `bot_id`/
  `bot_type` extraction 4 lines above it).
- **Test:** covered indirectly by the full suite (no `_log_trade` unit test exists
  at baseline); `pytest tests/engines/test_bot_executor.py` stays green.

### CHG-1-5 — Phase 1 test suite

- **New:** `tests/engines/test_order_service.py::TestTradeIntegrity` (13 tests).
- **New:** `tests/engines/test_bot_engine.py::TestSaveOrderTradeIntegrity` (4 tests).
- **Updated (behaviour change, not a bug):** `test_start_bot_buy_case1_ema_rsi`
  assert relaxed to the new contract —
  `save_order.assert_called_once_with("BUY", "EMA + RSI BUY LONG (CASE1)", <detail>, reason="EMA + RSI BUY LONG (CASE1)", status="open")`.
- **Revert:** delete both new classes; restore the single-argument assertion in
  `test_start_bot_buy_case1_ema_rsi`.

---

## Phase 2 — `BotRuntimeState` + `apps/trading/state.py` (DONE 2026-09-27)

Goal: a durable, upsert-able row per bot holding the engine snapshot + lifecycle
(`status`/`heartbeat_at`/`worker`) that Phase 3 (snapshot/restore), Phase 4
(recovery query) and Phase 5 (watchdog) all read.

### CHG-2-1 — `BotRuntimeState` model

- **File:** `apps/trading/models.py` (appended after `StrategyConfig`).
- **Fields:** `bot_type` (choices grid|martingale|quantum_ai|signal|custom),
  `bot_id` (indexed), `status` (`running|stopping|stopped`, default `running`,
  indexed), `state` (`JSONField(default=dict)` — opaque engine snapshot, shape
  owned by Phase 3), `worker` (owner id, double-run guard),
  `heartbeat_at`, `created_at`, `updated_at`.
- **Meta:** `db_table = "trading_bot_runtime_states"`, `ordering = ["-updated_at"]`,
  `UniqueConstraint(bot_type, bot_id)` named `uniq_trading_bot_runtime_state`.
- **Design choice — no ForeignKey:** recovery addresses bots by the same uniform
  `(bot_type, bot_id)` pair `BotOrder` uses (no join, and the quantum_ai /
  `InvestorPortfolio` FK trap is impossible here). Class constants
  `STATUS_RUNNING/STOPPING/STOPPED` are the only lifecycle strings.
- **Migration:** `apps/trading/migrations/0002_botruntimestate.py`
  (dep `trading.0001_initial`, single `CreateModel`).
  **Note:** migration numbers are per-app — this is `0002`, *not* `0018`
  (`0018` would be the next `bots` app migration; `0017` was Phase 1's).
- **Revert:** delete the `# BOT RUNTIME STATE` class block from
  `apps/trading/models.py` + `rm apps/trading/migrations/0002_botruntimestate.py`
  (+ `migrate trading 0001` if it was ever applied).
- **Not done on purpose:** no admin registration (managed programmatically),
  no FK cascade (stale rows are ignored by recovery, `rt.delete()` removes them).

### CHG-2-2 — `apps/trading/state.py` helpers

- **New file:** `apps/trading/state.py` — re-exports `RUNNING/STOPPING/STOPPED`
  and provides: `upsert(bot_type, bot_id, state=None, *, status, worker)`
  (`update_or_create`; **`state=None` keeps the stored payload** so a
  status-only update never wipes a snapshot; always stamps `heartbeat_at`),
  `get`, `get_state` (**never raises, `{}` on fresh DB**), `set_status`
  (`False` if row missing), `touch` (heartbeat only; **creates the row when
  absent** — an alive engine must always have a row), `delete` (returns row
  count), `running(*, bot_type, worker)` (Phase 4 candidate set),
  `stale(seconds)` (`status=running` AND (`heartbeat_at IS NULL` OR `< now-seconds`)
  — Phase 5 input).
- **Contract (module docstring):** reads are non-raising (recovery runs before
  any engine boot); writes may raise; the `state` payload shape is Phase 3's.
- **Revert:** `rm apps/trading/state.py` (nothing imports it yet in
  production code — Phase 3/4/5 are its consumers).

### CHG-2-3 — Phase 2 test suite

- **New:** `tests/persistence/test_runtime_state.py` (16 tests) — model
  defaults/unique/`__str__`; `upsert` create + `state=None` preservation +
  replace; non-raising reads on a fresh DB; lifecycle (`set_status` missing→False,
  `touch` creates, `touch` preserves payload + advances heartbeat, `delete`);
  `running()` filters (sets — Meta ordering is `-updated_at`); `stale()` includes
  old + null heartbeats, excludes fresh and cleanly-stopped rows.
- **Revert:** `rm tests/persistence/test_runtime_state.py`.

---

---

## Phase 3 — snapshot / restore (DONE 2026-09-27)

Goal: persist every running bot's live state (side/count/price/reason,
levels, running P/L, indicators, monitoring flags) and rebuild it after a
crash — the core of the <15s blind-window requirement. Event-driven
(force=True at lifecycle points) + throttled monitor-loop tick.

### CHG-3-1 — `apps/trading/state.py` snapshot/restore primitives

- **File:** `apps/trading/state.py`, appended after Phase 2's `stale()` under
  the `# PHASE 3 — SNAPSHOT / RESTORE` banner (banner :135-137,
  `SNAPSHOT_SCHEMA` :142, through end of file = `restore_engine` :370-end).
  Phase 2 API above (helpers, `RUNNING/STOPPING/STOPPED` re-exports :35-37) untouched.
- **Added:**
  - `SNAPSHOT_SCHEMA = 1` (:142) — payload version; `apply_state`/`restore_engine`
    refuse unknown schema **before any mutation**.
  - `SNAPSHOT_THROTTLE_S = 5.0` (:147) — crash blind window ≤5s from the loop.
  - `_engine_identity(engine)` (:150) → `(bot_type, bot_id)` from
    `engine.config` (default type `"grid"`; ids `str()`-coerced;
    missing/empty id → `(bot_type, None)` = not DB-tracked, snapshot skipped).
  - `_worker_id()` (:159) — `f"{socket.gethostname()}:{os.getpid()}"`.
  - `save_snapshot(bot_type, bot_id, state, *, worker=None)` (:164) — upserts
    `state` + `heartbeat_at` only; `worker` written **only when explicitly
    passed** (else preserved / model default `""`); **never touches `status`**
    — the contract that lets heartbeat writes coexist with the STOPPING/STOPPED
    lifecycle set by `tasks.stop_bot` / watchdog.
  - `collect_state(engine)` (:186) → schema-v1 dict, keys verbatim:
    `schema, ts, side, count, price, reason, prev_reason, last_trade_pnl,
    favor_lvl, against_lvl, percentage, unrealized_pnl, signals_generated,
    orders_executed, indicators{EMA,RSI,PrevRSI,BB,RSI_color,RSI_prev_color},
    monitoring, bot_running`. Levels fall back engine← when
    `engine.grid_monitor` is None; `percentage`/`monitoring`/`bot_running`
    are monitor-owned (0.0/False/False with no monitor). Derived flags
    (`NoTrade`, `BuyTrade`, …) are **never stored** — recomputed on apply.
  - `apply_state(engine, payload)` (:235) — empty/non-dict/`schema != 1` →
    False before mutation; key-presence guards; mirrors core fields into
    `engine.grid_monitor` when present (incl. `Percentage`/`Unrealized_Pnl`
    written onto the monitor); recomputes derived flags: `EmaBuy = price >= EMA != 0`,
    RSI bounds from `pair_config["RSI_Lower"/"RSI_Upper"]` + `RSI_color == "white"`,
    `BBBuy` in (Crossing Down Band / Closed Below Lower Band / Up Arrow),
    `NoTrade = count==0 and side=="None"`, `Buy/SellTrade = count==1 and
    side==…`; calls `engine._sync_strategy()` if callable; does **not** restore
    `monitoring`/`bot_running` (Phase 4 starts threads explicitly); corrupt
    value → exception → caller gets False, engine untouched where possible.
  - `snapshot_engine(engine, *, force=False, throttle_s=5.0, worker=None)`
    (:338) — 5s monotonic throttle (`engine._snapshot_monotonic`) stamped only
    after a successful write; `force=True` bypasses; never raises (False +
    `logger.exception`).
  - `restore_engine(engine)` (:370) — `get_state` (missing row → False,
    non-raising) + `apply_state`; **not yet called from production code** —
    Phase 4 wires it into `run_bot(restore_mode=True)`.
- **Revert:** in `apps/trading/state.py`, delete from the `# ====` banner line
  at **:135** through end of file (keeps Phase 2 intact — verify: file still
  ends at `stale()` and `python -c "import apps.trading.state"` works).
  No caller outside tests references these yet (only `bot_engine._snapshot_tick`),
  so also revert CHG-3-3 or imports break.
- **Test:** CHG-3-4 classes `TestCollectState`, `TestApplyState`,
  `TestSnapshotThrottle`, `TestSnapshotPersistence`.

### CHG-3-2 — `GridPositionMonitor.snapshot_cb` (ctor + both loops)

- **File:** `apps/trading/engines/grid_monitor.py`.
- **Added:** kwarg `snapshot_cb: Optional[Callable] = None` (:45, after
  `stop_cb`) → stored `self._snapshot_cb = snapshot_cb` (:60); both monitor
  loops tick it once per iteration right after the heartbeat update:
  grid-order loop `if self._snapshot_cb: self._snapshot_cb()` (:339-340,
  before `fetch_open_orders`), loss loop same (:590-591, after heartbeat).
- **Default `None` = zero behavior change** for every pre-existing caller
  (webhook/grid tests unchanged — verified by full suite).
- **Revert:** 4 edits — remove kwarg (:45) + attribute (:60); remove the two
  `if self._snapshot_cb:` blocks (:339-340 and :590-591).
- **Test:** CHG-3-4 `TestMonitorWiring` (default None, ctor identity,
  grid-loop 1 call with remote-stop `side_effect=[False, True]`,
  loss-loop 1 call with `_stop_event` mocked).

### CHG-3-3 — `BotEngine` wiring + `tasks.stop_bot` STOPPED flush

- **Files:** `apps/trading/engines/bot_engine.py`, `apps/trading/tasks.py`.
- **bot_engine.py:** `from apps.trading import state as runtime_state` (:35);
  ctor passes `snapshot_cb=self._snapshot_tick` into `GridPositionMonitor`
  (:118-120); `def _snapshot_tick(self, force: bool = False) -> bool`
  (:404-412) → `return runtime_state.snapshot_engine(self, force=force)`;
  startBot force-snapshots on the restore path (:433) and after the
  NoTrade/fall-through path (:518).
- **tasks.py:** `stop_bot` step 4 (:142-144) — function-local
  `from . import state as runtime_state` inside try/except →
  `runtime_state.set_status(bot_type, bot_id, runtime_state.STOPPED)`;
  any failure is swallowed so a status write can never fail a stop (durable
  `is_running`/`stopped_at` flags already committed in step 3).
- **Revert (per-edit — bot_engine.py is dirty at baseline, NEVER
  `git checkout --`):** delete import (:35), kwarg line (:118-120 comment +
  kwarg), `_snapshot_tick` method (:404-412), call sites (:433, :518);
  delete `tasks.py` step-4 block (:140-146 incl. its comment). Reference the
  mirrored reverse snippets in CHG-6a-9 for `stop_bot` context.
- **Test:** CHG-3-4 `TestEngineWiring` (ctor binds `snapshot_tick.__self__`
  to the engine, delegation of both `force` values, startBot normal path
  evaluates+force-snapshots once, restore path skips `_evaluate_conditions`)
  and `TestStopBotFlush` (STOPPED row with payload preserved, no row → no
  orphan, `set_status` raising → stop still succeeds).

### CHG-3-4 — Phase 3 test suite

- **New:** `tests/persistence/test_snapshot_restore.py` — **35 tests**
  (646 lines), 7 classes: `TestCollectState` (4), `TestApplyState` (9),
  `TestSnapshotThrottle` (4), `TestSnapshotPersistence` (7),
  `TestMonitorWiring` (4), `TestEngineWiring` (4), `TestStopBotFlush` (3).
- **Harness facts (why the tests are shaped this way):**
  - module `pytestmark = pytest.mark.django_db` (same as `test_stop_bot.py`);
    `_grid_bot()` copied verbatim; `user` fixture from root `conftest.py`.
  - `_engine_config()` returns a **fresh dict per call** — `BotEngine.__init__`
    mutates `config["parameters"]`.
  - `_stub_gm()` always includes `Percentage`/`Unrealized_Pnl` — `apply_state`
    writes them onto the monitor unconditionally inside the gm branch.
  - `engine.config` is the **same object** passed to the ctor — `startBot`
    reads `restore_mode` from it.
  - `fetch_ticker` must return a real dict (`{"last": 50000.0}`) — MagicMock
    keys produce child mocks.
  - grid-loop tick test uses remote-stop `side_effect=[False, True]` (break is
    inside the try, per CHG-6a-6) and patches
    `apps.trading.engines.grid_monitor.time.sleep`; loss-loop test mocks
    `_stop_event` (`is_set=False`, `wait=True`) and `_check_loss_profit_percent`.
- **Revert:** `rm tests/persistence/test_snapshot_restore.py`.

---

## Phase 4 — boot recovery: `worker_ready` → `recover_running_bots` (DONE 2026-09-28)

Goal: on Celery worker boot, reclaim every `BotRuntimeState` row left
`RUNNING` by a crashed worker (heartbeat older than
`RECOVERY_MIN_STALE_S = 15.0` — live engines write every 1-5 s, so an
older row belongs to a dead process), decide dispatch vs skip, and relaunch
the bot as `run_trading_bot(..., restore_mode=True)` so `startBot` applies
the Phase 3 snapshot **before** attaching to the exchange position.
Together with the <5 s snapshot throttle this closes the crash→reboot gap.

### CHG-4-1 — `recover_running_bots` in `apps/trading/state.py`

- **File:** `apps/trading/state.py` (516 lines after Phase 4) — new
  `# BOOT RECOVERY — Phase 4 (CHG-4-1)` banner at :391-393, content
  :401-end; plus a module-level import at :27.
- **Added:**
  - `from django.core.exceptions import ValidationError` (:27) — needed by
    the defensive lookup below.
  - `RECOVERY_MIN_STALE_S = 15.0` (:401) — staleness window; docstring
    notes multi-worker deployments must raise it above their heartbeat
    period so a booting worker never steals a sibling's healthy engine
    (dispatch-side dedupe: `set_status` refreshes `heartbeat_at`, so a
    sibling's fresh row makes `stale()` skip it on its own boot).
  - `_RECOVERY_MODEL_MAP = ("grid", "martingale", "quantum_ai")` (:407) —
    exactly the three types `check_stale_bots` owns. SignalBot has no
    `is_running`/`last_heartbeat` (webhook-owned) → rows are rejected as
    ineligible, never guessed at.
  - `_recovery_model(bot_type)` (:410) — returns the model class (function-
    local imports) or `None` when ineligible.
  - `_payload_has_position(payload)` (:431) — `None`/`{}` (crashed before
    first snapshot) → `True` = dispatch, let attach decide; explicitly flat
    payload (`side in ("None", "")` and `count == 0`) → `False` = skip
    (idle engines are owned by the `check_stale_bots` beat reaper).
  - `recover_running_bots(*, min_stale_s=RECOVERY_MIN_STALE_S) -> Dict`
    (:446) — lazy `from .tasks import run_trading_bot` (avoids the
    tasks↔state import cycle **and** makes `apps.trading.tasks.
    run_trading_bot` the single patch target in tests). Per candidate:
    1. ineligible type → `set_status(STOPPED)` + `errors` entry;
    2. `model.objects.filter(id=bot_id).first()` inside
       `except (ValidationError, ValueError)` → `bot = None` (a mangled/
       non-UUID `bot_id` **raises** on a UUID pk instead of returning an
       empty qs — found by `test_deleted_bot_marks_row_stopped`);
    3. missing bot → row → `STOPPED` + `errors`;
    4. `not bot.is_running` → row → `STOPPED` + `skipped` (stale crash
       leftover for an already-stopped model);
    5. flat payload → `skipped` (row left RUNNING — beat owns it);
    6. else `set_status(bot_type, bot_id, RUNNING)` (row-heartbeat refresh
       = boot dedupe), `bot.last_heartbeat = now` with
       `update_fields=["last_heartbeat", "updated_at"]` (auto_now column
       must be included or MySQL/SQLite warn/drop it), then
       `run_trading_bot.delay(str(bot_id), bot_type, restore_mode=True)`
       → `recovered`.
    Every candidate is wrapped in try/except → one bad row records an
    `errors` entry and the loop continues (never raises to Celery boot).
    Returns `{"recovered": [...], "skipped": [...], "errors": [...]}` +
    `logger.info` summary (`state.py:505`-style line).
- **Revert:** in `apps/trading/state.py` delete (a) line :27 import and
  (b) everything from the `# ===` banner line at **:391** through EOF —
  Phase 3 ends at `restore_engine` :388; verify with
  `wc -l` (→ ~393) and `python -c "import apps.trading.state"`.
  Then revert CHG-4-3 (no caller left) — or the hook would NameError.
- **Test:** CHG-4-4 classes `TestRecoverRunningBots` (10),
  `TestRecoveryUnitContracts` (3 + 6-param matrix).

### CHG-4-2 — `startBot(restore_mode=True)` applies snapshot before attach

- **File:** `apps/trading/engines/bot_engine.py` (baseline-dirty file —
  per-edit revert only, never `git checkout --`).
- **Added:** in the `if restore_mode:` branch, comment block :430-433 +
  `runtime_state.restore_engine(self)` at **:434**, inserted **before**
  `self._start_monitoring_for_existing_position()`. Order matters:
  `apply_state` puts reason/indicators/P&L/count from the payload onto the
  fresh engine, then attach overwrites side/count/levels/prices with live
  exchange truth — so the engine never flips back to `side="None"` for a
  restored position. No row/payload → `restore_engine` returns `False`
  (never raises) → identical cold start. The existing
  `_snapshot_tick(force=True)` after attach captures the post-attach state.
- **Revert:** delete the 5 comment lines + the `runtime_state.
  restore_engine(self)` line (block :430-434); keep the Phase 3
  `_snapshot_tick(force=True)` line that follows.
- **Test:** CHG-4-4 `TestStartBotRestoreWiring`
  (`test_restore_engine_applied_before_attach` asserts call ORDER
  `["restore", "attach"]` via a patched `apps.trading.state.restore_engine`,
  payload visibility on `eng2`, and no entry eval);
  existing `test_startbot_restore_mode_skips_entry_eval` stays green
  (module has `pytestmark = django_db`, so the new DB row lookup works).

### CHG-4-3 — Celery `worker_ready` hook in `apps/trading/apps.py`

- **File:** `apps/trading/apps.py`.
- **Added:**
  - `_install_celery_recovery_hook()` (:74, above `TradingConfig`) —
    function-local `from celery import signals`; nested `_recover(**_kw)`
    receiver wrapping `recover_running_bots()` in try/except (boot must
    never die on a bad row) + `logger.info` summary;
    `signals.worker_ready.connect(_recover, **kw)` with **`weak=False`**
    (module-function receivers are garbage-collected otherwise).
    `worker_ready` **only** — NOT `worker_process_init`, which fires per
    pool child and would dispatch every bot N times.
  - `ready()` now calls `_install_celery_recovery_hook()` at **:121** in
    its own try/except with `logger.exception("Failed to install Celery
    boot-recovery hook")` (:123), after the existing
    `_install_celery_shutdown_hooks()` (:117).
- **Revert:** delete `_install_celery_recovery_hook` (lines :74-~105) and
  the two-call try/except block inside `ready()` (keep CHG-6b's shutdown
  hooks call). Verified clean-at-baseline file → after revert
  `git diff apps/trading/apps.py` must show only the Phase 6b-era edits.
- **Test:** CHG-4-4 `TestRecoveryHookInstallation` (6) — receiver captured
  by patching `celery.signals.worker_ready.connect`; asserts exactly ONE
  connect (worker_ready only), `weak=False`, receiver calls
  `state.recover_running_bots`, receiver swallows its own exceptions,
  `cfg.ready()` wiring for `_is_celery_worker()=True`, no-op for `False`,
  and `ready()` surviving an installer failure.

### CHG-4-4 — Phase 4 test suite

- **File:** `tests/persistence/test_recovery.py` (new, 363 lines, 21
  functions / 26 tests incl. parametrize). `pytestmark = django_db`.
- **Coverage:** dispatch matrix (stale+position → dispatch + both
  heartbeats refreshed; fresh row → no-op; idle payload → skipped, row
  stays RUNNING; empty payload → dispatch; missing bot → STOPPED +
  errors; `is_running=False` → STOPPED + skipped; ineligible type →
  STOPPED + errors; `min_stale_s` threshold; dispatch failure → error
  recorded + next candidate still attempted — row order is
  `Meta.ordering = ["-updated_at"]`, **not** creation order, so the test
  asserts set-equality of attempted candidates, not sequence; `GridBot.save`
  raising → recorded, not fatal) + unit contracts (`_recovery_model` map,
  `_payload_has_position` 6-case matrix, default constant) + hook
  installation + `ready()` wiring + `startBot` order/visibility tests.
- **Revert:** delete the file.
- **Test:** `.venv/bin/python -m pytest tests/persistence/test_recovery.py -q`
  → **26 passed**; with `test_snapshot_restore.py` + `test_shutdown_signals.py`
  → 92 passed.

## Phase 5 — watchdog tuning (DONE 2026-09-28)

**Goal:** shrink the blind window when a worker *process* dies (no boot hook).
Two-tier timing contract, both layers now aligned:
- **Tier 1 (boot, seconds):** `BotRuntimeState.heartbeat_at` stale 15 s
  (`RECOVERY_MIN_STALE_S`, Phase 4) vs snapshot writes throttled at 5 s →
  `recover_running_bots` on worker start.
- **Tier 2 (periodic watchdog):** model `last_heartbeat` every ~10 s, stale
  cutoff 30 s, Beat polls every 30 s → detects a dead worker without restart.
  Worst-case detection ~60 s (cutoff 30 s + poll 30 s), vs ~5–10 min before.

### CHG-5-1 — heartbeat cadence 60 → 10 s

- **File:** `apps/trading/engines/grid_monitor.py`
- **Change:** `__init__` `self._heartbeat_interval = 60` → `10` (now :85;
  price loop writes `last_heartbeat` at :338 every 10 iterations ≈ 10 s at
  ~1 s/iter); loss/SL-TP loop `% 12` (5 s wait × 12 = 60 s) → `% 2`
  (5 s × 2 = 10 s) at :591. 2-line comments added at both sites.
- **Revert:** `= 10` → `= 60`; `% 2` → `% 12`; delete the 4 comment lines.
- **File:** `apps/trading/engines/bot_engine.py`
- **Change:** vestigial `self._heartbeat_interval = 60` → `10` (defined at
  :164 but **never read** — the monitor loops own the DB writes; kept in sync
  so the constant doesn't lie) + 2-line comment.
- **Revert:** `= 10` → `= 60`; delete the 2 comment lines.
- **Test:** `TestPhase5WatchdogTuning::test_heartbeat_interval_is_10_iterations`.

### CHG-5-2 — stale cutoff 5 min → 30 s

- **File:** `apps/trading/tasks.py` — `check_stale_bots()`
- **Change:** `cutoff = timezone.now() - timedelta(minutes=5)` →
  `timedelta(seconds=30)` + 2-line comment; docstring "in > 5 minutes" →
  "in > 30 seconds", "Runs every 2 minutes via Celery Beat" → "Runs every
  30 seconds via Celery Beat (Phase 5 / CHG-5-2, CHG-5-3)"; never-heartbeat
  comment "> 5 min ago" → "> 30s ago".
- **Revert:** `seconds=30` → `minutes=5`; restore the three old doc/comment
  strings; delete the 2-line comment.
- **Test:** `test_stale_cutoff_is_30_seconds` (2-min-old heartbeat caught —
  the old 5-min cutoff would have MISSED it; fresh heartbeat not reaped).

### CHG-5-3 — Celery Beat schedules

- **File:** `config/celery.py`
- **Change:** `check-stale-bots` `120.0` → `30.0` (comment 2 min → 30 s);
  `heartbeat-check` `300.0,  # 5 minutes` → `60.0,  # Phase 5 (CHG-5-3)`;
  `run-active-bots` **unchanged** (already 60.0). Note: the plan's wording
  "`check_all_active_bots` 300→60" maps to `heartbeat-check` (a 300 s task
  that delegates to `check_stale_bots`); `heartbeat-check` and
  `check-stale-bots` intentionally both poll — duplicate, idempotent.
- **Revert:** `30.0` → `120.0`; `60.0` → `300.0` (+ restore `# 5 minutes`).
- **Test:** `test_beat_schedules_tuned`.

### CHG-5-4 — Phase 5 tests

- **File:** `tests/engines/test_trading_tasks.py`
- **Change:** new class `TestPhase5WatchdogTuning` (3 tests) inserted after
  `TestHeartbeatCheck`: cadence constant, 30 s cutoff regression, beat
  schedules.
- **Revert:** delete the class.
- **Test:** `.venv/bin/python -m pytest tests/engines/test_trading_tasks.py -q`
  → **33 passed** (30 old + 3 new; first run caught a test-logic slip:
  `now-20s < now-30s` is False — a 20 s-old heartbeat is *fresh*; the stale
  fixture must be **older** than 30 s, so it uses 2 minutes).

### Known observations (pre-existing, out of Phase 5 scope)

- `check_all_active_bots` (60 s) re-dispatches running bots with
  `restore_mode=False`; `run_bot`'s DB-flag guard returns "already running
  (DB flag)" → `run_trading_bot` retries once → deduped by
  `task_dedup_{id}`. Wasteful but stable; untouched.
- A false-positive stale reap (heartbeat delayed >30 s by DB load) leaves
  `is_running=False` while the engine keeps running; heartbeats resume and
  the next pass skips the bot, but the flag stays False until a restore
  dispatch. Same pattern as the old 5-min path, now with a 3x margin
  (10 s cadence vs 30 s cutoff).

## CHG-3-5 — shutdown-path forced snapshot (DONE 2026-09-28)

**Goal:** close the CHG-6b deferred half — the only residual of Phase 3.
Before this, a graceful in-process SIGTERM/SIGINT stopped the engines
(`execution.stop_bot`) but never wrote a final `BotRuntimeState` snapshot, so
the row kept whatever the <=5 s-throttled tick last persisted. Now the handler
force-snapshots every live engine *before* teardown.

### CHG-3-5-1 — `_shutdown_handler` final snapshot

- **File:** `apps/trading/engines/execution.py` — `_shutdown_handler()` (:659)
- **Change:** body rewritten (was: peek keys -> `stop_bot(bid)` loop -> log):
  1. peek `engine_items = list(_running_engines.items())` under the RLock
     (values too — the snapshot needs the engine objects; registry left
     intact so `stop_bot` still does its own pop under the same lock);
  2. function-local `from apps.trading import state as runtime_state` inside
     try/except (import failure logs + `runtime_state = None` — teardown must
     still proceed); function-local keeps `execution.py` free of a module-level
     state/models import (no cycle risk at app-load time);
  3. per-engine best-effort `runtime_state.snapshot_engine(engine, force=True)`
     in try/except (`engine is None` skipped; failures logged via
     `logger.exception`) — `force=True` bypasses `SNAPSHOT_THROTTLE_S`;
  4. unchanged stop loop `for bid, _ in engine_items: stop_bot(bid)` +
     count log.
  All snapshots precede all stops (capture live state first). No status
  write: `save_snapshot` only touches payload+heartbeat — a SIGTERM'd row
  stays `running` with a fresh payload, so Phase 4 boot recovery re-dispatches
  it after a deploy restart; deliberate user stops still go through
  `tasks.stop_bot` -> `status=STOPPED`. Best-effort by contract: no
  persistence failure may block process shutdown.
- **Revert:** restore the old body (the `_chain_to_previous_handler(signum,
  frame)` tail is untouched by this change):

  ```python
  def _shutdown_handler(signum, frame):
      """Signal handler for SIGTERM/SIGINT — stops all running engines."""
      logger.warning(f"Received signal {signum}, stopping all running bots...")
      with _running_engines_lock:
          engine_ids = list(_running_engines.keys())
      for bid in engine_ids:
          stop_bot(bid)
      logger.info(f"Stopped {len(engine_ids)} running bot(s)")
  ```

- **Test:** `TestShutdownSnapshot` — see CHG-3-5-2.

### CHG-3-5-2 — shutdown snapshot tests

- **File:** `tests/persistence/test_shutdown_signals.py` — new class
  `TestShutdownSnapshot` (:330, 4 tests) appended after `TestShutdownHandler`:
  - `test_snapshot_before_teardown_with_force` (:338) — event order
    `[snapshot, snapshot, stop, stop]` + every snapshot `force=True`
    (patches `apps.trading.state.snapshot_engine`; the function-local import
    resolves the attribute at call time, so the patch is visible);
  - `test_snapshot_failure_never_blocks_stop_or_chain` (:363) —
    `snapshot_engine` raising `RuntimeError` -> stops still ran,
    `_prev_sig_handlers` chain still replayed, handler does not raise;
  - `test_one_engine_failure_still_snapshots_the_rest_and_stops_all` (:385) —
    first engine boom -> second still snapshotted, both stopped, all forced;
  - `test_identityless_engine_is_a_quiet_noop` (:406) — REAL
    `snapshot_engine` on a bare `object()` engine: `_engine_identity` returns
    `None` before any DB work -> False, no write, no raise (stop side mocked
    so a non-engine never goes through teardown).
  The file has no `pytestmark`/`django_db` -> the new tests stay DB-free
  (force/throttle DB behaviour is already covered by `TestSnapshotThrottle`
  in `test_snapshot_restore.py:343`).
- **Revert:** delete the `TestShutdownSnapshot` class (lines ~328-420); no
  other test changed — the 3 pre-existing `TestShutdownHandler` tests pass
  unmodified (their `object()` engines hit the identity short-circuit on the
  real snapshot path).
- **Test:** `.venv/bin/python -m pytest tests/persistence/test_shutdown_signals.py -q`
  -> **35 passed** (31 old + 4 new).

### Known observations (pre-existing, out of CHG-3-5 scope)

- The handler's `stop_bot(bid)` binds to `execution.stop_bot` with default
  `bot_type="quantum_ai"` -> for grid/martingale bots the model-flag update
  no-ops (wrong table), and quantum bots get `is_running=False` -> Phase 4
  recovery marks their row STOPPED (quantum not auto-restored after a
  graceful SIGTERM). Baseline behaviour (verified against `6752b71` — the
  "Update DB flag" write already existed there); CHG-3-5 only adds the
  snapshot and does not change stop semantics.
- `execution.stop_bot` itself never touches `BotRuntimeState` — by design:
  the shutdown path snapshots first (this change), while `tasks.stop_bot`
  owns the deliberate user-stop `status=STOPPED` flush.

### CHG-T-1 — persistence hardening test matrix (2026-09-29)

**File:** `tests/persistence/test_persistence_hardening.py` (NEW, 301 lines —
tests only; no production code touched)

**Change:** 13 tests covering the four properties the phase suites left
uncovered. Complements (never duplicates) test_snapshot_restore / test_recovery
/ test_stop_bot / test_shutdown_signals:

- **Security (4):** hostile payload keys (`user_id`/`status`/`is_running`/
  `worker`/`config`/`bot_id`) can never become engine attributes or rewrite
  identity; snapshot scoped strictly to `(bot_type, bot_id)` (cross-bot AND
  same-id/different-type leak attempts); tampered DB schema (`99`/`"abc"`/`[]`)
  refused with zero engine mutation — covers both the `apply_state` False path
  and the `int(schema)` exception path swallowed by `restore_engine`.
- **Optimization (3):** 20-tick burst = exactly 1 write + 1 SELECT
  (CaptureQueriesContext; SAVEPOINT/RELEASE noise filtered); `collect_state`
  = 0 queries (hot loop stays pure); `GridPositionMonitor._update_heartbeat`
  = 1 UPDATE, no SELECT (duck-typed `self` — method only reads `bot_config`).
- **Reliability (4):** pre-write `_Bomb` collect failure → `False`, no write,
  stamp NOT consumed (distinct from the post-write test at
  test_snapshot_restore:364); `json.dumps(collect_state(...))` with Decimal
  inputs pins the float()/int() casts (a Decimal leak would kill every
  JSONField save silently); stale boundary exact — 14 s alive, 16 s dead
  against default `RECOVERY_MIN_STALE_S=15`.
- **Concurrency (1):** 8 threads × `snapshot_engine` → no exception, writes
  bounded `1 ≤ call_count ≤ 8` (check-then-act race is ≤N, never >N),
  `True` results == save calls (no torn state).

**Revert:** delete the one file:
```
rm tests/persistence/test_persistence_hardening.py
```
No other file depends on it (no fixtures/imports point back).

**Test:** `.venv/bin/python -m pytest tests/persistence/test_persistence_hardening.py --tb=short -q` → **13 passed**;
full suite → **2183 passed, 13 skipped** (2170 + 13);
`/usr/bin/flake8 tests/persistence/test_persistence_hardening.py` → **0 findings** (exit 0).

## Test status
| When | Command | Result |
|---|---|---|
| Baseline (pre-persistence) | `.venv/bin/python -m pytest --tb=short -q` | 2006 passed, 13 skipped |
| After CHG-6a-1..9 | same | 2006 passed, 13 skipped (no regressions) |
| After CHG-6a-10 (tests) | same | **2038 passed, 13 skipped** (+32 new) |
| Targeted Phase 6a | `pytest tests/persistence tests/engines/test_bot_engine.py` | 124 passed |
| Targeted (pre-new-tests) | `pytest tests/engines/test_trading_tasks.py test_bot_executor.py test_bot_engine.py test_grid_monitor.py` | 210 passed |
| After CHG-6b-1..3 (code) | `pytest tests/persistence/test_shutdown_signals.py` | 31 passed (isolated) |
| After CHG-6b-4 (leak fix) | `pytest tests/persistence tests/engines/test_bot_executor.py tests/engines/test_redis_state.py tests/engines/test_bot_engine.py` | 214 passed |
| **After CHG-6b-1..5 (full suite)** | `.venv/bin/python -m pytest --tb=short -q` | **2069 passed, 13 skipped** (2006 baseline + 26 + 6 + 31) |
| Targeted Phase 1 (after code) | `pytest tests/engines/test_order_service.py "tests/engines/test_bot_engine.py"` | 141 passed (1 fix: CASE1 assert) |
| **After CHG-1-1..1-5 (full suite)** | `.venv/bin/python -m pytest --tb=short -q` | **2086 passed, 13 skipped** (2069 + 17 new) |
| Migration check | `python manage.py makemigrations --check --dry-run` | *No changes detected* |
| Targeted Phase 2 | `pytest tests/persistence/` | 73 passed (57 old + 16 new) |
| **After CHG-2-1..3 (full suite)** | `.venv/bin/python -m pytest --tb=short -q` | **2102 passed, 13 skipped** (2086 + 16) |
| Targeted Phase 3 | `pytest tests/persistence/test_snapshot_restore.py` | 35 passed (after 2 fixes: `_engine_config` needed `parameters.symbol`; `PrevReason` assert) |
| **After CHG-3-1..4 (full suite)** | `.venv/bin/python -m pytest --tb=short -q` | **2137 passed, 13 skipped** (2102 + 35) |
| Migration check (Phase 3) | `python manage.py makemigrations --check --dry-run` | *No changes detected* |
| Targeted Phase 4 | `pytest tests/persistence/test_recovery.py -q` | **26 passed** (after 2 fixes: non-UUID `filter(id=)` raises `ValidationError`; row order = `ordering = ["-updated_at"]`) |
| Targeted Phase 4 (3 persistence files) | `pytest tests/persistence/test_recovery.py test_snapshot_restore.py test_shutdown_signals.py -q` | 92 passed |
| **After CHG-4-1..4 (full suite)** | `.venv/bin/python -m pytest --tb=short -q` | **2163 passed, 13 skipped** (2137 + 26) |
| Migration check (Phase 4) | `python manage.py makemigrations --check --dry-run` | *No changes detected* |
| Targeted Phase 5 | `pytest tests/engines/test_trading_tasks.py -q` | **33 passed** (30 old + 3 new; 1 test fixed: stale fixture must be *older* than the cutoff) |
| **After CHG-5-1..4 (full suite)** | `.venv/bin/python -m pytest --tb=short -q` | **2166 passed, 13 skipped** (2163 + 3) |
| Migration check (Phase 5) | `python manage.py makemigrations --check --dry-run` | *No changes detected* |
| Targeted CHG-3-5 | `pytest tests/persistence/test_shutdown_signals.py -q` | **35 passed** (31 old + 4 new) |
| **After CHG-3-5 (full suite)** | `.venv/bin/python -m pytest --tb=short -q` | **2170 passed, 13 skipped** (2166 + 4) |
| Migration check (CHG-3-5) | `python manage.py makemigrations --check --dry-run` | *No changes detected* |
| Targeted hardening matrix | `pytest tests/persistence/test_persistence_hardening.py -q` | **13 passed** (1 initial fix: burst test must filter SAVEPOINT noise, count only table reads/writes) |
| **After CHG-T-1 (full suite)** | `.venv/bin/python -m pytest --tb=short -q` | **2183 passed, 13 skipped** (2170 + 13) |
| Migration check (CHG-T-1) | `python manage.py makemigrations --check --dry-run` | *No changes detected* |

### Lint

| Command | Result |
|---|---|
| `/usr/bin/flake8 tests/persistence/ apps/trading/engines/execution.py apps/trading/engines/grid_monitor.py apps/trading/tasks.py` | **0 findings** |
| `/usr/bin/flake8 apps/trading/apps.py` | **0 findings** (rewritten in CHG-6b-2) |
| `/usr/bin/flake8 tests/engines/test_bot_executor.py` | **0 findings** (CHG-6b-4) |
| `/usr/bin/flake8 tests/engines/test_bot_engine.py` | 8 × E501 — **pre-existing** (lines 1243–1561, signal-notification tests from prior uncommitted work; HEAD version of the file is flake8-clean). None in the new `TestRemoteStopCallback` class (467–555). |
| `/usr/bin/flake8 apps/trading/engines/bot_engine.py` | 4 × E501 (lines 246, 252, 287, 291) — **pre-existing** Telegram emoji map, not touched by Phase 6a/6b. |
| `/usr/bin/flake8 .` (repo-wide) | 30 findings, **all pre-existing** in unrelated files (`apps/analytics/views.py`, `core/middleware.py`, `core/shutdown.py`, `apps/users/views.py`, `locustfile.py`, `tests/*`, …). Repo-wide flake8 is **not** a green gate today — unchanged from baseline. |
| `/usr/bin/flake8 apps/bots/models.py apps/trading/engines/order_service.py apps/trading/engines/execution.py apps/bots/migrations/0017_botorder_trade_integrity.py tests/engines/test_order_service.py` (Phase 1) | **0 findings** |
| `/usr/bin/flake8 apps/trading/engines/bot_engine.py tests/engines/test_bot_engine.py` (Phase 1) | 4 + 8 × E501 — **same pre-existing lines as before Phase 1** (bot_engine 246/252/287/291; test file ≤1566). **0 new findings.** |
| `/usr/bin/flake8 apps/trading/models.py apps/trading/state.py apps/trading/migrations/0002_botruntimestate.py tests/persistence/test_runtime_state.py` (Phase 2) | **0 findings** |
| `/usr/bin/flake8 tests/persistence/test_snapshot_restore.py apps/trading/state.py apps/trading/engines/grid_monitor.py apps/trading/engines/bot_engine.py apps/trading/tasks.py` (Phase 3) | **0 new findings** — bot_engine still 4 × E501, now at **252/258/293/297** (same pre-existing emoji-map lines, shifted by Phase 3 insertions; baseline table above lists them as 246/252/287/291). |
| `/usr/bin/flake8 apps/trading/state.py apps/trading/apps.py tests/persistence/test_recovery.py` (Phase 4) | **0 findings** (one new E305 fixed: 2 blank lines required between `restore_engine` and the `# BOOT RECOVERY` banner comment). |
| `/usr/bin/flake8 apps/trading/engines/bot_engine.py` (Phase 4) | 4 × E501 at **252/258/293/297** — same pre-existing lines, **0 new**. |
| `/usr/bin/flake8 apps/trading/engines/grid_monitor.py apps/trading/tasks.py config/celery.py tests/engines/test_trading_tasks.py` (Phase 5) | **0 findings** (exit 0). |
| `/usr/bin/flake8 apps/trading/engines/bot_engine.py` (Phase 5) | 4 × E501 at **254/260/295/299** — same pre-existing emoji-map lines, shifted +2 by the CHG-5-1 comment, **0 new**. |
| `/usr/bin/flake8 apps/trading/engines/execution.py tests/persistence/test_shutdown_signals.py` (CHG-3-5) | **0 findings** (exit 0). |
| `/usr/bin/flake8 tests/persistence/test_persistence_hardening.py` (CHG-T-1) | **0 findings** (exit 0). |

---

## Backlog (later phases)

- ~~Phase 6b — SIGTERM/SIGINT registration in `apps.py:ready()`~~ → **DONE 2026-09-26**
  (CHG-6b-1..5). Note: the *planned* "flush `BotRuntimeState` on shutdown" half was
  deferred because the model did not exist yet → now available; do it in Phase 3
  (clean-shutdown snapshot + `status=stopped`).
- ~~Phase 1 — trade record integrity (`save_order(price=)`, bot FK, `BotOrder` columns).~~
  → **DONE 2026-09-27** (CHG-1-1..1-5, migration `0017`).
- ~~Phase 2 — `BotRuntimeState` model + `apps/trading/state.py`.~~
  → **DONE 2026-09-27** (CHG-2-1..3; migration is `apps/trading/migrations/0002_botruntimestate.py`
  — the plan's "0018" was wrong, migration numbers are per-app).
- ~~Phase 3 — snapshot/restore in `apps/trading/state.py` + loop wiring.~~
  → **DONE 2026-09-27** (CHG-3-1..4; `restore_engine` intentionally has no
  production caller yet — Phase 4 wires it). Residual: a forced snapshot in
  the in-process SIGTERM/SIGINT shutdown path (CHG-6b deferred half) ->
  **CLOSED 2026-09-28 (CHG-3-5)**.
- ~~Phase 4 — `worker_ready` recovery (`ready()` → `recover_running_bots`
  → `run_bot(restore_mode=True)` → `restore_engine` before attach).~~
  → **DONE 2026-09-28** (CHG-4-1..4; full suite 2163/13). Residual: the
  CHG-6b deferred half — a forced snapshot in the in-process
  SIGTERM/SIGINT shutdown path → **CLOSED 2026-09-28 (CHG-3-5)**.
- ~~Phase 5 — watchdog tuning (heartbeat 60→10 s, stale 5 min→30 s, beat
  120→30 s, `heartbeat-check` 300→60 s; align with `RECOVERY_MIN_STALE_S = 15.0`).~~
  → **DONE 2026-09-28** (CHG-5-1..4; full suite 2166/13). Two-tier timing now
  documented in the Phase 5 section above.
- ~~CHG-3-5 — forced snapshot in the in-process SIGTERM/SIGINT shutdown
  path.~~ → **DONE 2026-09-28** (the CHG-6b deferred half; only residual of
  Phase 3 — see section above).
- ~~Phase 7 — final docs: CHANGELOG / PROJECT_STATUS / todo.md.~~
  → **DONE 2026-09-28** (`docs/CHANGELOG.md` new top entry, `docs/PROJECT_STATUS.md`
  verified-positives + date, `tasks/todo.md` session-completion section).
- **All 7 phases + CHG-3-5 complete — this guide stays authoritative for reverts.**
