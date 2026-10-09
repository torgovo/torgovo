"""
Bot Engine - Trading Execution Engine

Ported from oldbybit.py BybitBots class.
(old)This engine preserves the EXACT same logic, flow, and values from the original
implementation but embeds it into the new adapter/strategy architecture.

Key methods ported 1:1 from oldbybit.py:
- calculated_grid_orders() -> _execute_grid_entry()
- monitor_grid_orders()    -> _monitor_grid_orders()  (the core order-ID based loop)
- monitor_lossProfit()     -> _monitor_loss_profit()
- close_open_order()       -> _close_open_position()
- close_all_orders()       -> _close_all_orders()
- create_order()           -> _create_order() (dollar/coin branching)
- prepare_order_data()     -> _prepare_order_data()

(new)Uses the raw CCXT exchange object directly — same as the original code.
All CCXT calls (create_order, fetch_open_orders, fetch_order, etc.) are
identical to oldbybit.py. The only difference is how the exchange is
initialized (via the adapter pattern instead of hardcoded credentials).

Exchange calls go through the adapter (self.executor.adapter) which handles
exchange-specific params, rate limiting, and error normalization for all
exchanges (Bybit, Binance, OKX, MEXC, Coinbase, etc.).
"""

import logging
import threading
import time
from typing import Any, Dict, Optional

# Phase 3: snapshot/restore helpers (module-level is cycle-free —
# apps/trading/state.py imports only apps.trading.models).
from apps.trading import state as runtime_state
from core.telegram_service import TelegramService

from .execution import BotExecutor
from .grid_monitor import GridPositionMonitor
from .order_service import BotOrderService

logger = logging.getLogger("trading.engines")


class BotEngine:
    """
    Trading Bot Engine — direct port of oldbybit.py BybitBots.

    Uses raw CCXT exchange instance for all trading operations,
    exactly as the original code did. The adapter is only used
    to initialize the exchange object.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize engine with a plain config dict.
        """
        self.config = config
        self.bot_name = config.get("bot_name", "unnamed")

        # Build executor (gives us the adapter with initialized CCXT exchange)
        self.executor = BotExecutor.from_config(config)

        # Redundant safety: keys are already popped in from_config(), but guard
        # against direct construction or mocked from_config() calls
        self.config.pop("api_key", None)
        self.config.pop("secret_key", None)
        self.config.pop("passphrase", None)

        # Symbol formatting (matches oldbybit.py exactly)
        # oldbybit.py: self.symbol = f"{pair_config['pair_symbol']}:{quote_currency}"
        pair_symbol = config.get("symbol", "")
        quote_currency = pair_symbol.split("/")[1] if "/" in pair_symbol else "USDT"
        self.symbol = f"{pair_symbol}:{quote_currency}"

        # The pair_config dict (matches oldbybit.py self.pair_config)
        self.pair_config = config.get("parameters", {})
        self.pair_config["pair_symbol"] = pair_symbol

        # Indicator state (mirrors oldbybit.py exactly)
        self.EMA = 0.0
        self.BB = None
        self.TSI = None
        self.ADX = None
        self.RSI = 0.0
        self.PrevRSI = 0.0
        self.RSI_color = None
        self.RSI_prev_color = None

        # Trading state
        self.current_side = "None"
        self.count = 0
        self.current_price = 0.0

        self.bot_running = False
        self.lock = threading.Lock()
        self.monitoring_threads = []

        # BotOrderService — pure order execution + persistence (no strategy/monitoring)
        self.order_service = BotOrderService(
            adapter=self.executor.adapter,
            symbol=self.symbol,
            pair_config=self.pair_config,
            bot_config=self.config,
        )

        # GridPositionMonitor — owns all monitoring thread lifecycle
        # Callbacks point directly to BotOrderService / BotEngine orchestration
        self.grid_monitor = GridPositionMonitor(
            adapter=self.executor.adapter,
            symbol=self.symbol,
            pair_config=self.pair_config,
            bot_config=self.config,
            create_order_cb=self.order_service.create_order,
            close_all_orders_cb=self.close_all_orders,
            # Phase 6a: fired from inside a monitor thread when another
            # worker requested a stop via Redis. Must NOT join threads.
            stop_cb=self._on_remote_stop,
            # Phase 3: called each loop iteration; _snapshot_tick self-
            # throttles (5s) and never raises, so loops stay safe.
            snapshot_cb=self._snapshot_tick,
        )

        self._stop_event = threading.Event()
        self.monitoring = False
        self.bot_running = False

        self.reason = ""
        self.PrevReason = ""
        self.Percentage = 0.0
        self.Unrealized_Pnl = 0.0
        self.last_trade_pnl = 0.0
        self.favor_lvl = []
        self.against_lvl = []

        # Condition flags (initialized same as oldbybit.py __init__)
        self.EmaBuyCondition = True if (self.current_price >= self.EMA != 0) else False
        self.EmaSellCondition = True if (self.current_price <= self.EMA != 0) else False
        self.RsiBuyCondition = (
            self.PrevRSI <= self.pair_config.get("RSI_Lower", 30) and self.RSI_color == "white"
        )
        self.RsiSellCondition = (
            self.PrevRSI >= self.pair_config.get("RSI_Upper", 70) and self.RSI_color == "white"
        )
        self.BBBuyCondition = (
            self.BB == "Crossing Down Band"
            or self.BB == "Closed Below Lower Band"
            or self.BB == "Up Arrow"
        )
        self.BBSellCondition = (
            self.BB == "Crossing Up Band"
            or self.BB == "Closed Above Upper Band"
            or self.BB == "Down Arrow"
        )
        self.NoTrade = True if (self.count == 0 and self.current_side == "None") else False
        self.BuyTrade = True if (self.count == 1 and self.current_side == "Buy") else False
        self.SellTrade = True if (self.count == 1 and self.current_side == "Sell") else False

        # Performance metrics
        self.signals_generated = 0
        self.orders_executed = 0

        # Heartbeat tracking
        self._heartbeat_counter = 0
        # Phase 5 (CHG-5-1): kept in sync with GridPositionMonitor (10
        # iterations ~10s); the monitor loops own the actual DB writes.
        self._heartbeat_interval = 10

        # SL/TP change tracking (last known values placed on exchange)
        self._last_sl: Optional[float] = None
        self._last_tp: Optional[float] = None

        # Quantum AI Strategy instance (synced with indicators for external use)
        from ..strategies.quantum_ai import QuantumAIStrategy

        self.strategy = QuantumAIStrategy(parameters=self.pair_config)
        self.strategy.symbol = self.symbol

        logger.info(f"✅ BotEngine initialized for {self.bot_name}")

    # =========================================================================
    # UPDATE CONDITIONS (from oldbybit.py update_conditions — exact copy)
    # =========================================================================

    def update_conditions(self):
        with self.lock:
            logger.info("updating conditions inside Lock")

            self.current_price = self.executor.adapter.fetch_ticker(self.symbol)["last"]
            self.EmaBuyCondition = self.current_price >= self.EMA != 0
            self.EmaSellCondition = self.current_price <= self.EMA != 0

            self.RsiBuyCondition = (
                self.PrevRSI <= self.pair_config.get("RSI_Lower", 30) and self.RSI_color == "white"
            )
            self.RsiSellCondition = (
                self.PrevRSI >= self.pair_config.get("RSI_Upper", 70) and self.RSI_color == "white"
            )

            self.BBBuyCondition = (
                self.BB == "Crossing Down Band"
                or self.BB == "Closed Below Lower Band"
                or self.BB == "Up Arrow"
            )
            self.BBSellCondition = (
                self.BB == "Crossing Up Band"
                or self.BB == "Closed Above Upper Band"
                or self.BB == "Down Arrow"
            )

            self.NoTrade = self.count == 0 and self.current_side == "None"
            self.BuyTrade = self.count == 1 and self.current_side == "Buy"
            self.SellTrade = self.count == 1 and self.current_side == "Sell"

            self._sync_strategy()

    def _sync_strategy(self):
        """Sync current indicator values to the strategy instance."""
        self.strategy.EMA = self.EMA
        self.strategy.RSI = self.RSI
        self.strategy.PrevRSI = self.PrevRSI
        self.strategy.RSI_color = self.RSI_color
        self.strategy.RSI_prev_color = self.RSI_prev_color
        self.strategy.BB = self.BB
        self.strategy.current_price = self.current_price
        self.strategy.current_side = self.current_side
        self.strategy.count = self.count

    # =========================================================================
    # INDICATOR DATA STRING (from oldbybit.py — exact copy)
    # =========================================================================

    def get_indicator_data(self):
        return (
            f"Symbol: {self.symbol} - CurrentPrice: {self.current_price} - "
            f"EMA: {self.EMA} - BB: {self.BB} - RSI: {self.RSI} - "
            f"PrevRSI: {self.PrevRSI} - RSI_Color: {self.RSI_color} - "
            f"PrevRSI_Color: {self.RSI_prev_color}"
        )

    def _send_signal_notification(self, event_type, reason, side, price, details=None):
        """
        Send a Telegram signal notification to the user.
        event_type: 'entry', 'exit_tp', 'exit_sl', 'close'
        """
        try:
            from django.contrib.auth import get_user_model

            User = get_user_model()
            user_id = self.config.get("user_id")
            if not user_id:
                return
            user = User.objects.get(id=user_id)

            if not getattr(user, "telegram_token", None) or not getattr(
                user, "telegram_chat_id", None
            ):
                return

            emoji_map = {
                "entry": "🟢" if side.upper() == "BUY" else "🔴",
                "exit_tp": "💰",
                "exit_sl": "🛑",
                "close": "⏹️",
            }
            emoji = emoji_map.get(event_type, "📊")
            label_map = {
                "entry": "SIGNAL",
                "exit_tp": "TP HIT",
                "exit_sl": "SL HIT",
                "close": "POSITION CLOSED",
            }
            label = label_map.get(event_type, event_type.upper())

            message = (
                f"{emoji} **{label}**\n\n"
                f"**Symbol:** {self.symbol}\n"
                f"**Side:** {side.upper()}\n"
                f"**Price:** {price}\n"
                f"**Reason:** {reason}\n"
                f"**Exchange:** {self.config.get('exchange_name', 'N/A')}\n"
                f"**Strategy:** {self.config.get('strategy', 'trading')}\n"
                f"**Indicators:** {self.get_indicator_data()}\n"
            )
            if details:
                message += f"**Details:** {details}\n"

            TelegramService.send_message(user.telegram_token, user.telegram_chat_id, message)
        except Exception as e:
            logger.debug(f"Failed to send signal notification: {e}")

    def _send_channel_notification(self, event_type, side, price):
        """
        Send a plain-text notification to the user's Telegram channel (broadcast).
        Uses channel_token and channel_chat_id fields on the user model.
        """
        try:
            from django.contrib.auth import get_user_model
            from django.utils import timezone as _tz

            User = get_user_model()
            user_id = self.config.get("user_id")
            if not user_id:
                return
            user = User.objects.get(id=user_id)

            if not getattr(user, "channel_token", None) or not getattr(
                user, "channel_chat_id", None
            ):
                return

            now = _tz.localtime(_tz.now())
            label_map = {
                "entry": "OPEN",
                "exit_tp": "TP HIT",
                "exit_sl": "SL HIT",
                "close": "CLOSE",
            }
            label = label_map.get(event_type, event_type.upper())
            exchange = self.config.get("exchange_name", "N/A")

            message = (
                f"Timezone: GMT+5\n"
                f"{now}\n"
                f"Exchange: {exchange}\n"
                f"{label} {side.upper()}\n"
                f"Symbol: {self.symbol}\n"
                f"Price: {price}"
            )

            TelegramService.send_channel_message(user, message)
        except Exception as e:
            logger.debug(f"Failed to send channel notification: {e}")

    # =========================================================================
    # RESET STATE (from oldbybit.py reset_trading_state — exact copy)
    # =========================================================================

    def reset_trading_state(self):
        self.monitoring = False
        self._stop_event.set()
        self.EMA = 0.0
        self.BB = None
        self.TSI = None
        self.ADX = None
        self.RSI = 0.0
        self.PrevRSI = 0.0
        self.RSI_color = None
        self.RSI_prev_color = None
        self.BB = ""
        self.current_side = "None"
        self.count = 0
        self.PrevReason = self.reason
        self.reason = ""
        self.bot_running = False
        self.favor_lvl = []
        self.against_lvl = []
        self.update_conditions()
        self._wait_for_threads()

    def _wait_for_threads(self):
        """Wait for all monitoring threads to finish"""
        self.grid_monitor.stop_all()

    def _notify_stopped(self) -> None:
        """Send the Telegram "bot stopped" notice (guarded — creds optional)."""
        try:
            from django.contrib.auth import get_user_model

            User = get_user_model()
            user_id = self.config.get("user_id")
            if user_id:
                user = User.objects.get(id=user_id)
                TelegramService.notify_bot_stopped(
                    user, self.config.get("strategy", "trading"), reason="Bot stopped"
                )
        except Exception as e:
            logger.warning(f"Failed to send Telegram stop notification: {e}")

    def stop_bot(self):
        """Properly stop the bot and clean up all threads"""
        logger.info(f"Stopping bot for {self.symbol}")
        self.monitoring = False
        self._stop_event.set()
        self._wait_for_threads()
        self.bot_running = False
        logger.info(f"Bot stopped for {self.symbol}")
        self._notify_stopped()

    def _on_remote_stop(self) -> None:
        """
        Phase 6a teardown driven by a cross-process stop request.

        Invoked from GridPositionMonitor._check_remote_stop, i.e. *inside* a
        monitor thread, so it must NEVER join threads — that would deadlock
        the caller. The monitor loops' flags are already cleared by the poll;
        this adds the engine-level flags and registry cleanup so a restart in
        the same worker is not blocked by the "already running here" guard.

        DB flags are NOT written here: they are persisted by the worker that
        received ``tasks.stop_bot``.
        """
        bot_id = self.config.get("bot_id")
        logger.info(f"Remote stop handled for {self.symbol} (bot {bot_id})")

        # Engine-level flags (the monitor instance's flags were set by the
        # poll that invoked this callback).
        self.monitoring = False
        self.bot_running = False
        self._stop_event.set()

        if bot_id:
            from apps.trading.engines import execution

            execution._mark_bot_stopped(str(bot_id))
            with execution._running_engines_lock:
                execution._running_engines.pop(str(bot_id), None)

        self._notify_stopped()

    # =========================================================================
    # PHASE 3: SNAPSHOT TICK (crash-consistent persistence)
    # =========================================================================

    def _snapshot_tick(self, force: bool = False) -> bool:
        """Write this engine's volatile state to BotRuntimeState.

        Wired into GridPositionMonitor as ``snapshot_cb`` (both monitor
        loops) and called with ``force=True`` at lifecycle points in
        ``startBot``. The helper throttles (5s) and swallows DB errors —
        nothing here may ever propagate into a monitor thread.
        """
        return runtime_state.snapshot_engine(self, force=force)

    # =========================================================================
    # MAIN EXECUTION: startBot() from oldbybit.py — exact copy of logic
    # =========================================================================

    def startBot(self):
        self.update_conditions()
        self.current_price = self.executor.adapter.fetch_ticker(self.symbol)["last"]
        self.bot_running = True

        restore_mode = self.config.get("restore_mode", False)

        # ---- RESTORE MODE: attach to existing position, skip entry eval ----
        if restore_mode:
            logger.info(
                f"{self.bot_name} starting in RESTORE MODE — attaching to existing position"
            )
            # Phase 4 (CHG-4-2): apply the persisted snapshot BEFORE
            # attaching — the payload restores reason/indicators/P&L/count,
            # then attach overwrites side/count/levels with live exchange
            # truth. No row/payload -> False -> identical cold start.
            runtime_state.restore_engine(self)
            self._start_monitoring_for_existing_position()
            # Phase 3: capture post-attach state so a second crash mid-
            # monitoring restarts from this point, not from a colder one.
            self._snapshot_tick(force=True)
            return

        # Send Telegram notification
        try:
            from django.contrib.auth import get_user_model

            User = get_user_model()
            user_id = self.config.get("user_id")
            if user_id:
                user = User.objects.get(id=user_id)
                TelegramService.notify_bot_started(
                    user, self.config.get("strategy", "trading"), self.config
                )
        except Exception as e:
            logger.warning(f"Failed to send Telegram start notification: {e}")

        logger.info(f"current side: {self.current_side}")
        logger.info(f"{self.bot_name} BOT START")
        logger.info(f"Current price: {self.current_price}")

        # Delegate entry/exit signal evaluation to QuantumAIStrategy
        conditions = self.strategy._evaluate_conditions(self.current_price)

        if self.NoTrade:
            signal = self.strategy._check_entry_conditions(
                conditions, self.current_price, self.symbol
            )
            if signal:
                side = signal.action.capitalize()
                self.count = 1
                self.current_side = side
                self.reason = signal.reason
                data = self.prepare_order_data(side, self.current_price)
                logger.info(f"data of the grid: {data}")
                detail = self.calculated_grid_orders(data)
                # Phase 1: mark live trade + persist the structured entry reason
                self.save_order(
                    side.upper(),
                    signal.reason,
                    detail,
                    reason=signal.reason,
                    status="open",
                )
                self._send_signal_notification(
                    "entry",
                    signal.reason,
                    side,
                    self.current_price,
                    details=str(self.pair_config.get("Stop_Loss", "")),
                )
                self._send_channel_notification("entry", side, self.current_price)

        elif self.BuyTrade:
            signal = self.strategy._check_buy_exit_conditions(
                conditions, self.current_price, self.symbol, None
            )
            if signal:
                logger.info(f"TP/Exit signal: {signal.reason}")
                pnl = self.grid_monitor.Percentage
                self._send_signal_notification(
                    "exit_tp" if "TP" in signal.reason.upper() else "exit_sl",
                    signal.reason,
                    "Buy",
                    self.current_price,
                    details=f"PnL: {pnl}%",
                )
                self._send_channel_notification(
                    "exit_tp" if "TP" in signal.reason.upper() else "exit_sl",
                    "Buy",
                    self.current_price,
                )
                self.close_all_orders(signal.reason)

        elif self.SellTrade:
            signal = self.strategy._check_sell_exit_conditions(
                conditions, self.current_price, self.symbol, None
            )
            if signal:
                logger.info(f"TP/Exit signal: {signal.reason}")
                pnl = self.grid_monitor.Percentage
                self._send_signal_notification(
                    "exit_tp" if "TP" in signal.reason.upper() else "exit_sl",
                    signal.reason,
                    "Sell",
                    self.current_price,
                    details=f"PnL: {pnl}%",
                )
                self._send_channel_notification(
                    "exit_tp" if "TP" in signal.reason.upper() else "exit_sl",
                    "Sell",
                    self.current_price,
                )
                self.close_all_orders(signal.reason)

        # Phase 3: force a snapshot NOW — entries/exits must never wait for
        # the next monitor tick (worst-case blind window stays ~5s).
        self._snapshot_tick(force=True)

    # Alias for webhook compatibility
    def execute_once(self):
        """Webhook-triggered execution. Calls startBot() and returns result dict."""
        result = {"success": False, "signal": None, "error": None}
        try:
            self.startBot()
            result["success"] = True
            result["signal"] = self.reason
        except Exception as e:
            logger.error(f"Execute once error: {type(e).__name__}: {e}")
            logger.debug("Full traceback", exc_info=True)
            result["error"] = str(e)
        return result

    # =========================================================================
    # MANUAL ORDERS (from oldbybit.py buy_order, sell_order, close_custom_order)
    # =========================================================================

    async def buy_order(self):
        from asgiref.sync import sync_to_async

        if self.NoTrade:
            data = self.prepare_order_data("Buy", self.current_price)
            logger.info(f"data of the grid: {data}")
            self.count = 1
            self.current_side = "Buy"
            self.PrevReason = self.reason
            self.reason = "Custom BUY"
            detail = self.calculated_grid_orders(data)
            await sync_to_async(self.save_order)(
                "BUY",
                "CUSTOM BUY ORDER",
                details=detail,
                reason="Custom BUY",
                status="open",
            )
            self._send_signal_notification("entry", "Custom BUY", "Buy", self.current_price)
            self._send_channel_notification("entry", "Buy", self.current_price)
            self.update_conditions()
        else:
            logger.info("Already Bought")

    async def sell_order(self):
        from asgiref.sync import sync_to_async

        if self.NoTrade:
            data = self.prepare_order_data("Sell", self.current_price)
            logger.info(f"data of the grid: {data}")
            self.count = 1
            self.current_side = "Sell"
            self.PrevReason = self.reason
            self.reason = "Custom SELL"
            detail = self.calculated_grid_orders(data)
            await sync_to_async(self.save_order)(
                "SELL",
                "CUSTOM SELL ORDER",
                details=detail,
                reason="Custom SELL",
                status="open",
            )
            self._send_signal_notification("entry", "Custom SELL", "Sell", self.current_price)
            self._send_channel_notification("entry", "Sell", self.current_price)
            self.update_conditions()
        else:
            logger.info("Already Sold")

    async def close_custom_order(self):
        from asgiref.sync import sync_to_async

        if self.BuyTrade or self.SellTrade:
            pnl = self.grid_monitor.Percentage
            self._send_signal_notification(
                "close",
                "Custom CLOSE",
                self.current_side,
                self.current_price,
                details=f"PnL: {pnl}%",
            )
            self._send_channel_notification("close", self.current_side, self.current_price)
            await sync_to_async(self.close_all_orders)(description="CUSTOM CLOSE ORDER")
        else:
            logger.info("No Trade in Record")

    # =========================================================================
    # PREPARE ORDER DATA (from oldbybit.py — exact copy)
    # =========================================================================

    def prepare_order_data(self, side, current_price):
        config = self.pair_config
        if self.pair_config.get("Amount_Type") == "dollar":
            quantity_dollar = config["quantity"]
            favor_level_qty_dollar = config["favor_level_qty"]
            against_level_qty_dollar = config["against_level_qty"]

            quantity = round(config["quantity"] / current_price, 4)
            favor_level_qty = round(config["favor_level_qty"] / current_price, 4)
            against_level_qty = round(config["against_level_qty"] / current_price, 4)
            logger.info(
                f"dollar calculated - coins: {quantity}, {favor_level_qty}, {against_level_qty}"
            )
        else:
            quantity = config["quantity"]
            favor_level_qty = config["favor_level_qty"]
            against_level_qty = config["against_level_qty"]
            quantity_dollar = None
            favor_level_qty_dollar = None
            against_level_qty_dollar = None
            logger.info(f"coin calculated: {quantity}, {favor_level_qty}, {against_level_qty}")

        quantity = float(self.executor.adapter.amount_to_precision(self.symbol, quantity))
        favor_level_qty = float(
            self.executor.adapter.amount_to_precision(self.symbol, favor_level_qty)
        )
        against_level_qty = float(
            self.executor.adapter.amount_to_precision(self.symbol, against_level_qty)
        )

        data = {
            "category": "futures",
            "symbol": self.symbol,
            "Order_Type": config.get("Order_Type", "market"),
            "side": side,
            "qty": quantity,
            "qty_dollar": quantity_dollar,
            "price": current_price,
            "favor_levels": config.get("favor_levels", 5),
            "against_levels": config.get("against_levels", 5),
            "favor_level_qty": favor_level_qty,
            "against_level_qty": against_level_qty,
            "favor_level_qty_dollar": favor_level_qty_dollar,
            "against_level_qty_dollar": against_level_qty_dollar,
            "favor_level_difference": config.get("favor_level_difference", 0.5),
            "against_level_difference": config.get("against_level_difference", 0.5),
        }
        return data

    # =========================================================================
    # FETCH CURRENT PRICE (from oldbybit.py — exact copy)
    # =========================================================================

    def fetch_current_price(self):
        self.current_price = self.executor.adapter.get_current_price(self.symbol)
        thread_id = threading.get_ident()
        logger.info(f"Thread ID: {thread_id} | Fetched current price: {self.current_price}")
        return self.current_price

    def save_order(
        self, side, description, details=None, *, reason=None, status=None, pnl=None, price=None
    ):
        """Save order via BotOrderService and track count.

        Phase 1 (persistence): optional trade-integrity kwargs are forwarded
        to BotOrderService — entry call sites pass ``reason``/``status="open"``,
        exit call sites pass ``status="closed"``/``pnl``.
        """
        result = self.order_service.save_order(
            side,
            description,
            details,
            indicators=self._get_indicators(),
            reason=reason,
            status=status,
            pnl=pnl,
            price=price,
        )
        if result:
            self.orders_executed += 1
        return result

    # =========================================================================
    # SAVE ORDER (from oldbybit.py — adapted for new models)
    # =========================================================================

    def _get_indicators(self) -> dict:
        """Return current indicator state as a dict (for BotOrderService.save_order)."""
        return {
            "EMA": self.EMA,
            "RSI": self.RSI,
            "PrevRSI": self.PrevRSI,
            "RSI_color": self.RSI_color,
            "RSI_prev_color": self.RSI_prev_color,
            "BB": self.BB,
            "TSI": self.TSI,
            "ADX": self.ADX,
        }

    # =========================================================================
    # CLOSE OPEN ORDER (from oldbybit.py — exact copy, uses raw CCXT)
    # =========================================================================

    def close_open_order(self, description):
        """Close position via BotOrderService, update state, save order.

        Kept for backward compatibility.
        """
        result = self.order_service.close_position(self.symbol)
        if result:
            self.Unrealized_Pnl = result["pnl"]
            self.Percentage = result["percentage"]
            self.last_trade_pnl = result["pnl"]
            # Phase 1: closing record carries realized P/L + closed status
            self.save_order(
                result["side"],
                description,
                result["detail"],
                status="closed",
                pnl=result["pnl"],
            )
            return result["detail"]
        return None

    # =========================================================================
    # CLOSE ALL ORDERS (from oldbybit.py — exact copy)
    # =========================================================================

    def close_all_orders(self, description):
        logger.info(
            f"cancelling all limit orders of self.symbol: {self.symbol}, "
            f"pair_config['pair_symbol']: {self.pair_config.get('pair_symbol')}"
        )
        self.reset_trading_state()
        self.order_service.cancel_all_orders(self.symbol)
        position = self.close_open_order(description)
        self.reason = description
        logger.info(f"All Orders Closed: {description}")
        return position

    # =========================================================================
    # CALCULATE GRIDS (from oldbybit.py — exact copy)
    # =========================================================================

    def calculate_grids(self, side):
        favor_levels = []
        against_levels = []
        if side.lower() == "buy":
            for levels in range(self.pair_config.get("favor_levels", 5)):
                favor_levels.append(
                    round(
                        self.current_price
                        * (
                            1
                            + (levels + 1)
                            * self.pair_config.get("favor_level_difference", 0.5)
                            / 100
                        ),
                        6,
                    )
                )
            for levels in range(self.pair_config.get("against_levels", 5)):
                against_levels.append(
                    round(
                        self.current_price
                        * (
                            1
                            - (levels + 1)
                            * self.pair_config.get("against_level_difference", 0.5)
                            / 100
                        ),
                        6,
                    )
                )

        if side.lower() == "sell":
            for levels in range(self.pair_config.get("favor_levels", 5)):
                favor_levels.append(
                    round(
                        self.current_price
                        * (
                            1
                            - (levels + 1)
                            * self.pair_config.get("favor_level_difference", 0.5)
                            / 100
                        ),
                        6,
                    )
                )
            for levels in range(self.pair_config.get("against_levels", 5)):
                against_levels.append(
                    round(
                        self.current_price
                        * (
                            1
                            + (levels + 1)
                            * self.pair_config.get("against_level_difference", 0.5)
                            / 100
                        ),
                        6,
                    )
                )

        return favor_levels, against_levels

    # =========================================================================
    # CALCULATED GRID ORDERS (from oldbybit.py — exact copy, uses raw CCXT)
    # =========================================================================

    def calculated_grid_orders(self, data):
        self.bot_running = True
        self.monitoring = True
        self.grid_monitor.bot_running = True
        self.grid_monitor.monitoring = True
        logger.info(f"Calculating Grids for {data['symbol']}")

        side = data["side"]
        qty = data["qty"]
        logger.info(f"quantity: {qty} - type {type(qty)}")
        price = data["price"]
        favor_level_qty = data["favor_level_qty"]
        against_level_qty = data["against_level_qty"]
        logger.info(
            f"Grid data: {data['symbol']} - {data['Order_Type']} - {side} - {qty} - {price}"
        )

        # Open initial order
        initial_order = None
        try:
            if self.pair_config.get("Amount_Type") == "dollar":
                qty_dollar = data["qty_dollar"]
                logger.info(
                    f"pair config amount type dollar {self.pair_config.get('Amount_Type')} - "
                    f"cost in dollars:{qty_dollar} - side: {side}"
                )
                if side == "Buy":
                    initial_order = self.executor.adapter.create_market_order_with_cost(
                        self.symbol, "buy", qty_dollar
                    )
                    logger.info(f"initial market buy order with dollar cost: {initial_order}")
                elif side == "Sell":
                    initial_order = self.executor.adapter.create_market_order_with_cost(
                        self.symbol, "sell", qty_dollar
                    )
                    logger.info(f"initial market sell order with dollar cost: {initial_order}")

            elif self.pair_config.get("Amount_Type") == "coin":
                logger.info(
                    f"pair config amount type coin - quantity in coins:{qty} - side: {side}"
                )
                initial_order = self.order_service.create_order(
                    order_type=self.pair_config.get("Order_Type", "market"),
                    side=side,
                    quantity=qty,
                    price=price,
                )
            else:
                logger.warning(f"neither dollar nor coin: {self.pair_config.get('Amount_Type')}")
        except Exception as e:
            logger.error(f"Creating initial order failed: {e}")

        favor_levels, against_levels = self.calculate_grids(side)
        # updating levels on global variable for indicator page
        self.favor_lvl, self.against_lvl = favor_levels, against_levels

        if side.lower() == "buy":
            # Open grid orders
            for level in favor_levels:
                level_price = float(level)
                try:
                    logger.info(f"quantity: {qty} - type {type(qty)}")
                    self.order_service.create_order("limit", "sell", favor_level_qty, level_price)
                except Exception as e:
                    logger.error(f"Creating favor order failed: {e}")

            for level in against_levels:
                level_price = float(level)
                try:
                    self.order_service.create_order("limit", "buy", against_level_qty, level_price)
                except Exception as e:
                    logger.error(f"Creating against order failed: {e}")

        if side.lower() == "sell":
            for level in favor_levels:
                level_price = float(level)
                try:
                    self.order_service.create_order("limit", "buy", favor_level_qty, level_price)
                except Exception as e:
                    logger.error(f"Creating favor order failed: {e}")

            for level in against_levels:
                level_price = float(level)
                try:
                    self.order_service.create_order("limit", "sell", against_level_qty, level_price)
                except Exception as e:
                    logger.error(f"Creating against order failed: {e}")

        # Place exchange-native SL/TP orders (falls back to polling)
        with self.grid_monitor.sltp_lock:
            self.grid_monitor._place_sltp_orders(side, price)

        # Start monitoring orders in background threads
        time.sleep(3)
        monitoring_thread = threading.Thread(
            target=self.monitor_grid_orders,
            args=(side, price, favor_levels, against_levels, favor_level_qty, against_level_qty),
            name=f"GridMonitor-{self.symbol}-{side}",
        )
        monitoring_thread.daemon = True
        monitoring_thread.start()
        self.grid_monitor.monitoring_threads.append(monitoring_thread)

        # Start SL/TP monitoring thread
        sltp_thread = threading.Thread(
            target=self.monitor_lossProfit, args=(side,), name=f"SLTP-{self.symbol}-{side}"
        )
        sltp_thread.daemon = True
        sltp_thread.start()
        self.grid_monitor.monitoring_threads.append(sltp_thread)
        self.grid_monitor.monitoring = True

        self.signals_generated += 1
        return initial_order

    # =========================================================================
    # MONITOR GRID ORDERS (from oldbybit.py — exact copy, uses raw CCXT)
    # ORDER-ID BASED grid monitoring loop
    # =========================================================================

    def monitor_grid_orders(
        self, side, entry_price, favor_levels, against_levels, favor_level_qty, against_level_qty
    ):
        """Delegate to GridPositionMonitor. Kept for backward compatibility with tests."""
        return self.grid_monitor._monitor_grid_orders(
            side, entry_price, favor_levels, against_levels, favor_level_qty, against_level_qty
        )

    # =========================================================================
    # MONITOR LOSS/PROFIT (from oldbybit.py — exact copy)
    # =========================================================================

    def monitor_lossProfit(self, side):
        """Delegate to GridPositionMonitor. Kept for backward compatibility with tests."""
        return self.grid_monitor._monitor_loss_profit(side)

    # =========================================================================
    # CHECK LOSS/PROFIT PERCENT (from oldbybit.py — exact copy, uses raw CCXT)
    # =========================================================================

    def check_lossProfit_percent(self):
        """Delegate to GridPositionMonitor. Kept for backward compatibility."""
        return self.grid_monitor._check_loss_profit_percent()

    # =========================================================================
    # EXCHANGE-NATIVE SL/TP (replaces 5-second polling with exchange stops)
    # =========================================================================

    def _place_sltp_orders(self, side, entry_price):
        """Delegate to GridPositionMonitor. Kept for backward compatibility."""
        self.grid_monitor._place_sltp_orders(side, entry_price)

    def _refresh_sltp_if_changed(self):
        """Delegate to GridPositionMonitor. Kept for backward compatibility."""
        self.grid_monitor._refresh_sltp_if_changed()

    # =========================================================================
    # HEARTBEAT (stale-bot detection)
    # =========================================================================

    def _update_heartbeat(self):
        """Delegate to GridPositionMonitor. Kept for backward compatibility."""
        self.grid_monitor._update_heartbeat()

    # =========================================================================
    # RESTORE MODE (attach to existing position after worker restart)
    # =========================================================================

    def _start_monitoring_for_existing_position(self):
        """
        Start monitoring threads for an existing position on the exchange.
        Called instead of entry evaluation when bot starts in restore_mode.
        """
        try:
            adapter = self.executor.adapter
            position = adapter.fetch_position(self.symbol)
            if not position or float(position.get("contracts", 0)) == 0:
                logger.info(
                    f"No position found for {self.symbol} in restore mode — nothing to monitor"
                )
                self.bot_running = False
                return

            size = float(position["contracts"])
            side = position.get("side", "")
            entry_price = float(position.get("entryPrice", self.current_price))

            self.current_side = "Buy" if side == "long" else "Sell"
            self.count = 1
            self.current_price = entry_price
            logger.info(
                f"Restore mode: attached to {side} position, size={size}, entry={entry_price}"
            )

            # Fetch open orders to rebuild grid levels
            open_orders = adapter.fetch_open_orders(self.symbol)
            favor_levels = []
            against_levels = []
            for o in open_orders:
                try:
                    p = float(o.get("price", 0))
                except (TypeError, ValueError):
                    continue
                if p == 0:
                    continue
                if side == "long":
                    if o.get("side", "").lower() == "sell":
                        favor_levels.append(p)
                    else:
                        against_levels.append(p)
                else:
                    if o.get("side", "").lower() == "buy":
                        favor_levels.append(p)
                    else:
                        against_levels.append(p)

            self.favor_lvl = sorted(favor_levels, reverse=(side == "short"))
            self.against_lvl = sorted(against_levels, reverse=(side == "long"))

            logger.info(
                f"Restore mode: restored {len(favor_levels)} favor levels, "
                f"{len(against_levels)} against levels"
            )

            # Use default level qty from config
            favor_level_qty = float(self.pair_config.get("favor_level_qty", 0))
            against_level_qty = float(self.pair_config.get("against_level_qty", 0))

            # Place exchange-native SL/TP orders (falls back to polling)
            with self.grid_monitor.sltp_lock:
                self.grid_monitor._place_sltp_orders(side, entry_price)

            self.monitoring = True
            self.bot_running = True
            self.grid_monitor.monitoring = True
            self.grid_monitor.bot_running = True

            grid_thread = threading.Thread(
                target=self.monitor_grid_orders,
                args=(
                    side,
                    entry_price,
                    favor_levels,
                    against_levels,
                    favor_level_qty,
                    against_level_qty,
                ),
                name=f"GridMonitor-Restore-{self.symbol}",
            )
            grid_thread.daemon = True
            grid_thread.start()
            self.grid_monitor.monitoring_threads.append(grid_thread)

            sltp_thread = threading.Thread(
                target=self.monitor_lossProfit, args=(side,), name=f"SLTP-Restore-{self.symbol}"
            )
            sltp_thread.daemon = True
            sltp_thread.start()
            self.grid_monitor.monitoring_threads.append(sltp_thread)

            logger.info(f"Restore mode: monitoring threads started for {self.symbol}")

        except Exception as e:
            logger.error(
                f"Failed to start restore monitoring for {self.symbol}: {type(e).__name__}: {e}"
            )
            logger.debug("Full traceback", exc_info=True)
            self.bot_running = False

    def get_status(self) -> Dict[str, Any]:
        return {
            "bot_name": self.bot_name,
            "symbol": self.symbol,
            "exchange": self.config.get("exchange_name", ""),
            "is_running": self.grid_monitor.monitoring,
            "bot_running": self.grid_monitor.bot_running,
            "current_side": self.current_side,
            "current_price": self.current_price,
            "count": self.count,
            "reason": self.reason,
            "percentage_pnl": self.grid_monitor.Percentage,
            "unrealized_pnl": self.grid_monitor.Unrealized_Pnl,
            "signals_generated": self.signals_generated,
            "orders_executed": self.orders_executed,
            "favor_levels": list(self.grid_monitor.favor_lvl),
            "against_levels": list(self.grid_monitor.against_lvl),
            "indicators": {
                "EMA": self.EMA,
                "RSI": self.RSI,
                "PrevRSI": self.PrevRSI,
                "BB": self.BB,
                "RSI_color": self.RSI_color,
            },
        }

    def __str__(self) -> str:
        return f"BotEngine({self.bot_name})"

    def __repr__(self) -> str:
        return f"BotEngine(name={self.bot_name}, symbol={self.symbol})"
