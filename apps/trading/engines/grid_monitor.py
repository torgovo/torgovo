"""
Grid Position Monitor — delegated thread lifecycle for BotEngine.

Extracted from BotEngine to separate position-monitoring concerns
from strategy evaluation and orchestration.

Replaced by BotOrderService in Phase 2 for order execution callbacks.
"""

import logging
import threading
import time
from typing import Callable, List, Optional

from django.db import close_old_connections
from django.utils import timezone

logger = logging.getLogger("trading.engines")


class GridPositionMonitor:
    """
    Owns all position-monitoring thread lifecycle.

    Runs two background threads per position:
      1. Grid monitor — watches limit-order fills, replaces filled levels
      2. SL/TP monitor — polls unrealised P&L, triggers close on threshold hit

    Order-execution callbacks are injected so this class stays decoupled from
    Django model logic and can later receive a BotOrderService.
    """

    def __init__(
        self,
        adapter,
        symbol: str,
        pair_config: dict,
        bot_config: dict,
        *,
        create_order_cb: Callable,
        close_all_orders_cb: Callable,
    ):
        self.adapter = adapter
        self.symbol = symbol
        self.pair_config = pair_config
        self.bot_config = bot_config
        self.bot_name = bot_config.get("bot_name", "unnamed")

        self._create_order_cb = create_order_cb
        self._close_all_orders_cb = close_all_orders_cb

        self.monitoring = False
        self.bot_running = False
        self._stop_event = threading.Event()
        self.monitoring_threads: List[threading.Thread] = []
        self.lock = threading.Lock()
        self.sltp_lock = threading.Lock()

        self.current_price = 0.0
        self.current_side = "None"
        self.count = 0
        self.reason = ""
        self.PrevReason = ""

        self.favor_lvl: List[float] = []
        self.against_lvl: List[float] = []

        self.Percentage = 0.0
        self.Unrealized_Pnl = 0.0
        self.last_trade_pnl = 0.0

        self._heartbeat_counter = 0
        self._heartbeat_interval = 60

        self._last_sl: Optional[float] = None
        self._last_tp: Optional[float] = None

    # =========================================================================
    # LIFECYCLE
    # =========================================================================

    def start_monitoring(
        self, side, entry_price, favor_levels, against_levels, favor_level_qty, against_level_qty
    ):
        """Start both grid-monitor and SL/TP-monitor threads."""
        time.sleep(3)
        self.monitoring = True
        grid_thread = threading.Thread(
            target=self._monitor_grid_orders,
            args=(
                side,
                entry_price,
                favor_levels,
                against_levels,
                favor_level_qty,
                against_level_qty,
            ),
            name=f"GridMonitor-{self.symbol}-{side}",
        )
        grid_thread.daemon = True
        grid_thread.start()
        self.monitoring_threads.append(grid_thread)

        sltp_thread = threading.Thread(
            target=self._monitor_loss_profit, args=(side,), name=f"SLTP-{self.symbol}-{side}"
        )
        sltp_thread.daemon = True
        sltp_thread.start()
        self.monitoring_threads.append(sltp_thread)

    def start_restore_monitoring(
        self, side, entry_price, favor_levels, against_levels, favor_level_qty, against_level_qty
    ):
        """Start monitoring threads for an existing position (restore mode)."""
        time.sleep(1)
        self.monitoring = True
        self.bot_running = True

        grid_thread = threading.Thread(
            target=self._monitor_grid_orders,
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
        self.monitoring_threads.append(grid_thread)

        sltp_thread = threading.Thread(
            target=self._monitor_loss_profit, args=(side,), name=f"SLTP-Restore-{self.symbol}"
        )
        sltp_thread.daemon = True
        sltp_thread.start()
        self.monitoring_threads.append(sltp_thread)

    def stop_all(self):
        """Signal stop and join all monitoring threads."""
        self.monitoring = False
        self._stop_event.set()
        for thread in self.monitoring_threads:
            if thread.is_alive():
                thread.join(timeout=5.0)
                if thread.is_alive():
                    logger.warning(f"Thread {thread.name} did not stop gracefully")
        self.monitoring_threads.clear()
        self.bot_running = False

    # =========================================================================
    # HEARTBEAT
    # =========================================================================

    def _update_heartbeat(self):
        bot_id = self.bot_config.get("bot_id")
        bot_type = self.bot_config.get("bot_type", "grid")
        if not bot_id:
            return
        try:
            if bot_type == "quantum_ai":
                from apps.bots.models import QuantumAIBot

                QuantumAIBot.objects.filter(id=bot_id).update(last_heartbeat=timezone.now())
            elif bot_type == "grid":
                from apps.bots.models import GridBot

                GridBot.objects.filter(id=bot_id).update(last_heartbeat=timezone.now())
            elif bot_type == "martingale":
                from apps.bots.models import MartingaleBot

                MartingaleBot.objects.filter(id=bot_id).update(last_heartbeat=timezone.now())
        except Exception as e:
            logger.warning(f"Heartbeat update failed for {bot_id}: {e}")

    # =========================================================================
    # FETCH PRICE
    # =========================================================================

    def fetch_current_price(self):
        self.current_price = self.adapter.get_current_price(self.symbol)
        thread_id = threading.get_ident()
        logger.info(f"Thread ID: {thread_id} | " f"Fetched current price: {self.current_price}")
        return self.current_price

    # =========================================================================
    # MONITOR GRID ORDERS  (from oldbybit.py — exact copy)
    # =========================================================================

    def _monitor_grid_orders(
        self, side, entry_price, favor_levels, against_levels, favor_level_qty, against_level_qty
    ):
        last_favor_level = None
        last_against_level = None
        logger.info("Monitoring Grid Orders.")
        self.current_price = self.fetch_current_price()
        logger.info(
            f"{self.symbol} Current price: {self.current_price}  "
            f"CurrentSide: {side} on KEYPAIR {self.symbol}, "
            f"owner={self.bot_name}"
        )

        favor_order_map = {}
        against_order_map = {}

        def place_and_register(price, ord_side, qty, register_map):
            try:
                resp = self._create_order_cb("limit", ord_side, qty, float(price))
                logger.info(f"order response: {resp}")
                order_id = resp.get("id") if isinstance(resp, dict) else getattr(resp, "id", None)
                if order_id is None:
                    order_id = resp.get("orderId") if isinstance(resp, dict) else None
                if order_id is None:
                    open_orders = self.adapter.fetch_open_orders(self.symbol)
                    logger.info("fetched open orders")
                    for o in open_orders:
                        if (
                            float(o.get("price", 0)) == float(price)
                            and o.get("side", "").lower() == ord_side.lower()
                        ):
                            order_id = o.get("id") or o.get("orderId") or o.get("clientOrderId")
                            break
                if order_id:
                    register_map[float(price)] = order_id
                else:
                    logger.warning(
                        f"Placed order but no id found for price {price} " f"side {ord_side}."
                    )
                return order_id
            except Exception as e:
                logger.error(f"Error placing order at {price} side {ord_side}: {e}")
                return None

        try:
            open_orders = self.adapter.fetch_open_orders(self.symbol)
            for o in open_orders:
                try:
                    p = round(float(o.get("price")), 8)
                except (TypeError, ValueError):
                    continue
                s = o.get("side", "").lower()
                oid = o.get("id") or o.get("orderId") or o.get("clientOrderId")
                if s == "sell":
                    if side.lower() == "buy":
                        favor_order_map[p] = oid
                    else:
                        against_order_map[p] = oid
                elif s == "buy":
                    if side.lower() == "buy":
                        against_order_map[p] = oid
                    else:
                        favor_order_map[p] = oid
        except Exception as e:
            logger.warning(f"Could not seed open orders into maps: {e}")

        for p in favor_order_map.keys():
            if p not in favor_levels:
                favor_levels.append(p)
        for p in against_order_map.keys():
            if p not in against_levels:
                against_levels.append(p)

        reverse_for_favor = side.lower() == "sell"
        reverse_for_against = side.lower() == "buy"
        favor_levels.sort(reverse=reverse_for_favor)
        against_levels.sort(reverse=reverse_for_against)

        self._heartbeat_counter = 0
        while self.monitoring:
            try:
                close_old_connections()
                self._heartbeat_counter += 1
                if self._heartbeat_counter % self._heartbeat_interval == 0:
                    self._update_heartbeat()

                open_orders = self.adapter.fetch_open_orders(self.symbol)
                current_buy_prices = set(
                    float(order["price"]) for order in open_orders if order["side"].lower() == "buy"
                )
                current_sell_prices = set(
                    float(order["price"])
                    for order in open_orders
                    if order["side"].lower() == "sell"
                )

                def is_filled(order_id):
                    if not order_id:
                        return False
                    try:
                        o = self.adapter.fetch_order(order_id, self.symbol)
                        logger.info(f"fetch order in is_filled function: {o}")
                        status = o.get("status") or o.get("state")
                        if isinstance(status, str) and status.lower() in (
                            "closed",
                            "filled",
                            "filled_partially",
                        ):
                            return True
                        return False
                    except Exception:
                        logger.debug(
                            "fetch_order failed for %s, " "searching open orders as fallback",
                            order_id,
                        )
                        try:
                            for o2 in open_orders:
                                if (
                                    o2.get("id") == order_id
                                    or o2.get("orderId") == order_id
                                    or o2.get("clientOrderId") == order_id
                                ):
                                    return False
                            return True
                        except Exception:
                            logger.debug("Fallback order lookup failed for %s", order_id)
                            return False

                favor_keys = sorted(list(favor_order_map.keys()), reverse=reverse_for_favor)
                for price in favor_keys:
                    order_id = favor_order_map.get(price)
                    if is_filled(order_id):
                        executed_level = float(price)
                        logger.info(f"Favor order filled at {executed_level} " f"id={order_id}")
                        favor_order_map.pop(price, None)
                        try:
                            if price in [float(x) for x in favor_levels]:
                                for i, v in enumerate(favor_levels):
                                    if float(v) == price:
                                        favor_levels.pop(i)
                                        break
                        except (ValueError, IndexError):
                            pass

                        if last_favor_level is not None and executed_level >= float(
                            last_favor_level
                        ):
                            if (
                                entry_price not in favor_levels
                                and entry_price not in against_levels
                            ):
                                place_price = float(entry_price)
                                ord_side = "buy" if side.lower() == "buy" else "sell"
                                if ord_side == "buy":
                                    if float(place_price) in current_buy_prices:
                                        continue
                                else:
                                    if float(place_price) in current_sell_prices:
                                        continue
                                new_oid = place_and_register(
                                    place_price, ord_side, against_level_qty, against_order_map
                                )
                                side_label = "Buy @" if side.lower() == "buy" else "Sell @"
                                logger.info(f"{side_label} {place_price}")
                                if new_oid:
                                    against_levels.append(place_price)
                                    against_levels.sort(reverse=reverse_for_against)
                                    self.against_lvl = against_levels[:]
                                    open_orders = self.adapter.fetch_open_orders(self.symbol)
                                    current_buy_prices = set(
                                        float(order["price"])
                                        for order in open_orders
                                        if order["side"].lower() == "buy"
                                    )
                                    current_sell_prices = set(
                                        float(order["price"])
                                        for order in open_orders
                                        if order["side"].lower() == "sell"
                                    )
                            last_favor_level = executed_level
                            entry_price = executed_level
                        else:
                            if (
                                entry_price not in favor_levels
                                and entry_price not in against_levels
                            ):
                                place_price = float(entry_price)
                                ord_side = "buy" if side.lower() == "buy" else "sell"
                                if ord_side == "buy":
                                    if float(place_price) in current_buy_prices:
                                        continue
                                else:
                                    if float(place_price) in current_sell_prices:
                                        continue
                                new_oid = place_and_register(
                                    place_price, ord_side, against_level_qty, against_order_map
                                )
                                side_label = "Buy @" if side.lower() == "buy" else "Sell @"
                                logger.info(f"{side_label} {place_price}")
                                if new_oid:
                                    against_levels.append(place_price)
                                    against_levels.sort(reverse=reverse_for_against)
                                    self.against_lvl = against_levels[:]
                                    open_orders = self.adapter.fetch_open_orders(self.symbol)
                                    current_buy_prices = set(
                                        float(order["price"])
                                        for order in open_orders
                                        if order["side"].lower() == "buy"
                                    )
                                    current_sell_prices = set(
                                        float(order["price"])
                                        for order in open_orders
                                        if order["side"].lower() == "sell"
                                    )
                            last_favor_level = executed_level
                            entry_price = executed_level
                        favor_levels.sort(reverse=reverse_for_favor)
                        self.favor_lvl = favor_levels[:]

                against_keys = sorted(list(against_order_map.keys()), reverse=reverse_for_against)
                for price in against_keys:
                    order_id = against_order_map.get(price)
                    if is_filled(order_id):
                        executed_level = float(price)
                        logger.info(f"Against order filled at {executed_level} " f"id={order_id}")
                        against_order_map.pop(price, None)
                        try:
                            if price in [float(x) for x in against_levels]:
                                for i, v in enumerate(against_levels):
                                    if float(v) == price:
                                        against_levels.pop(i)
                                        break
                        except (ValueError, IndexError):
                            pass

                        if last_against_level is not None and executed_level <= float(
                            last_against_level
                        ):
                            if (
                                entry_price not in favor_levels
                                and entry_price not in against_levels
                            ):
                                place_price = float(entry_price)
                                ord_side = "sell" if side.lower() == "buy" else "buy"
                                if ord_side == "buy":
                                    if float(place_price) in current_buy_prices:
                                        continue
                                else:
                                    if float(place_price) in current_sell_prices:
                                        continue
                                new_oid = place_and_register(
                                    place_price, ord_side, favor_level_qty, favor_order_map
                                )
                                side_label2 = "Sell @" if side.lower() == "buy" else "Buy @"
                                logger.info(f"{side_label2} {place_price}")
                                if new_oid:
                                    favor_levels.append(place_price)
                                    favor_levels.sort(reverse=reverse_for_favor)
                                    self.favor_lvl = favor_levels[:]
                                    open_orders = self.adapter.fetch_open_orders(self.symbol)
                                    current_buy_prices = set(
                                        float(order["price"])
                                        for order in open_orders
                                        if order["side"].lower() == "buy"
                                    )
                                    current_sell_prices = set(
                                        float(order["price"])
                                        for order in open_orders
                                        if order["side"].lower() == "sell"
                                    )
                            last_against_level = executed_level
                            entry_price = executed_level
                        else:
                            if (
                                entry_price not in favor_levels
                                and entry_price not in against_levels
                            ):
                                place_price = float(entry_price)
                                ord_side = "sell" if side.lower() == "buy" else "buy"
                                if ord_side == "buy":
                                    if float(place_price) in current_buy_prices:
                                        continue
                                else:
                                    if float(place_price) in current_sell_prices:
                                        continue
                                new_oid = place_and_register(
                                    place_price, ord_side, favor_level_qty, favor_order_map
                                )
                                side_label2 = "Sell @" if side.lower() == "buy" else "Buy @"
                                logger.info(f"{side_label2} {place_price}")
                                if new_oid:
                                    favor_levels.append(place_price)
                                    favor_levels.sort(reverse=reverse_for_favor)
                                    self.favor_lvl = favor_levels[:]
                                    open_orders = self.adapter.fetch_open_orders(self.symbol)
                                    current_buy_prices = set(
                                        float(order["price"])
                                        for order in open_orders
                                        if order["side"].lower() == "buy"
                                    )
                                    current_sell_prices = set(
                                        float(order["price"])
                                        for order in open_orders
                                        if order["side"].lower() == "sell"
                                    )
                            last_against_level = executed_level
                            entry_price = executed_level
                        against_levels.sort(reverse=reverse_for_against)
                        self.against_lvl = against_levels[:]

                time.sleep(1)

            except Exception as e:
                logger.exception(f"Error in monitor_grid_orders: {e}")
                time.sleep(2)

    # =========================================================================
    # MONITOR LOSS / PROFIT  (from oldbybit.py — exact copy)
    # =========================================================================

    def _monitor_loss_profit(self, side):
        loss_profit_percentage = 0.0
        time.sleep(4)
        self._heartbeat_counter = 0

        while self.monitoring and not self._stop_event.is_set():
            try:
                self._heartbeat_counter += 1
                if self._heartbeat_counter % 12 == 0:
                    self._update_heartbeat()
                if self._heartbeat_counter % 4 == 0:
                    self._refresh_sltp_if_changed()
                loss_profit_percentage = self._check_loss_profit_percent()
                if loss_profit_percentage is None:
                    loss_profit_percentage = 0.0

                elif (
                    self.pair_config.get("SL_Exit") == "sl"
                    or self.pair_config.get("SL_Exit") == "both"
                ):
                    if loss_profit_percentage <= self.pair_config.get("Stop_Loss", -999):
                        logger.info(f"SL HIT! Value: {loss_profit_percentage}")
                        self._close_all_orders_cb("SL hit Position and closed")

                if (
                    self.pair_config.get("SL_Exit") == "tp"
                    or self.pair_config.get("SL_Exit") == "both"
                ):
                    if loss_profit_percentage >= self.pair_config.get("Take_Profit", 999):
                        logger.info(f"TP HIT! Value: {loss_profit_percentage}")
                        self._close_all_orders_cb("TP hit Position and closed")

            except Exception as e:
                logger.exception(f"Loss Profit Exception: {str(e)}")

            if self._stop_event.wait(timeout=5.0):
                break

    # =========================================================================
    # CHECK LOSS / PROFIT PERCENT  (from oldbybit.py — exact copy)
    # =========================================================================

    def _check_loss_profit_percent(self):
        try:
            position = self.adapter.fetch_position(self.symbol)
            if position:
                size = float(position.get("notional", 0))
                pnl = float(position.get("unrealizedPnl", 0))
                if size == 0:
                    size = float(position.get("contracts", 0)) * self.current_price
                self.Unrealized_Pnl = pnl
                self.Percentage = pnl / size * 1000 if size != 0 else 0.0
            else:
                logger.info(f"No position found on {self.symbol} of bot: " f"{self.bot_name}")
        except Exception as e:
            logger.exception(f"Check Loss Profit Exception: {str(e)}")
            self.Unrealized_Pnl = 0.0
            self.Percentage = 0.0

        logger.info(
            f"Pair: {self.symbol}  Percentage: {self.Percentage}  "
            f"PNL: {self.Unrealized_Pnl}  Price: {self.current_price}"
        )

        if self.pair_config.get("SLTP_Type") == "percentage":
            return self.Percentage
        elif self.pair_config.get("SLTP_Type") == "dollars":
            return self.Unrealized_Pnl

    # =========================================================================
    # EXCHANGE-NATIVE SL/TP  (from oldbybit.py)
    # =========================================================================

    def _place_sltp_orders(self, side, entry_price):
        sl_val = self.pair_config.get("Stop_Loss", -999)
        tp_val = self.pair_config.get("Take_Profit", 999)

        is_long = side.lower() == "buy"

        try:
            position = self.adapter.fetch_position(self.symbol)
            size = (
                float(position["contracts"])
                if position and float(position.get("contracts", 0)) > 0
                else 0
            )
        except Exception:
            logger.debug(
                f"Could not fetch position for {self.symbol} "
                f"in SL/TP placement, using config size"
            )
            size = 0

        if size == 0:
            qty_config = self.pair_config
            if self.pair_config.get("Amount_Type") == "dollar":
                size = round(qty_config["quantity"] / entry_price, 4) if entry_price else 0
            else:
                size = qty_config.get("quantity", 0)
            size = float(self.adapter.amount_to_precision(self.symbol, size)) if size else 0

        if size <= 0:
            logger.info(f"SL/TP: no position size for {self.symbol}, skipping")
            return

        opposite_side = "sell" if is_long else "buy"

        if tp_val != 999:
            if is_long:
                tp_price = entry_price * (1 + tp_val / 1000)
            else:
                tp_price = entry_price * (1 - tp_val / 1000)
            try:
                tp_result = self.adapter.create_take_profit_order(
                    symbol=self.symbol,
                    side=opposite_side,
                    amount=size,
                    take_profit_price=tp_price,
                    params={"reduceOnly": True},
                )
                if tp_result.get("retCode") == 0:
                    logger.info(f"TP set @ ${tp_price:.4f}")
                    self._last_tp = tp_val
                else:
                    logger.warning(f"TP placement warn: " f"{tp_result.get('retMsg', '?')}")
            except NotImplementedError:
                logger.info("SL/TP: exchange has no native TP, " "using polling fallback")
            except Exception as e:
                logger.warning(f"TP placement failed (non-critical): {e}")

        if sl_val != -999:
            if is_long:
                sl_price = entry_price * (1 + sl_val / 1000)
            else:
                sl_price = entry_price * (1 - sl_val / 1000)
            try:
                sl_result = self.adapter.create_stop_loss_order(
                    symbol=self.symbol,
                    side=opposite_side,
                    amount=size,
                    stop_price=sl_price,
                    params={"reduceOnly": True},
                )
                if sl_result.get("retCode") == 0:
                    logger.info(f"SL set @ ${sl_price:.4f}")
                    self._last_sl = sl_val
                else:
                    logger.warning(f"SL placement warn: " f"{sl_result.get('retMsg', '?')}")
            except NotImplementedError:
                logger.info("SL/TP: exchange has no native SL, " "using polling fallback")
            except Exception as e:
                logger.warning(f"SL placement failed (non-critical): {e}")

    def _refresh_sltp_if_changed(self):
        bot_id = self.bot_config.get("bot_id")
        bot_type = self.bot_config.get("bot_type", "")
        if not bot_id or bot_type not in ("grid", "martingale"):
            return

        with self.sltp_lock:
            try:
                if bot_type == "grid":
                    from apps.bots.models import GridBot

                    bot = GridBot.objects.only("take_profit_percent", "stop_loss_percent").get(
                        id=bot_id
                    )
                else:
                    from apps.bots.models import MartingaleBot

                    bot = MartingaleBot.objects.only(
                        "take_profit_percent", "stop_loss_percent"
                    ).get(id=bot_id)

                db_tp = (
                    float(bot.take_profit_percent) if bot.take_profit_percent is not None else None
                )
                db_sl = float(bot.stop_loss_percent) if bot.stop_loss_percent is not None else None

                if db_tp == self._last_tp and db_sl == self._last_sl:
                    return

                logger.info(f"SL/TP config changed: re-applying SL={db_sl}, " f"TP={db_tp}")
                self.pair_config["Stop_Loss"] = db_sl
                self.pair_config["Take_Profit"] = db_tp

                side = None
                entry_price = self.current_price
                try:
                    position = self.adapter.fetch_position(self.symbol)
                    if position and float(position.get("contracts", 0)) > 0:
                        entry_price = float(position.get("entryPrice", self.current_price))
                        side = "buy" if position.get("side") == "long" else "sell"
                except Exception:
                    logger.debug(f"Could not fetch position for SL/TP refresh " f"on {self.symbol}")
                    pass

                if not side:
                    raw = self.current_side.lower()
                    if raw in ("buy", "sell"):
                        side = raw

                if side:
                    self._place_sltp_orders(side, entry_price)
            except Exception as e:
                logger.warning(f"Failed to refresh SL/TP: {e}")
