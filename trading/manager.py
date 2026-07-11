"""
Trading Manager for handling multiple trading bots across different users and exchanges.
"""
import threading
import logging
from typing import Dict, Any, Optional
from django.utils import timezone
from django.contrib.auth import get_user_model
from .exchanges.binance import BinanceBot
from .exchanges.bybit import BybitBot
from .exchanges.okx import OKXBot
from .exchanges.mexc import MEXCBot
from .exchanges.alpaca import AlpacaBot
from .strategies.grid_bot import GridTradingStrategy
from .strategies.martingale_bot import MartingaleTradingStrategy
from .strategies.quantum_ai_bot import QuantumAITradingStrategy

User = get_user_model()
logger = logging.getLogger('trading')


class TradingManager:
    """
    Centralized manager for handling multiple trading bots across different users and exchanges.

    Key Responsibilities:
    - Initialize and manage trading bots for different users and pairs
    - Provide thread-safe bot creation and management
    - Handle bot lifecycle (create, start, stop, refresh)
    - Exchange-specific bot instantiation
    - Async bot execution with threading
    """

    def __init__(self):
        # Thread-safe dictionary to store bots
        self._bots: Dict[str, Any] = {}
        self._grid_bots: Dict[str, Any] = {}
        self._martingale_bots: Dict[str, Any] = {}
        self._quantum_ai_bots: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self.logger = logging.getLogger(__name__)

    def create_bot(self, user: User, bot_type: str, config: Dict[str, Any]) -> Optional[Any]:
        """
        Create a trading bot for a specific user and configuration.

        Args:
            user: Django user instance
            bot_type: Type of bot (grid, martingale, quantum_ai, custom)
            config: Bot configuration dictionary

        Returns:
            Bot instance or None if creation fails
        """
        from apps.payments.models import BotSubscription

        bot_key = self._generate_bot_key(user, bot_type, config)

        # Validate subscription exists and is active
        try:
            subscription = BotSubscription.objects.get(
                user=user,
                plan__bot_type=bot_type,
                status='active'
            )
            config['subscription_id'] = str(subscription.id)  # Pass to bot if needed
        except BotSubscription.DoesNotExist:
            self.logger.error(f"No active {bot_type} subscription for user {user.id}")
            raise ValueError(f"No active subscription found. Please subscribe first.")

        with self._lock:
            # Check if bot already exists
            if bot_key in self._bots:
                self.logger.warning(f"Bot {bot_key} already exists. Returning existing instance.")
                return self._bots[bot_key]

            try:
                # Create bot based on type
                if bot_type == 'grid':
                    bot = self._create_grid_bot(user, config)
                    self._grid_bots[bot_key] = bot
                elif bot_type == 'martingale':
                    bot = self._create_martingale_bot(user, config)
                    self._martingale_bots[bot_key] = bot
                elif bot_type == 'quantum_ai':
                    bot = self._create_quantum_ai_bot(user, config)
                    self._quantum_ai_bots[bot_key] = bot
                elif bot_type == 'custom':
                    # Custom bots use webhook, not TradingManager
                    self.logger.warning("Custom bots are managed via webhooks, not TradingManager")
                    return None
                else:
                    self.logger.error(f"Unsupported bot type: {bot_type}")
                    return None

                self._bots[bot_key] = bot
                self.logger.info(f"Created {bot_type} bot for {bot_key}")
                return bot

            except Exception as e:
                self.logger.error(f"Failed to create {bot_type} bot: {e}")
                return None

    def _create_grid_bot(self, user: User, config: Dict[str, Any]) -> GridTradingStrategy:
        """Create grid trading bot."""
        exchange_bot = self._get_exchange_bot(user, config['exchange_name'])
        return GridTradingStrategy(
            user=user,
            exchange_bot=exchange_bot,
            config=config
        )

    def _create_martingale_bot(self, user: User, config: Dict[str, Any]) -> MartingaleTradingStrategy:
        """Create martingale trading bot."""
        exchange_bot = self._get_exchange_bot(user, config['exchange_name'])
        return MartingaleTradingStrategy(
            user=user,
            exchange_bot=exchange_bot,
            config=config
        )

    def _create_quantum_ai_bot(self, user: User, config: Dict[str, Any]) -> QuantumAITradingStrategy:
        """Create quantum AI trading bot."""
        exchange_bots = {}
        for exchange_name in config.get('exchanges', []):
            exchange_bots[exchange_name] = self._get_exchange_bot(user, exchange_name)

        return QuantumAITradingStrategy(
            user=user,
            exchange_bots=exchange_bots,
            config=config
        )

    def _get_exchange_bot(self, user: User, exchange_name: str):
        """Get exchange-specific bot instance."""
        from apps.exchanges.models import ExchangeCredentials

        try:
            credentials = ExchangeCredentials.objects.get(
                user=user,
                exchange_name=exchange_name,
                is_active=True
            )

            # Create exchange bot based on exchange name
            if exchange_name.lower() == 'binance':
                return BinanceBot(user, credentials)
            elif exchange_name.lower() == 'bybit':
                return BybitBot(user, credentials)
            elif exchange_name.lower() == 'okx':
                return OKXBot(user, credentials)
            elif exchange_name.lower() == 'mexc':
                return MEXCBot(user, credentials)
            elif exchange_name.lower() == 'alpaca':
                return AlpacaBot(user, credentials)
            else:
                raise ValueError(f"Unsupported exchange: {exchange_name}")

        except ExchangeCredentials.DoesNotExist:
            raise ValueError(f"No credentials found for exchange: {exchange_name}")

    def _generate_bot_key(self, user: User, bot_type: str, config: Dict[str, Any]) -> str:
        """Generate unique bot key."""
        if bot_type == 'quantum_ai':
            return f"{user.id}_{bot_type}_{config.get('bot_name', 'default')}"
        else:
            return f"{user.id}_{bot_type}_{config.get('trading_pair', 'unknown')}_{config.get('exchange_name', 'unknown')}"

    def start_bot(self, user: User, bot_type: str, config: Dict[str, Any]) -> bool:
        """
        Start a specific bot.
        Validates subscription before starting.

        Args:
            user: Django user instance
            bot_type: Type of bot
            config: Bot configuration

        Returns:
            True if bot started successfully
        """
        from apps.payments.models import BotSubscription

        bot_key = self._generate_bot_key(user, bot_type, config)

        # Verify subscription is active before starting
        try:
            subscription = BotSubscription.objects.get(
                user=user,
                plan__bot_type=bot_type,
                status='active'
            )
        except BotSubscription.DoesNotExist:
            self.logger.error(f"Cannot start bot: No active {bot_type} subscription for {user.id}")
            return False

        with self._lock:
            bot = self._bots.get(bot_key)
            if not bot:
                self.logger.warning(f"Bot {bot_key} not found")
                return False

            # Use threading to start bot asynchronously
            bot_thread = threading.Thread(
                target=self._run_bot,
                args=(bot, bot_type, bot_key),
                daemon=True
            )
            bot_thread.start()

            # Update database status
            self._update_bot_status(user, bot_type, config, is_running=True)

            self.logger.info(f"Started {bot_type} bot {bot_key}")
            return True

    def _run_bot(self, bot: Any, bot_type: str, bot_key: str):
        """Run bot in separate thread."""
        try:
            if hasattr(bot, 'start'):
                bot.start()
            elif hasattr(bot, 'run'):
                bot.run()
            else:
                self.logger.error(f"Bot {bot_key} doesn't have start() or run() method")
        except Exception as e:
            self.logger.error(f"Error running {bot_type} bot {bot_key}: {e}")

    def stop_bot(self, user: User, bot_type: str, config: Dict[str, Any]) -> bool:
        """
        Stop a specific bot.

        Args:
            user: Django user instance
            bot_type: Type of bot
            config: Bot configuration

        Returns:
            True if bot stopped successfully
        """
        bot_key = self._generate_bot_key(user, bot_type, config)

        with self._lock:
            bot = self._bots.get(bot_key)
            if bot:
                try:
                    if hasattr(bot, 'stop'):
                        bot.stop()
                    elif hasattr(bot, 'shutdown'):
                        bot.shutdown()

                    # Remove from active bots
                    self._remove_bot_from_dictionaries(bot_key, bot_type)

                    # Update database status
                    self._update_bot_status(user, bot_type, config, is_running=False)

                    self.logger.info(f"Stopped and removed {bot_type} bot {bot_key}")
                    return True
                except Exception as e:
                    self.logger.error(f"Error stopping {bot_type} bot {bot_key}: {e}")
                    return False
            return False

    def _remove_bot_from_dictionaries(self, bot_key: str, bot_type: str):
        """Helper to remove bot from all tracking dictionaries."""
        if bot_key in self._bots:
            del self._bots[bot_key]
        if bot_type == 'grid' and bot_key in self._grid_bots:
            del self._grid_bots[bot_key]
        elif bot_type == 'martingale' and bot_key in self._martingale_bots:
            del self._martingale_bots[bot_key]
        elif bot_type == 'quantum_ai' and bot_key in self._quantum_ai_bots:
            del self._quantum_ai_bots[bot_key]

    def _update_bot_status(self, user: User, bot_type: str, config: Dict[str, Any], is_running: bool):
        """Update bot running status in database."""
        from apps.bots.models import GridBot, MartingaleBot

        try:
            if bot_type == 'grid':
                GridBot.objects.filter(
                    user=user,
                    trading_pair=config['trading_pair'],
                    exchange_name=config['exchange_name']
                ).update(
                    is_running=is_running,
                    started_at=timezone.now() if is_running else None,
                    stopped_at=timezone.now() if not is_running else None
                )
            elif bot_type == 'martingale':
                MartingaleBot.objects.filter(
                    user=user,
                    trading_pair=config['trading_pair'],
                    exchange_name=config['exchange_name']
                ).update(
                    is_running=is_running,
                    started_at=timezone.now() if is_running else None,
                    stopped_at=timezone.now() if not is_running else None
                )
        except Exception as e:
            self.logger.error(f"Failed to update bot status in DB: {e}")

    def get_bot(self, user: User, bot_type: str, config: Dict[str, Any]) -> Optional[Any]:
        """
        Retrieve a specific bot instance.

        Args:
            user: Django user instance
            bot_type: Type of bot
            config: Bot configuration

        Returns:
            Bot instance or None
        """
        bot_key = self._generate_bot_key(user, bot_type, config)
        return self._bots.get(bot_key)

    def refresh_bot_config(self, user: User, bot_type: str, config: Dict[str, Any]) -> bool:
        """
        Refresh configuration of an existing bot from the database.

        Args:
            user: Django user instance
            bot_type: Type of bot
            config: Current configuration

        Returns:
            True if bot was refreshed successfully
        """
        from apps.bots.models import PairConfig

        bot_key = self._generate_bot_key(user, bot_type, config)

        with self._lock:
            bot = self._bots.get(bot_key)
            if not bot:
                self.logger.warning(f"Bot {bot_key} not found for refresh")
                return False

            try:
                # Get fresh configuration from database
                pair_config = PairConfig.objects.get(
                    subscription__user=user,
                    pair_symbol=config['trading_pair'],
                    bot_type=bot_type,
                    subscription__status='active'
                )

                # Update bot's configuration (your bots must have this method)
                if hasattr(bot, 'config'):
                    bot.config = pair_config
                elif hasattr(bot, 'update_config'):
                    bot.update_config(pair_config)

                self.logger.info(f"Refreshed configuration for {bot_type} bot {bot_key}")
                return True

            except Exception as e:
                self.logger.error(f"Failed to refresh {bot_type} bot {bot_key}: {e}")
                return False

    def refresh_all_bots_for_user(self, user: User) -> int:
        """
        Refresh configuration for all bots belonging to a specific user.

        Args:
            user: Django user instance

        Returns:
            Number of bots refreshed
        """
        refreshed_count = 0

        with self._lock:
            # Find all bots for this user
            user_bots = {k: v for k, v in self._bots.items() if str(user.id) in k}

            for bot_key, bot in user_bots.items():
                # Extract bot type and config from bot_key
                parts = bot_key.split('_')
                if len(parts) >= 2:
                    bot_type = parts[1]

                    # Try to get bot config from bot instance
                    config = {}
                    if hasattr(bot, 'config'):
                        config = bot.config
                    elif hasattr(bot, 'get_config'):
                        config = bot.get_config()
                    else:
                        # Default config for refresh
                        config = {'bot_name': 'unknown'}

                    if self.refresh_bot_config(user, bot_type, config):
                        refreshed_count += 1

        self.logger.info(f"Refreshed {refreshed_count} bots for user {user.email}")
        return refreshed_count

    def get_user_bots(self, user: User) -> Dict[str, Dict[str, Any]]:
        """
        Get all bots for a specific user.

        Args:
            user: Django user instance

        Returns:
            Dictionary of bot information
        """
        user_bots = {}

        with self._lock:
            for bot_key, bot in self._bots.items():
                if str(user.id) in bot_key:
                    # Extract bot type from key
                    parts = bot_key.split('_')
                    bot_type = parts[1] if len(parts) > 1 else 'unknown'

                    user_bots[bot_key] = {
                        'type': bot_type,
                        'bot': bot,
                        'status': 'running' if hasattr(bot, 'is_running') and bot.is_running else 'stopped',
                        'config': getattr(bot, 'config', {}),
                    }

        return user_bots

    def get_system_stats(self) -> Dict[str, Any]:
        """
        Get system-wide statistics.

        Returns:
            Dictionary with system statistics
        """
        with self._lock:
            total_bots = len(self._bots)
            grid_bots = len(self._grid_bots)
            martingale_bots = len(self._martingale_bots)
            quantum_ai_bots = len(self._quantum_ai_bots)

            # Count running bots
            running_bots = 0
            for bot in self._bots.values():
                if hasattr(bot, 'is_running') and bot.is_running:
                    running_bots += 1

            return {
                'total_bots': total_bots,
                'running_bots': running_bots,
                'grid_bots': grid_bots,
                'martingale_bots': martingale_bots,
                'quantum_ai_bots': quantum_ai_bots,
                'stopped_bots': total_bots - running_bots,
            }

    def shutdown_all_bots(self):
        """Shutdown all running bots."""
        with self._lock:
            bots_to_stop = list(self._bots.items())

        for bot_key, bot in bots_to_stop:
            try:
                if hasattr(bot, 'stop'):
                    bot.stop()
                elif hasattr(bot, 'shutdown'):
                    bot.shutdown()
                self.logger.info(f"Shutdown bot {bot_key}")
            except Exception as e:
                self.logger.error(f"Error shutting down bot {bot_key}: {e}")

        # Clear all bot dictionaries
        with self._lock:
            self._bots.clear()
            self._grid_bots.clear()
            self._martingale_bots.clear()
            self._quantum_ai_bots.clear()

        self.logger.info("All bots have been shutdown")


# Global singleton instance
trading_manager = TradingManager()