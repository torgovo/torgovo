"""
Coinbase Exchange Adapter

PURE PYTHON - NO DJANGO IMPORTS
"""

from typing import Any, Dict, List, Optional

import ccxt

from .base_adapter import BaseAdapter


class CoinbaseAdapter(BaseAdapter):
    """
    Adapter for Coinbase exchange.

    Coinbase Specifics:
    - Spot trading focused (no futures)
    - Requires passphrase for API authentication
    - Standard symbol format (BTC/USDT)
    - post_only for limit orders
    """

    @property
    def exchange_name(self) -> str:
        return "coinbase"

    def _initialize_exchange(self) -> ccxt.Exchange:
        """Initialize Coinbase CCXT instance with passphrase."""
        config = {
            "apiKey": self.credentials.get("api_key"),
            "secret": self.credentials.get("secret_key"),
            "password": self.credentials.get("passphrase"),
            "enableRateLimit": True,
        }

        exchange = ccxt.coinbase(config)

        if self.demo_mode:
            self._enable_demo_mode(exchange)

        try:
            exchange.load_markets()
        except Exception:
            pass

        return exchange

    def format_symbol(self, symbol: str) -> str:
        """Coinbase uses standard format - strip any futures suffix."""
        if ":" in symbol:
            symbol = symbol.split(":")[0]
        return symbol

    def create_limit_order(
        self, symbol: str, side: str, amount: float, price: float, params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Create a limit order on Coinbase with post_only."""
        formatted_symbol = self.format_symbol(symbol)
        amount = self.amount_to_precision(symbol, amount)
        price = self.price_to_precision(symbol, price)

        order_params = params or {}
        order_params.setdefault("post_only", True)

        order = self._make_request(
            "create_limit_order", formatted_symbol, side.lower(), amount, price, params=order_params
        )
        return self._normalize_order(order)

    def fetch_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Coinbase is spot-only - no futures positions."""
        return []

    def close_position(self, symbol: str, side: str, amount: float) -> Dict[str, Any]:
        """Coinbase spot close uses opposite side market order."""
        close_side = "sell" if side.lower() == "long" else "buy"
        return self.create_market_order(symbol, close_side, amount)
