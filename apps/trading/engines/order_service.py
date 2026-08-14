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

    def save_order(
        self, side: str, description: str, details: Any = None, indicators: Optional[dict] = None
    ) -> Any:
        from django.utils import timezone

        try:
            from apps.bots.models import BotOrder, Indicator

            user_id = self.bot_config.get("user_id")
            bot_name = self.bot_config.get("bot_name", "unnamed")
            current_price = self.bot_config.get("current_price", 0)

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
            }

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
