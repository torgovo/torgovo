"""
Bot Engine - Professional Trading Execution

Single entry point for all bot operations. Replaces old TradingManager
and provides clean interface for TradingView webhooks, grid management,
and performance tracking.

Designed for long-term maintainability by development teams.
"""
import logging
import time
import threading
from decimal import Decimal
from typing import Optional, Dict, Any
from django.db import close_old_connections

from ..managers.execution import BotExecutor
from ..models import TradingBot

logger = logging.getLogger('trading.engines')


class BotEngine:
    """
    Trading Bot Engine
    
    Provides the exact same interface as the old bot system but with
    modern architecture underneath:
    - TradingView webhooks: update_indicator() + execute_once()
    - Grid management: start_grid_management() with background thread
    - State tracking: Uses Django ORM instead of memory
    
    Usage:
        engine = BotEngine(trading_bot_instance)
        engine.update_indicator('EMA', 45000)
        engine.execute_once()
        engine.start_grid_management()
    """
    
    def __init__(self, trading_bot: TradingBot):
        """
        Initialize engine with a TradingBot model instance.
        
        Args:
            trading_bot: Django TradingBot model instance
        """
        self.bot = trading_bot
        self.executor = BotExecutor.from_bot_instance(trading_bot)
        
        # Indicator cache (mimics old bot.EMA = value pattern)
        self._indicator_cache: Dict[str, Any] = {}
        
        # Grid management thread
        self._management_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # Performance metrics
        self.signals_generated = 0
        self.orders_executed = 0
        
        logger.info(f"✅ BotEngine initialized for {trading_bot.name}")
    
    # =========================================================================
    # INDICATOR INTERFACE (For TradingView Webhooks)
    # =========================================================================
    
    @property
    def EMA(self) -> Optional[float]:
        """Get cached EMA value"""
        return self._indicator_cache.get('EMA')
    
    @EMA.setter
    def EMA(self, value: float):
        """Set EMA value from TradingView"""
        self._indicator_cache['EMA'] = float(value)
    
    @property
    def RSI(self) -> Optional[float]:
        """Get cached RSI value"""
        return self._indicator_cache.get('RSI')
    
    @RSI.setter
    def RSI(self, value: float):
        """Set RSI value from TradingView"""
        self._indicator_cache['RSI'] = float(value)
    
    @property
    def PrevRSI(self) -> Optional[float]:
        """Get cached previous RSI value"""
        return self._indicator_cache.get('PrevRSI')
    
    @PrevRSI.setter
    def PrevRSI(self, value: float):
        """Set previous RSI value from TradingView"""
        self._indicator_cache['PrevRSI'] = float(value)
    
    @property
    def RSI_color(self) -> Optional[str]:
        """Get cached RSI color (white/red/green)"""
        return self._indicator_cache.get('RSI_color')
    
    @RSI_color.setter
    def RSI_color(self, color: str):
        """Set RSI color from TradingView"""
        self._indicator_cache['RSI_color'] = color
    
    @property
    def RSI_prev_color(self) -> Optional[str]:
        """Get cached previous RSI color"""
        return self._indicator_cache.get('RSI_prev_color')
    
    @RSI_prev_color.setter
    def RSI_prev_color(self, color: str):
        """Set previous RSI color from TradingView"""
        self._indicator_cache['RSI_prev_color'] = color
    
    @property
    def BB(self) -> Optional[str]:
        """Get cached Bollinger Bands signal"""
        return self._indicator_cache.get('BB')
    
    @BB.setter
    def BB(self, signal: str):
        """Set Bollinger Bands signal from TradingView"""
        self._indicator_cache['BB'] = signal
    
    # =========================================================================
    # OLD BOT PROPERTIES (For Template Context)
    # =========================================================================
    
    @property
    def symbol(self) -> str:
        """Trading pair symbol (BTC/USDT)"""
        return self.bot.symbol
    
    @property
    def current_price(self) -> float:
        """Current market price (fetched from exchange)"""
        try:
            return self.executor.adapter.get_current_price(self.bot.symbol)
        except Exception:
            return 0.0
    
    @property
    def current_side(self) -> str:
        """Current position side: 'Buy', 'Sell', or 'None'"""
        try:
            positions = self.executor.adapter.fetch_positions(self.bot.symbol)
            if positions:
                side = positions[0].get('side', '').lower()
                return 'Buy' if side == 'long' else 'Sell'
            return 'None'
        except Exception:
            return 'None'
    
    @property
    def count(self) -> int:
        """Trade state: 1 = in trade, 0 = no trade"""
        try:
            positions = self.executor.adapter.fetch_positions(self.bot.symbol)
            return 1 if positions else 0
        except Exception:
            return 0
    
    @property
    def monitoring(self) -> bool:
        """Is grid management running?"""
        return self._management_thread is not None and self._management_thread.is_alive()
    
    @property
    def favor_lvl(self) -> list:
        """Favor (take-profit) grid levels"""
        return getattr(self.executor.strategy, 'favor_levels', [])
    
    @property
    def against_lvl(self) -> list:
        """Against (DCA) grid levels"""
        return getattr(self.executor.strategy, 'against_levels', [])
    
    @property
    def Percentage(self) -> float:
        """Current PnL percentage"""
        try:
            positions = self.executor.adapter.fetch_positions(self.bot.symbol)
            if positions:
                pos = positions[0]
                return float(pos.get('percentage', 0))
            return 0.0
        except Exception:
            return 0.0
    
    @property
    def Unrealized_Pnl(self) -> float:
        """Current unrealized PnL in USD"""
        try:
            positions = self.executor.adapter.fetch_positions(self.bot.symbol)
            if positions:
                return float(positions[0].get('unrealizedPnl', 0))
            return 0.0
        except Exception:
            return 0.0
    
    @property
    def pair_config(self) -> Dict[str, Any]:
        """Mimics old pair_config.data for template compatibility"""
        return {
            'pair_symbol': self.bot.symbol,
            'quantity': float(self.bot.position_size),
            'favor_levels': self.bot.custom_parameters.get('favor_levels', 3),
            'against_levels': self.bot.custom_parameters.get('against_levels', 3),
            'favor_level_qty': self.bot.custom_parameters.get('favor_level_qty', 5),
            'against_level_qty': self.bot.custom_parameters.get('against_level_qty', 5),
            **self.bot.custom_parameters
        }
    
    @pair_config.setter
    def pair_config(self, value: Dict):
        """No-op setter for compatibility (actual config stored in DB)"""
        pass
    
    # =========================================================================
    # MAIN EXECUTION METHODS
    # =========================================================================
    
    def execute_once(self) -> Dict[str, Any]:
        """
        Execute strategy once (for webhooks).
        If signal generated, automatically start grid management.
        
        Returns:
            Dict with execution result
        """
        result = {
            'success': False,
            'signal': None,
            'order': None,
            'error': None,
        }
        
        try:
            # Fetch market data (OHLCV for indicator calculations)
            market_data = self._fetch_market_data()
            
            # Get account info
            account_info = self.executor.adapter.get_account_info()
            
            # Get current position
            positions = self.executor.adapter.fetch_positions(self.bot.symbol)
            current_position = positions[0] if positions else None
            
            # Execute strategy with cached indicators
            signal = self.executor.strategy.execute_with_indicators(
                market_data=market_data,
                account_info=account_info,
                indicators=self._indicator_cache
            )
            
            if signal and signal.action != 'hold':
                result['signal'] = signal.to_dict()
                
                # Execute order
                order = self.executor.adapter.execute_order(signal.to_dict())
                result['order'] = order
                
                # Update bot stats
                self.signals_generated += 1
                
                # Start grid management if entry signal
                if 'entry' in signal.reason.lower():
                    self.start_grid_management()
            
            result['success'] = True
            
        except Exception as e:
            logger.error(f"Execute once error: {e}", exc_info=True)
            result['error'] = str(e)
        
        return result
    
    def update_conditions(self):
        """
        Legacy method name - kept for compatibility.
        Old views call bot.update_conditions()
        """
        return self.execute_once()
    
    # =========================================================================
    # GRID MANAGEMENT
    # =========================================================================
    
    def start_grid_management(self, interval_seconds: float = 2):
        """
        Start the grid management loop in a background thread.
        Replaces old TradingManager's thread management.
        
        Args:
            interval_seconds: How often to check grid levels (default: 2 sec)
        """
        if self.monitoring:
            logger.warning(f"Grid management already running for {self.bot.symbol}")
            return
        
        self._stop_event.clear()
        self._management_thread = threading.Thread(
            target=self._grid_management_loop,
            args=(interval_seconds,),
            daemon=True,
            name=f"GridMgmt-{self.bot.symbol.replace('/', '')}"
        )
        self._management_thread.start()
        
        logger.info(
            f"🔄 Grid management started for {self.bot.symbol} "
            f"(interval: {interval_seconds}s)"
        )
    
    def stop_grid_management(self):
        """Stop the grid management loop."""
        if not self.monitoring:
            logger.warning(f"Grid management not running for {self.bot.symbol}")
            return
        
        self._stop_event.set()
        self._management_thread.join(timeout=5)
        
        logger.info(f"⏹️ Grid management stopped for {self.bot.symbol}")
    
    def _grid_management_loop(self, interval_seconds: float):
        """
        Background thread: manages grid orders.
        This is your old manage_grid_orders() logic.
        """
        consecutive_errors = 0
        
        while not self._stop_event.is_set():
            try:
                # Clean DB connections (critical for threads)
                close_old_connections()
                
                # Check and manage grid levels
                self._manage_grid_orders()
                
                # Reset error counter on success
                consecutive_errors = 0
                
                # Sleep with stop event check
                self._stop_event.wait(timeout=interval_seconds)
                
            except Exception as e:
                consecutive_errors += 1
                logger.error(
                    f"Grid mgmt error ({consecutive_errors}): {e}",
                    exc_info=True
                )
                
                # Stop after 5 consecutive errors
                if consecutive_errors >= 5:
                    logger.error(f"Stopping grid mgmt after 5 errors")
                    break
                
                # Exponential backoff
                time.sleep(min(30, 2 ** consecutive_errors))
        
        logger.info(f"Grid management loop exited for {self.bot.symbol}")
    
    def _manage_grid_orders(self):
        """
        Core grid management logic (your old implementation).
        Checks if price hit favor/against levels and executes.
        """
        symbol = self.bot.symbol
        current_price = self.executor.adapter.get_current_price(symbol)
        
        # Get open positions and orders
        positions = self.executor.adapter.fetch_positions(symbol)
        open_orders = self.executor.adapter.fetch_open_orders(symbol)
        
        # Check favor levels (take profit)
        favor_levels = getattr(self.executor.strategy, 'favor_levels', [])
        for level_price in favor_levels:
            if self._should_trigger_level(current_price, level_price):
                self._execute_favor_level(level_price, positions, open_orders)
        
        # Check against levels (DCA/add to position)
        against_levels = getattr(self.executor.strategy, 'against_levels', [])
        for level_price in against_levels:
            if self._should_trigger_level(current_price, level_price):
                self._execute_against_level(level_price, positions, open_orders)
    
    def _should_trigger_level(self, current_price: float, level_price: float) -> bool:
        """
        Check if price reached a grid level (±0.05% tolerance).
        Matches old behavior exactly.
        """
        if level_price <= 0 or current_price <= 0:
            return False
        
        tolerance = 0.0005  # 0.05%
        diff = abs(current_price - level_price) / level_price
        return diff <= tolerance
    
    def _execute_favor_level(self, level_price: float, positions, open_orders):
        """Execute take-profit at favor level."""
        symbol = self.bot.symbol
        
        # Find if we have an order at this level already
        for order in open_orders:
            if abs(float(order.get('price', 0)) - level_price) / level_price <= 0.001:
                logger.debug(f"Order already exists at {level_price}")
                return
        
        # Create take-profit order
        # (Your old logic here - modify as needed)
        try:
            position = positions[0] if positions else None
            if not position:
                return
            
            side = 'sell' if position['side'].lower() == 'long' else 'buy'
            amount = float(position.get('contracts', 0))
            
            if amount > 0:
                order = self.executor.adapter.create_limit_order(
                    symbol=symbol,
                    side=side,
                    amount=amount,
                    price=level_price,
                    params={'reduceOnly': True}
                )
                logger.info(f"✅ Favor level order: {order}")
        except Exception as e:
            logger.error(f"Favor level execution error: {e}", exc_info=True)
    
    def _execute_against_level(self, level_price: float, positions, open_orders):
        """Execute DCA/add to position at against level."""
        symbol = self.bot.symbol
        
        # Check if order exists
        for order in open_orders:
            if abs(float(order.get('price', 0)) - level_price) / level_price <= 0.001:
                logger.debug(f"Order already exists at {level_price}")
                return
        
        # Create DCA order
        # (Your old logic here - modify as needed)
        try:
            position = positions[0] if positions else None
            params = self.executor.strategy.parameters
            
            # Determine side
            if position:
                side = 'buy' if position['side'].lower() == 'long' else 'sell'
            else:
                # New position - use favor_levels to determine
                favor_levels = getattr(self.executor.strategy, 'favor_levels', [])
                side = 'buy' if level_price < min(favor_levels) else 'sell'
            
            amount = params.get('against_level_qty', 5)
            
            order = self.executor.adapter.create_limit_order(
                symbol=symbol,
                side=side,
                amount=amount,
                price=level_price
            )
            logger.info(f"✅ Against level order: {order}")
        except Exception as e:
            logger.error(f"Against level execution error: {e}", exc_info=True)
    
    # =========================================================================
    # DATA FETCHING
    # =========================================================================
    
    def _fetch_market_data(self) -> Dict[str, Any]:
        """Fetch OHLCV and ticker data for strategy execution."""
        return {
            'ticker': self.executor.adapter.fetch_ticker(self.bot.symbol),
            'ohlcv': self.executor.adapter.fetch_ohlcv(self.bot.symbol, '1h', limit=100),
        }
    
    # =========================================================================
    # STATUS & METRICS
    # =========================================================================
    
    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive bot status."""
        return {
            'bot_name': self.bot.name,
            'symbol': self.bot.symbol,
            'exchange': self.bot.exchange_credentials.exchange_name,
            'is_running': self.monitoring,
            'current_side': self.current_side,
            'current_price': self.current_price,
            'percentage_pnl': self.Percentage,
            'unrealized_pnl': self.Unrealized_Pnl,
            'signals_generated': self.signals_generated,
            'orders_executed': self.orders_executed,
            'favor_levels': list(self.favor_lvl),
            'against_levels': list(self.against_lvl),
            'indicators': dict(self._indicator_cache),
        }
    
    def __str__(self) -> str:
        return f"BotEngine({self.bot.name})"
    
    def __repr__(self) -> str:
        return f"BotEngine(bot={self.bot.id}, symbol={self.bot.symbol})"