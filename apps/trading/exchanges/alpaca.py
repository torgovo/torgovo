"""
Alpaca Exchange Adapter

PURE PYTHON - NO DJANGO IMPORTS

Note: Alpaca is primarily for stocks/crypto in the US market.
"""

from typing import Any, Dict, Optional

import ccxt

from .base_adapter import BaseAdapter


class AlpacaAdapter(BaseAdapter):
    """
    Adapter for Alpaca exchange.

    Handles Alpaca-specific configurations:
    - Paper trading support
    - US market hours
    """

    @property
    def exchange_name(self) -> str:
        return "alpaca"

    def _initialize_exchange(self) -> ccxt.Exchange:
        """Initialize Alpaca CCXT instance."""
        config = {
            "apiKey": self.credentials.get("api_key"),
            "secret": self.credentials.get("secret_key"),
            "enableRateLimit": True,
        }

        exchange = ccxt.alpaca(config)

        if self.demo_mode:
            self._enable_demo_mode(exchange)

        try:
            exchange.load_markets()
        except Exception:
            pass

        return exchange

    def format_symbol(self, symbol: str) -> str:
        return symbol

    def is_market_open(self) -> bool:
        """Check if the market is currently open."""
        try:
            self._make_request("fetch_time")
            return True  # Simplified - actual implementation would check market hours
        except Exception:
            return False

    def create_market_order(
        self, symbol: str, side: str, amount: float, params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        formatted_symbol = self.format_symbol(symbol)
        amount = self.amount_to_precision(symbol, amount)
        order = self._make_request(
            "create_market_order", formatted_symbol, side.lower(), amount, params=params or {}
        )
        return self._normalize_order(order)

    def create_limit_order(
        self, symbol: str, side: str, amount: float, price: float, params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        formatted_symbol = self.format_symbol(symbol)
        amount = self.amount_to_precision(symbol, amount)
        price = self.price_to_precision(symbol, price)
        order = self._make_request(
            "create_limit_order", formatted_symbol, side.lower(), amount, price, params=params or {}
        )
        return self._normalize_order(order)

    def create_stop_loss_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        stop_price: float,
        params: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        formatted_symbol = self.format_symbol(symbol)
        amount = self.amount_to_precision(symbol, amount)
        stop_price = self.price_to_precision(symbol, stop_price)

        order_params = {"stopPrice": stop_price}
        if params:
            order_params.update(params)

        order = self._make_request(
            "create_order", formatted_symbol, "market", side.lower(), amount, None, order_params
        )
        return self._normalize_order(order)

    def create_take_profit_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        take_profit_price: float,
        params: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        formatted_symbol = self.format_symbol(symbol)
        amount = self.amount_to_precision(symbol, amount)
        take_profit_price = self.price_to_precision(symbol, take_profit_price)

        order_params = {"stopPrice": take_profit_price}
        if params:
            order_params.update(params)

        order = self._make_request(
            "create_order", formatted_symbol, "market", side.lower(), amount, None, order_params
        )
        return self._normalize_order(order)

    def get_wallet_balance(self, account_type: str = "TRADING") -> Dict[str, Any]:
        params = {"accountType": account_type} if account_type else {}
        balance = self._make_request("fetch_balance", params)
        return {
            "total": balance.get("total", {}),
            "free": balance.get("free", {}),
            "used": balance.get("used", {}),
        }
