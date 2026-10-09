"""
Bot Order Service — stateless order execution and persistence.

Extracted from BotEngine to decouple order operations from strategy
evaluation and monitoring.  Used by both BotEngine (orchestration) and
GridPositionMonitor (callbacks via BotEngine wrappers).

Phase 3 replaces BotEngine wrappers with direct BotOrderService references.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger("trading.engines")

# Exchange response keys that carry the executed price, most authoritative first.
# (CCXT unifies to `price`/`average`; adapters/exchanges add their own extras.)
_FILL_PRICE_KEYS = (
    "average",  # CCXT unified avg fill price
    "fillPrice",
    "avgPrice",
    "price",  # CCXT unified order price
    "entryPrice",
)

# bot_type -> (model import path, BotOrder FK field).  ``quantum_ai`` is
# deliberately absent: BotOrder.quantum_ai_investment points at
# InvestorPortfolio, NOT QuantumAIBot, so wiring it by pk would corrupt rows.
_BOT_FK_MAP = {
    "grid": ("apps.bots.models", "GridBot", "grid_bot"),
    "martingale": ("apps.bots.models", "MartingaleBot", "martingale_bot"),
    "signal": ("apps.bots.models", "SignalBot", "signal_bot"),
}


def _extract_fill_price(details: Any) -> Optional[float]:
    """Return the executed price from an exchange order response, or None.

    Phase 1 fix: ``bot_config["current_price"]`` is never written anywhere in
    the engine (it is a read-only *engine* attribute), so Price used to be
    persisted as 0 for every order.  The exchange response is the truth.
    """
    if not isinstance(details, dict):
        return None
    for key in _FILL_PRICE_KEYS:
        raw = details.get(key)
        if raw in (None, ""):
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return None


def _resolve_price(explicit: Optional[float], details: Any, bot_config: dict) -> float:
    """explicit arg -> exchange fill price -> bot_config fallback -> 0."""
    for candidate in (explicit, _extract_fill_price(details)):
        if candidate in (None, ""):
            continue
        try:
            value = float(candidate)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    try:
        return float(bot_config.get("current_price") or 0)
    except (TypeError, ValueError):
        return 0.0


class BotOrderService:
    """
    Stateless order execution + DB persistence.

    Each method receives the bare minimum context it needs (adapter, symbol,
    config) rather than holding references — but for convenience the common
    triad (adapter, symbol, config) is stored at init time and used as the
    primary exchange/adapter target.

    In Phase 3 BotEngine's ``create_order``, ``close_open_order``,
    ``close_all_orders``, ``save_order``, and ``qty`` become one-line
    wrappers here; GridPositionMonitor receives *these* methods directly.
    """

    def __init__(self, adapter, symbol: str, pair_config: dict, bot_config: dict):
        self.adapter = adapter
        self.symbol = symbol
        self.pair_config = pair_config
        self.bot_config = bot_config

    # =========================================================================
    # CREATE ORDER
    # =========================================================================

    def create_order(
        self, order_type: str, side: str, quantity: float, price: Optional[float] = None
    ) -> Optional[dict]:
        try:
            if self.pair_config.get("Amount_Type") == "dollar":
                if order_type == "market":
                    data = self.adapter.create_market_order_with_cost(self.symbol, side, quantity)
                elif order_type == "limit":
                    data = self.adapter.create_limit_order(self.symbol, side, quantity, price)
                else:
                    data = self.adapter.create_market_order_with_cost(self.symbol, side, quantity)
            else:
                if order_type == "market":
                    data = self.adapter.create_market_order(self.symbol, side, quantity)
                elif order_type == "limit":
                    data = self.adapter.create_limit_order(self.symbol, side, quantity, price)
                else:
                    data = self.adapter.create_market_order(self.symbol, side, quantity)
            logger.info(
                f"Order type: {order_type} - Side: {side} - "
                f"Quantity: {quantity} - Price: {price}"
            )
            return data
        except Exception as e:
            logger.error(f"Cannot create order: {e}")
            return None

    # =========================================================================
    # CLOSE POSITION  (exchange only — no DB persistence)
    # =========================================================================

    def close_position(self, symbol: str) -> Optional[dict]:
        """
        Fetch the current position on *symbol* and close it with a
        market reduce-only order.

        Returns the exchange order response dict, or ``None`` when there is
        no open position or the close failed.
        """
        try:
            adapter = self.adapter
            position = adapter.fetch_position(symbol)
            if not position or float(position.get("contracts", 0)) == 0:
                logger.info(f"No position found on {symbol}")
                return None

            size = float(position["contracts"])
            side = position.get("side", "")

            pnl = float(position.get("unrealized_pnl", 0))
            percentage = 0.0
            if self.pair_config.get("SLTP_Type") == "percentage":
                percentage = pnl / size * 1000

            if side == "short":
                detail = adapter.create_market_order(symbol, "buy", size, {"reduceOnly": True})
                logger.info("Short Order Closed")
                return {"detail": detail, "pnl": pnl, "percentage": percentage, "side": side}

            elif side == "long":
                detail = adapter.create_market_order(symbol, "sell", size, {"reduceOnly": True})
                logger.info("Long Order Closed")
                return {"detail": detail, "pnl": pnl, "percentage": percentage, "side": side}

            else:
                logger.info(f"No recognized side: {side}")
                return None

        except Exception as e:
            logger.error(f"No position found: {e}")
            return None

    # =========================================================================
    # CANCEL ALL ORDERS
    # =========================================================================

    def cancel_all_orders(self, symbol: str):
        try:
            self.adapter.cancel_all_orders(symbol)
        except Exception as e:
            logger.warning(f"Cancel all orders failed for {symbol}: {e}")

    # =========================================================================
    # SAVE ORDER  (DB persistence)
    # =========================================================================

    def _link_bot_fk(self, order_kwargs: dict) -> None:
        """Populate the polymorphic BotOrder FK for this bot (Phase 1).

        Additive: only writes when the bot_type is mappable and the row
        resolves.  ``quantum_ai`` is intentionally not mapped — see
        ``_BOT_FK_MAP``.  Any failure is logged and swallowed so the order
        row is still persisted (with ``bot_id``/``bot_type`` as fallback).
        """
        bot_type = order_kwargs.get("bot_type")
        bot_id = order_kwargs.get("bot_id")
        if not bot_type or not bot_id:
            return
        mapping = _BOT_FK_MAP.get(bot_type)
        if not mapping:
            return
        try:
            module_name, model_name, field_name = mapping
            import importlib

            model = getattr(importlib.import_module(module_name), model_name)
            instance = model.objects.filter(id=bot_id).first()
            if instance is not None:
                order_kwargs[field_name] = instance
        except Exception as exc:  # noqa: BLE001 — linkage must never lose a trade
            logger.warning(f"Could not link BotOrder to {bot_type} {bot_id}: {exc}")

    def save_order(
        self,
        side: str,
        description: str,
        details: Any = None,
        indicators: Optional[dict] = None,
        *,
        # Phase 1 (persistence): all additive/optional — existing callers and
        # tests keep working unchanged.
        price: Optional[float] = None,
        reason: Optional[str] = None,
        status: Optional[str] = None,
        pnl: Optional[float] = None,
    ) -> Any:
        from django.utils import timezone

        try:
            from apps.bots.models import BotOrder, Indicator

            user_id = self.bot_config.get("user_id")
            bot_name = self.bot_config.get("bot_name", "unnamed")
            # Phase 1: never trust the unset bot_config["current_price"] first —
            # resolve the real fill price (explicit -> exchange -> fallback -> 0).
            current_price = _resolve_price(price, details, self.bot_config)

            order_kwargs = {
                "Pair": self.symbol,
                "Side": side,
                "Category": "futures",
                "Order_type": "Market",
                "Quantity": self.pair_config.get("quantity", 0),
                "Price": current_price,
                "Exchange": self.bot_config.get("exchange_name", "Bybit"),
                "Description": f"[{bot_name}] {description}",
                "Details": details if isinstance(details, dict) else {"raw": str(details)},
                # Phase 1: trade-record integrity (additive columns, 0017)
                "bot_type": self.bot_config.get("bot_type") or None,
                "bot_id": str(self.bot_config.get("bot_id") or "") or None,
                "Reason": reason,
                "Status": status or "closed",
                "Realized_PnL": pnl,
            }

            # Best-effort polymorphic FK wiring (grid/martingale/signal only).
            # Never let linkage failure lose the trade record itself.
            self._link_bot_fk(order_kwargs)

            if user_id:
                from django.contrib.auth import get_user_model

                User = get_user_model()
                user = User.objects.get(id=user_id)
                order_kwargs["user"] = user

                if indicators:
                    indicator = Indicator.objects.create(
                        Pair=self.symbol,
                        user=user,
                        EMA=indicators.get("EMA", 0.0),
                        RSI=indicators.get("RSI", 0.0),
                        Prev_RSI=indicators.get("PrevRSI", 0.0),
                        Color=indicators.get("RSI_color", ""),
                        Prev_Color=indicators.get("RSI_prev_color", ""),
                        BB=indicators.get("BB", ""),
                        TSI=indicators.get("TSI"),
                        ADX=indicators.get("ADX"),
                    )
                    order_kwargs["Indicators"] = indicator

            order = BotOrder.objects.create(**order_kwargs)
            logger.info(f"Placed order: {order}")

            # Send Telegram notification if configured
            if user_id:
                try:
                    if (
                        hasattr(user, "telegram_token")
                        and user.telegram_token
                        and hasattr(user, "telegram_chat_id")
                        and user.telegram_chat_id
                    ):
                        trade_data = {
                            "symbol": self.symbol,
                            "side": side,
                            "amount": str(self.pair_config.get("quantity", 0)),
                            "price": str(current_price),
                            "exchange": self.bot_config.get("exchange_name", "Bybit"),
                            "timestamp": timezone.now().isoformat(),
                        }
                        from core.telegram_service import TelegramService

                        TelegramService.send_trade_alert(user, trade_data)
                except Exception as e:
                    logger.warning(f"Failed to send Telegram notification: {e}")

            return order

        except Exception as e:
            logger.exception(f"Failed to save order: {e}")
            return None

    # =========================================================================
    # QUANTITY HELPER
    # =========================================================================

    def qty(self, current_price: float):
        if self.pair_config.get("Amount_Type") == "dollar":
            quantity = round(self.pair_config["quantity"] / current_price, 4)
            favor_level_qty = round(self.pair_config["favor_level_qty"] / current_price, 4)
            against_level_qty = round(self.pair_config["against_level_qty"] / current_price, 4)
            logger.info(
                f"dollar calculated: {quantity}, " f"{favor_level_qty}, {against_level_qty}"
            )
            return quantity, favor_level_qty, against_level_qty
        else:
            quantity = self.pair_config["quantity"]
            favor_level_qty = self.pair_config["favor_level_qty"]
            against_level_qty = self.pair_config["against_level_qty"]
            logger.info(f"coin calculated: {quantity}, " f"{favor_level_qty}, {against_level_qty}")
            return quantity, favor_level_qty, against_level_qty
