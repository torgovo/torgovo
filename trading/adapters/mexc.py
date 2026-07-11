"""
MEXC Exchange Adapter
"""
import ccxt
import logging
from typing import Dict, Any, List, Optional
from .base import BaseExchangeAdapter

logger = logging.getLogger('trading.adapters.mexc')


class MEXCAdapter(BaseExchangeAdapter):
    """MEXC exchange adapter."""
    
    @property
    def exchange_name(self) -> str:
        return 'mexc'
    
    def _initialize_exchange(self):
        try:
            exchange = ccxt.mexc({
                "apiKey": self.credentials.get('api_key'),
                "secret": self.credentials.get('secret_key'),
                "enableRateLimit": True,
                "options": {"defaultType": "swap"}
            })
            logger.info(f"MEXC exchange initialized")
            return exchange
        except Exception as e:
            logger.error(f"MEXC initialization failed: {e}")
            raise
    
    def format_symbol(self, symbol: str) -> str:
        if ':' not in symbol:
            quote = symbol.split('/')[1] if '/' in symbol else 'USDT'
            return f"{symbol}:{quote}"
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
        return self.exchange.create_order(self.format_symbol(symbol), 'limit', side.lower(), amount, price)
    
    def fetch_open_orders(self, symbol: str) -> List[Dict[str, Any]]:
        return self.exchange.fetch_open_orders(self.format_symbol(symbol))
    
    def fetch_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        return self.exchange.fetch_order(order_id, symbol=self.format_symbol(symbol))
    
    def cancel_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        return self.exchange.cancel_order(order_id, self.format_symbol(symbol))
    
    def cancel_all_orders(self, symbol: str) -> None:
        self.exchange.cancel_all_orders(symbol=self.format_symbol(symbol))
    
    def fetch_positions(self, symbol: str = None) -> List[Dict[str, Any]]:
        if symbol:
            return self.exchange.fetch_positions(symbols=[self.format_symbol(symbol)])
        return self.exchange.fetch_positions()
    
    def close_position(self, symbol: str, side: str, amount: float) -> Dict[str, Any]:
        close_side = 'buy' if side.lower() == 'short' else 'sell'
        return self.exchange.create_order(
            self.format_symbol(symbol), 'market', close_side, amount,
            params={'reduceOnly': True}
        )
    
    def get_position_pnl(self, symbol: str) -> Dict[str, float]:
        positions = self.fetch_positions(symbol)
        if positions:
            pos = positions[0]
            return {
                'size': abs(float(pos.get('contracts', 0))),
                'unrealized_pnl': float(pos.get('unrealizedPnl', 0)),
                'percentage': 0,
                'side': pos.get('side', 'none')
            }
        return {'size': 0, 'unrealized_pnl': 0, 'percentage': 0, 'side': 'none'}
