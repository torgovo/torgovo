"""
Martingale Trading Strategy

A strategy that increases position size after losses to recover
when the trend reverses.

PURE PYTHON - NO DJANGO IMPORTS

WARNING: Martingale strategies carry significant risk as they
require exponentially larger capital during drawdowns.
"""
import logging
from typing import Dict, Any, Optional, List
from .base import BaseStrategy, Signal

logger = logging.getLogger('trading.strategies.martingale')


class MartingaleStrategy(BaseStrategy):
    """
    Martingale Trading Strategy.

    After a losing trade, increases the next position size by a multiplier
    to recover losses when a winning trade occurs.

    Parameters:
        - symbol: Trading pair
        - base_amount: Initial position size
        - multiplier: Position size multiplier after loss (default: 2.0)
        - max_multiplications: Maximum number of doublings (default: 5)
        - take_profit_percentage: TP percentage (default: 1.0)
        - stop_loss_percentage: SL percentage (default: 1.0)
        - direction: 'long', 'short', or 'both' (default: 'both')
    """

    @property
    def name(self) -> str:
        return 'Martingale'

    @property
    def required_parameters(self) -> List[str]:
        return ['symbol', 'base_amount']

    def __init__(self, parameters: Dict[str, Any] = None):
        defaults = {
            'multiplier': 2.0,
            'max_multiplications': 5,
            'take_profit_percentage': 1.0,
            'stop_loss_percentage': 1.0,
            'direction': 'both',
        }
        merged_params = {**defaults, **(parameters or {})}
        super().__init__(merged_params)

        # Martingale state
        self.current_level = 0
        self.consecutive_losses = 0
        self.last_trade_result: Optional[str] = None  # 'win' or 'loss'

    def execute(
        self,
        market_data: Dict[str, Any],
        account_info: Dict[str, Any],
        current_position: Optional[Dict[str, Any]] = None
    ) -> Optional[Signal]:
        """
        Execute Martingale strategy logic.

        Algorithm:
        1. If no position, enter based on direction preference
        2. If position closed with loss, increase size for next trade
        3. If position closed with win, reset to base size
        """
        symbol = self.parameters['symbol']
        ticker = market_data.get('ticker', {})
        current_price = ticker.get('last', 0)

        if not current_price:
            return None

        has_position = current_position and float(current_position.get('contracts', 0)) != 0

        if has_position:
            # Check if we should close the position
            return self._check_exit(current_position, current_price, symbol)
        else:
            # Determine next trade direction and size
            return self._check_entry(market_data, account_info, current_price, symbol)

    def _check_entry(
        self,
        market_data: Dict[str, Any],
        account_info: Dict[str, Any],
        current_price: float,
        symbol: str
    ) -> Optional[Signal]:
        """Check if we should enter a new position."""
        direction = self.parameters['direction']
        base_amount = self.parameters['base_amount']
        multiplier = self.parameters['multiplier']

        # Calculate position size based on current martingale level
        position_size = base_amount * (multiplier ** self.current_level)

        # Cap at max multiplications
        max_level = self.parameters['max_multiplications']
        if self.current_level >= max_level:
            logger.warning(f"Max martingale level reached ({max_level}), resetting")
            self.current_level = 0
            position_size = base_amount

        # Determine trade direction
        if direction == 'both':
            # Use simple momentum to decide
            ohlcv = market_data.get('ohlcv', [])
            if len(ohlcv) >= 2:
                prev_close = ohlcv[-2]['close']
                action = 'buy' if current_price > prev_close else 'sell'
            else:
                action = 'buy'  # Default
        elif direction == 'long':
            action = 'buy'
        else:
            action = 'sell'

        side = 'long' if action == 'buy' else 'short'

        return Signal(
            action=action,
            symbol=symbol,
            amount=position_size,
            stop_loss=self.calculate_stop_loss(current_price, side),
            take_profit=self.calculate_take_profit(current_price, side),
            reason=f"Martingale entry: Level {self.current_level}, Size {position_size:.4f}",
            metadata={
                'martingale_level': self.current_level,
                'multiplier': multiplier,
            }
        )

    def _check_exit(
        self,
        current_position: Dict[str, Any],
        current_price: float,
        symbol: str
    ) -> Optional[Signal]:
        """Check if we should exit the current position."""
        entry_price = float(current_position.get('entry_price', 0))
        side = current_position.get('side', '').lower()
        contracts = abs(float(current_position.get('contracts', 0)))

        if entry_price == 0:
            return None

        # Calculate PnL percentage
        if side == 'long':
            pnl_pct = ((current_price - entry_price) / entry_price) * 100
        else:
            pnl_pct = ((entry_price - current_price) / entry_price) * 100

        tp_pct = self.parameters['take_profit_percentage']
        sl_pct = self.parameters['stop_loss_percentage']

        # Check take profit
        if pnl_pct >= tp_pct:
            self._register_win()
            close_side = 'sell' if side == 'long' else 'buy'
            return Signal(
                action=close_side,
                symbol=symbol,
                amount=contracts,
                reason=f"Martingale TP: PnL {pnl_pct:.2f}%, resetting level",
                metadata={'result': 'win', 'pnl_pct': pnl_pct}
            )

        # Check stop loss
        if pnl_pct <= -sl_pct:
            self._register_loss()
            close_side = 'sell' if side == 'long' else 'buy'
            return Signal(
                action=close_side,
                symbol=symbol,
                amount=contracts,
                reason=f"Martingale SL: PnL {pnl_pct:.2f}%, increasing level",
                metadata={'result': 'loss', 'pnl_pct': pnl_pct}
            )

        return None

    def _register_win(self):
        """Record a winning trade and reset martingale level."""
        self.last_trade_result = 'win'
        self.current_level = 0
        self.consecutive_losses = 0
        logger.info("Martingale: Win recorded, resetting to base level")

    def _register_loss(self):
        """Record a losing trade and increase martingale level."""
        self.last_trade_result = 'loss'
        self.consecutive_losses += 1
        self.current_level += 1
        logger.info(f"Martingale: Loss recorded, increasing to level {self.current_level}")

    def reset(self):
        """Reset martingale state."""
        self.current_level = 0
        self.consecutive_losses = 0
        self.last_trade_result = None

    def get_status(self) -> Dict[str, Any]:
        """Get martingale strategy status."""
        status = super().get_status()
        status.update({
            'current_level': self.current_level,
            'consecutive_losses': self.consecutive_losses,
            'current_multiplier': self.parameters['multiplier'] ** self.current_level,
            'next_position_size': self.parameters['base_amount'] * (self.parameters['multiplier'] ** self.current_level),
        })
        return status
