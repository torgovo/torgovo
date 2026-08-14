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
_running_engines: Dict[str, Any] = {}
_running_engines_lock = threading.Lock()


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
            demo_mode=config.get("is_testnet", False),
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


# ── Graceful shutdown ──────────────────────────────────────────────────
import signal as _signal  # noqa: E402  (graceful-shutdown block)


def _shutdown_handler(signum, frame):
    """Signal handler for SIGTERM/SIGINT — stops all running engines."""
    logger.warning(f"Received signal {signum}, stopping all running bots...")
    with _running_engines_lock:
        engine_ids = list(_running_engines.keys())
    for bid in engine_ids:
        stop_bot(bid)
    logger.info(f"Stopped {len(engine_ids)} running bot(s)")


# Register handlers (only in non-Django-management context)
import os as _os  # noqa: E402  (graceful-shutdown block)

if _os.environ.get("RUN_MAIN") or "gunicorn" in (_os.environ.get("SERVER_SOFTWARE", "")):
    _signal.signal(_signal.SIGTERM, _shutdown_handler)
    _signal.signal(_signal.SIGINT, _shutdown_handler)


def _collect_engine_state(engine) -> dict:
    """Extract serialisable state dict from a BotEngine instance."""
    try:
        return {
            "current_side": getattr(engine, "current_side", None),
            "entry_price": getattr(engine, "entry_price", None),
            "count": getattr(engine, "count", 0),
            "reason": getattr(engine, "reason", ""),
            "total_pnl": getattr(engine, "total_pnl", 0.0),
            "favor_levels": getattr(engine, "favor_levels", []),
            "against_levels": getattr(engine, "against_levels", []),
            "favor_orders": getattr(engine, "favor_orders", []),
            "against_orders": getattr(engine, "against_orders", []),
        }
    except Exception:
        logger.exception("Failed to collect engine state")
        return {}


def stop_bot(bot_id: str, bot_type: str = "quantum_ai") -> Dict[str, Any]:
    """
    Stop a running bot by signaling its engine threads.
    Saves engine state to Redis for seamless recovery.
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

    return {"success": True, "bot_id": bot_id}
