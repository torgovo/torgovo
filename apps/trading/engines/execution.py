"""
Bot Execution Manager

This module bridges Django models with pure Python strategies and adapters.
It handles:
- Loading bot configurations from the database
- Instantiating the correct strategy and adapter
- Running the trading loop
- Logging execution results back to the database

This is the ONLY place where Django imports mix with trading logic.
"""

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from django.core.cache import cache

logger = logging.getLogger("trading.managers")

# In-process lock: prevents duplicate BotEngine instances per bot_id
_running_bots: set = set()
_running_bots_lock = threading.Lock()

# Track running engine instances so stop_bot() can signal them
# RLock (not Lock): ``_shutdown_handler`` runs *on the main thread* and may be
# delivered while that same thread already holds this lock inside ``run_bot``
# or ``stop_bot``. A non-reentrant Lock would then self-deadlock the process
# we are trying to shut down. Drop-in compatible with every ``with`` usage.
_running_engines: Dict[str, Any] = {}
_running_engines_lock = threading.RLock()


def _is_bot_running(bot_id: str) -> bool:
    """Check if bot_id is already running in this process."""
    with _running_bots_lock:
        return bot_id in _running_bots


def _mark_bot_starting(bot_id: str) -> bool:
    """Atomically mark bot as starting. Returns False if already running."""
    with _running_bots_lock:
        if bot_id in _running_bots:
            return False
        _running_bots.add(bot_id)
        return True


def _mark_bot_stopped(bot_id: str):
    """Remove bot from running set."""
    with _running_bots_lock:
        _running_bots.discard(bot_id)


def _try_redis_lock(bot_id: str, ttl: int = 120) -> bool:
    """
    Try to acquire a Redis-backed distributed lock for the bot.
    Prevents duplicate restore across Celery workers.
    Returns True if lock was acquired (safe to proceed).
    """
    lock_key = f"bot_exec_lock_{bot_id}"
    return cache.add(lock_key, "1", ttl)


def _release_redis_lock(bot_id: str):
    """Release the Redis distributed lock."""
    cache.delete(f"bot_exec_lock_{bot_id}")


# ── Redis bot state persistence ────────────────────────────────────────

BOT_STATE_TTL = 86_400  # 24 hours (survives restarts)


def _bot_state_key(bot_id: str) -> str:
    return f"bot:state:{bot_id}"


def save_bot_state(
    bot_id: str,
    bot_type: str,
    engine_state: dict,
    *,
    ttl: int = BOT_STATE_TTL,
) -> None:
    """
    Persist bot engine state to Redis.

    Called by BotEngine on graceful shutdown (SIGTERM / stop_bot).
    The next worker that restores this bot reads the state and resumes
    without re-evaluating entry conditions.
    """
    import json
    from datetime import datetime as _dt

    payload = {
        "bot_id": bot_id,
        "bot_type": bot_type,
        "saved_at": _dt.utcnow().isoformat(),
        "state": engine_state,
    }
    try:
        raw = json.dumps(payload, default=str)
        cache.set(_bot_state_key(bot_id), raw, ttl)
        logger.info(f"Saved Redis state for bot {bot_id} (ttl={ttl}s)")
    except Exception as exc:
        logger.error(f"Failed to save Redis state for bot {bot_id}: {exc}")


def load_bot_state(bot_id: str) -> dict | None:
    """
    Load previously saved bot state from Redis.

    Returns the inner ``state`` dict, or ``None`` if no state exists or if
    it expired.
    """
    raw = cache.get(_bot_state_key(bot_id))
    if not raw:
        return None
    try:
        import json

        payload = json.loads(raw)
        return payload.get("state")
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.warning(f"Corrupt Redis state for bot {bot_id}: {exc}")
        cache.delete(_bot_state_key(bot_id))
        return None


def clear_bot_state(bot_id: str) -> None:
    """Remove saved bot state from Redis (e.g. after successful restore)."""
    cache.delete(_bot_state_key(bot_id))


class BotExecutor:
    """
    Executes trading bots by combining strategies and adapters.

    This class is responsible for:
    1. Loading configuration from Django models
    2. Creating strategy and adapter instances
    3. Running the trading loop
    4. Handling errors and logging
    """

    def __init__(self, strategy, adapter, bot_config=None, symbol: str = None):
        """
        Initialize the bot executor.

        Args:
            strategy: Instantiated strategy object (BaseStrategy subclass)
            adapter: Instantiated adapter object (BaseAdapter subclass)
            bot_config: Optional Django BotConfiguration model instance
            symbol: Trading symbol (required if bot_config not provided)
        """
        self.strategy = strategy
        self.adapter = adapter
        self.bot_config = bot_config
        self.symbol = symbol or (
            bot_config.get("symbol")
            if isinstance(bot_config, dict)
            else (bot_config.symbol if bot_config else None)
        )

        if not self.symbol:
            raise ValueError("Symbol must be provided either in bot_config or directly")

        self.is_running = False
        self.execution_count = 0
        self.last_execution: Optional[datetime] = None
        self.errors: list = []

    @classmethod
    def from_config(cls, config: dict):
        """
        Create a BotExecutor from a plain config dict.

        Args:
            config: Dict with keys:
                - strategy: str (e.g. 'quantum_ai', 'grid')
                - symbol: str (e.g. 'BTC/USDT')
                - exchange_name: str (e.g. 'bybit')
                - api_key: str (decrypted)
                - secret_key: str (decrypted)
                - passphrase: str (optional)
                - is_testnet: bool
                - parameters: dict (strategy-specific params)

        Returns:
            BotExecutor instance
        """
        from ..exchanges import get_adapter
        from ..strategies import get_strategy

        strategy_name = config.get("strategy", "quantum_ai")
        symbol = config.get("symbol", "")
        parameters = config.get("parameters", {})

        # Instantiate strategy
        strategy_class = get_strategy(strategy_name)
        strategy = strategy_class(parameters={"symbol": symbol, **parameters})

        # Create exchange adapter
        credentials = {
            "api_key": config.get("api_key", ""),
            "secret_key": config.get("secret_key", ""),
            "passphrase": config.get("passphrase", ""),
        }
        adapter = get_adapter(
            exchange_name=config.get("exchange_name", "bybit"),
            credentials=credentials,
            demo_mode=config.get("is_demo", False) or config.get("is_testnet", False),
        )

        config.pop("api_key", None)
        config.pop("secret_key", None)
        config.pop("passphrase", None)

        return cls(strategy=strategy, adapter=adapter, bot_config=config, symbol=symbol)

    def run_once(self) -> Dict[str, Any]:
        """
        Execute one iteration of the trading loop.

        Returns:
            Dict with execution result
        """
        result = {
            "success": False,
            "signal": None,
            "order": None,
            "error": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        try:
            # Fetch market data
            market_data = self._fetch_market_data()

            # Fetch account info
            account_info = self.adapter.get_account_info()

            # Fetch current position (if any)
            current_position = self._get_current_position()

            # Execute strategy
            signal = self.strategy.execute(market_data, account_info, current_position)

            if signal and signal.action != "hold":
                result["signal"] = signal.to_dict()

                # Execute the order
                order = self.adapter.execute_order(signal.to_dict())
                result["order"] = order

                # Log to database if we have a config
                if self.bot_config:
                    self._log_trade(signal, order)

            result["success"] = True
            self.execution_count += 1
            self.last_execution = datetime.now(timezone.utc)

        except Exception as e:
            logger.error(f"Bot execution error: {type(e).__name__}: {e}")
            logger.debug("Full traceback", exc_info=True)
            result["error"] = str(e)
            self.errors.append(
                {"error": str(e), "timestamp": datetime.now(timezone.utc).isoformat()}
            )

            # Update bot status if we have a config
            if self.bot_config:
                self._handle_error(e)

        return result

    def run_loop(self, interval_seconds: float = 60, max_iterations: Optional[int] = None):
        """
        Run the trading loop continuously.

        Args:
            interval_seconds: Time between iterations
            max_iterations: Maximum number of iterations (None for infinite)
        """
        self.is_running = True
        iteration = 0

        logger.info(f"Starting bot loop for {self.symbol} on {self.adapter.exchange_name}")

        try:
            while self.is_running:
                if max_iterations and iteration >= max_iterations:
                    break

                result = self.run_once()

                if result.get("signal"):
                    logger.info(f"Signal generated: {result['signal']}")

                if result.get("error"):
                    logger.warning(f"Iteration error: {result['error']}")

                iteration += 1
                time.sleep(interval_seconds)

        except KeyboardInterrupt:
            logger.info("Bot loop interrupted by user")
        finally:
            self.is_running = False
            logger.info(f"Bot loop stopped after {iteration} iterations")

    def stop(self):
        """Stop the trading loop."""
        self.is_running = False

    def _fetch_market_data(self) -> Dict[str, Any]:
        """Fetch all necessary market data for the strategy."""
        return {
            "ticker": self.adapter.fetch_ticker(self.symbol),
            "ohlcv": self.adapter.fetch_ohlcv(self.symbol, "1h", limit=100),
            "orderbook": self.adapter.fetch_order_book(self.symbol, limit=10),
        }

    def _get_current_position(self) -> Optional[Dict[str, Any]]:
        """Get current position if any."""
        try:
            positions = self.adapter.fetch_positions(self.symbol)
            if positions:
                return positions[0]
        except Exception as e:
            logger.debug(f"No position data: {e}")
        return None

    def _log_trade(self, signal, order):
        """Log trade to database."""
        try:
            from apps.bots.models import BotOrder

            # bot_config is now a dict, extract user_id if present
            user_id = self.bot_config.get("user_id") if isinstance(self.bot_config, dict) else None
            if not user_id:
                logger.warning("No user_id in config, skipping trade log")
                return

            from django.contrib.auth import get_user_model

            User = get_user_model()
            user = User.objects.get(id=user_id)

            # Phase 1: entry log -> live trade, linked to its owning bot.
            bot_id = self.bot_config.get("bot_id")
            bot_type = self.bot_config.get("bot_type")

            BotOrder.objects.create(
                user=user,
                Pair=signal.symbol,
                Exchange=self.adapter.exchange_name,
                Side=signal.action,
                Category=self.strategy.name.lower().replace(" ", "_"),
                Order_type=signal.order_type,
                Quantity=signal.amount,
                Price=signal.price or order.get("price", 0),
                Description=signal.reason,
                Details=signal.metadata,
                bot_id=str(bot_id) if bot_id else None,
                bot_type=bot_type or None,
                Reason=signal.reason,
                Status="open",
            )

        except Exception as e:
            logger.exception(f"Failed to log trade: {e}")

    def _handle_error(self, error: Exception):
        """Handle execution errors."""
        try:
            # Update bot status to error if too many consecutive errors
            if len(self.errors) >= 5:
                bot_id = (
                    self.bot_config.get("bot_id") if isinstance(self.bot_config, dict) else None
                )
                bot_type = (
                    self.bot_config.get("bot_type") if isinstance(self.bot_config, dict) else None
                )
                if bot_id and bot_type:
                    self._update_bot_status(bot_id, bot_type, "error")
                logger.error(f"Bot {bot_id} exceeded error threshold (5+ consecutive errors)")
        except Exception as e:
            logger.exception(f"Failed to handle bot error: {e}")

    @staticmethod
    def _update_bot_status(bot_id: str, bot_type: str, new_status: str):
        """Update bot model status in database."""
        try:
            if bot_type == "grid":
                from apps.bots.models import GridBot

                GridBot.objects.filter(id=bot_id).update(is_running=False)
            elif bot_type == "martingale":
                from apps.bots.models import MartingaleBot

                MartingaleBot.objects.filter(id=bot_id).update(is_running=False)
            elif bot_type == "signal":
                from apps.bots.models import SignalBot

                SignalBot.objects.filter(id=bot_id).update(is_active=False)
            logger.info(f"Updated bot {bot_id} status to {new_status}")
        except Exception as e:
            logger.exception(f"Failed to update bot {bot_id} status: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Get executor status."""
        return {
            "is_running": self.is_running,
            "symbol": self.symbol,
            "exchange": self.adapter.exchange_name,
            "strategy": self.strategy.name,
            "execution_count": self.execution_count,
            "last_execution": self.last_execution.isoformat() if self.last_execution else None,
            "error_count": len(self.errors),
            "strategy_status": self.strategy.get_status(),
        }


def run_bot(bot_id: str, bot_type: str = "grid", restore_mode: bool = False) -> Dict[str, Any]:
    """
    Run a single iteration of a bot by its ID.
    This is the main entry point for Celery tasks.

    Builds a config dict from the actual bot model in apps/bots/,
    then runs BotExecutor.

    Args:
        bot_id: UUID of the bot
        bot_type: 'grid', 'martingale', 'signal', or 'quantum_ai'
        restore_mode: If True, skip entry evaluation and attach to existing position

    Returns:
        Execution result dict
    """

    def _safe_float(val, default=None):
        try:
            return float(val) if val is not None else default
        except (TypeError, ValueError):
            return default

    try:
        # Guard: prevent duplicate starts (in-process + Redis for multi-worker)
        if not _mark_bot_starting(bot_id):
            return {"success": False, "error": f"Bot {bot_id} is already running in this process"}
        if restore_mode and not _try_redis_lock(bot_id):
            _mark_bot_stopped(bot_id)
            return {"success": False, "error": f"Bot {bot_id} restore locked by another worker"}

        # Drop any stale stop flag from a previous session, otherwise a restart
        # within _STOP_REQ_TTL seconds would be killed immediately on the first
        # monitor-loop poll.
        clear_stop_request(bot_id)

        # ---- Quantum AI: uses fund master keys, not user credentials ----
        if bot_type == "quantum_ai":
            from apps.bots.models import QuantumAIBot
            from core.utils import decrypt_api_key

            bot = QuantumAIBot.objects.select_related("fund").get(id=bot_id)
            fund = bot.fund
            if bot.is_running and not restore_mode:
                _mark_bot_stopped(bot_id)
                return {"success": False, "error": f"Bot {bot_id} is already running (DB flag)"}
            bot.is_running = True
            bot.save(update_fields=["is_running"])
            config = {
                "bot_id": str(bot.id),
                "bot_name": bot.bot_name,
                "bot_type": "quantum_ai",
                "user_id": None,
                "strategy": "quantum_ai",
                "symbol": bot.trading_pair,
                "exchange_name": bot.exchange_name,
                "api_key": decrypt_api_key(fund.master_api_key),
                "secret_key": decrypt_api_key(fund.master_secret_key),
                "passphrase": (
                    decrypt_api_key(fund.master_passphrase) if fund.master_passphrase else ""
                ),
                "is_testnet": False,
                "restore_mode": restore_mode,
                "parameters": {**bot.strategy_parameters},
            }
            from .bot_engine import BotEngine

            engine = BotEngine(config)
            # SECURITY: zero credentials from config dict now that engine owns them
            config.pop("api_key", None)
            config.pop("secret_key", None)
            config.pop("passphrase", None)
            engine.startBot()
            with _running_engines_lock:
                _running_engines[bot_id] = engine
            return {
                "success": True,
                "mode": "restore" if restore_mode else "new",
                "signal": engine.reason,
                "side": engine.current_side,
            }

        # ---- User bots: grid / martingale / signal ----
        if bot_type == "grid":
            from apps.bots.models import GridBot

            bot = GridBot.objects.select_related("user", "subscription").get(id=bot_id)
        elif bot_type == "martingale":
            from apps.bots.models import MartingaleBot

            bot = MartingaleBot.objects.select_related("user", "subscription").get(id=bot_id)
        elif bot_type == "signal":
            from apps.bots.models import SignalBot

            bot = SignalBot.objects.select_related("user", "subscription").get(id=bot_id)
        else:
            _mark_bot_stopped(bot_id)
            return {"success": False, "error": f"Unknown bot_type: {bot_type}"}

        if bot.is_running and not restore_mode:
            _mark_bot_stopped(bot_id)
            return {"success": False, "error": f"Bot {bot_id} is already running (DB flag)"}
        bot.is_running = True
        bot.save(update_fields=["is_running"])

        from apps.exchanges.models import ExchangeCredentials

        credentials = ExchangeCredentials.objects.get(
            user=bot.user, exchange_name=bot.exchange_name, is_active=True
        )
        creds = credentials.get_decrypted_credentials()
        try:
            config = {
                "bot_id": str(bot.id),
                "bot_name": bot.bot_name,
                "bot_type": bot_type,
                "user_id": str(bot.user.id),
                "strategy": bot_type,
                "symbol": bot.trading_pair,
                "exchange_name": bot.exchange_name,
                "api_key": creds.get("api_key", ""),
                "secret_key": creds.get("secret_key", ""),
                "passphrase": creds.get("passphrase", ""),
                "is_testnet": credentials.is_testnet,
                "restore_mode": restore_mode,
                "parameters": {},
            }

            if bot_type in ("grid", "martingale"):
                config["parameters"] = {
                    "favor_levels": bot.favor_levels,
                    "against_levels": bot.against_levels,
                    "favor_level_qty": _safe_float(bot.favor_level_qty, 0.0),
                    "against_level_qty": _safe_float(bot.against_level_qty, 0.0),
                    "favor_level_difference": _safe_float(bot.favor_level_difference, 0.5),
                    "against_level_difference": _safe_float(bot.against_level_difference, 0.5),
                    "Take_Profit": _safe_float(bot.take_profit_percent),
                    "Stop_Loss": _safe_float(bot.stop_loss_percent),
                    "Amount_Type": getattr(bot, "amount_type", "quote"),
                    "Order_Type": "market",
                    "SLTP_Type": "percentage",
                    "quantity": _safe_float(bot.base_amount, 0.0),
                }
                from .bot_engine import BotEngine

                engine = BotEngine(config)
                config.pop("api_key", None)
                config.pop("secret_key", None)
                config.pop("passphrase", None)
                engine.startBot()
                with _running_engines_lock:
                    _running_engines[bot_id] = engine
                return {"success": True, "signal": engine.reason, "side": engine.current_side}

            # Signal bots: use BotExecutor strategy path
            executor = BotExecutor.from_config(config)
            config.pop("api_key", None)
            config.pop("secret_key", None)
            config.pop("passphrase", None)
            return executor.run_once()
        finally:
            del creds
            config.pop("api_key", None)
            config.pop("secret_key", None)
            config.pop("passphrase", None)

    except Exception as e:
        _mark_bot_stopped(bot_id)
        _release_redis_lock(bot_id)
        logger.error(f"Error running bot {bot_id}: {type(e).__name__}: {e}")
        logger.debug("Full traceback", exc_info=True)
        return {"success": False, "error": str(e)}


import os as _os  # noqa: E402  (graceful-shutdown block)

# ── Graceful shutdown (Phase 6b) ───────────────────────────────────────
# Registration runs from TWO places, because no single one covers every host:
#   * this module (legacy gate below) — Django runserver child / gunicorn;
#   * ``apps.trading.apps.TradingConfig.ready()`` — Celery workers, via the
#     ``worker_ready`` / ``worker_process_init`` hooks it installs.
# Both paths funnel through ``_install_shutdown_handler()``, which is
# idempotent and CHAINS to whatever handler it displaced, so Celery's warm
# shutdown, gunicorn's ``sys.exit(0)`` and Django's Ctrl-C still run.
import signal as _signal  # noqa: E402  (graceful-shutdown block)

# Handler displaced for each signum; replayed after our teardown.
_prev_sig_handlers: dict = {}


def _install_shutdown_handler(signum=None) -> bool:
    """Install ``_shutdown_handler`` for ``signum`` (SIGTERM+SIGINT default).

    Idempotent and self-healing: if we already own the slot the existing chain
    is left untouched; if somebody else (Celery's ``install_platform_tweaks``)
    has since displaced us, we reclaim the slot and record *their* handler as
    the one to chain to. Returns True when our handler ends up installed.
    """
    signums = (_signal.SIGTERM, _signal.SIGINT) if signum is None else (signum,)
    installed = True
    for sig in signums:
        try:
            prev = _signal.getsignal(sig)
        except (AttributeError, ValueError, OSError):
            installed = False
            continue
        if prev is _shutdown_handler:
            continue  # already ours — keep the chain already recorded
        try:
            _signal.signal(sig, _shutdown_handler)
        except (AttributeError, ValueError, OSError, RuntimeError):
            # Not the main thread (signals are main-thread-only) or a
            # platform without this signal — leave the current owner alone.
            installed = False
            continue
        _prev_sig_handlers[sig] = prev
    return installed


def _chain_to_previous_handler(signum, frame) -> None:
    """Replay the handler we displaced (Celery / gunicorn / Django default)."""
    prev = _prev_sig_handlers.get(signum)
    if not callable(prev) or prev is _shutdown_handler:
        return  # SIG_DFL / SIG_IGN / ourselves — nothing safe to call
    try:
        prev(signum, frame)
    except Exception:
        logger.exception("Chained signal handler for %s failed", signum)


def _shutdown_handler(signum, frame):
    """Signal handler for SIGTERM/SIGINT — final snapshot, then stop all engines."""
    logger.warning(f"Received signal {signum}, stopping all running bots...")
    with _running_engines_lock:
        engine_items = list(_running_engines.items())
    # CHG-3-5: force a FINAL snapshot BEFORE teardown so Phase 4 boot
    # recovery gets the live in-process payload (force bypasses the 5s
    # throttle). save_snapshot writes payload+heartbeat only — status is
    # untouched. Best-effort: no persistence failure may block shutdown.
    try:
        from apps.trading import state as runtime_state
    except Exception:
        logger.exception("Shutdown snapshot skipped: state module unavailable")
        runtime_state = None
    if runtime_state is not None:
        for bid, engine in engine_items:
            if engine is None:
                continue
            try:
                runtime_state.snapshot_engine(engine, force=True)
            except Exception:
                logger.exception("Shutdown snapshot failed for %s", bid)
    for bid, _ in engine_items:
        stop_bot(bid)
    logger.info(f"Stopped {len(engine_items)} running bot(s)")
    # Hand the signal back to the previous owner instead of swallowing it:
    # Celery needs it to finish its warm shutdown, gunicorn to reap the
    # worker, and Django's default_int_handler to raise KeyboardInterrupt.
    _chain_to_previous_handler(signum, frame)


# Legacy gate, kept verbatim from the pre-6b module-level registration: only
# the processes that used to self-register at import time. Celery workers do
# NOT match this gate — they register through apps.ready() instead.
if _os.environ.get("RUN_MAIN") or "gunicorn" in (_os.environ.get("SERVER_SOFTWARE", "")):
    _install_shutdown_handler()


def _collect_engine_state(engine) -> dict:
    """Extract serialisable state dict from a BotEngine instance.

    DEAD-2: Fixed attribute names to match actual BotEngine attributes.
    """
    try:
        return {
            "current_side": getattr(engine, "current_side", None),
            "count": getattr(engine, "count", 0),
            "reason": getattr(engine, "reason", ""),
            "current_price": getattr(engine, "current_price", 0.0),
            "unrealized_pnl": getattr(engine, "Unrealized_Pnl", 0.0),
            "favor_lvl": getattr(engine, "favor_lvl", []),
            "against_lvl": getattr(engine, "against_lvl", []),
        }
    except Exception:
        logger.exception("Failed to collect engine state")
        return {}


# ── Cross-process stop signalling (Phase 6a) ───────────────────────────
# The API / Celery ``stop_bot`` task frequently runs on a *different* worker
# than the one holding the engine, so an in-process registry lookup cannot
# reach it. The engine's monitor loops poll this Redis flag and tear
# themselves down when it appears.

_STOP_REQ_TTL = 600  # seconds — long enough to outlive a slow worker restart


def _stop_req_key(bot_id: str) -> str:
    """Redis key carrying a pending stop request for one bot."""
    return f"bot:stop_req:{bot_id}"


def request_stop(bot_id: str) -> None:
    """
    Flag a bot for cross-process shutdown.

    Called by ``tasks.stop_bot`` *before* the in-process teardown attempt, so
    the owning worker stops its threads within seconds even when it is not
    the worker that received the stop request.
    """
    try:
        cache.set(_stop_req_key(bot_id), 1, _STOP_REQ_TTL)
        logger.info(f"Stop requested for {bot_id} (key {_stop_req_key(bot_id)})")
    except Exception as exc:
        # Never let a Redis failure abort the caller's stop flow — the
        # in-process path and the DB flags below still run.
        logger.error(f"Failed to set stop flag for {bot_id}: {exc}")


def stop_requested(bot_id: str) -> bool:
    """
    True when a cross-process stop has been requested for this bot.

    Fails CLOSED on Redis errors from the *caller's* perspective? No — it
    fails OPEN (returns False) so a transient Redis blip can never silently
    kill a healthy bot's monitoring threads. The durable stop signal is the
    DB ``is_running`` flag written by ``tasks.stop_bot``.
    """
    try:
        return bool(cache.get(_stop_req_key(bot_id)))
    except Exception as exc:
        logger.debug(f"stop_requested lookup failed for {bot_id}: {exc}")
        return False


def clear_stop_request(bot_id: str) -> None:
    """
    Drop a pending stop flag when a bot (re)starts.

    Without this, restarting within ``_STOP_REQ_TTL`` seconds would be killed
    instantly by the previous session's flag.
    """
    try:
        cache.delete(_stop_req_key(bot_id))
    except Exception as exc:
        logger.debug(f"clear_stop_request failed for {bot_id}: {exc}")


def stop_bot(bot_id: str, bot_type: str = "quantum_ai") -> Dict[str, Any]:
    """
    Stop a running bot by signaling its engine threads.
    Saves engine state to Redis for seamless recovery.

    Only reaches the engine when it lives in *this* process; cross-process
    stops are handled by :func:`request_stop` + the monitor-loop poll.
    """
    _mark_bot_stopped(bot_id)

    with _running_engines_lock:
        engine = _running_engines.pop(bot_id, None)

    if engine:
        engine_state = _collect_engine_state(engine)
        save_bot_state(bot_id, bot_type, engine_state)
        engine.stop_bot()

    # Update DB flag
    try:
        if bot_type == "quantum_ai":
            from apps.bots.models import QuantumAIBot

            QuantumAIBot.objects.filter(id=bot_id).update(
                is_running=False, stopped_at=datetime.now(timezone.utc)
            )
        elif bot_type == "grid":
            from apps.bots.models import GridBot

            GridBot.objects.filter(id=bot_id).update(
                is_running=False, stopped_at=datetime.now(timezone.utc)
            )
        elif bot_type == "martingale":
            from apps.bots.models import MartingaleBot

            MartingaleBot.objects.filter(id=bot_id).update(
                is_running=False, stopped_at=datetime.now(timezone.utc)
            )
    except Exception as e:
        logger.exception(f"Failed to update DB flag for {bot_id}: {e}")

    # ``engine_found`` tells the caller whether threads were actually joined
    # in this process. When it is False the engine lives on another worker and
    # only the Redis stop flag can reach it.
    return {"success": True, "bot_id": bot_id, "engine_found": engine is not None}
