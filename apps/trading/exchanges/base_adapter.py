"""
Base Exchange Adapter

This is the abstract base class that all exchange adapters must implement.
The adapter pattern allows strategies to be exchange-agnostic by providing
a standardized interface for all exchange operations.

PURE PYTHON - NO DJANGO IMPORTS
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import ccxt

logger = logging.getLogger("trading.exchanges")


class BaseAdapter(ABC):
    """
    Abstract base class for exchange adapters.

    Each exchange (Bybit, Binance, etc.) implements this interface.
    The adapter translates standard commands into exchange-specific API calls.

    Key Responsibilities:
    - Initialize CCXT exchange with proper configuration
    - Handle data normalization (ensure consistent data format)
    - Manage rate limiting and retries
    - Provide standardized methods for all trading operations
    """

    def __init__(self, credentials: Dict[str, str], demo_mode: bool = False):
        """
        Initialize exchange adapter with credentials.

        Args:
            credentials: Dict with 'api_key', 'secret_key', and optionally 'passphrase'
            demo_mode: Whether to use testnet/demo trading
        """
        self.credentials = credentials
        self.demo_mode = demo_mode
        self.exchange: ccxt.Exchange = self._initialize_exchange()

        # Rate limiting
        self.rate_limit_delay = 0.05  # 50ms default
        self.max_retries = 3
        self.retry_delay = 1

        # Request tracking
        self.request_count = 0
        self.last_request_time = 0

    @staticmethod
    def _enable_demo_mode(exchange: ccxt.Exchange):
        """
        Enable demo/testnet mode on a CCXT exchange instance.
        Prefers demo trading over sandbox where available.

        Args:
            exchange: CCXT exchange instance

        Raises:
            ValueError: If the exchange has no demo or sandbox support
        """
        if hasattr(exchange, "enable_demo_trading"):
            try:
                exchange.enable_demo_trading(True)
                return
            except (ccxt.NotSupported, KeyError):
                pass

        if hasattr(exchange, "set_sandbox_mode"):
            try:
                exchange.set_sandbox_mode(True)
                return
            except (ccxt.NotSupported, TypeError):
                pass

        raise ValueError(
            f"{exchange.id} does not provide a demo or sandbox API environment. "
            "Use MockAdapter for testing instead."
        )

    @abstractmethod
    def _initialize_exchange(self) -> ccxt.Exchange:
        """
        Initialize the CCXT exchange instance with appropriate settings.
        Must be implemented by each exchange subclass.

        Returns:
            Configured CCXT exchange instance
        """
        pass

    @property
    @abstractmethod
    def exchange_name(self) -> str:
        """Return the exchange name (e.g., 'bybit', 'binance')"""
        pass

    # ==========================================================================
    # SYMBOL FORMATTING
    # ==========================================================================

    def format_symbol(self, symbol: str) -> str:
        """
        Format symbol for this exchange.
        Override in subclass if exchange uses non-standard symbol format.

        Args:
            symbol: Standard symbol like 'BTC/USDT'

        Returns:
            Exchange-specific symbol
        """
        return symbol

    # ==========================================================================
    # RATE LIMITING & RETRIES
    # ==========================================================================

    def _rate_limit(self):
        """Apply rate limiting between requests."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self.last_request_time = time.time()

    def _make_request(self, method: str, *args, **kwargs) -> Any:
        """
        Make API request with retry logic and rate limiting.

        Args:
            method: Exchange method name (e.g., 'fetch_ticker')
            *args: Method arguments
            **kwargs: Method keyword arguments

        Returns:
            API response

        Raises:
            Exception: If request fails after retries
        """
        for attempt in range(self.max_retries):
            try:
                self._rate_limit()
                self.request_count += 1
                func = getattr(self.exchange, method)
                return func(*args, **kwargs)

            except ccxt.NetworkError as e:
                logger.warning(f"Network error on attempt {attempt + 1}: {e}")
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(self.retry_delay * (2**attempt))

            except ccxt.AuthenticationError as e:
                logger.error(f"Authentication error for {self.exchange_name}: {e}")
                raise

            except ccxt.RateLimitExceeded as e:
                logger.warning(f"Rate limit exceeded: {e}")
                time.sleep(self.retry_delay * (2**attempt))
                if attempt == self.max_retries - 1:
                    raise

            except ccxt.ExchangeError as e:
                logger.warning(f"Exchange error on attempt {attempt + 1}: {e}")
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(self.retry_delay * (2**attempt))

    # ==========================================================================
    # MARKET DATA - Standardized output
    # ==========================================================================

    def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch current ticker data for symbol.

        Returns standardized dict with:
            - last: float - Last traded price
            - bid: float - Best bid price
            - ask: float - Best ask price
            - high: float - 24h high
            - low: float - 24h low
            - volume: float - 24h volume in base currency
            - timestamp: int - Unix timestamp in milliseconds
        """
        formatted_symbol = self.format_symbol(symbol)
        ticker = self._make_request("fetch_ticker", formatted_symbol)
        return self._normalize_ticker(ticker)

    def _normalize_ticker(self, ticker: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize ticker data to standard format."""
        return {
            "symbol": ticker.get("symbol"),
            "last": float(ticker.get("last", 0)),
            "bid": float(ticker.get("bid", 0)),
            "ask": float(ticker.get("ask", 0)),
            "high": float(ticker.get("high", 0)),
            "low": float(ticker.get("low", 0)),
            "volume": float(ticker.get("baseVolume", 0)),
            "quote_volume": float(ticker.get("quoteVolume", 0)),
            "change_24h": float(ticker.get("change", 0)),
            "percentage_24h": float(ticker.get("percentage", 0)),
            "timestamp": ticker.get("timestamp"),
        }

    def get_current_price(self, symbol: str) -> float:
        """Get current price for symbol."""
        ticker = self.fetch_ticker(symbol)
        return ticker["last"]

    def fetch_ohlcv(
        self, symbol: str, timeframe: str = "1h", limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Fetch OHLCV candlestick data.

        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
            timeframe: Candlestick timeframe (e.g., '1m', '5m', '1h', '1d')
            limit: Number of candles to fetch

        Returns:
            List of dicts with: timestamp, open, high, low, close, volume
        """
        formatted_symbol = self.format_symbol(symbol)
        ohlcv = self._make_request("fetch_ohlcv", formatted_symbol, timeframe, limit=limit)
        return self._normalize_ohlcv(ohlcv)

    def _normalize_ohlcv(self, ohlcv: List) -> List[Dict[str, Any]]:
        """Normalize OHLCV data to standard format."""
        return [
            {
                "timestamp": candle[0],
                "open": float(candle[1]),
                "high": float(candle[2]),
                "low": float(candle[3]),
                "close": float(candle[4]),
                "volume": float(candle[5]),
            }
            for candle in ohlcv
        ]

    def fetch_order_book(self, symbol: str, limit: int = 20) -> Dict[str, Any]:
        """Fetch order book for symbol."""
        formatted_symbol = self.format_symbol(symbol)
        orderbook = self._make_request("fetch_order_book", formatted_symbol, limit)
        return {
            "symbol": symbol,
            "bids": orderbook.get("bids", [])[:limit],
            "asks": orderbook.get("asks", [])[:limit],
            "timestamp": orderbook.get("timestamp"),
        }

    # ==========================================================================
    # ACCOUNT DATA
    # ==========================================================================

    def fetch_balance(self) -> Dict[str, Any]:
        """
        Fetch account balance.

        Returns standardized dict with:
            - total: Dict[currency, amount]
            - free: Dict[currency, amount]
            - used: Dict[currency, amount]
        """
        balance = self._make_request("fetch_balance")
        return {
            "total": balance.get("total", {}),
            "free": balance.get("free", {}),
            "used": balance.get("used", {}),
            "timestamp": balance.get("timestamp", int(time.time() * 1000)),
        }

    def get_account_info(self) -> Dict[str, Any]:
        """
        Get comprehensive account information.

        Returns dict with balance and other account details.
        """
        balance = self.fetch_balance()
        return {
            "balance": balance,
            "exchange": self.exchange_name,
            "demo_mode": self.demo_mode,
        }

    # ==========================================================================
    # ORDER CREATION
    # ==========================================================================

    def create_market_order(
        self, symbol: str, side: str, amount: float, params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Create a market order.

        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
            side: 'buy' or 'sell'
            amount: Amount in base currency
            params: Exchange-specific parameters

        Returns:
            Normalized order response
        """
        formatted_symbol = self.format_symbol(symbol)
        amount = self.amount_to_precision(symbol, amount)
        order = self._make_request(
            "create_market_order", formatted_symbol, side.lower(), amount, params=params or {}
        )
        return self._normalize_order(order)

    def create_limit_order(
        self, symbol: str, side: str, amount: float, price: float, params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Create a limit order.

        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
            side: 'buy' or 'sell'
            amount: Amount in base currency
            price: Limit price
            params: Exchange-specific parameters

        Returns:
            Normalized order response
        """
        formatted_symbol = self.format_symbol(symbol)
        amount = self.amount_to_precision(symbol, amount)
        price = self.price_to_precision(symbol, price)
        order = self._make_request(
            "create_limit_order", formatted_symbol, side.lower(), amount, price, params=params or {}
        )
        return self._normalize_order(order)

    def _normalize_order(self, order: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize order response to standard format."""
        return {
            "id": order.get("id"),
            "client_order_id": order.get("clientOrderId"),
            "symbol": order.get("symbol"),
            "side": order.get("side"),
            "type": order.get("type"),
            "amount": float(order.get("amount", 0)),
            "price": float(order.get("price", 0)) if order.get("price") else None,
            "filled": float(order.get("filled", 0)),
            "remaining": float(order.get("remaining", 0)),
            "cost": float(order.get("cost", 0)),
            "status": order.get("status"),
            "timestamp": order.get("timestamp"),
            "fee": order.get("fee", {}),
        }

    # ==========================================================================
    # ORDER MANAGEMENT
    # ==========================================================================

    def fetch_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        """Fetch a specific order by ID."""
        formatted_symbol = self.format_symbol(symbol)
        order = self._make_request("fetch_order", order_id, formatted_symbol)
        return self._normalize_order(order)

    def fetch_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch all open orders."""
        if symbol:
            formatted_symbol = self.format_symbol(symbol)
            orders = self._make_request("fetch_open_orders", formatted_symbol)
        else:
            orders = self._make_request("fetch_open_orders")
        return [self._normalize_order(o) for o in orders]

    def cancel_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        """Cancel a specific order."""
        formatted_symbol = self.format_symbol(symbol)
        result = self._make_request("cancel_order", order_id, formatted_symbol)
        return {
            "id": order_id,
            "symbol": symbol,
            "cancelled": True,
            "info": result,
        }

    def cancel_all_orders(self, symbol: str) -> List[Dict[str, Any]]:
        """Cancel all open orders for symbol."""
        formatted_symbol = self.format_symbol(symbol)
        try:
            result = self._make_request("cancel_all_orders", formatted_symbol)
            return result
        except Exception:
            # Fallback: cancel orders one by one
            open_orders = self.fetch_open_orders(symbol)
            cancelled = []
            for order in open_orders:
                try:
                    self.cancel_order(order["id"], symbol)
                    cancelled.append(order)
                except Exception as e:
                    logger.error(f"Failed to cancel order {order['id']}: {e}")
            return cancelled

    # ==========================================================================
    # POSITION MANAGEMENT (Futures/Margin)
    # ==========================================================================

    def fetch_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Fetch open positions (for futures/margin trading).

        Returns list of positions with standardized format.
        """
        if symbol:
            formatted_symbol = self.format_symbol(symbol)
            positions = self._make_request("fetch_positions", [formatted_symbol])
        else:
            positions = self._make_request("fetch_positions")

        return [self._normalize_position(p) for p in positions if float(p.get("contracts", 0)) != 0]

    def _normalize_position(self, position: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize position data to standard format."""

        def safe_float(val, default=0.0):
            if val is None:
                return default
            try:
                return float(val)
            except (TypeError, ValueError):
                return default

        return {
            "symbol": position.get("symbol"),
            "side": position.get("side"),
            "contracts": safe_float(position.get("contracts")),
            "entry_price": safe_float(position.get("entryPrice")),
            "mark_price": safe_float(position.get("markPrice")),
            "unrealized_pnl": safe_float(position.get("unrealizedPnl")),
            "leverage": safe_float(position.get("leverage"), 1),
            "liquidation_price": safe_float(position.get("liquidationPrice"), None),
            "margin": safe_float(position.get("margin")),
        }

    def close_position(self, symbol: str, side: str, amount: float) -> Dict[str, Any]:
        """
        Close an open position.

        Args:
            symbol: Trading pair
            side: Current position side ('long' or 'short')
            amount: Position size to close

        Returns:
            Order response
        """
        # To close, we place opposite order
        close_side = "sell" if side.lower() == "long" else "buy"
        return self.create_market_order(symbol, close_side, amount, params={"reduceOnly": True})

    # ==========================================================================
    # UTILITY METHODS
    # ==========================================================================

    def amount_to_precision(self, symbol: str, amount: float) -> float:
        """Format amount to exchange precision."""
        formatted_symbol = self.format_symbol(symbol)
        try:
            return float(self.exchange.amount_to_precision(formatted_symbol, amount))
        except Exception:
            return amount

    def price_to_precision(self, symbol: str, price: float) -> float:
        """Format price to exchange precision."""
        formatted_symbol = self.format_symbol(symbol)
        try:
            return float(self.exchange.price_to_precision(formatted_symbol, price))
        except Exception:
            return price

    def is_order_filled(self, order: Dict[str, Any]) -> bool:
        """Check if an order is filled."""
        status = order.get("status", "")
        return status.lower() in ("closed", "filled")

    def is_order_open(self, order: Dict[str, Any]) -> bool:
        """Check if an order is still open."""
        status = order.get("status", "")
        return status.lower() in ("open", "new", "partially_filled")

    def get_minimum_order_amount(self, symbol: str) -> float:
        """Get minimum order amount for a symbol."""
        formatted_symbol = self.format_symbol(symbol)
        try:
            markets = self.exchange.markets
            if formatted_symbol in markets:
                return float(
                    markets[formatted_symbol].get("limits", {}).get("amount", {}).get("min", 0)
                )
        except Exception:
            pass
        return 0.0

    def fetch_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Fetch a single position for a symbol (singular wrapper).
        Some exchanges (Bybit, Binance futures) have this as a distinct endpoint.
        Falls back to fetch_positions() and returns the first match.

        Args:
            symbol: Trading pair

        Returns:
            Position dict or None
        """
        formatted_symbol = self.format_symbol(symbol)
        try:
            position = self._make_request("fetch_position", formatted_symbol)
            return self._normalize_position(position)
        except (ccxt.NotSupported, AttributeError):
            positions = self.fetch_positions(symbol)
            if positions:
                return positions[0]
            return {
                "symbol": formatted_symbol,
                "side": None,
                "contracts": 0,
                "entry_price": 0,
                "unrealized_pnl": 0,
            }

    def create_market_order_with_cost(
        self, symbol: str, side: str, cost: float, params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Create a market order by cost (quote currency) instead of amount.
        Supported by Bybit (create_market_buy_order_with_cost / _sell).

        Falls back to standard market order with calculated amount.
        """
        formatted_symbol = self.format_symbol(symbol)
        try:
            method = f"create_market_{side}_order_with_cost"
            order = self._make_request(method, formatted_symbol, cost, params=params or {})
            return self._normalize_order(order)
        except (ccxt.NotSupported, AttributeError):
            # Fallback: estimate amount from current price
            price = self.get_current_price(symbol)
            amount = cost / price if price > 0 else cost
            return self.create_market_order(symbol, side, amount, params)

    def execute_order(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute an order based on a signal from a strategy.

        Args:
            signal: Dict with 'action', 'symbol', 'amount', optionally 'price'

        Returns:
            Order response
        """
        action = signal.get("action", "").lower()
        symbol = signal.get("symbol")
        amount = signal.get("amount", 0)
        price = signal.get("price")
        order_type = signal.get("type", "market").lower()

        if not action or not symbol or not amount:
            raise ValueError("Signal must contain 'action', 'symbol', and 'amount'")

        if order_type == "limit" and price:
            return self.create_limit_order(symbol, action, amount, price)
        else:
            return self.create_market_order(symbol, action, amount)

    def __str__(self) -> str:
        return f"{self.__class__.__name__}(demo={self.demo_mode})"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(exchange={self.exchange_name}, demo={self.demo_mode})"
