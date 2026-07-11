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
import threading
import time
from typing import Optional, Dict, Any
from datetime import datetime
from django.core.cache import cache

logger = logging.getLogger('trading.managers')

# In-process lock: prevents duplicate BotEngine instances per bot_id
_running_bots: set = set()
_running_bots_lock = threading.Lock()

# Track running engine instances so stop_bot() can signal them
_running_engines: Dict[str, Any] = {}
_running_engines_lock = threading.Lock()


def _is_bot_running(bot_id: str) -> bool:
    """Check if bot_id is already running in this process."""
    with _running_bots_lock:
        return bot_id in _running_bots


def _mark_bot_starting(bot_id: str) -> bool:
    """Atomically mark bot as starting. Returns False if already running."""
    with _running_bots_lock:
        if bot_id in _running_bots:
            return False
        _running_bots.add(bot_id)
        return True


def _mark_bot_stopped(bot_id: str):
    """Remove bot from running set."""
    with _running_bots_lock:
        _running_bots.discard(bot_id)


def _try_redis_lock(bot_id: str, ttl: int = 120) -> bool:
    """
    Try to acquire a Redis-backed distributed lock for the bot.
    Prevents duplicate restore across Celery workers.
    Returns True if lock was acquired (safe to proceed).
    """
    lock_key = f"bot_exec_lock_{bot_id}"
    return cache.add(lock_key, "1", ttl)


def _release_redis_lock(bot_id: str):
    """Release the Redis distributed lock."""
    cache.delete(f"bot_exec_lock_{bot_id}")


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


def run_bot(bot_id: str, bot_type: str = 'grid', restore_mode: bool = False) -> Dict[str, Any]:
    """
    Run a single iteration of a bot by its ID.
    This is the main entry point for Celery tasks.
    
    Builds a config dict from the actual bot model in apps/bots/,
    then runs BotExecutor.
    
    Args:
        bot_id: UUID of the bot
        bot_type: 'grid', 'martingale', 'signal', or 'quantum_ai'
        restore_mode: If True, skip entry evaluation and attach to existing position
    
    Returns:
        Execution result dict
    """
    def _safe_float(val, default=None):
        try:
            return float(val) if val is not None else default
        except (TypeError, ValueError):
            return default

    try:
        # Guard: prevent duplicate starts (in-process + Redis for multi-worker)
        if not _mark_bot_starting(bot_id):
            return {'success': False, 'error': f'Bot {bot_id} is already running in this process'}
        if restore_mode and not _try_redis_lock(bot_id):
            _mark_bot_stopped(bot_id)
            return {'success': False, 'error': f'Bot {bot_id} restore locked by another worker'}

        # ---- Quantum AI: uses fund master keys, not user credentials ----
        if bot_type == 'quantum_ai':
            from apps.bots.models import QuantumAIBot
            from core.utils import decrypt_api_key
            bot = QuantumAIBot.objects.select_related('fund').get(id=bot_id)
            fund = bot.fund
            if bot.is_running and not restore_mode:
                _mark_bot_stopped(bot_id)
                return {'success': False, 'error': f'Bot {bot_id} is already running (DB flag)'}
            bot.is_running = True
            bot.save(update_fields=['is_running'])
            config = {
                'bot_id': str(bot.id),
                'bot_name': bot.bot_name,
                'bot_type': 'quantum_ai',
                'user_id': None,
                'strategy': 'quantum_ai',
                'symbol': bot.trading_pair,
                'exchange_name': bot.exchange_name,
                'api_key': decrypt_api_key(fund.master_api_key),
                'secret_key': decrypt_api_key(fund.master_secret_key),
                'passphrase': decrypt_api_key(fund.master_passphrase) if fund.master_passphrase else '',
                'is_testnet': False,
                'restore_mode': restore_mode,
                'parameters': {**bot.strategy_parameters},
            }
            from .bot_engine import BotEngine
            engine = BotEngine(config)
            engine.startBot()
            with _running_engines_lock:
                _running_engines[bot_id] = engine
            return {'success': True, 'mode': 'restore' if restore_mode else 'new', 'signal': engine.reason, 'side': engine.current_side}

        # ---- User bots: grid / martingale / signal ----
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
            _mark_bot_stopped(bot_id)
            return {'success': False, 'error': f'Unknown bot_type: {bot_type}'}

        if bot.is_running and not restore_mode:
            _mark_bot_stopped(bot_id)
            return {'success': False, 'error': f'Bot {bot_id} is already running (DB flag)'}
        bot.is_running = True
        bot.save(update_fields=['is_running'])

        from apps.exchanges.models import ExchangeCredentials
        credentials = ExchangeCredentials.objects.get(
            user=bot.user,
            exchange_name=bot.exchange_name,
            is_active=True
        )
        creds = credentials.get_decrypted_credentials()

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
            'restore_mode': restore_mode,
            'parameters': {},
        }

        if bot_type in ('grid', 'martingale'):
            config['parameters'] = {
                'favor_levels': bot.favor_levels,
                'against_levels': bot.against_levels,
                'favor_level_qty': _safe_float(bot.favor_level_qty, 0.0),
                'against_level_qty': _safe_float(bot.against_level_qty, 0.0),
                'favor_level_difference': _safe_float(bot.favor_level_difference, 0.5),
                'against_level_difference': _safe_float(bot.against_level_difference, 0.5),
                'Take_Profit': _safe_float(bot.take_profit_percent),
                'Stop_Loss': _safe_float(bot.stop_loss_percent),
                'Amount_Type': getattr(bot, 'amount_type', 'quote'),
                'Order_Type': 'market',
                'SLTP_Type': 'percentage',
                'quantity': _safe_float(bot.base_amount, 0.0),
            }
            from .bot_engine import BotEngine
            engine = BotEngine(config)
            engine.startBot()
            with _running_engines_lock:
                _running_engines[bot_id] = engine
            return {'success': True, 'signal': engine.reason, 'side': engine.current_side}

        # Signal bots: use BotExecutor strategy path
        executor = BotExecutor.from_config(config)
        return executor.run_once()

    except Exception as e:
        _mark_bot_stopped(bot_id)
        _release_redis_lock(bot_id)
        logger.error(f"Error running bot {bot_id}: {e}", exc_info=True)
        return {'success': False, 'error': str(e)}


def stop_bot(bot_id: str, bot_type: str = 'quantum_ai') -> Dict[str, Any]:
    """
    Stop a running bot by signaling its engine threads.
    """
    _mark_bot_stopped(bot_id)

    with _running_engines_lock:
        engine = _running_engines.pop(bot_id, None)

    if engine:
        engine.stop_bot()

    # Update DB flag
    try:
        if bot_type == 'quantum_ai':
            from apps.bots.models import QuantumAIBot
            QuantumAIBot.objects.filter(id=bot_id).update(is_running=False, stopped_at=datetime.utcnow())
        elif bot_type == 'grid':
            from apps.bots.models import GridBot
            GridBot.objects.filter(id=bot_id).update(is_running=False, stopped_at=datetime.utcnow())
        elif bot_type == 'martingale':
            from apps.bots.models import MartingaleBot
            MartingaleBot.objects.filter(id=bot_id).update(is_running=False, stopped_at=datetime.utcnow())
    except Exception as e:
        logger.error(f"Failed to update DB flag for {bot_id}: {e}")

    return {'success': True, 'bot_id': bot_id}
