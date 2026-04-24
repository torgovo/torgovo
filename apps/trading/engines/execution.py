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
    def from_config(cls, config: dict):
        """
        Create a BotExecutor from a plain config dict.
        
        Args:
            config: Dict with keys:
                - strategy: str (e.g. 'quantum_ai', 'grid')
                - symbol: str (e.g. 'BTC/USDT')
                - exchange_name: str (e.g. 'bybit')
                - api_key: str (decrypted)
                - secret_key: str (decrypted)
                - passphrase: str (optional)
                - is_testnet: bool
                - parameters: dict (strategy-specific params)
        
        Returns:
            BotExecutor instance
        """
        from ..strategies import get_strategy
        from ..exchanges import get_adapter

        strategy_name = config.get('strategy', 'quantum_ai')
        symbol = config.get('symbol', '')
        parameters = config.get('parameters', {})

        # Instantiate strategy
        strategy_class = get_strategy(strategy_name)
        strategy = strategy_class(parameters={
            'symbol': symbol,
            **parameters
        })

        # Create exchange adapter
        credentials = {
            'api_key': config.get('api_key', ''),
            'secret_key': config.get('secret_key', ''),
            'passphrase': config.get('passphrase', ''),
        }
        adapter = get_adapter(
            exchange_name=config.get('exchange_name', 'bybit'),
            credentials=credentials,
            demo_mode=config.get('is_testnet', False)
        )

        return cls(
            strategy=strategy,
            adapter=adapter,
            bot_config=config,
            symbol=symbol
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
            from apps.bots.models import Order

            # bot_config is now a dict, extract user_id if present
            user_id = self.bot_config.get('user_id') if isinstance(self.bot_config, dict) else None
            if not user_id:
                logger.warning("No user_id in config, skipping trade log")
                return

            from django.contrib.auth import get_user_model
            User = get_user_model()
            user = User.objects.get(id=user_id)

            Order.objects.create(
                user=user,
                Pair=signal.symbol,
                Exchange=self.adapter.exchange_name,
                Side=signal.action,
                Category=self.strategy.name.lower().replace(' ', '_'),
                Order_type=signal.order_type,
                Quantity=signal.amount,
                Price=signal.price or order.get('price', 0),
                Description=signal.reason,
                Details=signal.metadata,
            )

        except Exception as e:
            logger.error(f"Failed to log trade: {e}")

    def _handle_error(self, error: Exception):
        """Handle execution errors."""
        try:
            # Update bot status to error if too many consecutive errors
            if len(self.errors) >= 5:
                bot_id = self.bot_config.get('bot_id') if isinstance(self.bot_config, dict) else None
                bot_type = self.bot_config.get('bot_type') if isinstance(self.bot_config, dict) else None
                if bot_id and bot_type:
                    self._update_bot_status(bot_id, bot_type, 'error')
                logger.error(f"Bot {bot_id} exceeded error threshold (5+ consecutive errors)")
        except Exception as e:
            logger.error(f"Failed to handle bot error: {e}")

    @staticmethod
    def _update_bot_status(bot_id: str, bot_type: str, new_status: str):
        """Update bot model status in database."""
        try:
            if bot_type == 'grid':
                from apps.bots.models import GridBot
                GridBot.objects.filter(id=bot_id).update(is_running=False)
            elif bot_type == 'martingale':
                from apps.bots.models import MartingaleBot
                MartingaleBot.objects.filter(id=bot_id).update(is_running=False)
            elif bot_type == 'signal':
                from apps.bots.models import SignalBot
                SignalBot.objects.filter(id=bot_id).update(is_active=False)
            logger.info(f"Updated bot {bot_id} status to {new_status}")
        except Exception as e:
            logger.error(f"Failed to update bot {bot_id} status: {e}")

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


def run_bot(bot_id: str, bot_type: str = 'grid') -> Dict[str, Any]:
    """
    Run a single iteration of a bot by its ID.
    This is the main entry point for Celery tasks.
    
    Builds a config dict from the actual bot model in apps/bots/,
    then runs BotExecutor.
    
    Args:
        bot_id: UUID of the bot
        bot_type: 'grid', 'martingale', 'signal', or 'quantum_ai'
    
    Returns:
        Execution result dict
    """
    try:
        # Import the right bot model based on type
        if bot_type == 'grid':
            from apps.bots.models import GridBot
            bot = GridBot.objects.select_related('user', 'subscription').get(id=bot_id)
        elif bot_type == 'martingale':
            from apps.bots.models import MartingaleBot
            bot = MartingaleBot.objects.select_related('user', 'subscription').get(id=bot_id)
        elif bot_type == 'signal':
            from apps.bots.models import SignalBot
            bot = SignalBot.objects.select_related('user', 'subscription').get(id=bot_id)
        else:
            return {'success': False, 'error': f'Unknown bot_type: {bot_type}'}

        # Get exchange credentials
        from apps.exchanges.models import ExchangeCredentials
        credentials = ExchangeCredentials.objects.get(
            user=bot.user,
            exchange_name=bot.exchange_name,
            is_active=True
        )
        creds = credentials.get_decrypted_credentials()

        # Build config dict
        config = {
            'bot_id': str(bot.id),
            'bot_name': bot.bot_name,
            'bot_type': bot_type,
            'user_id': str(bot.user.id),
            'strategy': bot_type,
            'symbol': bot.trading_pair,
            'exchange_name': bot.exchange_name,
            'api_key': creds.get('api_key', ''),
            'secret_key': creds.get('secret_key', ''),
            'passphrase': creds.get('passphrase', ''),
            'is_testnet': credentials.is_testnet,
            'parameters': {},
        }

        # Add bot-type-specific parameters
        if bot_type in ('grid', 'martingale'):
            config['parameters'] = {
                'favor_levels': bot.favor_levels,
                'against_levels': bot.against_levels,
                'level_spacing_percent': float(bot.level_spacing_percent),
                'initial_amount': float(bot.initial_amount),
                'base_amount': float(bot.base_amount),
                'take_profit_percent': float(bot.take_profit_percent),
                'stop_loss_percent': float(bot.stop_loss_percent),
            }

        executor = BotExecutor.from_config(config)
        return executor.run_once()

    except Exception as e:
        logger.error(f"Error running bot {bot_id}: {e}", exc_info=True)
        return {'success': False, 'error': str(e)}
