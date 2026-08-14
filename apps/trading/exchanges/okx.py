"""
OKX Exchange Adapter

PURE PYTHON - NO DJANGO IMPORTS
"""

from typing import Any, Dict, Optional

import ccxt

from .base_adapter import BaseAdapter


class OKXAdapter(BaseAdapter):
    """
    Adapter for OKX exchange.

    Handles OKX-specific configurations:
    - Requires passphrase for authentication
    - Symbol formatting
    - Testnet configuration
    """

    @property
    def exchange_name(self) -> str:
        return "okx"

    def _initialize_exchange(self) -> ccxt.Exchange:
        """Initialize OKX CCXT instance."""
        config = {
            "apiKey": self.credentials.get("api_key"),
            "secret": self.credentials.get("secret_key"),
            "password": self.credentials.get("passphrase"),  # OKX requires passphrase
            "enableRateLimit": True,
            "options": {
                "defaultType": "spot",
            },
        }

        exchange = ccxt.okx(config)

        if self.demo_mode:
            self._enable_demo_mode(exchange)

        try:
            exchange.load_markets()
        except Exception:
            pass

        return exchange

    def set_market_type(self, market_type: str = "spot"):
        """
        Set the market type.

        Args:
            market_type: 'spot', 'swap', 'futures', 'option'
        """
        self.exchange.options["defaultType"] = market_type

    def format_symbol(self, symbol: str) -> str:
        """Format symbol for OKX perpetual swaps."""
        if self.exchange.options.get("defaultType") == "swap":
            if ":" not in symbol and "-SWAP" not in symbol:
                base_quote = symbol.split("/")
                if len(base_quote) == 2:
                    return f"{symbol}:{base_quote[1]}"
        return symbol

    def set_leverage(
        self, symbol: str, leverage: int, margin_mode: str = "cross"
    ) -> Dict[str, Any]:
        """Set leverage for a symbol."""
        formatted_symbol = self.format_symbol(symbol)
        params = {"mgnMode": margin_mode}
        return self._make_request("set_leverage", leverage, formatted_symbol, params)

    def get_account_config(self) -> Dict[str, Any]:
        """Get account configuration."""
        return self._make_request("fetch_account_configuration")

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

        order_params = {"triggerPrice": stop_price}
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

        order_params = {"triggerPrice": take_profit_price}
        if params:
            order_params.update(params)

        order = self._make_request(
            "create_order", formatted_symbol, "market", side.lower(), amount, None, order_params
        )
        return self._normalize_order(order)

    def get_wallet_balance(self, account_type: str = "UNIFIED") -> Dict[str, Any]:
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
