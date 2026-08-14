"""
MEXC Exchange Adapter

PURE PYTHON - NO DJANGO IMPORTS
"""

from typing import Any, Dict, Optional

import ccxt

from .base_adapter import BaseAdapter


class MEXCAdapter(BaseAdapter):
    """
    Adapter for MEXC exchange.

    Handles MEXC-specific configurations.
    """

    @property
    def exchange_name(self) -> str:
        return "mexc"

    def _initialize_exchange(self) -> ccxt.Exchange:
        """Initialize MEXC CCXT instance."""
        config = {
            "apiKey": self.credentials.get("api_key"),
            "secret": self.credentials.get("secret_key"),
            "enableRateLimit": True,
            "options": {
                "defaultType": "spot",
            },
        }

        exchange = ccxt.mexc(config)

        if self.demo_mode:
            self._enable_demo_mode(exchange)

        try:
            exchange.load_markets()
        except Exception:
            pass

        return exchange

    def format_symbol(self, symbol: str) -> str:
        return symbol

    def set_market_type(self, market_type: str = "spot"):
        """Set the market type."""
        self.exchange.options["defaultType"] = market_type

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

        order_params = {
            "stopPrice": stop_price,
            "type": "STOP_LOSS",
        }
        if params:
            order_params.update(params)

        order = self._make_request(
            "create_order", formatted_symbol, "STOP_LOSS", side.lower(), amount, None, order_params
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

        order_params = {
            "stopPrice": take_profit_price,
            "type": "TAKE_PROFIT",
        }
        if params:
            order_params.update(params)

        order = self._make_request(
            "create_order",
            formatted_symbol,
            "TAKE_PROFIT",
            side.lower(),
            amount,
            None,
            order_params,
        )
        return self._normalize_order(order)

    def get_wallet_balance(self, account_type: str = "SPOT") -> Dict[str, Any]:
        params = {"accountType": account_type} if account_type else {}
        balance = self._make_request("fetch_balance", params)
        return {
            "total": balance.get("total", {}),
            "free": balance.get("free", {}),
            "used": balance.get("used", {}),
        }

    def get_funding_rate(self, symbol: str) -> Dict[str, Any]:
        formatted_symbol = self.format_symbol(symbol)
        try:
            funding = self._make_request("fetch_funding_rate", formatted_symbol)
            return {
                "symbol": symbol,
                "funding_rate": float(funding.get("fundingRate", 0)),
                "funding_timestamp": funding.get("fundingTimestamp"),
                "next_funding_timestamp": funding.get("nextFundingTimestamp"),
            }
        except Exception:
            return {
                "symbol": symbol,
                "funding_rate": 0,
                "funding_timestamp": None,
            }
