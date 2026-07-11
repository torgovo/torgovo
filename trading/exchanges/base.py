"""
Base exchange bot class for trading integration
"""
import time
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Tuple
from decimal import Decimal
import ccxt
from django.conf import settings
from core.utils import decrypt_api_key

logger = logging.getLogger('trading')


class BaseExchangeBot(ABC):
    """
    Abstract base class for all exchange integrations.
    Provides common functionality and interface for different exchanges.
    """

    def __init__(self, user, exchange_credentials):
        """
        Initialize exchange bot.

        Args:
            user: Django user instance
            exchange_credentials: ExchangeCredentials model instance
        """
        self.user = user
        self.exchange_name = exchange_credentials.exchange_name
        self.is_testnet = exchange_credentials.is_testnet

        # Decrypt credentials
        api_key = decrypt_api_key(exchange_credentials.api_key)
        secret_key = decrypt_api_key(exchange_credentials.secret_key)
        passphrase = (
            decrypt_api_key(exchange_credentials.passphrase)
            if exchange_credentials.passphrase else None
        )

        # Initialize CCXT exchange
        self.exchange = self._create_exchange(api_key, secret_key, passphrase)

        # Configuration
        self.rate_limit_delay = 60 / getattr(self.exchange, 'rateLimit', 1200)  # seconds
        self.max_retries = getattr(settings, 'EXCHANGE_CONFIG', {}).get('MAX_RETRIES', 3)
        self.retry_delay = getattr(settings, 'EXCHANGE_CONFIG', {}).get('RETRY_DELAY', 1)

        # State
        self.is_connected = False
        self.last_error = None
        self.request_count = 0

    @abstractmethod
    def _create_exchange(self, api_key: str, secret_key: str, passphrase: str = None):
        """
        Create CCXT exchange instance.
        Must be implemented by each exchange subclass.
        """
        pass

    def connect(self) -> bool:
        """
        Connect to exchange and verify credentials.

        Returns:
            True if connection successful
        """
        try:
            # Test connection by fetching balance
            balance = self.get_balance()
            self.is_connected = True
            self.last_error = None
            logger.info(f"Connected to {self.exchange_name} for user {self.user.email}")
            return True

        except Exception as e:
            self.is_connected = False
            self.last_error = str(e)
            logger.error(f"Failed to connect to {self.exchange_name}: {e}")
            return False

    def _make_request(self, method: str, *args, **kwargs) -> Any:
        """
        Make API request with retry logic and rate limiting.

        Args:
            method: Exchange method name
            *args: Method arguments
            **kwargs: Method keyword arguments

        Returns:
            API response

        Raises:
            Exception: If request fails after retries
        """
        for attempt in range(self.max_retries):
            try:
                # Rate limiting
                time.sleep(self.rate_limit_delay)

                # Make request
                self.request_count += 1
                func = getattr(self.exchange, method)
                result = func(*args, **kwargs)

                return result

            except ccxt.NetworkError as e:
                logger.warning(f"Network error on attempt {attempt + 1}: {e}")
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(self.retry_delay * (2 ** attempt))

            except ccxt.AuthenticationError as e:
                logger.error(f"Authentication error for {self.exchange_name}: {e}")
                raise

            except ccxt.ExchangeError as e:
                logger.warning(f"Exchange error on attempt {attempt + 1}: {e}")
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(self.retry_delay * (2 ** attempt))

            except Exception as e:
                logger.error(f"Unexpected error on attempt {attempt + 1}: {e}")
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(self.retry_delay * (2 ** attempt))

    def get_balance(self) -> Dict[str, Dict[str, Any]]:
        """
        Get account balance.

        Returns:
            Dictionary with balance information
        """
        try:
            balance = self._make_request('fetch_balance')
            return {
                'total': balance.get('total', {}),
                'free': balance.get('free', {}),
                'used': balance.get('used', {}),
                'timestamp': balance.get('timestamp', time.time() * 1000),
            }
        except Exception as e:
            logger.error(f"Error fetching balance from {self.exchange_name}: {e}")
            raise

    def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Get ticker information for a symbol.

        Args:
            symbol: Trading symbol (e.g., 'BTC/USDT')

        Returns:
            Ticker information
        """
        try:
            ticker = self._make_request('fetch_ticker', symbol)
            return {
                'symbol': symbol,
                'last': ticker.get('last'),
                'bid': ticker.get('bid'),
                'ask': ticker.get('ask'),
                'high': ticker.get('high'),
                'low': ticker.get('low'),
                'volume': ticker.get('baseVolume'),
                'quote_volume': ticker.get('quoteVolume'),
                'timestamp': ticker.get('timestamp'),
                'change': ticker.get('change'),
                'percentage': ticker.get('percentage'),
            }
        except Exception as e:
            logger.error(f"Error fetching ticker for {symbol}: {e}")
            raise

    def get_order_book(self, symbol: str, limit: int = 20) -> Dict[str, Any]:
        """
        Get order book for a symbol.

        Args:
            symbol: Trading symbol
            limit: Number of bids/asks to return

        Returns:
            Order book data
        """
        try:
            orderbook = self._make_request('fetch_order_book', symbol, limit)
            return {
                'symbol': symbol,
                'bids': orderbook.get('bids', [])[:limit],
                'asks': orderbook.get('asks', [])[:limit],
                'timestamp': orderbook.get('timestamp'),
                'datetime': orderbook.get('datetime'),
            }
        except Exception as e:
            logger.error(f"Error fetching order book for {symbol}: {e}")
            raise

    def create_market_order(self, symbol: str, side: str, amount: float) -> Dict[str, Any]:
        """
        Create a market order.

        Args:
            symbol: Trading symbol
            side: 'buy' or 'sell'
            amount: Order amount

        Returns:
            Order information
        """
        try:
            order = self._make_request('create_market_order', symbol, side, amount)
            return self._format_order(order)
        except Exception as e:
            logger.error(f"Error creating market order: {e}")
            raise

    def create_limit_order(self, symbol: str, side: str, amount: float, price: float) -> Dict[str, Any]:
        """
        Create a limit order.

        Args:
            symbol: Trading symbol
            side: 'buy' or 'sell'
            amount: Order amount
            price: Order price

        Returns:
            Order information
        """
        try:
            order = self._make_request('create_limit_order', symbol, side, amount, price)
            return self._format_order(order)
        except Exception as e:
            logger.error(f"Error creating limit order: {e}")
            raise

    def cancel_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        """
        Cancel an order.

        Args:
            order_id: Order ID
            symbol: Trading symbol

        Returns:
            Cancellation information
        """
        try:
            result = self._make_request('cancel_order', order_id, symbol)
            return {
                'order_id': order_id,
                'symbol': symbol,
                'cancelled': True,
                'timestamp': time.time() * 1000,
            }
        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            raise

    def get_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        """
        Get order information.

        Args:
            order_id: Order ID
            symbol: Trading symbol

        Returns:
            Order information
        """
        try:
            order = self._make_request('fetch_order', order_id, symbol)
            return self._format_order(order)
        except Exception as e:
            logger.error(f"Error fetching order {order_id}: {e}")
            raise

    def get_open_orders(self, symbol: str = None) -> List[Dict[str, Any]]:
        """
        Get open orders.

        Args:
            symbol: Trading symbol (optional)

        Returns:
            List of open orders
        """
        try:
            if symbol:
                orders = self._make_request('fetch_open_orders', symbol)
            else:
                orders = self._make_request('fetch_open_orders')

            return [self._format_order(order) for order in orders]
        except Exception as e:
            logger.error(f"Error fetching open orders: {e}")
            raise

    def get_order_history(self, symbol: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get order history.

        Args:
            symbol: Trading symbol (optional)
            limit: Number of orders to return

        Returns:
            List of historical orders
        """
        try:
            if symbol:
                orders = self._make_request('fetch_my_trades', symbol, limit=limit)
            else:
                orders = self._make_request('fetch_my_trades', limit=limit)

            return [self._format_trade(trade) for trade in orders]
        except Exception as e:
            logger.error(f"Error fetching order history: {e}")
            raise

    def _format_order(self, order: Dict[str, Any]) -> Dict[str, Any]:
        """Format order data to standard format."""
        return {
            'id': order.get('id'),
            'symbol': order.get('symbol'),
            'side': order.get('side'),
            'type': order.get('type'),
            'amount': order.get('amount'),
            'price': order.get('price'),
            'filled': order.get('filled'),
            'remaining': order.get('remaining'),
            'status': order.get('status'),
            'timestamp': order.get('timestamp'),
            'datetime': order.get('datetime'),
            'fee': order.get('fee', {}),
        }

    def _format_trade(self, trade: Dict[str, Any]) -> Dict[str, Any]:
        """Format trade data to standard format."""
        return {
            'id': trade.get('id'),
            'order_id': trade.get('order'),
            'symbol': trade.get('symbol'),
            'side': trade.get('side'),
            'amount': trade.get('amount'),
            'price': trade.get('price'),
            'cost': trade.get('cost'),
            'timestamp': trade.get('timestamp'),
            'datetime': trade.get('datetime'),
            'fee': trade.get('fee', {}),
        }

    def get_symbols(self) -> List[str]:
        """
        Get available trading symbols.

        Returns:
            List of trading symbols
        """
        try:
            markets = self._make_request('fetch_markets')
            return [market['symbol'] for market in markets if market.get('active')]
        except Exception as e:
            logger.error(f"Error fetching symbols: {e}")
            raise

    def get_fees(self, symbol: str = None) -> Dict[str, Any]:
        """
        Get trading fees.

        Args:
            symbol: Trading symbol (optional)

        Returns:
            Fee information
        """
        try:
            if symbol:
                return self._make_request('fetch_trading_fees')
            else:
                return self.exchange.fees
        except Exception as e:
            logger.error(f"Error fetching fees: {e}")
            raise

    def validate_symbol(self, symbol: str) -> bool:
        """
        Validate if symbol exists on exchange.

        Args:
            symbol: Trading symbol

        Returns:
            True if symbol is valid
        """
        try:
            markets = self._make_request('fetch_markets')
            symbol_found = any(
                market['symbol'] == symbol and market.get('active')
                for market in markets
            )
            return symbol_found
        except Exception as e:
            logger.error(f"Error validating symbol {symbol}: {e}")
            return False

    def get_price_precision(self, symbol: str) -> int:
        """
        Get price precision for a symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Number of decimal places for price
        """
        try:
            markets = self._make_request('fetch_markets')
            for market in markets:
                if market['symbol'] == symbol:
                    return market.get('precision', {}).get('price', 8)
            return 8  # Default precision
        except Exception as e:
            logger.error(f"Error getting price precision for {symbol}: {e}")
            return 8

    def get_amount_precision(self, symbol: str) -> int:
        """
        Get amount precision for a symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Number of decimal places for amount
        """
        try:
            markets = self._make_request('fetch_markets')
            for market in markets:
                if market['symbol'] == symbol:
                    return market.get('precision', {}).get('amount', 8)
            return 8  # Default precision
        except Exception as e:
            logger.error(f"Error getting amount precision for {symbol}: {e}")
            return 8

    def get_min_order_amount(self, symbol: str) -> float:
        """
        Get minimum order amount for a symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Minimum order amount
        """
        try:
            markets = self._make_request('fetch_markets')
            for market in markets:
                if market['symbol'] == symbol:
                    return market.get('limits', {}).get('amount', {}).get('min', 0.00000001)
            return 0.00000001  # Default minimum
        except Exception as e:
            logger.error(f"Error getting min order amount for {symbol}: {e}")
            return 0.00000001

    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self.exchange_name})"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(user={self.user.email}, exchange={self.exchange_name})"