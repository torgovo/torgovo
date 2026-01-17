"""
Base Exchange Adapter Interface
All exchange adapters must implement these methods
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger('trading.adapters')


class BaseExchangeAdapter(ABC):
    """
    Abstract base class for exchange adapters.
    Each exchange (Bybit, Binance, etc.) implements this interface.
    
    The adapter translates standard commands into exchange-specific API calls.
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
        self.exchange = self._initialize_exchange()
    
    @abstractmethod
    def _initialize_exchange(self):
        """Initialize the CCXT exchange instance with appropriate settings."""
        pass
    
    @property
    @abstractmethod
    def exchange_name(self) -> str:
        """Return the exchange name (e.g., 'bybit', 'binance')"""
        pass
    
    # ==================== SYMBOL FORMATTING ====================
    
    @abstractmethod
    def format_symbol(self, symbol: str) -> str:
        """
        Format symbol for this exchange.
        
        Args:
            symbol: Standard symbol like 'BTC/USDT'
            
        Returns:
            Exchange-specific symbol (e.g., 'BTC/USDT:USDT' for Bybit futures)
        """
        pass
    
    # ==================== MARKET DATA ====================
    
    def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """Fetch current ticker data for symbol."""
        formatted_symbol = self.format_symbol(symbol)
        return self.exchange.fetch_ticker(formatted_symbol)
    
    def get_current_price(self, symbol: str) -> float:
        """Get current price for symbol."""
        ticker = self.fetch_ticker(symbol)
        return float(ticker['last'])
    
    def fetch_balance(self) -> Dict[str, Any]:
        """Fetch account balance."""
        return self.exchange.fetch_balance()
    
    # ==================== ORDER CREATION ====================
    
    @abstractmethod
    def create_market_order(self, symbol: str, side: str, amount: float, 
                           amount_in_dollars: bool = False) -> Dict[str, Any]:
        """
        Create a market order.
        
        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
            side: 'buy' or 'sell'
            amount: Amount to trade (in coins or dollars based on amount_in_dollars)
            amount_in_dollars: If True, amount is in quote currency (USDT)
            
        Returns:
            Order response from exchange
        """
        pass
    
    @abstractmethod
    def create_limit_order(self, symbol: str, side: str, amount: float, 
                          price: float) -> Dict[str, Any]:
        """
        Create a limit order.
        
        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
            side: 'buy' or 'sell'
            amount: Amount in base currency (coins)
            price: Limit price
            
        Returns:
            Order response from exchange
        """
        pass
    
    # ==================== ORDER MANAGEMENT ====================
    
    @abstractmethod
    def fetch_open_orders(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch all open orders for symbol."""
        pass
    
    @abstractmethod
    def fetch_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        """Fetch a specific order by ID."""
        pass
    
    @abstractmethod
    def cancel_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        """Cancel a specific order."""
        pass
    
    @abstractmethod
    def cancel_all_orders(self, symbol: str) -> None:
        """Cancel all open orders for symbol."""
        pass
    
    # ==================== POSITION MANAGEMENT ====================
    
    @abstractmethod
    def fetch_positions(self, symbol: str = None) -> List[Dict[str, Any]]:
        """Fetch open positions."""
        pass
    
    @abstractmethod
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
        pass
    
    # ==================== UTILITY METHODS ====================
    
    def amount_to_precision(self, symbol: str, amount: float) -> float:
        """Format amount to exchange precision."""
        formatted_symbol = self.format_symbol(symbol)
        return float(self.exchange.amount_to_precision(formatted_symbol, amount))
    
    def price_to_precision(self, symbol: str, price: float) -> float:
        """Format price to exchange precision."""
        formatted_symbol = self.format_symbol(symbol)
        return float(self.exchange.price_to_precision(formatted_symbol, price))
    
    def is_order_filled(self, order: Dict[str, Any]) -> bool:
        """Check if an order is filled."""
        status = order.get('status') or order.get('state', '')
        return status.lower() in ('closed', 'filled')
    
    def get_order_id(self, order: Dict[str, Any]) -> Optional[str]:
        """Extract order ID from order response."""
        return order.get('id') or order.get('orderId') or order.get('clientOrderId')
