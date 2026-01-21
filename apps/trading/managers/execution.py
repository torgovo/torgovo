"""
Bot Execution Manager

This module bridges Django models with pure Python strategies and adapters.
It handles:
- Loading bot configurations from the database
- Instantiating the correct strategy and adapter
- Running the trading loop
- Logging execution results back to the database

This is the ONLY place where Django imports mix with trading logic.
"""
import logging
import time
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger('trading.managers')


class BotExecutor:
    """
    Executes trading bots by combining strategies and adapters.

    This class is responsible for:
    1. Loading configuration from Django models
    2. Creating strategy and adapter instances
    3. Running the trading loop
    4. Handling errors and logging
    """

    def __init__(
        self,
        strategy,
        adapter,
        bot_config=None,
        symbol: str = None
    ):
        """
        Initialize the bot executor.

        Args:
            strategy: Instantiated strategy object (BaseStrategy subclass)
            adapter: Instantiated adapter object (BaseAdapter subclass)
            bot_config: Optional Django BotConfiguration model instance
            symbol: Trading symbol (required if bot_config not provided)
        """
        self.strategy = strategy
        self.adapter = adapter
        self.bot_config = bot_config
        self.symbol = symbol or (bot_config.symbol if bot_config else None)

        if not self.symbol:
            raise ValueError("Symbol must be provided either in bot_config or directly")

        self.is_running = False
        self.execution_count = 0
        self.last_execution: Optional[datetime] = None
        self.errors: list = []

    @classmethod
    def from_config(cls, bot_config):
        """
        Create a BotExecutor from a Django BotConfiguration model.

        Args:
            bot_config: BotConfiguration model instance

        Returns:
            BotExecutor instance
        """
        from ..strategies import get_strategy
        from ..exchanges import get_adapter

        # Get strategy class and instantiate
        strategy_class = get_strategy(bot_config.strategy)
        strategy = strategy_class(parameters={
            'symbol': bot_config.symbol,
            **bot_config.parameters
        })

        # Get credentials and create adapter
        credentials = bot_config.exchange_credentials.get_decrypted_credentials()
        adapter = get_adapter(
            exchange_name=bot_config.exchange_credentials.exchange_name,
            credentials=credentials,
            demo_mode=bot_config.exchange_credentials.is_testnet
        )

        return cls(
            strategy=strategy,
            adapter=adapter,
            bot_config=bot_config,
            symbol=bot_config.symbol
        )

    def run_once(self) -> Dict[str, Any]:
        """
        Execute one iteration of the trading loop.

        Returns:
            Dict with execution result
        """
        result = {
            'success': False,
            'signal': None,
            'order': None,
            'error': None,
            'timestamp': datetime.utcnow().isoformat(),
        }

        try:
            # Fetch market data
            market_data = self._fetch_market_data()

            # Fetch account info
            account_info = self.adapter.get_account_info()

            # Fetch current position (if any)
            current_position = self._get_current_position()

            # Execute strategy
            signal = self.strategy.execute(market_data, account_info, current_position)

            if signal and signal.action != 'hold':
                result['signal'] = signal.to_dict()

                # Execute the order
                order = self.adapter.execute_order(signal.to_dict())
                result['order'] = order

                # Log to database if we have a config
                if self.bot_config:
                    self._log_trade(signal, order)

            result['success'] = True
            self.execution_count += 1
            self.last_execution = datetime.utcnow()

        except Exception as e:
            logger.error(f"Bot execution error: {e}", exc_info=True)
            result['error'] = str(e)
            self.errors.append({
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            })

            # Update bot status if we have a config
            if self.bot_config:
                self._handle_error(e)

        return result

    def run_loop(self, interval_seconds: float = 60, max_iterations: Optional[int] = None):
        """
        Run the trading loop continuously.

        Args:
            interval_seconds: Time between iterations
            max_iterations: Maximum number of iterations (None for infinite)
        """
        self.is_running = True
        iteration = 0

        logger.info(f"Starting bot loop for {self.symbol} on {self.adapter.exchange_name}")

        try:
            while self.is_running:
                if max_iterations and iteration >= max_iterations:
                    break

                result = self.run_once()

                if result.get('signal'):
                    logger.info(f"Signal generated: {result['signal']}")

                if result.get('error'):
                    logger.warning(f"Iteration error: {result['error']}")

                iteration += 1
                time.sleep(interval_seconds)

        except KeyboardInterrupt:
            logger.info("Bot loop interrupted by user")
        finally:
            self.is_running = False
            logger.info(f"Bot loop stopped after {iteration} iterations")

    def stop(self):
        """Stop the trading loop."""
        self.is_running = False

    def _fetch_market_data(self) -> Dict[str, Any]:
        """Fetch all necessary market data for the strategy."""
        return {
            'ticker': self.adapter.fetch_ticker(self.symbol),
            'ohlcv': self.adapter.fetch_ohlcv(self.symbol, '1h', limit=100),
            'orderbook': self.adapter.fetch_order_book(self.symbol, limit=10),
        }

    def _get_current_position(self) -> Optional[Dict[str, Any]]:
        """Get current position if any."""
        try:
            positions = self.adapter.fetch_positions(self.symbol)
            if positions:
                return positions[0]
        except Exception as e:
            logger.debug(f"No position data: {e}")
        return None

    def _log_trade(self, signal, order):
        """Log trade to database."""
        try:
            from ..models import BotConfiguration
            from apps.bots.models import Order

            Order.objects.create(
                user=self.bot_config.user,
                pair=signal.symbol,
                exchange=self.adapter.exchange_name,
                side=signal.action,
                category=self.strategy.name.lower().replace(' ', '_'),
                order_type=signal.order_type,
                quantity=signal.amount,
                price=signal.price or order.get('price', 0),
                executed_price=order.get('price', 0),
                exchange_order_id=order.get('id', ''),
                status=order.get('status', 'created'),
                description=signal.reason,
                details=signal.metadata,
            )

            # Update bot stats
            self.bot_config.total_trades += 1
            self.bot_config.last_trade_at = datetime.utcnow()
            self.bot_config.save(update_fields=['total_trades', 'last_trade_at'])

        except Exception as e:
            logger.error(f"Failed to log trade: {e}")

    def _handle_error(self, error: Exception):
        """Handle execution errors."""
        try:
            # Update bot status to error if too many consecutive errors
            if len(self.errors) >= 5:
                self.bot_config.status = 'error'
                self.bot_config.save(update_fields=['status'])
        except Exception as e:
            logger.error(f"Failed to update bot status: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Get executor status."""
        return {
            'is_running': self.is_running,
            'symbol': self.symbol,
            'exchange': self.adapter.exchange_name,
            'strategy': self.strategy.name,
            'execution_count': self.execution_count,
            'last_execution': self.last_execution.isoformat() if self.last_execution else None,
            'error_count': len(self.errors),
            'strategy_status': self.strategy.get_status(),
        }


def run_bot(bot_id: str) -> Dict[str, Any]:
    """
    Run a single iteration of a bot by its ID.

    This is the main entry point for Celery tasks.

    Args:
        bot_id: UUID of the BotConfiguration

    Returns:
        Execution result dict
    """
    from ..models import BotConfiguration

    try:
        bot_config = BotConfiguration.objects.select_related(
            'exchange_credentials', 'user'
        ).get(id=bot_id, is_active=True)

        if bot_config.status != 'active':
            return {'success': False, 'error': f'Bot is not active: {bot_config.status}'}

        executor = BotExecutor.from_config(bot_config)
        return executor.run_once()

    except BotConfiguration.DoesNotExist:
        return {'success': False, 'error': f'Bot not found: {bot_id}'}
    except Exception as e:
        logger.error(f"Error running bot {bot_id}: {e}", exc_info=True)
        return {'success': False, 'error': str(e)}
