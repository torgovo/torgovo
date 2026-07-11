"""
Grid trading strategy implementation
"""
import time
import logging
from decimal import Decimal
from typing import Dict, Any, List
from .base import BaseTradingStrategy

logger = logging.getLogger('trading')


class GridTradingStrategy(BaseTradingStrategy):
    """
    Grid trading strategy that places buy and sell orders at predefined price levels.
    Automatically executes trades when price hits grid levels.
    """

    def __init__(self, user, exchange_bot, config: Dict[str, Any]):
        """
        Initialize grid trading strategy.

        Args:
            user: Django user instance
            exchange_bot: Exchange bot instance
            config: Grid configuration with parameters:
                - trading_pair: Trading pair (e.g., 'BTC/USDT')
                - base_amount: Base order amount
                - favor_levels: Number of buy levels below current price
                - against_levels: Number of sell levels above current price
                - level_spacing_percent: Percentage spacing between levels
                - take_profit_percent: Take profit percentage
                - stop_loss_percent: Stop loss percentage
        """
        super().__init__(user, exchange_bot, config=config)

        # Grid configuration
        self.trading_pair = config['trading_pair']
        self.base_amount = Decimal(str(config['base_amount']))
        self.favor_levels = config['favor_levels']
        self.against_levels = config['against_levels']
        self.level_spacing_percent = Decimal(str(config['level_spacing_percent']))
        self.take_profit_percent = Decimal(str(config['take_profit_percent']))
        self.stop_loss_percent = Decimal(str(config['stop_loss_percent']))

        # Grid state
        self.grid_levels = []
        self.executed_levels = []
        self.current_price = Decimal('0')
        self.upper_bound = Decimal('0')
        self.lower_bound = Decimal('0')

        # Risk management
        self.max_position_size = self.base_amount * (self.favor_levels + self.against_levels + 1)
        self.stop_loss_price = Decimal('0')
        self.take_profit_price = Decimal('0')

    def start(self):
        """Start the grid trading strategy."""
        if self.is_running:
            logger.warning(f"Grid bot for {self.user.email} is already running")
            return

        try:
            self.validate_config(self.config)

            # Get current price and calculate grid
            ticker = self.exchange_bot.get_ticker(self.trading_pair)
            self.current_price = Decimal(str(ticker['last']))

            if self.current_price == 0:
                raise TradingBotException("Invalid current price")

            self.calculate_grid_levels()
            self.setup_risk_management()

            self.is_running = True
            self.start_time = timezone.now()

            self.log_activity('start', f"Grid trading started for {self.trading_pair}")
            logger.info(f"Grid trading started for {self.user.email} on {self.trading_pair}")

            # Main trading loop
            self.run_grid_loop()

        except Exception as e:
            self.handle_error(e, "start_grid_trading")
            raise

    def stop(self):
        """Stop the grid trading strategy."""
        if not self.is_running:
            return

        self.is_running = False
        self.stop_event.set()

        # Cancel all open orders
        self.cancel_all_orders()

        self.log_activity('stop', f"Grid trading stopped for {self.trading_pair}")
        logger.info(f"Grid trading stopped for {self.user.email}")

    def run_grid_loop(self):
        """Main grid trading loop."""
        while self.is_running and not self.stop_event.is_set():
            try:
                if self.is_paused:
                    time.sleep(5)
                    continue

                # Update current price
                ticker = self.exchange_bot.get_ticker(self.trading_pair)
                self.current_price = Decimal(str(ticker['last']))

                # Check for trigger conditions
                self.check_triggers()

                # Check risk management
                self.check_risk_management()

                # Sleep before next iteration
                time.sleep(1)

            except Exception as e:
                self.handle_error(e, "grid_loop")
                time.sleep(5)  # Wait before retrying

    def calculate_grid_levels(self):
        """Calculate grid levels based on current price."""
        spacing_amount = self.current_price * (self.level_spacing_percent / Decimal('100'))

        # Calculate lower bound (favor levels - buy orders)
        self.lower_bound = self.current_price - (spacing_amount * self.favor_levels)

        # Calculate upper bound (against levels - sell orders)
        self.upper_bound = self.current_price + (spacing_amount * self.against_levels)

        # Generate grid levels
        self.grid_levels = []

        # Buy levels (favor)
        for i in range(1, self.favor_levels + 1):
            price = self.current_price - (spacing_amount * i)
            self.grid_levels.append({
                'price': price,
                'side': 'buy',
                'amount': self.base_amount,
                'executed': False,
                'order_id': None,
                'level_number': -i  # Negative for favor levels
            })

        # Sell levels (against)
        for i in range(1, self.against_levels + 1):
            price = self.current_price + (spacing_amount * i)
            self.grid_levels.append({
                'price': price,
                'side': 'sell',
                'amount': self.base_amount,
                'executed': False,
                'order_id': None,
                'level_number': i  # Positive for against levels
            })

        # Sort by price
        self.grid_levels.sort(key=lambda x: x['price'])

        self.log_activity('grid_calculated', f"Grid levels calculated: {len(self.grid_levels)} levels")

    def setup_risk_management(self):
        """Setup risk management parameters."""
        # Stop loss at 2x grid range below lower bound
        grid_range = self.upper_bound - self.lower_bound
        self.stop_loss_price = self.lower_bound - (grid_range * Decimal('2'))

        # Take profit at 2x grid range above upper bound
        self.take_profit_price = self.upper_bound + (grid_range * Decimal('2'))

    def place_grid_orders(self):
        """Place all grid orders."""
        try:
            for level in self.grid_levels:
                if not level['executed'] and not level['order_id']:
                    # Place order
                    order = self.exchange_bot.create_limit_order(
                        symbol=self.trading_pair,
                        side=level['side'],
                        amount=float(level['amount']),
                        price=float(level['price'])
                    )

                    level['order_id'] = order['id']
                    self.log_activity('order_placed', f"Grid order placed: {level['side']} {level['amount']} @ {level['price']}")

        except Exception as e:
            self.handle_error(e, "place_grid_orders")

    def check_triggers(self):
        """Check if price triggers any grid levels."""
        for level in self.grid_levels:
            if level['executed']:
                continue

            # Check buy trigger
            if level['side'] == 'buy' and self.current_price <= level['price']:
                self.execute_grid_level(level)

            # Check sell trigger
            elif level['side'] == 'sell' and self.current_price >= level['price']:
                self.execute_grid_level(level)

    def execute_grid_level(self, level: Dict[str, Any]):
        """Execute a grid level."""
        try:
            # Cancel existing limit order if exists
            if level['order_id']:
                self.exchange_bot.cancel_order(level['order_id'], self.trading_pair)

            # Execute market order
            order = self.exchange_bot.create_market_order(
                symbol=self.trading_pair,
                side=level['side'],
                amount=float(level['amount'])
            )

            # Mark level as executed
            level['executed'] = True
            level['order_id'] = None
            self.executed_levels.append(level)

            # Create opposite level
            self.create_opposite_level(level)

            # Log trade
            trade_data = {
                'symbol': self.trading_pair,
                'exchange': self.exchange_bot.exchange_name,
                'side': level['side'],
                'amount': level['amount'],
                'price': level['price'],
                'executed_price': Decimal(str(order['price'])),
                'order_id': order['id'],
                'status': order['status'],
                'description': f"Grid level {level['level_number']} executed",
                'details': {
                    'grid_level': level['level_number'],
                    'trigger_price': float(level['price']),
                    'executed_price': float(order['price']),
                }
            }

            self.log_trade(trade_data)
            self.log_activity('grid_executed', f"Grid level {level['level_number']} executed")

        except Exception as e:
            self.handle_error(e, f"execute_grid_level_{level['level_number']}")

    def create_opposite_level(self, executed_level: Dict[str, Any]):
        """Create opposite level after execution."""
        # If buy was executed, create sell at higher price
        # If sell was executed, create buy at lower price
        spacing = self.current_price * (self.level_spacing_percent / Decimal('100'))

        if executed_level['side'] == 'buy':
            # Create sell level
            opposite_price = executed_level['price'] + spacing * 2
            opposite_side = 'sell'
        else:
            # Create buy level
            opposite_price = executed_level['price'] - spacing * 2
            opposite_side = 'buy'

        opposite_level = {
            'price': opposite_price,
            'side': opposite_side,
            'amount': self.base_amount,
            'executed': False,
            'order_id': None,
            'level_number': -executed_level['level_number'],  # Invert level number
            'is_opposite': True
        }

        self.grid_levels.append(opposite_level)

    def check_risk_management(self):
        """Check risk management conditions."""
        # Check stop loss
        if self.current_price <= self.stop_loss_price:
            self.execute_stop_loss()

        # Check take profit
        elif self.current_price >= self.take_profit_price:
            self.execute_take_profit()

    def execute_stop_loss(self):
        """Execute stop loss order."""
        try:
            # Get current position
            balance = self.exchange_bot.get_balance()

            # Determine base currency and close position
            base_currency = self.trading_pair.split('/')[0]
            available_balance = balance['free'].get(base_currency, 0)

            if available_balance > 0:
                order = self.exchange_bot.create_market_order(
                    symbol=self.trading_pair,
                    side='sell',
                    amount=float(available_balance)
                )

                self.log_activity('stop_loss', f"Stop loss executed: {available_balance} @ {self.current_price}")
                self.stop()

        except Exception as e:
            self.handle_error(e, "execute_stop_loss")

    def execute_take_profit(self):
        """Execute take profit order."""
        try:
            # Close all positions and stop
            self.cancel_all_orders()
            self.log_activity('take_profit', f"Take profit reached: {self.current_price}")
            self.stop()

        except Exception as e:
            self.handle_error(e, "execute_take_profit")

    def cancel_all_orders(self):
        """Cancel all open orders for this pair."""
        try:
            open_orders = self.exchange_bot.get_open_orders(self.trading_pair)
            for order in open_orders:
                self.exchange_bot.cancel_order(order['id'], self.trading_pair)

            self.log_activity('orders_cancelled', f"Cancelled {len(open_orders)} open orders")

        except Exception as e:
            self.handle_error(e, "cancel_all_orders")

    def get_required_config_fields(self) -> list:
        """Get required configuration fields."""
        return [
            'trading_pair',
            'base_amount',
            'favor_levels',
            'against_levels',
            'level_spacing_percent',
            'take_profit_percent',
            'stop_loss_percent'
        ]

    def get_grid_status(self) -> Dict[str, Any]:
        """Get detailed grid status."""
        return {
            'trading_pair': self.trading_pair,
            'current_price': float(self.current_price),
            'total_levels': len(self.grid_levels),
            'executed_levels': len(self.executed_levels),
            'buy_levels_placed': len([l for l in self.grid_levels if l['side'] == 'buy' and not l['executed']]),
            'sell_levels_placed': len([l for l in self.grid_levels if l['side'] == 'sell' and not l['executed']]),
            'grid_range': {
                'lower': float(self.lower_bound),
                'upper': float(self.upper_bound),
                'current': float(self.current_price),
            },
            'risk_management': {
                'stop_loss_price': float(self.stop_loss_price),
                'take_profit_price': float(self.take_profit_price),
            }
        }