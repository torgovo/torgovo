"""
Coinbase Exchange Adapter
"""
import ccxt
import logging
from typing import Dict, Any, List, Optional
from .base import BaseExchangeAdapter

logger = logging.getLogger('trading.adapters.coinbase')


class CoinbaseAdapter(BaseExchangeAdapter):
    """
    Coinbase exchange adapter.
    
    Coinbase Specifics:
    - Requires passphrase
    - Product ID format: BTC-USD (hyphen instead of slash)
    - Spot trading focused
    """
    
    @property
    def exchange_name(self) -> str:
        return 'coinbase'
    
    def _initialize_exchange(self):
        try:
            exchange = ccxt.coinbase({
                "apiKey": self.credentials.get('api_key'),
                "secret": self.credentials.get('secret_key'),
                "password": self.credentials.get('passphrase'),
                "enableRateLimit": True,
            })
            
            if self.demo_mode:
                exchange.set_sandbox_mode(True)
            
            logger.info(f"Coinbase exchange initialized")
            return exchange
        except Exception as e:
            logger.error(f"Coinbase initialization failed: {e}")
            raise
    
    def format_symbol(self, symbol: str) -> str:
        """BTC/USD -> BTC/USD (Coinbase uses standard format in CCXT)"""
        if ':' in symbol:
            symbol = symbol.split(':')[0]
        return symbol
    
    def create_market_order(self, symbol: str, side: str, amount: float,
                           amount_in_dollars: bool = False) -> Dict[str, Any]:
        formatted = self.format_symbol(symbol)
        if amount_in_dollars:
            price = self.get_current_price(symbol)
            amount = amount / price
        return self.exchange.create_order(formatted, 'market', side.lower(), amount)
    
    def create_limit_order(self, symbol: str, side: str, amount: float,
                          price: float) -> Dict[str, Any]:
        return self.exchange.create_order(
            self.format_symbol(symbol), 'limit', side.lower(), amount, price,
            params={'post_only': True}
        )
    
    def fetch_open_orders(self, symbol: str) -> List[Dict[str, Any]]:
        return self.exchange.fetch_open_orders(self.format_symbol(symbol))
    
    def fetch_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        return self.exchange.fetch_order(order_id, symbol=self.format_symbol(symbol))
    
    def cancel_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        return self.exchange.cancel_order(order_id, self.format_symbol(symbol))
    
    def cancel_all_orders(self, symbol: str) -> None:
        self.exchange.cancel_all_orders(symbol=self.format_symbol(symbol))
    
    def fetch_positions(self, symbol: str = None) -> List[Dict[str, Any]]:
        # Coinbase is primarily spot, positions via balance
        return []
    
    def close_position(self, symbol: str, side: str, amount: float) -> Dict[str, Any]:
        close_side = 'sell' if side.lower() == 'long' else 'buy'
        return self.exchange.create_order(self.format_symbol(symbol), 'market', close_side, amount)
    
    def get_position_pnl(self, symbol: str) -> Dict[str, float]:
        return {'size': 0, 'unrealized_pnl': 0, 'percentage': 0, 'side': 'none'}
