"""
Quantum AI Trading Strategy

Core logic extracted from oldbybit.py and apps/exchanges/handlers/bybitbot.py.
This is a grid-based strategy that uses multiple technical indicators (EMA, RSI, BB)
to generate entry signals and manages positions with grid orders.

PURE PYTHON - NO DJANGO IMPORTS
"""
import logging
from typing import Dict, Any, Optional, List, Tuple
from decimal import Decimal
from datetime import datetime

from .base import BaseStrategy, Signal

logger = logging.getLogger('trading.strategies.quantum_ai')


class QuantumAIStrategy(BaseStrategy):
    """
    Quantum AI Trading Strategy.

    Uses a combination of technical indicators:
    - EMA (Exponential Moving Average) - trend direction
    - RSI (Relative Strength Index) - overbought/oversold conditions
    - Bollinger Bands (BB) - volatility and mean reversion signals

    The strategy combines these indicators in 6 different cases for entry
    and manages positions with a grid of limit orders for favor/against levels.

    Parameters (from pair_config):
        - symbol: Trading pair (e.g., 'BTC/USDT')
        - quantity: Initial position size
        - Amount_Type: 'dollar' or 'coin'
        - Order_Type: 'market' or 'limit'
        - RSI_Lower: RSI oversold threshold (default: 30)
        - RSI_Upper: RSI overbought threshold (default: 70)
        - favor_levels: Number of take-profit grid levels
        - against_levels: Number of DCA/averaging grid levels
        - favor_level_qty: Quantity per favor level
        - against_level_qty: Quantity per against level
        - favor_level_difference: Percentage spacing for favor levels
        - against_level_difference: Percentage spacing for against levels
        - Stop_Loss: Stop loss value
        - Take_Profit: Take profit value
        - SLTP_Type: 'percentage' or 'dollars'

        Entry Config Parameters:
        - EMA_RSI_Entry: 'buy', 'sell', 'both', or 'none'
        - EMA_BB_Entry: 'buy', 'sell', 'both', or 'none'
        - BB_RSI_Entry: 'buy', 'sell', 'both', or 'none'
        - RSI_Entry: 'buy', 'sell', 'both', or 'none'
        - BB_Entry: 'buy', 'sell', 'both', or 'none'
        - EMA_BB_RSI_Entry: 'buy', 'sell', 'both', or 'none'

        Exit Config Parameters:
        - RSI_Exit: 'tp', 'sl', 'both', or 'none'
        - BB_Exit: 'tp', 'sl', 'both', or 'none'
        - BB_RSI_Exit: 'tp', 'sl', 'both', or 'none'
        - EMA_BB_Exit: 'tp', 'sl', 'both', or 'none'
    """

    

    @property
    def name(self) -> str:
        return 'Quantum AI'

    @property
    def required_parameters(self) -> List[str]:
        return ['symbol']

    def __init__(self, parameters: Dict[str, Any] = None):
        """Initialize Quantum AI strategy with parameters."""
        # Default parameters matching oldbybit.py
        defaults = {
            'quantity': 10,  # Default $10 or 0.01 coins
            'Amount_Type': 'dollar',  # 'dollar' or 'coin'
            'Order_Type': 'market',
            'RSI_Lower': 30,
            'RSI_Upper': 70,
            'favor_levels': 5,
            'against_levels': 5,
            'favor_level_qty': 5,
            'against_level_qty': 5,
            'favor_level_difference': 0.5,  # 0.5% per level
            'against_level_difference': 0.5,
            'Stop_Loss': -2,  # -2% default
            'Take_Profit': 5,  # 5% default
            'SLTP_Type': 'percentage',  # 'percentage' or 'dollars'
            # Entry configurations
            'EMA_RSI_Entry': 'both',
            'EMA_BB_Entry': 'none',
            'BB_RSI_Entry': 'none',
            'RSI_Entry': 'none',
            'BB_Entry': 'none',
            'EMA_BB_RSI_Entry': 'none',
            # Exit configurations
            'RSI_Exit': 'none',
            'BB_Exit': 'tp',
            'BB_RSI_Exit': 'none',
            'EMA_BB_Exit': 'none',
        }
        merged_params = {**defaults, **(parameters or {})}
        super().__init__(merged_params)

        # Indicator state (will be updated from external source)
        self.EMA: float = 0.0
        self.RSI: float = 50.0
        self.PrevRSI: float = 50.0
        self.RSI_color: Optional[str] = None
        self.RSI_prev_color: Optional[str] = None
        self.BB: Optional[str] = None  # BB signal string

        # Trading state
        self.current_side: str = "None"  # "Buy", "Sell", or "None"
        self.count: int = 0  # 0 = no trade, 1 = in trade
        self.current_price: float = 0.0

        # Grid state
        self.favor_levels: List[float] = []
        self.against_levels: List[float] = []

        # Performance tracking
        self.Percentage: float = 0.0
        self.Unrealized_Pnl: float = 0.0
        self.last_trade_pnl: float = 0.0

    # =========================================================================
    # INDICATOR CONDITIONS
    # =========================================================================

    def update_indicators(self, indicators: Dict[str, Any]):
        """
        Update indicator values from external source.

        Args:
            indicators: Dict with keys: EMA, RSI, PrevRSI, RSI_color, RSI_prev_color, BB
        """
        self.EMA = float(indicators.get('EMA', 0.0))
        self.RSI = float(indicators.get('RSI', 50.0))
        self.PrevRSI = float(indicators.get('PrevRSI', 50.0))
        self.RSI_color = indicators.get('RSI_color')
        self.RSI_prev_color = indicators.get('RSI_prev_color')
        self.BB = indicators.get('BB')

    def _evaluate_conditions(self, current_price: float) -> Dict[str, bool]:
        """
        Evaluate all indicator conditions for the current price.

        Returns:
            Dict with all condition flags
        """
        self.current_price = current_price
        params = self.parameters

        # EMA conditions
        ema_buy = current_price >= self.EMA and self.EMA != 0
        ema_sell = current_price <= self.EMA and self.EMA != 0

        # RSI conditions
        rsi_buy = self.PrevRSI <= params['RSI_Lower'] and self.RSI_color == 'white'
        rsi_sell = self.PrevRSI >= params['RSI_Upper'] and self.RSI_color == 'white'

        # Bollinger Bands conditions
        bb_buy = self.BB in ["Crossing Down Band", "Closed Below Lower Band", "Up Arrow"]
        bb_sell = self.BB in ["Crossing Up Band", "Closed Above Upper Band", "Down Arrow"]

        # Trade state conditions
        no_trade = self.count == 0 and self.current_side == "None"
        buy_trade = self.count == 1 and self.current_side == "Buy"
        sell_trade = self.count == 1 and self.current_side == "Sell"

        return {
            'EMA_Buy': ema_buy,
            'EMA_Sell': ema_sell,
            'RSI_Buy': rsi_buy,
            'RSI_Sell': rsi_sell,
            'BB_Buy': bb_buy,
            'BB_Sell': bb_sell,
            'NoTrade': no_trade,
            'BuyTrade': buy_trade,
            'SellTrade': sell_trade,
        }

    # =========================================================================
    # MAIN EXECUTE METHOD
    # =========================================================================

    def execute(
        self,
        market_data: Dict[str, Any],
        account_info: Dict[str, Any],
        current_position: Optional[Dict[str, Any]] = None
    ) -> Optional[Signal]:
        """
        Execute Quantum AI strategy logic.

        This method implements the entry and exit logic from oldbybit.py startBot().

        Args:
            market_data: Dict with ticker, indicators, etc.
            account_info: Dict with balance info
            current_position: Dict with current position if any

        Returns:
            Signal if action should be taken, None otherwise
        """
        ticker = market_data.get('ticker', {})
        current_price = ticker.get('last', 0)
        if not current_price:
            return None

        # Update indicators if provided
        if 'indicators' in market_data:
            self.update_indicators(market_data['indicators'])

        # Sync state with current position
        self._sync_position_state(current_position)

        # Evaluate conditions
        conditions = self._evaluate_conditions(current_price)
        params = self.parameters
        symbol = params['symbol']

        # Check entry conditions (when no trade active)
        if conditions['NoTrade']:
            signal = self._check_entry_conditions(conditions, current_price, symbol)
            if signal:
                return signal

        # Check exit conditions (when in a trade)
        elif conditions['BuyTrade']:
            signal = self._check_buy_exit_conditions(conditions, current_price, symbol, current_position)
            if signal:
                return signal

        elif conditions['SellTrade']:
            signal = self._check_sell_exit_conditions(conditions, current_price, symbol, current_position)
            if signal:
                return signal

        return None

    def _sync_position_state(self, current_position: Optional[Dict[str, Any]]):
        """Sync internal state with actual position."""
        if current_position and float(current_position.get('contracts', 0)) != 0:
            side = current_position.get('side', '').lower()
            if side in ['long', 'buy']:
                self.current_side = "Buy"
                self.count = 1
            elif side in ['short', 'sell']:
                self.current_side = "Sell"
                self.count = 1
        else:
            self.current_side = "None"
            self.count = 0

    # =========================================================================
    # ENTRY CONDITIONS (from startBot)
    # =========================================================================

    def _check_entry_conditions(
        self,
        conditions: Dict[str, bool],
        current_price: float,
        symbol: str
    ) -> Optional[Signal]:
        """
        Check all 6 entry cases for buy and sell.
        Logic extracted from oldbybit.py startBot().
        """
        params = self.parameters

        # ===================== BUY CASES =====================

        # CASE 1: EMA + RSI
        if (conditions['EMA_Buy'] and conditions['RSI_Buy'] and
                params['EMA_RSI_Entry'] in ['buy', 'both']):
            return self._create_entry_signal('buy', symbol, current_price, 'EMA + RSI BUY LONG (CASE1)')

        # CASE 2: BB + EMA
        if (conditions['BB_Buy'] and conditions['EMA_Buy'] and
                params['EMA_BB_Entry'] in ['buy', 'both']):
            return self._create_entry_signal('buy', symbol, current_price, 'EMA + BOLLINGER BANDS BUY LONG (CASE2)')

        # CASE 3: BB + RSI
        if (conditions['RSI_Buy'] and conditions['BB_Buy'] and
                params['BB_RSI_Entry'] in ['buy', 'both']):
            return self._create_entry_signal('buy', symbol, current_price, 'BOLLINGER BANDS + RSI BUY LONG (CASE3)')

        # CASE 4: RSI Only
        if (conditions['RSI_Buy'] and
                params['RSI_Entry'] in ['buy', 'both']):
            return self._create_entry_signal('buy', symbol, current_price, 'RSI ONLY BUY LONG (CASE4)')

        # CASE 5: BB Only
        if (conditions['BB_Buy'] and
                params['BB_Entry'] in ['buy', 'both']):
            return self._create_entry_signal('buy', symbol, current_price, 'BOLLINGER BANDS ONLY BUY LONG (CASE5)')

        # CASE 6: EMA + RSI + BB
        if (conditions['EMA_Buy'] and conditions['RSI_Buy'] and conditions['BB_Buy'] and
                params['EMA_BB_RSI_Entry'] in ['buy', 'both']):
            return self._create_entry_signal('buy', symbol, current_price, 'EMA + RSI + BOLLINGER BANDS BUY LONG (CASE6)')

        # ===================== SELL CASES =====================

        # CASE 1: EMA + RSI
        if (conditions['EMA_Sell'] and conditions['RSI_Sell'] and
                params['EMA_RSI_Entry'] in ['sell', 'both']):
            return self._create_entry_signal('sell', symbol, current_price, 'EMA + RSI SELL SHORT (CASE1)')

        # CASE 2: BB + EMA
        if (conditions['BB_Sell'] and conditions['EMA_Sell'] and
                params['EMA_BB_Entry'] in ['sell', 'both']):
            return self._create_entry_signal('sell', symbol, current_price, 'EMA + BOLLINGER BANDS SELL SHORT (CASE2)')

        # CASE 3: BB + RSI
        if (conditions['BB_Sell'] and conditions['RSI_Sell'] and
                params['BB_RSI_Entry'] in ['sell', 'both']):
            return self._create_entry_signal('sell', symbol, current_price, 'BOLLINGER BANDS + RSI SELL SHORT (CASE3)')

        # CASE 4: RSI Only
        if (conditions['RSI_Sell'] and
                params['RSI_Entry'] in ['sell', 'both']):
            return self._create_entry_signal('sell', symbol, current_price, 'RSI ONLY SELL SHORT (CASE4)')

        # CASE 5: BB Only
        if (conditions['BB_Sell'] and
                params['BB_Entry'] in ['sell', 'both']):
            return self._create_entry_signal('sell', symbol, current_price, 'BOLLINGER BANDS ONLY SELL SHORT (CASE5)')

        # CASE 6: EMA + RSI + BB
        if (conditions['EMA_Sell'] and conditions['RSI_Sell'] and conditions['BB_Sell'] and
                params['EMA_BB_RSI_Entry'] in ['sell', 'both']):
            return self._create_entry_signal('sell', symbol, current_price, 'EMA + RSI + BOLLINGER BANDS SELL SHORT (CASE6)')

        return None

    def _create_entry_signal(
        self,
        action: str,
        symbol: str,
        current_price: float,
        reason: str
    ) -> Signal:
        """Create an entry signal with grid order data."""
        params = self.parameters

        # Calculate quantity
        if params['Amount_Type'] == 'dollar':
            quantity = params['quantity'] / current_price
        else:
            quantity = params['quantity']

        # Calculate grid levels
        favor_levels, against_levels = self.calculate_grids(action, current_price)
        self.favor_levels = favor_levels
        self.against_levels = against_levels

        # Update state
        self.current_side = "Buy" if action == 'buy' else "Sell"
        self.count = 1
        self.signals_generated += 1

        signal = Signal(
            action=action,
            symbol=symbol,
            amount=quantity,
            price=current_price if params['Order_Type'] == 'limit' else None,
            order_type=params['Order_Type'],
            reason=reason,
            metadata={
                'strategy': 'quantum_ai',
                'entry_case': reason,
                'favor_levels': favor_levels,
                'against_levels': against_levels,
                'favor_level_qty': params['favor_level_qty'],
                'against_level_qty': params['against_level_qty'],
                'Amount_Type': params['Amount_Type'],
                'indicators': {
                    'EMA': self.EMA,
                    'RSI': self.RSI,
                    'BB': self.BB,
                }
            }
        )
        self.last_signal = signal
        return signal

    # =========================================================================
    # EXIT CONDITIONS
    # =========================================================================

    def _check_buy_exit_conditions(
        self,
        conditions: Dict[str, bool],
        current_price: float,
        symbol: str,
        current_position: Optional[Dict[str, Any]]
    ) -> Optional[Signal]:
        """Check take-profit conditions for long positions."""
        params = self.parameters

        # TP CASE 1: BB Only
        if (conditions['BB_Sell'] and params['BB_Exit'] in ['tp', 'both']):
            return self._create_exit_signal('sell', symbol, current_position, 'BOLLINGER BANDS TP (BUY CASE1)')

        # TP CASE 2: RSI Only
        if (conditions['RSI_Sell'] and params['RSI_Exit'] in ['tp', 'both']):
            return self._create_exit_signal('sell', symbol, current_position, 'RSI TP (BUY CASE2)')

        # TP CASE 3: BB + RSI
        if (conditions['RSI_Sell'] and conditions['BB_Sell'] and
                params['BB_RSI_Exit'] in ['tp', 'both']):
            return self._create_exit_signal('sell', symbol, current_position, 'BOLLINGER BANDS + RSI TP (BUY CASE3)')

        # TP CASE 4: EMA + BB
        if (conditions['BB_Sell'] and (conditions['EMA_Sell'] or conditions['EMA_Buy']) and
                params['EMA_BB_Exit'] in ['tp', 'both']):
            return self._create_exit_signal('sell', symbol, current_position, 'EMA + BOLLINGER BANDS TP (BUY CASE4)')

        # Check percentage-based stop loss / take profit
        sltp_signal = self._check_sltp_exit(current_position, current_price, 'long', symbol)
        if sltp_signal:
            return sltp_signal

        return None

    def _check_sell_exit_conditions(
        self,
        conditions: Dict[str, bool],
        current_price: float,
        symbol: str,
        current_position: Optional[Dict[str, Any]]
    ) -> Optional[Signal]:
        """Check take-profit conditions for short positions."""
        params = self.parameters

        # TP CASE 1: RSI Only
        if (conditions['RSI_Buy'] and params['RSI_Exit'] in ['tp', 'both']):
            return self._create_exit_signal('buy', symbol, current_position, 'RSI TP (SELL CASE1)')

        # TP CASE 2: BB + RSI
        if (conditions['BB_Buy'] and conditions['RSI_Buy'] and
                params['BB_RSI_Exit'] in ['tp', 'both']):
            return self._create_exit_signal('buy', symbol, current_position, 'BOLLINGER BANDS + RSI TP (SELL CASE2)')

        # TP CASE 3: BB Only
        if (conditions['BB_Buy'] and params['BB_Exit'] in ['tp', 'both']):
            return self._create_exit_signal('buy', symbol, current_position, 'BOLLINGER BANDS TP (SELL CASE3)')

        # TP CASE 4: EMA + BB
        if (conditions['EMA_Buy'] and conditions['BB_Buy'] and
                params['EMA_BB_Exit'] in ['tp', 'both']):
            return self._create_exit_signal('buy', symbol, current_position, 'EMA + BOLLINGER BANDS TP (SELL CASE4)')

        # Check percentage-based stop loss / take profit
        sltp_signal = self._check_sltp_exit(current_position, current_price, 'short', symbol)
        if sltp_signal:
            return sltp_signal

        return None

    def _check_sltp_exit(
        self,
        current_position: Optional[Dict[str, Any]],
        current_price: float,
        side: str,
        symbol: str
    ) -> Optional[Signal]:
        """Check percentage-based SL/TP conditions."""
        if not current_position:
            return None

        params = self.parameters
        entry_price = float(current_position.get('entry_price', 0))
        contracts = abs(float(current_position.get('contracts', 0)))
        unrealized_pnl = float(current_position.get('unrealized_pnl', 0))

        if entry_price <= 0 or contracts <= 0:
            return None

        # Calculate percentage PnL
        if params['SLTP_Type'] == 'percentage':
            notional = contracts * current_price
            if notional > 0:
                pnl_pct = (unrealized_pnl / notional) * 100
            else:
                pnl_pct = 0

            # Check stop loss
            if pnl_pct <= params['Stop_Loss']:
                close_side = 'sell' if side == 'long' else 'buy'
                return self._create_exit_signal(
                    close_side, symbol, current_position,
                    f'STOP LOSS HIT ({pnl_pct:.2f}%)'
                )

            # Check take profit
            if pnl_pct >= params['Take_Profit']:
                close_side = 'sell' if side == 'long' else 'buy'
                return self._create_exit_signal(
                    close_side, symbol, current_position,
                    f'TAKE PROFIT HIT ({pnl_pct:.2f}%)'
                )

        elif params['SLTP_Type'] == 'dollars':
            # Check dollar-based SL/TP
            if unrealized_pnl <= params['Stop_Loss']:
                close_side = 'sell' if side == 'long' else 'buy'
                return self._create_exit_signal(
                    close_side, symbol, current_position,
                    f'STOP LOSS HIT (${unrealized_pnl:.2f})'
                )

            if unrealized_pnl >= params['Take_Profit']:
                close_side = 'sell' if side == 'long' else 'buy'
                return self._create_exit_signal(
                    close_side, symbol, current_position,
                    f'TAKE PROFIT HIT (${unrealized_pnl:.2f})'
                )

        return None

    def _create_exit_signal(
        self,
        action: str,
        symbol: str,
        current_position: Optional[Dict[str, Any]],
        reason: str
    ) -> Signal:
        """Create an exit signal to close position."""
        contracts = abs(float(current_position.get('contracts', 0))) if current_position else 0

        # Reset state
        self.current_side = "None"
        self.count = 0
        self.signals_generated += 1

        signal = Signal(
            action=action,
            symbol=symbol,
            amount=contracts,
            order_type='market',
            reason=reason,
            metadata={
                'strategy': 'quantum_ai',
                'exit_type': reason,
                'close_position': True,
                'reduce_only': True,
            }
        )
        self.last_signal = signal
        return signal

    # =========================================================================
    # GRID CALCULATIONS (from oldbybit.py calculate_grids)
    # =========================================================================

    def calculate_grids(self, side: str, current_price: float) -> Tuple[List[float], List[float]]:
        """
        Calculate grid levels for favor and against orders.

        For BUY:
          - Favor levels are ABOVE entry (sell to take profit)
          - Against levels are BELOW entry (buy to average down)

        For SELL:
          - Favor levels are BELOW entry (buy to take profit)
          - Against levels are ABOVE entry (sell to average up)

        Args:
            side: 'buy' or 'sell'
            current_price: Current market price

        Returns:
            Tuple of (favor_levels, against_levels) as lists of prices
        """
        params = self.parameters
        favor_levels = []
        against_levels = []

        num_favor = params['favor_levels']
        num_against = params['against_levels']
        favor_diff = params['favor_level_difference']
        against_diff = params['against_level_difference']

        if side.lower() == 'buy':
            # Favor levels: above entry (for taking profit by selling)
            for i in range(num_favor):
                price = current_price * (1 + (i + 1) * favor_diff / 100)
                favor_levels.append(round(price, 6))

            # Against levels: below entry (for averaging down by buying more)
            for i in range(num_against):
                price = current_price * (1 - (i + 1) * against_diff / 100)
                against_levels.append(round(price, 6))

        elif side.lower() == 'sell':
            # Favor levels: below entry (for taking profit by buying back)
            for i in range(num_favor):
                price = current_price * (1 - (i + 1) * favor_diff / 100)
                favor_levels.append(round(price, 6))

            # Against levels: above entry (for averaging up by selling more)
            for i in range(num_against):
                price = current_price * (1 + (i + 1) * against_diff / 100)
                against_levels.append(round(price, 6))

        return favor_levels, against_levels

    def prepare_order_data(self, side: str, current_price: float) -> Dict[str, Any]:
        """
        Prepare order data for grid execution (matching oldbybit.py format).

        Args:
            side: 'Buy' or 'Sell'
            current_price: Current market price

        Returns:
            Dict with all order parameters
        """
        params = self.parameters
        symbol = params['symbol']

        if params['Amount_Type'] == 'dollar':
            quantity_dollar = params['quantity']
            favor_qty_dollar = params['favor_level_qty']
            against_qty_dollar = params['against_level_qty']

            quantity = round(params['quantity'] / current_price, 4)
            favor_level_qty = round(params['favor_level_qty'] / current_price, 4)
            against_level_qty = round(params['against_level_qty'] / current_price, 4)
        else:
            quantity = params['quantity']
            favor_level_qty = params['favor_level_qty']
            against_level_qty = params['against_level_qty']
            quantity_dollar = None
            favor_qty_dollar = None
            against_qty_dollar = None

        return {
            "category": 'futures',
            "symbol": symbol,
            "Order_Type": params['Order_Type'],
            "side": side,
            "qty": quantity,
            "qty_dollar": quantity_dollar,
            "price": current_price,
            "favor_levels": params['favor_levels'],
            "against_levels": params['against_levels'],
            "favor_level_qty": favor_level_qty,
            "against_level_qty": against_level_qty,
            "favor_level_qty_dollar": favor_qty_dollar,
            "against_level_qty_dollar": against_qty_dollar,
            "favor_level_difference": params['favor_level_difference'],
            "against_level_difference": params['against_level_difference'],
        }

    # =========================================================================
    # STATUS AND UTILITIES
    # =========================================================================

    def reset_state(self):
        """Reset trading state (called after closing positions)."""
        self.current_side = "None"
        self.count = 0
        self.favor_levels = []
        self.against_levels = []
        self.Percentage = 0.0
        self.Unrealized_Pnl = 0.0

    def get_indicator_data(self) -> str:
        """Get indicator data string for logging."""
        return (
            f"Symbol: {self.parameters.get('symbol')} - "
            f"CurrentPrice: {self.current_price} - "
            f"EMA: {self.EMA} - "
            f"RSI: {self.RSI} - "
            f"PrevRSI: {self.PrevRSI} - "
            f"RSI_Color: {self.RSI_color} - "
            f"BB: {self.BB}"
        )

    def get_status(self) -> Dict[str, Any]:
        """Get strategy status."""
        status = super().get_status()
        status.update({
            'current_side': self.current_side,
            'count': self.count,
            'current_price': self.current_price,
            'favor_levels': self.favor_levels,
            'against_levels': self.against_levels,
            'percentage_pnl': self.Percentage,
            'unrealized_pnl': self.Unrealized_Pnl,
            'indicators': {
                'EMA': self.EMA,
                'RSI': self.RSI,
                'PrevRSI': self.PrevRSI,
                'BB': self.BB,
            }
        })
        return status
