"""
OKX Exchange Adapter
Implements BaseExchangeAdapter for OKX-specific API calls
"""
import ccxt
import logging
from typing import Dict, Any, List, Optional
from .base import BaseExchangeAdapter

logger = logging.getLogger('trading.adapters.okx')


class OKXAdapter(BaseExchangeAdapter):
    """
    OKX exchange adapter.
    
    OKX Specifics:
    - Requires passphrase in addition to API key/secret
    - Uses 'swap' for perpetual futures
    - Symbol format: BTC/USDT:USDT
    """
    
    @property
    def exchange_name(self) -> str:
        return 'okx'
    
    def _initialize_exchange(self):
        """Initialize OKX CCXT exchange instance."""
        try:
            exchange = ccxt.okx({
                "apiKey": self.credentials.get('api_key'),
                "secret": self.credentials.get('secret_key'),
                "password": self.credentials.get('passphrase'),  # OKX requires passphrase
                "enableRateLimit": True,
                "options": {
                    "defaultType": "swap",  # Perpetual futures
                }
            })
            
            if self.demo_mode:
                exchange.set_sandbox_mode(True)
            
            logger.info(f"OKX exchange initialized (demo={self.demo_mode})")
            return exchange
        except Exception as e:
            logger.error(f"OKX exchange initialization failed: {e}")
            raise
    
    def format_symbol(self, symbol: str) -> str:
        """Format symbol for OKX. BTC/USDT -> BTC/USDT:USDT"""
        if ':' not in symbol:
            quote = symbol.split('/')[1] if '/' in symbol else 'USDT'
            return f"{symbol}:{quote}"
        return symbol
    
    # ==================== ORDER CREATION ====================
    
    def create_market_order(self, symbol: str, side: str, amount: float,
                           amount_in_dollars: bool = False) -> Dict[str, Any]:
        """Create market order on OKX."""
        formatted_symbol = self.format_symbol(symbol)
        
        try:
            if amount_in_dollars:
                price = self.get_current_price(symbol)
                amount = amount / price
            
            order = self.exchange.create_order(
                formatted_symbol, 'market', side.lower(), amount
            )
            logger.info(f"OKX market order created: {side} {amount} {symbol}")
            return order
        except Exception as e:
            logger.error(f"OKX create_market_order failed: {e}")
            raise
    
    def create_limit_order(self, symbol: str, side: str, amount: float,
                          price: float) -> Dict[str, Any]:
        """Create limit order on OKX."""
        formatted_symbol = self.format_symbol(symbol)
        
        try:
            order = self.exchange.create_order(
                formatted_symbol, 'limit', side.lower(), amount, price
            )
            logger.info(f"OKX limit order created: {side} {amount} @ {price} {symbol}")
            return order
        except Exception as e:
            logger.error(f"OKX create_limit_order failed: {e}")
            raise
    
    # ==================== ORDER MANAGEMENT ====================
    
    def fetch_open_orders(self, symbol: str) -> List[Dict[str, Any]]:
        return self.exchange.fetch_open_orders(self.format_symbol(symbol))
    
    def fetch_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        return self.exchange.fetch_order(order_id, symbol=self.format_symbol(symbol))
    
    def cancel_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        return self.exchange.cancel_order(order_id, self.format_symbol(symbol))
    
    def cancel_all_orders(self, symbol: str) -> None:
        self.exchange.cancel_all_orders(symbol=self.format_symbol(symbol))
    
    # ==================== POSITION MANAGEMENT ====================
    
    def fetch_positions(self, symbol: str = None) -> List[Dict[str, Any]]:
        if symbol:
            return self.exchange.fetch_positions(symbols=[self.format_symbol(symbol)])
        return self.exchange.fetch_positions()
    
    def close_position(self, symbol: str, side: str, amount: float) -> Dict[str, Any]:
        formatted = self.format_symbol(symbol)
        close_side = 'buy' if side.lower() == 'short' else 'sell'
        
        return self.exchange.create_order(
            formatted, 'market', close_side, amount, None,
            params={'reduceOnly': True}
        )
    
    def get_position_pnl(self, symbol: str) -> Dict[str, float]:
        positions = self.fetch_positions(symbol)
        if positions:
            pos = positions[0]
            size = abs(float(pos.get('contracts', 0)))
            pnl = float(pos.get('unrealizedPnl', 0))
            return {'size': size, 'unrealized_pnl': pnl, 'percentage': 0, 'side': pos.get('side', 'none')}
        return {'size': 0, 'unrealized_pnl': 0, 'percentage': 0, 'side': 'none'}
