"""
Grid Trading Strategy

A market-neutral strategy that places buy and sell orders at
regular intervals (grid levels) around the current price.

PURE PYTHON - NO DJANGO IMPORTS
"""
import logging
from typing import Dict, Any, Optional, List
from .base import BaseStrategy, Signal

logger = logging.getLogger('trading.strategies.grid')


class GridTradingStrategy(BaseStrategy):
    """
    Grid Trading Strategy.

    Places a grid of buy orders below current price and sell orders above.
    Profits from price oscillation within the grid range.

    Parameters:
        - symbol: Trading pair
        - grid_levels: Number of grid levels (default: 10)
        - grid_spacing_percentage: Spacing between levels as % (default: 1.0)
        - amount_per_grid: Amount per grid order (default: 10 USDT)
        - upper_limit: Upper price limit (optional)
        - lower_limit: Lower price limit (optional)
    """

    @property
    def name(self) -> str:
        return 'Grid Trading'

    @property
    def required_parameters(self) -> List[str]:
        return ['symbol', 'amount_per_grid']

    def __init__(self, parameters: Dict[str, Any] = None):
        defaults = {
            'grid_levels': 10,
            'grid_spacing_percentage': 1.0,
            'amount_per_grid': 10,
        }
        merged_params = {**defaults, **(parameters or {})}
        super().__init__(merged_params)

        # Grid state (in production, this would be loaded from database)
        self.grid_orders: Dict[str, Dict] = {}
        self.grid_initialized = False

    def execute(
        self,
        market_data: Dict[str, Any],
        account_info: Dict[str, Any],
        current_position: Optional[Dict[str, Any]] = None
    ) -> Optional[Signal]:
        """
        Execute grid trading logic.

        Algorithm:
        1. If grid not initialized, calculate grid levels
        2. Check for filled orders
        3. Place counter-orders for filled orders
        """
        symbol = self.parameters['symbol']
        ticker = market_data.get('ticker', {})
        current_price = ticker.get('last', 0)

        if not current_price:
            logger.warning(f"No price data for {symbol}")
            return None

        # Initialize grid if needed
        if not self.grid_initialized:
            return self._initialize_grid(current_price, account_info, symbol)

        # Check for grid rebalancing opportunities
        return self._check_grid_opportunities(current_price, account_info, symbol)

    def _initialize_grid(
        self,
        current_price: float,
        account_info: Dict[str, Any],
        symbol: str
    ) -> Optional[Signal]:
        """Initialize the grid around current price."""
        grid_levels = self.parameters['grid_levels']
        spacing_pct = self.parameters['grid_spacing_percentage'] / 100
        amount = self.parameters['amount_per_grid']

        # Calculate grid prices
        upper_limit = self.parameters.get('upper_limit', current_price * (1 + spacing_pct * grid_levels / 2))
        lower_limit = self.parameters.get('lower_limit', current_price * (1 - spacing_pct * grid_levels / 2))

        price_step = (upper_limit - lower_limit) / grid_levels

        # Generate grid levels
        grid_prices = []
        for i in range(grid_levels + 1):
            price = lower_limit + (i * price_step)
            grid_prices.append(price)

        # Find the first buy level below current price
        buy_levels = [p for p in grid_prices if p < current_price]
        if buy_levels:
            buy_price = max(buy_levels)  # Closest buy level
            self.grid_initialized = True

            return Signal(
                action='buy',
                symbol=symbol,
                amount=amount / buy_price,  # Convert USDT to base currency
                price=buy_price,
                order_type='limit',
                reason=f"Grid init: Buy at {buy_price:.2f}",
                metadata={
                    'grid_type': 'init',
                    'grid_prices': grid_prices,
                    'upper_limit': upper_limit,
                    'lower_limit': lower_limit,
                }
            )

        return None

    def _check_grid_opportunities(
        self,
        current_price: float,
        account_info: Dict[str, Any],
        symbol: str
    ) -> Optional[Signal]:
        """
        Check if any grid levels need orders placed.

        In production, this would:
        1. Check filled orders from the adapter
        2. Place counter-orders
        """
        # This is a simplified version
        # In production, you'd track filled orders and place counters
        return None

    def calculate_grid_levels(
        self,
        current_price: float,
        upper_limit: Optional[float] = None,
        lower_limit: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Calculate grid levels for display/planning.

        Returns:
            Dict with grid information
        """
        grid_levels = self.parameters['grid_levels']
        spacing_pct = self.parameters['grid_spacing_percentage'] / 100

        if not upper_limit:
            upper_limit = current_price * (1 + spacing_pct * grid_levels / 2)
        if not lower_limit:
            lower_limit = current_price * (1 - spacing_pct * grid_levels / 2)

        price_step = (upper_limit - lower_limit) / grid_levels

        levels = []
        for i in range(grid_levels + 1):
            price = lower_limit + (i * price_step)
            level_type = 'buy' if price < current_price else 'sell'
            levels.append({
                'price': price,
                'type': level_type,
                'level': i,
            })

        return {
            'current_price': current_price,
            'upper_limit': upper_limit,
            'lower_limit': lower_limit,
            'grid_levels': grid_levels,
            'price_step': price_step,
            'levels': levels,
        }

    def get_status(self) -> Dict[str, Any]:
        """Get grid strategy status."""
        status = super().get_status()
        status.update({
            'grid_initialized': self.grid_initialized,
            'active_orders': len(self.grid_orders),
        })
        return status
