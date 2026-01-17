"""
Bybit Exchange Adapter
Implements BaseExchangeAdapter for Bybit-specific API calls
"""
import ccxt
import logging
from typing import Dict, Any, List, Optional
from .base import BaseExchangeAdapter

logger = logging.getLogger('trading.adapters.bybit')


class BybitAdapter(BaseExchangeAdapter):
    """
    Bybit exchange adapter.
    Handles all Bybit-specific API syntax and parameters.
    
    Bybit Specifics:
    - Futures symbols need :USDT suffix (BTC/USDT -> BTC/USDT:USDT)
    - Requires 'category': 'linear' param for USDT perpetual futures
    - Supports create_market_order_with_cost for dollar-based orders
    - Demo trading via enable_demo_trading()
    """
    
    @property
    def exchange_name(self) -> str:
        return 'bybit'
    
    def _initialize_exchange(self):
        """Initialize Bybit CCXT exchange instance."""
        try:
            exchange = ccxt.bybit({
                "apiKey": self.credentials.get('api_key'),
                "secret": self.credentials.get('secret_key'),
                "enableRateLimit": True,
                "options": {
                    "defaultType": "linear",  # USDT perpetual futures
                    "trade.type": "linear",
                }
            })
            
            if self.demo_mode:
                exchange.enable_demo_trading(True)
            
            logger.info(f"Bybit exchange initialized (demo={self.demo_mode})")
            return exchange
        except Exception as e:
            logger.error(f"Bybit exchange initialization failed: {e}")
            raise
    
    def format_symbol(self, symbol: str) -> str:
        """
        Format symbol for Bybit futures.
        BTC/USDT -> BTC/USDT:USDT
        """
        if ':' not in symbol:
            quote_currency = symbol.split('/')[1] if '/' in symbol else 'USDT'
            return f"{symbol}:{quote_currency}"
        return symbol
    
    def _get_closing_symbol(self, symbol: str) -> str:
        """Get symbol format for closing positions (removes /)."""
        formatted = self.format_symbol(symbol)
        return formatted.replace('/', '')
    
    # ==================== ORDER CREATION ====================
    
    def create_market_order(self, symbol: str, side: str, amount: float,
                           amount_in_dollars: bool = False) -> Dict[str, Any]:
        """
        Create market order on Bybit.
        
        Bybit-specific: Uses create_market_order_with_cost for dollar amounts.
        """
        formatted_symbol = self.format_symbol(symbol)
        
        try:
            if amount_in_dollars:
                # Use cost-based order for dollar amounts
                if side.lower() == 'buy':
                    order = self.exchange.create_market_buy_order_with_cost(
                        formatted_symbol,
                        cost=amount,
                        params={'category': 'linear'}
                    )
                else:
                    order = self.exchange.create_market_sell_order_with_cost(
                        formatted_symbol,
                        cost=amount,
                        params={'category': 'linear'}
                    )
            else:
                # Standard coin-based order
                order = self.exchange.create_order(
                    formatted_symbol,
                    'market',
                    side.lower(),
                    amount,
                    None,
                    params={'category': 'linear'}
                )
            
            logger.info(f"Bybit market order created: {side} {amount} {symbol}")
            return order
        except Exception as e:
            logger.error(f"Bybit create_market_order failed: {e}")
            raise
    
    def create_limit_order(self, symbol: str, side: str, amount: float,
                          price: float) -> Dict[str, Any]:
        """Create limit order on Bybit."""
        formatted_symbol = self.format_symbol(symbol)
        
        try:
            order = self.exchange.create_order(
                formatted_symbol,
                'limit',
                side.lower(),
                amount,
                price,
                params={'category': 'linear'}
            )
            logger.info(f"Bybit limit order created: {side} {amount} @ {price} {symbol}")
            return order
        except Exception as e:
            logger.error(f"Bybit create_limit_order failed: {e}")
            raise
    
    # ==================== ORDER MANAGEMENT ====================
    
    def fetch_open_orders(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch open orders from Bybit."""
        formatted_symbol = self.format_symbol(symbol)
        return self.exchange.fetch_open_orders(
            formatted_symbol,
            params={'category': 'linear'}
        )
    
    def fetch_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        """Fetch specific order from Bybit."""
        formatted_symbol = self.format_symbol(symbol)
        return self.exchange.fetch_order(
            order_id,
            symbol=formatted_symbol,
            params={'category': 'linear'}
        )
    
    def cancel_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        """Cancel order on Bybit."""
        formatted_symbol = self.format_symbol(symbol)
        return self.exchange.cancel_order(
            order_id,
            formatted_symbol,
            params={'category': 'linear'}
        )
    
    def cancel_all_orders(self, symbol: str) -> None:
        """Cancel all open orders on Bybit."""
        closing_symbol = self._get_closing_symbol(symbol)
        logger.info(f"Cancelling all orders for {closing_symbol}")
        self.exchange.cancel_all_orders(symbol=closing_symbol)
    
    # ==================== POSITION MANAGEMENT ====================
    
    def fetch_positions(self, symbol: str = None) -> List[Dict[str, Any]]:
        """Fetch positions from Bybit."""
        if symbol:
            closing_symbol = self._get_closing_symbol(symbol)
            return self.exchange.fetch_positions(
                symbols=closing_symbol,
                params={'category': 'linear'}
            )
        return self.exchange.fetch_positions(params={'category': 'linear'})
    
    def fetch_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch single position for symbol."""
        formatted_symbol = self.format_symbol(symbol)
        try:
            return self.exchange.fetch_position(
                symbol=formatted_symbol,
                params={'category': 'linear'}
            )
        except Exception:
            return None
    
    def close_position(self, symbol: str, side: str, amount: float) -> Dict[str, Any]:
        """
        Close position on Bybit.
        
        Args:
            symbol: Trading pair
            side: Current position side ('long' or 'short')
            amount: Position size to close
        """
        closing_symbol = self._get_closing_symbol(symbol)
        
        # Opposite side to close
        close_side = 'buy' if side.lower() == 'short' else 'sell'
        
        try:
            order = self.exchange.create_order(
                symbol=closing_symbol,
                type='market',
                side=close_side,
                amount=amount,
                params={'reduceOnly': True}
            )
            logger.info(f"Bybit position closed: {side} {amount} {symbol}")
            return order
        except Exception as e:
            logger.error(f"Bybit close_position failed: {e}")
            raise
    
    def get_position_pnl(self, symbol: str) -> Dict[str, float]:
        """Get position PnL info."""
        position = self.fetch_position(symbol)
        
        if position:
            size = float(position.get('notional', 0))
            pnl = float(position.get('unrealizedPnl', 0))
            percentage = (pnl / size * 100) if size > 0 else 0
            
            return {
                'size': size,
                'unrealized_pnl': pnl,
                'percentage': percentage,
                'side': position.get('side', 'none')
            }
        
        return {'size': 0, 'unrealized_pnl': 0, 'percentage': 0, 'side': 'none'}
