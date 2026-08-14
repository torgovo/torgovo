"""
Webhook Alert Trading Strategy

Executes trades based on incoming webhook signals from external sources
like TradingView, custom scripts, or other trading platforms.

PURE PYTHON - NO DJANGO IMPORTS
"""

import logging
from typing import Any, Dict, List, Optional

from .base import BaseStrategy, Signal

logger = logging.getLogger("trading.strategies.webhook")


class WebhookAlertStrategy(BaseStrategy):
    """
    Webhook Alert Trading Strategy.

    Processes incoming webhook signals and converts them to trading signals.
    The webhook payload should contain action, symbol, and optionally amount/price.

    Parameters:
        - symbol: Default trading pair (can be overridden by webhook)
        - default_amount: Default position size if not specified in webhook
        - use_percentage: Use percentage of balance instead of fixed amount
        - percentage: Percentage of balance to use (default: 10)
        - require_secret: Require secret validation (default: True)
        - secret: Secret key for validation (required if require_secret is True)
    """

    @property
    def name(self) -> str:
        return "Webhook Alert"

    @property
    def required_parameters(self) -> List[str]:
        return ["symbol"]

    def __init__(self, parameters: Dict[str, Any] = None):
        defaults = {
            "default_amount": 0.01,
            "use_percentage": False,
            "percentage": 10,
            "require_secret": True,
            "stop_loss_percentage": 2,
            "take_profit_percentage": 5,
        }
        merged_params = {**defaults, **(parameters or {})}
        super().__init__(merged_params)

    def execute(
        self,
        market_data: Dict[str, Any],
        account_info: Dict[str, Any],
        current_position: Optional[Dict[str, Any]] = None,
    ) -> Optional[Signal]:
        """
        Execute webhook strategy.

        NOTE: This method is typically not called directly.
        Instead, process_webhook() is called when a webhook arrives.

        This implementation checks for pending webhooks in market_data.
        """
        webhook_data = market_data.get("webhook_signal")
        if not webhook_data:
            return None

        return self.process_webhook(webhook_data, market_data, account_info)

    def process_webhook(
        self,
        webhook_data: Dict[str, Any],
        market_data: Dict[str, Any],
        account_info: Dict[str, Any],
    ) -> Optional[Signal]:
        """
        Process an incoming webhook signal.

        Expected webhook_data format:
        {
            "action": "buy" | "sell" | "close",
            "symbol": "BTC/USDT",  # optional, uses default if not provided
            "amount": 0.01,  # optional
            "price": 50000,  # optional, for limit orders
            "type": "market" | "limit",  # optional, default: market
            "stop_loss": 48000,  # optional
            "take_profit": 52000,  # optional
            "secret": "your_secret",  # required if require_secret is True
            "comment": "TradingView signal"  # optional
        }

        Args:
            webhook_data: Incoming webhook payload
            market_data: Current market data
            account_info: Account balance info

        Returns:
            Signal if valid, None if invalid
        """
        # Validate secret if required
        if self.parameters.get("require_secret"):
            provided_secret = webhook_data.get("secret", "")
            expected_secret = self.parameters.get("secret", "")
            if provided_secret != expected_secret:
                logger.warning("Webhook rejected: Invalid secret")
                return None

        # Extract action (required)
        action = webhook_data.get("action", "").lower()
        if action not in ["buy", "sell", "close", "long", "short"]:
            logger.warning(f"Webhook rejected: Invalid action '{action}'")
            return None

        # Normalize action
        if action == "long":
            action = "buy"
        elif action == "short":
            action = "sell"

        # Get symbol
        symbol = webhook_data.get("symbol", self.parameters["symbol"])

        # Calculate amount
        amount = self._calculate_amount(webhook_data, market_data, account_info, symbol)
        if amount <= 0:
            logger.warning("Webhook rejected: Invalid amount")
            return None

        # Get optional parameters
        price = webhook_data.get("price")
        order_type = webhook_data.get("type", "market").lower()
        stop_loss = webhook_data.get("stop_loss")
        take_profit = webhook_data.get("take_profit")
        comment = webhook_data.get("comment", "Webhook signal")

        # Calculate SL/TP if not provided
        current_price = market_data.get("ticker", {}).get("last", price)
        if not stop_loss and current_price:
            side = "long" if action == "buy" else "short"
            stop_loss = self.calculate_stop_loss(current_price, side)
        if not take_profit and current_price:
            side = "long" if action == "buy" else "short"
            take_profit = self.calculate_take_profit(current_price, side)

        signal = Signal(
            action=action,
            symbol=symbol,
            amount=amount,
            price=float(price) if price else None,
            order_type=order_type,
            stop_loss=float(stop_loss) if stop_loss else None,
            take_profit=float(take_profit) if take_profit else None,
            reason=f"Webhook: {comment}",
            metadata={
                "source": "webhook",
                "raw_data": webhook_data,
            },
        )

        self.signals_generated += 1
        self.last_signal = signal

        logger.info(f"Webhook signal processed: {signal}")
        return signal

    def _calculate_amount(
        self,
        webhook_data: Dict[str, Any],
        market_data: Dict[str, Any],
        account_info: Dict[str, Any],
        symbol: str,
    ) -> float:
        """Calculate position size from webhook data or parameters."""
        # If amount specified in webhook, use it
        if "amount" in webhook_data:
            return float(webhook_data["amount"])

        # If using percentage of balance
        if self.parameters.get("use_percentage"):
            percentage = self.parameters.get("percentage", 10) / 100
            quote_currency = symbol.split("/")[-1] if "/" in symbol else "USDT"
            free_balance = account_info.get("balance", {}).get("free", {}).get(quote_currency, 0)
            current_price = market_data.get("ticker", {}).get("last", 1)

            if current_price > 0:
                return (float(free_balance) * percentage) / current_price

        # Default amount
        return self.parameters.get("default_amount", 0.01)

    def validate_webhook(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate webhook payload without executing.

        Returns:
            Dict with 'valid' boolean and 'errors' list
        """
        errors = []

        # Check secret
        if self.parameters.get("require_secret"):
            if webhook_data.get("secret") != self.parameters.get("secret"):
                errors.append("Invalid or missing secret")

        # Check action
        action = webhook_data.get("action", "").lower()
        if action not in ["buy", "sell", "close", "long", "short"]:
            errors.append(f"Invalid action: {action}")

        # Check symbol if provided
        symbol = webhook_data.get("symbol")
        if symbol and "/" not in symbol:
            errors.append(f"Invalid symbol format: {symbol}")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
        }

    def get_status(self) -> Dict[str, Any]:
        """Get webhook strategy status."""
        status = super().get_status()
        status.update(
            {
                "require_secret": self.parameters.get("require_secret", True),
                "use_percentage": self.parameters.get("use_percentage", False),
            }
        )
        return status
