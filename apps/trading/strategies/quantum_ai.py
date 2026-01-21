"""
Quantum AI Trading Strategy

This strategy uses technical indicators and AI-inspired logic
to generate trading signals.

PURE PYTHON - NO DJANGO IMPORTS
"""
import logging
from typing import Dict, Any, Optional, List
from .base import BaseStrategy, Signal

logger = logging.getLogger('trading.strategies.quantum_ai')


class QuantumAIStrategy(BaseStrategy):
    """
    Quantum AI Trading Strategy.

    Uses a combination of technical indicators (RSI, MACD, Moving Averages)
    with dynamic position sizing based on market volatility.

    Parameters:
        - rsi_period: RSI calculation period (default: 14)
        - rsi_oversold: RSI oversold threshold (default: 30)
        - rsi_overbought: RSI overbought threshold (default: 70)
        - ema_fast: Fast EMA period (default: 12)
        - ema_slow: Slow EMA period (default: 26)
        - risk_percentage: Percentage of balance to risk (default: 5)
        - stop_loss_percentage: Stop loss percentage (default: 2)
        - take_profit_percentage: Take profit percentage (default: 5)
    """

    @property
    def name(self) -> str:
        return 'Quantum AI'

    @property
    def required_parameters(self) -> List[str]:
        return ['symbol']

    def __init__(self, parameters: Dict[str, Any] = None):
        # Set defaults before calling super
        defaults = {
            'rsi_period': 14,
            'rsi_oversold': 30,
            'rsi_overbought': 70,
            'ema_fast': 12,
            'ema_slow': 26,
            'risk_percentage': 5,
            'stop_loss_percentage': 2,
            'take_profit_percentage': 5,
        }
        merged_params = {**defaults, **(parameters or {})}
        super().__init__(merged_params)

    def execute(
        self,
        market_data: Dict[str, Any],
        account_info: Dict[str, Any],
        current_position: Optional[Dict[str, Any]] = None
    ) -> Optional[Signal]:
        """
        Execute Quantum AI strategy logic.

        Algorithm:
        1. Calculate RSI from OHLCV data
        2. Calculate EMA crossover
        3. Generate signal based on combined indicators
        """
        symbol = self.parameters['symbol']
        ohlcv = market_data.get('ohlcv', [])
        ticker = market_data.get('ticker', {})

        if len(ohlcv) < self.parameters['ema_slow'] + 5:
            logger.warning(f"Not enough OHLCV data for {symbol}")
            return None

        # Extract close prices
        closes = [candle['close'] for candle in ohlcv]
        current_price = ticker.get('last', closes[-1])

        # Calculate indicators
        rsi = self._calculate_rsi(closes, self.parameters['rsi_period'])
        ema_fast = self._calculate_ema(closes, self.parameters['ema_fast'])
        ema_slow = self._calculate_ema(closes, self.parameters['ema_slow'])

        # Determine trend
        trend = 'bullish' if ema_fast[-1] > ema_slow[-1] else 'bearish'
        ema_crossover = self._detect_crossover(ema_fast, ema_slow)

        # Check if we have a position
        has_position = current_position and float(current_position.get('contracts', 0)) != 0
        position_side = current_position.get('side', '').lower() if has_position else None

        # Generate signals
        signal = None

        if has_position:
            # Check exit conditions
            if position_side == 'long':
                if self.should_exit_long(market_data, current_position, rsi, ema_crossover):
                    signal = Signal(
                        action='sell',
                        symbol=symbol,
                        amount=abs(float(current_position.get('contracts', 0))),
                        reason=f"Exit long: RSI={rsi:.2f}, trend={trend}"
                    )
            elif position_side == 'short':
                if self.should_exit_short(market_data, current_position, rsi, ema_crossover):
                    signal = Signal(
                        action='buy',
                        symbol=symbol,
                        amount=abs(float(current_position.get('contracts', 0))),
                        reason=f"Exit short: RSI={rsi:.2f}, trend={trend}"
                    )
        else:
            # Check entry conditions
            if self._should_enter_long(rsi, ema_crossover, trend):
                position_size = self.calculate_position_size(account_info, current_price, symbol)
                if position_size > 0:
                    signal = Signal(
                        action='buy',
                        symbol=symbol,
                        amount=position_size,
                        stop_loss=self.calculate_stop_loss(current_price, 'long'),
                        take_profit=self.calculate_take_profit(current_price, 'long'),
                        reason=f"Enter long: RSI={rsi:.2f}, EMA crossover={ema_crossover}, trend={trend}",
                        metadata={'rsi': rsi, 'ema_fast': ema_fast[-1], 'ema_slow': ema_slow[-1]}
                    )
            elif self._should_enter_short(rsi, ema_crossover, trend):
                position_size = self.calculate_position_size(account_info, current_price, symbol)
                if position_size > 0:
                    signal = Signal(
                        action='sell',
                        symbol=symbol,
                        amount=position_size,
                        stop_loss=self.calculate_stop_loss(current_price, 'short'),
                        take_profit=self.calculate_take_profit(current_price, 'short'),
                        reason=f"Enter short: RSI={rsi:.2f}, EMA crossover={ema_crossover}, trend={trend}",
                        metadata={'rsi': rsi, 'ema_fast': ema_fast[-1], 'ema_slow': ema_slow[-1]}
                    )

        if signal:
            self.signals_generated += 1
            self.last_signal = signal

        return signal

    def _should_enter_long(self, rsi: float, ema_crossover: str, trend: str) -> bool:
        """Check conditions for long entry."""
        rsi_oversold = rsi < self.parameters['rsi_oversold']
        bullish_crossover = ema_crossover == 'bullish'

        # Enter long when RSI is oversold and we have bullish crossover or trend
        return rsi_oversold and (bullish_crossover or trend == 'bullish')

    def _should_enter_short(self, rsi: float, ema_crossover: str, trend: str) -> bool:
        """Check conditions for short entry."""
        rsi_overbought = rsi > self.parameters['rsi_overbought']
        bearish_crossover = ema_crossover == 'bearish'

        # Enter short when RSI is overbought and we have bearish crossover or trend
        return rsi_overbought and (bearish_crossover or trend == 'bearish')

    def should_exit_long(
        self,
        market_data: Dict[str, Any],
        current_position: Dict[str, Any],
        rsi: float,
        ema_crossover: str
    ) -> bool:
        """Check conditions for exiting long position."""
        # Exit when RSI is overbought or bearish crossover
        rsi_overbought = rsi > self.parameters['rsi_overbought']
        bearish_crossover = ema_crossover == 'bearish'

        # Check if unrealized PnL hit take profit or stop loss
        entry_price = float(current_position.get('entry_price', 0))
        current_price = market_data.get('ticker', {}).get('last', entry_price)

        if entry_price > 0:
            pnl_pct = ((current_price - entry_price) / entry_price) * 100
            if pnl_pct >= self.parameters['take_profit_percentage']:
                return True
            if pnl_pct <= -self.parameters['stop_loss_percentage']:
                return True

        return rsi_overbought or bearish_crossover

    def should_exit_short(
        self,
        market_data: Dict[str, Any],
        current_position: Dict[str, Any],
        rsi: float,
        ema_crossover: str
    ) -> bool:
        """Check conditions for exiting short position."""
        rsi_oversold = rsi < self.parameters['rsi_oversold']
        bullish_crossover = ema_crossover == 'bullish'

        entry_price = float(current_position.get('entry_price', 0))
        current_price = market_data.get('ticker', {}).get('last', entry_price)

        if entry_price > 0:
            pnl_pct = ((entry_price - current_price) / entry_price) * 100
            if pnl_pct >= self.parameters['take_profit_percentage']:
                return True
            if pnl_pct <= -self.parameters['stop_loss_percentage']:
                return True

        return rsi_oversold or bullish_crossover

    def _calculate_rsi(self, closes: List[float], period: int) -> float:
        """Calculate RSI (Relative Strength Index)."""
        if len(closes) < period + 1:
            return 50.0  # Neutral

        deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]

        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def _calculate_ema(self, data: List[float], period: int) -> List[float]:
        """Calculate Exponential Moving Average."""
        if len(data) < period:
            return data

        multiplier = 2 / (period + 1)
        ema = [sum(data[:period]) / period]  # Start with SMA

        for price in data[period:]:
            ema.append((price - ema[-1]) * multiplier + ema[-1])

        return ema

    def _detect_crossover(self, fast: List[float], slow: List[float]) -> str:
        """Detect EMA crossover."""
        if len(fast) < 2 or len(slow) < 2:
            return 'none'

        # Bullish crossover: fast crosses above slow
        if fast[-2] <= slow[-2] and fast[-1] > slow[-1]:
            return 'bullish'

        # Bearish crossover: fast crosses below slow
        if fast[-2] >= slow[-2] and fast[-1] < slow[-1]:
            return 'bearish'

        return 'none'
