"""
Bybit Exchange Adapter

PURE PYTHON - NO DJANGO IMPORTS
"""

from typing import Any, Dict, Optional

import ccxt

from .base_adapter import BaseAdapter


class BybitAdapter(BaseAdapter):
    """
    Adapter for Bybit exchange.

    Handles Bybit-specific configurations:
    - Symbol formatting (BTC/USDT:USDT for perpetual futures)
    - Testnet configuration
    - Unified account support
    """

    @property
    def exchange_name(self) -> str:
        return "bybit"

    def _initialize_exchange(self) -> ccxt.Exchange:
        """Initialize Bybit CCXT instance."""
        config = {
            "apiKey": self.credentials.get("api_key"),
            "secret": self.credentials.get("secret_key"),
            "enableRateLimit": True,
            "options": {
                "defaultType": "swap",  # Perpetual futures by default
                "adjustForTimeDifference": True,
            },
        }

        exchange = ccxt.bybit(config)

        if self.demo_mode:
            self._enable_demo_mode(exchange)

        try:
            exchange.load_markets()
        except Exception:
            pass

        return exchange

    def format_symbol(self, symbol: str) -> str:
        """
        Format symbol for Bybit.

        Bybit perpetual futures use format: BTC/USDT:USDT
        Spot uses standard format: BTC/USDT
        """
        if self.exchange.options.get("defaultType") == "swap":
            # For perpetual futures, add settlement currency
            if ":" not in symbol:
                base_quote = symbol.split("/")
                if len(base_quote) == 2:
                    return f"{symbol}:{base_quote[1]}"
        return symbol

    def set_market_type(self, market_type: str = "swap"):
        """
        Set the market type.

        Args:
            market_type: 'spot', 'swap' (perpetual), 'future', 'option'
        """
        self.exchange.options["defaultType"] = market_type

    def set_leverage(self, symbol: str, leverage: int, side: str = None) -> Dict[str, Any]:
        """
        Set leverage for a symbol.

        Args:
            symbol: Trading pair
            leverage: Leverage multiplier
            side: 'long', 'short', or None for both

        Returns:
            Response from exchange
        """
        formatted_symbol = self.format_symbol(symbol)

        params = {}
        if side:
            params["side"] = "Buy" if side.lower() == "long" else "Sell"

        return self._make_request("set_leverage", leverage, formatted_symbol, params)

    def set_position_mode(self, hedged: bool = False) -> Dict[str, Any]:
        """
        Set position mode.

        Args:
            hedged: True for hedge mode (separate long/short), False for one-way

        Returns:
            Response from exchange
        """
        return self._make_request("set_position_mode", hedged)

    def create_market_order(
        self, symbol: str, side: str, amount: float, params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Create a market order with Bybit-specific handling.

        Bybit requires 'Buy'/'Sell' for perpetual futures.
        """
        formatted_symbol = self.format_symbol(symbol)
        amount = self.amount_to_precision(symbol, amount)

        # Bybit uses capitalized sides for some endpoints
        bybit_side = side.lower()

        order_params = params or {}

        order = self._make_request(
            "create_market_order", formatted_symbol, bybit_side, amount, params=order_params
        )
        return self._normalize_order(order)

    def create_limit_order(
        self, symbol: str, side: str, amount: float, price: float, params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Create a limit order with Bybit-specific handling."""
        formatted_symbol = self.format_symbol(symbol)
        amount = self.amount_to_precision(symbol, amount)
        price = self.price_to_precision(symbol, price)

        bybit_side = side.lower()
        order_params = params or {}

        order = self._make_request(
            "create_limit_order", formatted_symbol, bybit_side, amount, price, params=order_params
        )
        return self._normalize_order(order)

    def set_position_tpsl(
        self,
        symbol: str,
        side: str,
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Set stop-loss and/or take-profit on an existing position.

        Uses Bybit v5 POST /v5/position/trading-stop endpoint.
        `side` is the position side ('long' or 'short').
        Pass None for a price to leave it unchanged.
        """
        market_id = self.exchange.market(symbol)["id"]

        if not hasattr(self, "_position_idx"):
            try:
                mode = self.exchange.fetch_position_mode()
                self._position_idx = 0 if mode == "OneWay" else None
            except Exception:
                self._position_idx = 0
        position_idx = (
            self._position_idx
            if self._position_idx is not None
            else (1 if side.lower() == "long" else 2)
        )

        payload = {
            "symbol": market_id,
            "category": "linear",
            "tpTriggerBy": "MarkPrice",
            "slTriggerBy": "MarkPrice",
            "positionIdx": position_idx,
        }
        if take_profit_price is not None:
            payload["takeProfit"] = str(self.price_to_precision(symbol, take_profit_price))
        if stop_loss_price is not None:
            payload["stopLoss"] = str(self.price_to_precision(symbol, stop_loss_price))

        resp = self._make_request("privatePostV5PositionTradingStop", payload)

        return {"retCode": resp.get("retCode", -1), "retMsg": resp.get("retMsg", "")}

    def _get_position_side(self, symbol: str) -> str:
        """Get the current position side for a symbol."""
        try:
            pos = self.fetch_position(symbol)
            if pos and float(pos.get("contracts", 0)) > 0:
                return pos.get("side", "long")
        except Exception:
            pass
        return "long"

    def create_stop_loss_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        stop_price: float,
        params: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Create a stop-loss order on an existing position.

        Uses the v5 trading-stop endpoint to set SL on the position.
        `side` is the order side (buy/sell); position side is auto-detected.
        `amount` is accepted for API compatibility but not sent to Bybit.
        """
        pos_side = self._get_position_side(symbol)
        return self.set_position_tpsl(
            symbol=symbol,
            side=pos_side,
            stop_loss_price=stop_price,
            take_profit_price=None,
        )

    def create_take_profit_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        take_profit_price: float,
        params: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Create a take-profit order on an existing position.

        Uses the v5 trading-stop endpoint to set TP on the position.
        `side` is the order side (buy/sell); position side is auto-detected.
        `amount` is accepted for API compatibility but not sent to Bybit.
        """
        pos_side = self._get_position_side(symbol)
        return self.set_position_tpsl(
            symbol=symbol,
            side=pos_side,
            stop_loss_price=None,
            take_profit_price=take_profit_price,
        )

    def get_wallet_balance(self, account_type: str = "UNIFIED") -> Dict[str, Any]:
        """
        Get wallet balance for Bybit unified account.

        Args:
            account_type: 'UNIFIED', 'CONTRACT', 'SPOT'

        Returns:
            Balance information
        """
        params = {"accountType": account_type}
        balance = self._make_request("fetch_balance", params)
        return {
            "total": balance.get("total", {}),
            "free": balance.get("free", {}),
            "used": balance.get("used", {}),
        }

    def get_funding_rate(self, symbol: str) -> Dict[str, Any]:
        """Get current funding rate for perpetual."""
        formatted_symbol = self.format_symbol(symbol)
        try:
            funding = self._make_request("fetch_funding_rate", formatted_symbol)
            return {
                "symbol": symbol,
                "funding_rate": float(funding.get("fundingRate", 0)),
                "funding_timestamp": funding.get("fundingTimestamp"),
            }
        except Exception:
            return {
                "symbol": symbol,
                "funding_rate": 0,
                "funding_timestamp": None,
            }

    def get_position_info(self, symbol: str) -> Dict[str, Any]:
        """Get detailed position information."""
        positions = self.fetch_positions(symbol)
        if positions:
            return positions[0]
        return {
            "symbol": symbol,
            "side": None,
            "contracts": 0,
            "entry_price": 0,
            "unrealized_pnl": 0,
        }
