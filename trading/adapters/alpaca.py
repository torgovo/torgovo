"""
Alpaca Exchange Adapter
"""
import ccxt
import logging
from typing import Dict, Any, List, Optional
from .base import BaseExchangeAdapter

logger = logging.getLogger('trading.adapters.alpaca')


class AlpacaAdapter(BaseExchangeAdapter):
    """
    Alpaca exchange adapter.
    
    Alpaca Specifics:
    - Stock and crypto trading
    - Paper trading mode available
    - Different symbol formats
    """
    
    @property
    def exchange_name(self) -> str:
        return 'alpaca'
    
    def _initialize_exchange(self):
        try:
            exchange = ccxt.alpaca({
                "apiKey": self.credentials.get('api_key'),
                "secret": self.credentials.get('secret_key'),
                "enableRateLimit": True,
            })
            
            if self.demo_mode:
                exchange.set_sandbox_mode(True)  # Paper trading
            
            logger.info(f"Alpaca exchange initialized (demo={self.demo_mode})")
            return exchange
        except Exception as e:
            logger.error(f"Alpaca initialization failed: {e}")
            raise
    
    def format_symbol(self, symbol: str) -> str:
        """Format symbol for Alpaca. BTC/USD stays as is."""
        if ':' in symbol:
            symbol = symbol.split(':')[0]
        return symbol
    
    def create_market_order(self, symbol: str, side: str, amount: float,
                           amount_in_dollars: bool = False) -> Dict[str, Any]:
        formatted = self.format_symbol(symbol)
        
        if amount_in_dollars:
            # Alpaca supports notional orders
            return self.exchange.create_order(
                formatted, 'market', side.lower(), None,
                params={'notional': amount}
            )
        return self.exchange.create_order(formatted, 'market', side.lower(), amount)
    
    def create_limit_order(self, symbol: str, side: str, amount: float,
                          price: float) -> Dict[str, Any]:
        return self.exchange.create_order(
            self.format_symbol(symbol), 'limit', side.lower(), amount, price,
            params={'time_in_force': 'gtc'}
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
        try:
            return self.exchange.fetch_positions()
        except Exception:
            return []
    
    def close_position(self, symbol: str, side: str, amount: float) -> Dict[str, Any]:
        close_side = 'sell' if side.lower() == 'long' else 'buy'
        return self.exchange.create_order(self.format_symbol(symbol), 'market', close_side, amount)
    
    def get_position_pnl(self, symbol: str) -> Dict[str, float]:
        positions = self.fetch_positions(symbol)
        for pos in positions:
            if pos.get('symbol') == self.format_symbol(symbol):
                return {
                    'size': abs(float(pos.get('contracts', 0))),
                    'unrealized_pnl': float(pos.get('unrealizedPnl', 0)),
                    'percentage': 0,
                    'side': 'long' if float(pos.get('contracts', 0)) > 0 else 'short'
                }
        return {'size': 0, 'unrealized_pnl': 0, 'percentage': 0, 'side': 'none'}
