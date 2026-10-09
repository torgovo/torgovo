"""
Runtime-state helpers for crash recovery (persistence Phases 2 + 3).

Thin, explicit data-access layer over :class:`apps.trading.models.BotRuntimeState`.

Contract:
  * One row per ``(bot_type, bot_id)`` — all writes are upserts.
  * Helpers never raise for "row missing" on reads: recovery must survive a
    fresh database. Writes may raise (the caller decides whether persistence
    failure is fatal — the one exception is :func:`snapshot_engine`, which
    swallows errors because it runs inside monitor loops).
  * The *shape* of the ``state`` payload is defined by :func:`collect_state`
    / :func:`apply_state` (Phase 3, schema v1). Lifecycle fields (``status``
    / ``heartbeat_at`` / ``worker``) are owned by Phase 2 helpers above.

Lifecycle helpers mirror ``BotRuntimeState.STATUS_*``:
``RUNNING`` -> ``STOPPING`` -> ``STOPPED``.  A row left in ``RUNNING`` after a
worker death is what the Phase 4 recovery task picks up.
"""

import logging
import os
import socket
import time
from typing import Any, Dict, Optional

from django.core.exceptions import ValidationError
from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.trading.models import BotRuntimeState

logger = logging.getLogger(__name__)

# Re-exported so callers never hardcode magic strings.
RUNNING = BotRuntimeState.STATUS_RUNNING
STOPPING = BotRuntimeState.STATUS_STOPPING
STOPPED = BotRuntimeState.STATUS_STOPPED


def upsert(
    bot_type: str,
    bot_id: Any,
    state: Optional[Dict[str, Any]] = None,
    *,
    status: str = RUNNING,
    worker: str = "",
) -> BotRuntimeState:
    """Insert-or-update the state row for one bot and stamp a heartbeat.

    ``state=None`` keeps the previously stored payload (so a status-only
    update never wipes a snapshot).
    """
    defaults: Dict[str, Any] = {
        "status": status,
        "worker": worker,
        "heartbeat_at": timezone.now(),
    }
    if state is not None:
        defaults["state"] = state
    obj, _created = BotRuntimeState.objects.update_or_create(
        bot_type=bot_type, bot_id=str(bot_id), defaults=defaults
    )
    return obj


def get(bot_type: str, bot_id: Any) -> Optional[BotRuntimeState]:
    """Return the row for one bot, or ``None`` if never tracked."""
    return BotRuntimeState.objects.filter(bot_type=bot_type, bot_id=str(bot_id)).first()


def get_state(bot_type: str, bot_id: Any) -> Dict[str, Any]:
    """Return the stored snapshot dict; ``{}`` when the bot was never tracked.

    Read helpers are deliberately non-raising — recovery runs before (or
    instead of) any engine boot and must not blow up on a fresh DB.
    """
    obj = get(bot_type, bot_id)
    return obj.state if obj is not None else {}


def set_status(bot_type: str, bot_id: Any, status: str, *, worker: str = "") -> bool:
    """Transition lifecycle status + heartbeat. ``False`` if row missing."""
    updated = BotRuntimeState.objects.filter(bot_type=bot_type, bot_id=str(bot_id)).update(
        status=status, worker=worker, heartbeat_at=timezone.now()
    )
    return bool(updated)


def touch(bot_type: str, bot_id: Any, *, worker: str = "") -> bool:
    """Stamp a heartbeat only (creates the row with empty state if absent).

    An alive engine must always have a row, even if it has never snapshotted
    yet — that is what the watchdog measures.
    """
    if set_status(bot_type, bot_id, RUNNING, worker=worker):
        return True
    upsert(bot_type, bot_id, status=RUNNING, worker=worker)
    return True


def delete(bot_type: str, bot_id: Any) -> int:
    """Drop the row (clean stop / bot deletion). Returns rows removed."""
    deleted, _ = BotRuntimeState.objects.filter(bot_type=bot_type, bot_id=str(bot_id)).delete()
    return int(deleted or 0)


def running(*, bot_type: Optional[str] = None, worker: Optional[str] = None) -> QuerySet:
    """Rows in ``running`` status — the Phase 4 recovery candidate set."""
    qs = BotRuntimeState.objects.filter(status=RUNNING)
    if bot_type:
        qs = qs.filter(bot_type=bot_type)
    if worker:
        qs = qs.filter(worker=worker)
    return qs


def stale(seconds: float) -> QuerySet:
    """Running rows whose heartbeat is older than ``seconds`` (or missing).

    Phase 5 watchdog input: these engines stopped ticking while still marked
    ``running`` — i.e. the worker died without a clean shutdown.
    """
    cutoff = timezone.now() - timezone.timedelta(seconds=seconds)
    return BotRuntimeState.objects.filter(status=RUNNING).filter(
        Q(heartbeat_at__isnull=True) | Q(heartbeat_at__lt=cutoff)
    )


# =========================================================================
# PHASE 3 — SNAPSHOT / RESTORE (payload shape + throttled writer)
# =========================================================================

# Payload version. Bump when collect_state/apply_state change shape;
# restore_engine refuses payloads with a NEWER schema (unknown keys are
# tolerated on the way in, missing keys keep their current value).
SNAPSHOT_SCHEMA = 1

# Decided cadence: event-driven (force=True at lifecycle points) + a
# throttled monitor-loop tick — worst-case blind window after a crash is
# ~5s of state + Phase 4 recovery time (target: <15s end-to-end).
SNAPSHOT_THROTTLE_S = 5.0


def _engine_identity(engine) -> tuple:
    """Return ``(bot_type, bot_id)`` from an engine config; ``bot_id`` None
    when the engine is not DB-tracked (unit tests / ad-hoc construction)."""
    cfg = getattr(engine, "config", None) or {}
    bot_id = cfg.get("bot_id")
    bot_type = cfg.get("bot_type", "grid")
    return bot_type, str(bot_id) if bot_id not in (None, "") else None


def _worker_id() -> str:
    """Cheap process identity stamped on snapshots (ownership attribution)."""
    return f"{socket.gethostname()}:{os.getpid()}"


def save_snapshot(
    bot_type: str, bot_id: Any, state: Dict[str, Any], *, worker: Optional[str] = None
) -> BotRuntimeState:
    """Upsert ONLY the payload + heartbeat — never touches status.

    Unlike :func:`upsert` (status-oriented, used by lifecycle helpers), a
    snapshot from a live engine must not clobber ``stopping``/``stopped``
    nor wipe the owning ``worker``. A brand-new row gets the model default
    (``running``), which is correct: an engine that is snapshotting is alive.
    """
    defaults: Dict[str, Any] = {
        "state": state,
        "heartbeat_at": timezone.now(),
    }
    if worker:
        defaults["worker"] = worker
    obj, _created = BotRuntimeState.objects.update_or_create(
        bot_type=bot_type, bot_id=str(bot_id), defaults=defaults
    )
    return obj


def collect_state(engine) -> Dict[str, Any]:
    """Serialize the engine's volatile in-memory state (pure, no I/O).

    Schema v1 captures everything that would otherwise be lost on restart:
    trade position (side/count/price), entry reason bookkeeping, grid levels,
    P/L, performance counters and indicator state. Derived condition flags
    (NoTrade/BuyTrade/SellTrade/...) are NOT stored — apply_state recomputes
    them from the raw values.

    Source of truth preference: the grid monitor's copies for values it
    owns while threads are running (levels/P&L), engine copies otherwise.
    """
    gm = getattr(engine, "grid_monitor", None)

    def _gm(name: str, default: Any) -> Any:
        return getattr(gm, name, default) if gm is not None else default

    return {
        "schema": SNAPSHOT_SCHEMA,
        "ts": timezone.now().isoformat(),
        "side": engine.current_side,
        "count": int(engine.count or 0),
        "price": float(engine.current_price or 0.0),
        "reason": engine.reason or "",
        "prev_reason": getattr(engine, "PrevReason", "") or "",
        "last_trade_pnl": float(getattr(engine, "last_trade_pnl", 0.0) or 0.0),
        # Levels: prefer the monitor's live copy, fall back to the engine's
        # (at entry time calculated_grid_orders fills the engine copy first).
        "favor_lvl": [float(x) for x in (_gm("favor_lvl", None) or engine.favor_lvl or [])],
        "against_lvl": [float(x) for x in (_gm("against_lvl", None) or engine.against_lvl or [])],
        "percentage": float(_gm("Percentage", 0.0) or 0.0),
        "unrealized_pnl": float(_gm("Unrealized_Pnl", 0.0) or 0.0),
        "signals_generated": int(getattr(engine, "signals_generated", 0) or 0),
        "orders_executed": int(getattr(engine, "orders_executed", 0) or 0),
        "indicators": {
            "EMA": float(engine.EMA or 0.0),
            "RSI": float(engine.RSI or 0.0),
            "PrevRSI": float(engine.PrevRSI or 0.0),
            "BB": engine.BB,
            "RSI_color": engine.RSI_color,
            "RSI_prev_color": engine.RSI_prev_color,
        },
        # Observability only — apply_state deliberately does NOT restore these
        # (monitor threads are started explicitly by the caller).
        "monitoring": bool(_gm("monitoring", False)),
        "bot_running": bool(_gm("bot_running", False)),
    }


def apply_state(engine, payload: Dict[str, Any]) -> bool:
    """Write a snapshot payload back onto an engine + its grid monitor.

    * Only keys present in ``payload`` are touched (partial/old payloads
      stay compatible); derived flags are ALWAYS recomputed.
    * Formulas mirror ``BotEngine.update_conditions`` exactly — except the
      ticker fetch: the restored ``current_price`` must not be overwritten.
    * Returns ``False`` for empty/unknown-schema payloads (nothing applied).
    """
    if not payload or not isinstance(payload, dict):
        return False
    schema = payload.get("schema")
    if schema is not None and int(schema) != SNAPSHOT_SCHEMA:
        logger.warning(f"Unsupported snapshot schema {schema!r} (have {SNAPSHOT_SCHEMA}) — ignored")
        return False

    # --- raw trading state -------------------------------------------------
    if "side" in payload:
        engine.current_side = str(payload["side"])
    if "count" in payload:
        engine.count = int(payload["count"] or 0)
    if "price" in payload:
        engine.current_price = float(payload["price"] or 0.0)
    if "reason" in payload:
        engine.reason = payload["reason"] or ""
    if "prev_reason" in payload:
        engine.PrevReason = payload["prev_reason"] or ""
    if "last_trade_pnl" in payload:
        engine.last_trade_pnl = float(payload["last_trade_pnl"] or 0.0)
    if payload.get("favor_lvl") is not None:
        engine.favor_lvl = [float(x) for x in payload["favor_lvl"]]
    if payload.get("against_lvl") is not None:
        engine.against_lvl = [float(x) for x in payload["against_lvl"]]
    if "signals_generated" in payload:
        engine.signals_generated = int(payload["signals_generated"] or 0)
    if "orders_executed" in payload:
        engine.orders_executed = int(payload["orders_executed"] or 0)

    # --- indicator state ---------------------------------------------------
    ind = payload.get("indicators") or {}
    if "EMA" in ind:
        engine.EMA = float(ind["EMA"] or 0.0)
    if "RSI" in ind:
        engine.RSI = float(ind["RSI"] or 0.0)
    if "PrevRSI" in ind:
        engine.PrevRSI = float(ind["PrevRSI"] or 0.0)
    if "BB" in ind:
        engine.BB = ind["BB"]
    if "RSI_color" in ind:
        engine.RSI_color = ind["RSI_color"]
    if "RSI_prev_color" in ind:
        engine.RSI_prev_color = ind["RSI_prev_color"]

    # --- mirror into the grid monitor (it owns the live monitoring copy) ---
    gm = getattr(engine, "grid_monitor", None)
    if gm is not None:
        gm.current_side = engine.current_side
        gm.count = engine.count
        gm.current_price = engine.current_price
        gm.reason = engine.reason
        gm.PrevReason = engine.PrevReason
        gm.last_trade_pnl = engine.last_trade_pnl
        gm.favor_lvl = list(engine.favor_lvl)
        gm.against_lvl = list(engine.against_lvl)
        if "percentage" in payload:
            gm.Percentage = float(payload["percentage"] or 0.0)
        engine.Percentage = gm.Percentage
        if "unrealized_pnl" in payload:
            gm.Unrealized_Pnl = float(payload["unrealized_pnl"] or 0.0)
        engine.Unrealized_Pnl = gm.Unrealized_Pnl

    # --- recompute derived condition flags (update_conditions formulas) ----
    engine.EmaBuyCondition = engine.current_price >= engine.EMA != 0
    engine.EmaSellCondition = engine.current_price <= engine.EMA != 0
    engine.RsiBuyCondition = (
        engine.PrevRSI <= engine.pair_config.get("RSI_Lower", 30) and engine.RSI_color == "white"
    )
    engine.RsiSellCondition = (
        engine.PrevRSI >= engine.pair_config.get("RSI_Upper", 70) and engine.RSI_color == "white"
    )
    engine.BBBuyCondition = engine.BB in (
        "Crossing Down Band",
        "Closed Below Lower Band",
        "Up Arrow",
    )
    engine.BBSellCondition = engine.BB in (
        "Crossing Up Band",
        "Closed Above Upper Band",
        "Down Arrow",
    )
    engine.NoTrade = engine.count == 0 and engine.current_side == "None"
    engine.BuyTrade = engine.count == 1 and engine.current_side == "Buy"
    engine.SellTrade = engine.count == 1 and engine.current_side == "Sell"
    sync = getattr(engine, "_sync_strategy", None)
    if callable(sync):
        sync()
    # monitoring/bot_running are intentionally NOT restored — threads must be
    # started explicitly (Phase 4 recovery -> start_monitoring/restore path).
    return True


def snapshot_engine(
    engine,
    *,
    force: bool = False,
    throttle_s: float = SNAPSHOT_THROTTLE_S,
    worker: Optional[str] = None,
) -> bool:
    """Throttled snapshot write for one engine. ``True`` iff a row was written.

    * ``force=True`` bypasses the throttle — called at lifecycle points
      (end of ``startBot``) so entries/exits never wait for the next tick.
    * Regular ticks run inside monitor loops every ~1s; the throttle collapses
      them to ≤ ``throttle_s`` writes (decided 5s cadence).
    * NEVER raises: a persistence hiccup must not kill a monitor loop —
      the next tick simply retries.
    """
    bot_type, bot_id = _engine_identity(engine)
    if bot_id is None:
        return False
    now = time.monotonic()
    last = getattr(engine, "_snapshot_monotonic", 0.0)
    if not force and (now - last) < throttle_s:
        return False
    try:
        save_snapshot(bot_type, bot_id, collect_state(engine), worker=worker or _worker_id())
    except Exception:
        logger.exception(f"Snapshot failed for {bot_type}/{bot_id}")
        return False
    engine._snapshot_monotonic = now
    return True


def restore_engine(engine) -> bool:
    """Apply the stored snapshot onto a freshly constructed engine.

    ``False`` when there is no row/payload (fresh DB or bot never snapshotted)
    — callers treat that as a normal cold start. Phase 4 wires this into the
    recovery path (``run_bot(restore_mode=True)``) before ``startBot()``.
    """
    bot_type, bot_id = _engine_identity(engine)
    if bot_id is None:
        return False
    payload = get_state(bot_type, bot_id)
    if not payload:
        return False
    try:
        return apply_state(engine, payload)
    except Exception:
        logger.exception(f"Restore failed for {bot_type}/{bot_id}")
        return False


# =========================================================================
# BOOT RECOVERY — Phase 4 (CHG-4-1)
# =========================================================================

#: Boot-time staleness window for crash recovery. Live engines write a
#: heartbeat every ~1-10 s (grid loop 1 s + 5 s snapshot throttle, loss
#: loop 5 s), so a row older than 15 s belongs to a dead worker — the
#: crash-to-boot time itself counts toward staleness. Multi-worker
#: deployments should raise this above their heartbeat period so a booting
#: worker never steals a sibling's healthy engine.
RECOVERY_MIN_STALE_S = 15.0

#: Model-backed bot types eligible for dispatch recovery — the same three
#: types check_stale_bots (Celery beat) owns. SignalBot has neither
#: is_running nor last_heartbeat (webhook-owned, re-triggered per alert),
#: so signal rows are rejected as ineligible instead of guessed at.
_RECOVERY_MODEL_MAP = ("grid", "martingale", "quantum_ai")


def _recovery_model(bot_type: str):
    """Model class for an eligible recovery type, else ``None``.

    Imports are function-local (models are not import-safe at module load
    time, same convention as tasks.py).
    """
    if bot_type == "grid":
        from apps.bots.models import GridBot

        return GridBot
    if bot_type == "martingale":
        from apps.bots.models import MartingaleBot

        return MartingaleBot
    if bot_type == "quantum_ai":
        from apps.bots.models import QuantumAIBot

        return QuantumAIBot
    return None


def _payload_has_position(payload: Dict[str, Any]) -> bool:
    """True unless the snapshot clearly describes a flat, entry-idle engine.

    An EMPTY payload counts as "unknown -> restore": attach is a safe
    no-op when no position exists (startBot sets bot_running=False and
    returns) and restore mode never places entry orders, so dispatching
    costs one wasted boot at worst.
    """
    if not payload:
        return True
    side = payload.get("side") or "None"
    count = payload.get("count") or 0
    return not (str(side) in ("None", "") and not count)


def recover_running_bots(*, min_stale_s: float = RECOVERY_MIN_STALE_S) -> Dict[str, Any]:
    """Boot-time crash recovery (Phase 4 — wired to Celery ``worker_ready``).

    Re-dispatches engines whose :class:`BotRuntimeState` row still says
    ``running`` but whose heartbeat went stale across a worker restart, so
    open trades regain monitoring within seconds of boot instead of waiting
    for the 2-minute ``check_stale_bots`` beat (5-minute cutoff).

    DB reads/writes + ``.delay()`` only — no exchange calls — so worker
    boot is never blocked on network I/O. Never raises: one broken
    candidate must not take the worker down.

    Per candidate: deleted bot / ineligible type -> row -> STOPPED;
    model ``is_running=False`` -> row -> STOPPED (leftover row); flat
    payload -> skipped (idle bots are owned by ``check_stale_bots``);
    otherwise both heartbeats are refreshed (row heartbeat dedupes a
    sibling worker booting seconds later; model heartbeat keeps the beat
    watchdog from racing the queued restore — same trick as
    ``_handle_stale_bot``) and ``restore_mode=True`` is dispatched.

    Returns ``{"recovered": [...], "skipped": [...], "errors": [...]}``
    with ``"bot_type/bot_id"`` entries (errors carry a reason suffix).
    """
    from .tasks import run_trading_bot

    recovered, skipped, errors = [], [], []

    for row in stale(min_stale_s):
        bot_type, bot_id = row.bot_type, row.bot_id
        try:
            if bot_type not in _RECOVERY_MODEL_MAP:
                # Orphan row of an unknown/ineligible type — nothing will
                # ever heartbeat it; stop it once instead of every boot.
                set_status(bot_type, bot_id, STOPPED)
                errors.append(f"{bot_type}/{bot_id}: ineligible bot_type (row -> stopped)")
                continue
            model = _recovery_model(bot_type)
            try:
                bot = model.objects.filter(id=bot_id).first()
            except (ValidationError, ValueError):
                # bot_id rows carry string ids; a mangled/non-UUID value
                # raises on a UUID pk instead of returning an empty qs.
                bot = None
            if bot is None:
                set_status(bot_type, bot_id, STOPPED)
                errors.append(f"{bot_type}/{bot_id}: bot missing (row -> stopped)")
                continue
            if not bot.is_running:
                set_status(bot_type, bot_id, STOPPED)
                skipped.append(f"{bot_type}/{bot_id}: model not running (row -> stopped)")
                continue
            if not _payload_has_position(row.state):
                skipped.append(f"{bot_type}/{bot_id}: no open position")
                continue
            # Heartbeat refresh BEFORE dispatch (mirrors _handle_stale_bot):
            # row heartbeat dedupes sibling workers, model heartbeat holds
            # off the beat watchdog until this restore has had time to boot.
            set_status(bot_type, bot_id, RUNNING)
            bot.last_heartbeat = timezone.now()
            bot.save(update_fields=["last_heartbeat", "updated_at"])
            run_trading_bot.delay(str(bot_id), bot_type, restore_mode=True)
            recovered.append(f"{bot_type}/{bot_id}")
        except Exception as exc:
            logger.exception(f"Boot recovery failed for {bot_type}/{bot_id}")
            errors.append(f"{bot_type}/{bot_id}: {type(exc).__name__}: {exc}")

    logger.info(
        f"Boot recovery: {len(recovered)} dispatched, {len(skipped)} skipped, "
        f"{len(errors)} errors"
    )
    return {"recovered": recovered, "skipped": skipped, "errors": errors}
