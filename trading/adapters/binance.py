"""
Binance Exchange Adapter
Implements BaseExchangeAdapter for Binance-specific API calls
"""
import ccxt
import logging
from typing import Dict, Any, List, Optional
from .base import BaseExchangeAdapter

logger = logging.getLogger('trading.adapters.binance')


class BinanceAdapter(BaseExchangeAdapter):
    """
    Binance exchange adapter.
    Handles all Binance-specific API syntax and parameters.
    
    Binance Specifics:
    - Futures uses 'future' defaultType
    - Symbol format stays as BTC/USDT (no suffix)
    - Requires 'timeInForce': 'GTC' for limit orders
    - Different position mode handling
    """
    
    @property
    def exchange_name(self) -> str:
        return 'binance'
    
    def _initialize_exchange(self):
        """Initialize Binance CCXT exchange instance."""
        try:
            exchange = ccxt.binance({
                "apiKey": self.credentials.get('api_key'),
                "secret": self.credentials.get('secret_key'),
                "enableRateLimit": True,
                "options": {
                    "defaultType": "future",  # USDT-M futures
                }
            })
            
            if self.demo_mode:
                exchange.set_sandbox_mode(True)
            
            logger.info(f"Binance exchange initialized (demo={self.demo_mode})")
            return exchange
        except Exception as e:
            logger.error(f"Binance exchange initialization failed: {e}")
            raise
    
    def format_symbol(self, symbol: str) -> str:
        """
        Format symbol for Binance.
        BTC/USDT stays as BTC/USDT (no suffix needed)
        """
        # Remove any suffix if present
        if ':' in symbol:
            symbol = symbol.split(':')[0]
        return symbol
    
    # ==================== ORDER CREATION ====================
    
    def create_market_order(self, symbol: str, side: str, amount: float,
                           amount_in_dollars: bool = False) -> Dict[str, Any]:
        """Create market order on Binance."""
        formatted_symbol = self.format_symbol(symbol)
        
        try:
            if amount_in_dollars:
                # Convert dollars to coins using current price
                price = self.get_current_price(symbol)
                amount = amount / price
            
            order = self.exchange.create_order(
                formatted_symbol,
                'market',
                side.lower(),
                amount
            )
            logger.info(f"Binance market order created: {side} {amount} {symbol}")
            return order
        except Exception as e:
            logger.error(f"Binance create_market_order failed: {e}")
            raise
    
    def create_limit_order(self, symbol: str, side: str, amount: float,
                          price: float) -> Dict[str, Any]:
        """Create limit order on Binance."""
        formatted_symbol = self.format_symbol(symbol)
        
        try:
            order = self.exchange.create_order(
                formatted_symbol,
                'limit',
                side.lower(),
                amount,
                price,
                params={'timeInForce': 'GTC'}  # Binance-specific
            )
            logger.info(f"Binance limit order created: {side} {amount} @ {price} {symbol}")
            return order
        except Exception as e:
            logger.error(f"Binance create_limit_order failed: {e}")
            raise
    
    # ==================== ORDER MANAGEMENT ====================
    
    def fetch_open_orders(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch open orders from Binance."""
        formatted_symbol = self.format_symbol(symbol)
        return self.exchange.fetch_open_orders(formatted_symbol)
    
    def fetch_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        """Fetch specific order from Binance."""
        formatted_symbol = self.format_symbol(symbol)
        return self.exchange.fetch_order(order_id, symbol=formatted_symbol)
    
    def cancel_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        """Cancel order on Binance."""
        formatted_symbol = self.format_symbol(symbol)
        return self.exchange.cancel_order(order_id, formatted_symbol)
    
    def cancel_all_orders(self, symbol: str) -> None:
        """Cancel all open orders on Binance."""
        formatted_symbol = self.format_symbol(symbol)
        logger.info(f"Cancelling all orders for {formatted_symbol}")
        self.exchange.cancel_all_orders(symbol=formatted_symbol)
    
    # ==================== POSITION MANAGEMENT ====================
    
    def fetch_positions(self, symbol: str = None) -> List[Dict[str, Any]]:
        """Fetch positions from Binance."""
        if symbol:
            formatted = self.format_symbol(symbol)
            return self.exchange.fetch_positions(symbols=[formatted])
        return self.exchange.fetch_positions()
    
    def fetch_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch single position for symbol."""
        formatted_symbol = self.format_symbol(symbol)
        try:
            positions = self.exchange.fetch_positions(symbols=[formatted_symbol])
            return positions[0] if positions else None
        except Exception:
            return None
    
    def close_position(self, symbol: str, side: str, amount: float) -> Dict[str, Any]:
        """Close position on Binance."""
        formatted_symbol = self.format_symbol(symbol)
        close_side = 'BUY' if side.lower() == 'short' else 'SELL'
        
        try:
            order = self.exchange.create_order(
                symbol=formatted_symbol,
                type='MARKET',
                side=close_side,
                amount=amount,
                params={'reduceOnly': True}
            )
            logger.info(f"Binance position closed: {side} {amount} {symbol}")
            return order
        except Exception as e:
            logger.error(f"Binance close_position failed: {e}")
            raise
    
    def get_position_pnl(self, symbol: str) -> Dict[str, float]:
        """Get position PnL info."""
        position = self.fetch_position(symbol)
        
        if position:
            size = abs(float(position.get('contracts', 0)))
            pnl = float(position.get('unrealizedPnl', 0))
            entry = float(position.get('entryPrice', 0))
            percentage = (pnl / (size * entry) * 100) if (size * entry) > 0 else 0
            
            return {
                'size': size,
                'unrealized_pnl': pnl,
                'percentage': percentage,
                'side': position.get('side', 'none')
            }
        
        return {'size': 0, 'unrealized_pnl': 0, 'percentage': 0, 'side': 'none'}
