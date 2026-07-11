"""
Martingale trading strategy implementation
"""
import time
import logging
from decimal import Decimal
from typing import Dict, Any
from django.utils import timezone
from .base import BaseTradingStrategy, TradingBotException

logger = logging.getLogger('trading')


class MartingaleTradingStrategy(BaseTradingStrategy):
    """
    Martingale trading strategy that doubles position size after losses.
    Implements progressive betting with configurable multiplier.
    """

    def __init__(self, user, exchange_bot, config: Dict[str, Any]):
        """
        Initialize martingale trading strategy.

        Args:
            user: Django user instance
            exchange_bot: Exchange bot instance
            config: Martingale configuration
        """
        super().__init__(user, exchange_bot, config=config)

        # Martingale configuration
        self.trading_pair = config['trading_pair']
        self.base_amount = Decimal(str(config['base_amount']))
        self.favor_levels = config['favor_levels']
        self.against_levels = config['against_levels']
        self.level_spacing_percent = Decimal(str(config['level_spacing_percent']))
        self.multiplier_factor = Decimal(str(config['multiplier_factor']))
        self.take_profit_percent = Decimal(str(config['take_profit_percent']))
        self.stop_loss_percent = Decimal(str(config['stop_loss_percent']))

        # Martingale state
        self.current_level = 0
        self.max_level_reached = 0
        self.current_position_size = self.base_amount
        self.entry_price = Decimal('0')
        self.last_side = None
        self.consecutive_losses = 0
        self.max_consecutive_losses = config.get('max_consecutive_losses', 7)

    def start(self):
        """Start the martingale trading strategy."""
        if self.is_running:
            logger.warning(f"Martingale bot for {self.user.email} is already running")
            return

        try:
            self.validate_config(self.config)

            # Get current price
            ticker = self.exchange_bot.get_ticker(self.trading_pair)
            current_price = Decimal(str(ticker['last']))

            if current_price == 0:
                raise TradingBotException("Invalid current price")

            self.setup_risk_management()

            self.is_running = True
            self.start_time = timezone.now()

            self.log_activity('start', f"Martingale trading started for {self.trading_pair}")
            logger.info(f"Martingale trading started for {self.user.email} on {self.trading_pair}")

            # Main trading loop
            self.run_martingale_loop()

        except Exception as e:
            self.handle_error(e, "start_martingale_trading")
            raise

    def stop(self):
        """Stop the martingale trading strategy."""
        if not self.is_running:
            return

        self.is_running = False
        self.stop_event.set()

        # Close any open positions
        self.close_positions()

        self.log_activity('stop', f"Martingale trading stopped for {self.trading_pair}")
        logger.info(f"Martingale trading stopped for {self.user.email}")

    def run_martingale_loop(self):
        """Main martingale trading loop."""
        while self.is_running and not self.stop_event.is_set():
            try:
                if self.is_paused:
                    time.sleep(5)
                    continue

                # Update current price
                ticker = self.exchange_bot.get_ticker(self.trading_pair)
                current_price = Decimal(str(ticker['last']))

                # Analyze market conditions and make trading decisions
                self.analyze_market_conditions(current_price)

                # Check risk management
                self.check_risk_management(current_price)

                # Sleep before next iteration
                time.sleep(5)

            except Exception as e:
                self.handle_error(e, "martingale_loop")
                time.sleep(5)

    def analyze_market_conditions(self, current_price: Decimal):
        """
        Analyze market conditions and make trading decisions.
        This is a simplified implementation - in production, use technical indicators.
        """
        try:
            # Simple trend detection (use proper technical analysis in production)
            from apps.bots.models import TechnicalIndicator

            # Get recent technical indicators
            recent_indicators = TechnicalIndicator.objects.filter(
                pair=self.trading_pair,
                exchange=self.exchange_bot.exchange_name,
                indicator_type__in=['RSI', 'EMA', 'BB'],
                timestamp__gte=timezone.now() - timezone.timedelta(minutes=30)
            ).order_by('-timestamp')[:10]

            # Simple trading logic based on indicators
            should_buy = self.evaluate_buy_signal(recent_indicators, current_price)
            should_sell = self.evaluate_sell_signal(recent_indicators, current_price)

            if should_buy and self.last_side != 'buy':
                self.execute_buy(current_price)
            elif should_sell and self.last_side != 'sell':
                self.execute_sell(current_price)

        except Exception as e:
            self.handle_error(e, "analyze_market_conditions")

    def evaluate_buy_signal(self, indicators: list, current_price: Decimal) -> bool:
        """Evaluate if we should execute a buy order."""
        # Simplified logic - implement proper technical analysis
        rsi_values = [ind.value for ind in indicators if ind.indicator_type == 'RSI']

        if rsi_values:
            latest_rsi = rsi_values[0]
            return latest_rsi < 30  # Oversold condition

        return False

    def evaluate_sell_signal(self, indicators: list, current_price: Decimal) -> bool:
        """Evaluate if we should execute a sell order."""
        # Simplified logic - implement proper technical analysis
        rsi_values = [ind.value for ind in indicators if ind.indicator_type == 'RSI']

        if rsi_values:
            latest_rsi = rsi_values[0]
            return latest_rsi > 70  # Overbought condition

        return False

    def execute_buy(self, current_price: Decimal):
        """Execute a buy order with martingale sizing."""
        try:
            # Calculate position size based on current martingale level
            position_size = self.calculate_position_size()

            # Execute market buy order
            order = self.exchange_bot.create_market_order(
                symbol=self.trading_pair,
                side='buy',
                amount=float(position_size)
            )

            # Update state
            self.entry_price = Decimal(str(order.get('price', current_price)))
            self.last_side = 'buy'
            self.current_position_size = position_size

            # Set take profit and stop loss
            self.set_exit_prices()

            # Log trade
            trade_data = {
                'symbol': self.trading_pair,
                'exchange': self.exchange_bot.exchange_name,
                'side': 'buy',
                'amount': position_size,
                'price': self.entry_price,
                'executed_price': Decimal(str(order.get('price', self.entry_price))),
                'order_id': order.get('id', ''),
                'status': order.get('status', 'filled'),
                'take_profit': self.take_profit_price,
                'stop_loss': self.stop_loss_price,
                'description': f'Martingale buy order at level {self.current_level}',
                'details': {
                    'martingale_level': self.current_level,
                    'multiplier_used': float(self.multiplier_factor ** self.current_level),
                    'position_size': float(position_size),
                }
            }

            self.log_trade(trade_data)
            self.log_activity('buy_executed', f"Martingale buy executed at level {self.current_level}")

        except Exception as e:
            self.handle_error(e, "execute_buy")

    def execute_sell(self, current_price: Decimal):
        """Execute a sell order to close position."""
        try:
            if not self.last_side or not self.entry_price:
                return  # No position to close

            # Get current balance of the base asset
            balance = self.exchange_bot.get_balance()
            base_currency = self.trading_pair.split('/')[0]
            available_balance = balance['free'].get(base_currency, 0)

            if available_balance <= 0:
                return  # No balance to sell

            # Execute market sell order
            order = self.exchange_bot.create_market_order(
                symbol=self.trading_pair,
                side='sell',
                amount=float(available_balance)
            )

            # Calculate profit/loss
            exit_price = Decimal(str(order.get('price', current_price)))
            profit_loss = (exit_price - self.entry_price) * self.current_position_size

            # Update martingale state based on result
            if profit_loss > 0:
                # Profit - reset martingale level
                self.current_level = 0
                self.consecutive_losses = 0
                self.current_position_size = self.base_amount
            else:
                # Loss - increment martingale level
                self.consecutive_losses += 1
                self.current_level += 1
                self.max_level_reached = max(self.max_level_reached, self.current_level)

                # Check if we've reached max consecutive losses
                if self.consecutive_losses >= self.max_consecutive_losses:
                    self.log_activity('max_losses_reached', f"Max consecutive losses reached: {self.consecutive_losses}")
                    self.stop()

            # Update state
            self.last_side = 'sell'
            self.entry_price = Decimal('0')

            # Log trade
            trade_data = {
                'symbol': self.trading_pair,
                'exchange': self.exchange_bot.exchange_name,
                'side': 'sell',
                'amount': available_balance,
                'price': exit_price,
                'executed_price': Decimal(str(order.get('price', exit_price))),
                'order_id': order.get('id', ''),
                'status': order.get('status', 'filled'),
                'profit_loss': profit_loss,
                'description': f'Martingale close from level {self.current_level - 1}',
                'details': {
                    'consecutive_losses': self.consecutive_losses - 1,
                    'current_level': self.current_level,
                    'entry_price': float(self.entry_price),
                    'exit_price': float(exit_price),
                }
            }

            self.log_trade(trade_data)
            self.log_activity('sell_executed', f"Martingale sell executed, P/L: {profit_loss}")

        except Exception as e:
            self.handle_error(e, "execute_sell")

    def calculate_position_size(self) -> Decimal:
        """Calculate position size based on current martingale level."""
        base_amount = self.base_amount
        multiplier = self.multiplier_factor ** self.current_level
        return base_amount * multiplier

    def set_exit_prices(self):
        """Set take profit and stop loss prices."""
        if self.entry_price == 0:
            return

        # Calculate TP/SL based on last order
        tp_multiplier = 1 + (self.take_profit_percent / 100)
        sl_multiplier = 1 - (self.stop_loss_percent / 100)

        if self.last_side == 'buy':
            self.take_profit_price = self.entry_price * tp_multiplier
            self.stop_loss_price = self.entry_price * sl_multiplier
        else:  # sell position (not typical for martingale)
            self.take_profit_price = self.entry_price / tp_multiplier
            self.stop_loss_price = self.entry_price / sl_multiplier

    def check_risk_management(self, current_price: Decimal):
        """Check risk management conditions."""
        # Check stop loss
        if self.stop_loss_price and self.last_side == 'buy':
            if current_price <= self.stop_loss_price:
                self.execute_stop_loss()
        elif self.last_side == 'sell' and self.stop_loss_price:
            if current_price >= self.stop_loss_price:
                self.execute_stop_loss()

        # Check take profit
        if self.take_profit_price:
            if self.last_side == 'buy' and current_price >= self.take_profit_price:
                self.execute_take_profit()
            elif self.last_side == 'sell' and current_price <= self.take_profit_price:
                self.execute_take_profit()

    def execute_stop_loss(self):
        """Execute stop loss order."""
        try:
            self.log_activity('stop_loss_triggered', f"Stop loss triggered at level {self.current_level}")
            # Current position will be closed in the next iteration
        except Exception as e:
            self.handle_error(e, "execute_stop_loss")

    def execute_take_profit(self):
        """Execute take profit order."""
        try:
            self.log_activity('take_profit_triggered', f"Take profit triggered at level {self.current_level}")
        except Exception as e:
            self.handle_error(e, "execute_take_profit")

    def close_positions(self):
        """Close all open positions."""
        try:
            if self.last_side:
                # Close current position
                ticker = self.exchange_bot.get_ticker(self.trading_pair)
                current_price = Decimal(str(ticker['last']))
                self.execute_sell(current_price)
        except Exception as e:
            self.handle_error(e, "close_positions")

    def get_required_config_fields(self) -> list:
        """Get required configuration fields."""
        return [
            'trading_pair',
            'base_amount',
            'favor_levels',
            'against_levels',
            'level_spacing_percent',
            'multiplier_factor',
            'take_profit_percent',
            'stop_loss_percent'
        ]

    def setup_risk_management(self):
        """Setup risk management parameters."""
        # Additional risk management setup
        self.max_position_size = self.base_amount * (self.multiplier_factor ** self.favor_levels)
        logger.info(f"Martingale max position size: {self.max_position_size}")

    def get_status(self) -> Dict[str, Any]:
        """Get detailed martingale status."""
        base_status = super().get_status()
        base_status.update({
            'current_level': self.current_level,
            'max_level_reached': self.max_level_reached,
            'consecutive_losses': self.consecutive_losses,
            'current_position_size': float(self.current_position_size),
            'last_side': self.last_side,
            'entry_price': float(self.entry_price) if self.entry_price else None,
            'take_profit_price': float(self.take_profit_price) if self.take_profit_price else None,
            'stop_loss_price': float(self.stop_loss_price) if self.stop_loss_price else None,
        })
        return base_status