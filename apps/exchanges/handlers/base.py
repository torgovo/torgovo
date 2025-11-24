import threading
import logging
from typing import Dict, Any

# from bot.bots.BinanceBot import BinanceBots
from apps.exchanges.handlers.bybitbot import BybitBots
# from bot.bots.KrakenSpotBot import KrakenBots
# from bot.BybitArbitrageBot import BybitArbitrageBot
# from bot.bots.MexcBot import MexcBots

logger = logging.getLogger('Torgovo.BotManager')

class TradingManager:
    """
    Centralized manager for handling multiple trading bots across different users and pairs.

    Key Responsibilities:
    - Initialize and manage trading bots for different users and pairs
    - Provide thread-safe bot creation and management
    - Handle bot lifecycle (start, stop, pause)
    """

    def __init__(self):
        # Thread-safe dictionary to store bots
        self._bots: Dict[str, Any] = {}
        self._arbitrage_bots: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self.logger = logging.getLogger(__name__)

    def create_arbitrage_bot(self, user: object, exchange: str):
        arbitrage_key = f"{user}_{exchange}_arbitrage"
        with self._lock:
            if arbitrage_key in self._arbitrage_bots:
                self.logger.warning(f"Arbitrage Bot {arbitrage_key} already exists. Returning existing instance.")
                return self._bots[arbitrage_key]

            if exchange == 'bybit':
                print("Creating Bybit Arbitrage Bot...")
                try:
                    # arbitrage = BybitArbitrageBot(user)
                    # self._arbitrage_bots[arbitrage_key] = arbitrage
                    # self.logger.info(f"Created Arbitrage Bot for {arbitrage_key}")
                    # return arbitrage
                    pass
                except Exception as e:
                    self.logger.error(f"Failed to create {exchange} Arbitrage bot: {e}")
                    raise

    def start_arbitrage_bot(self, user: object, exchange: str):
        """
        Start a specific arbitrage bot for a user and exchange.
        """
        arbitrage_key = f"{user}_{exchange}_arbitrage"

        with self._lock:
            bot = self._arbitrage_bots.get(arbitrage_key)
            if not bot:
                print(f"Arbitrage Bot {arbitrage_key} not found")
                self.logger.warning(f"Arbitrage Bot {arbitrage_key} not found")
                return False

            # Use threading to start bot asynchronously
            bot_thread = threading.Thread(target=bot.startBot)
            bot_thread.start()
            self.logger.info(f"Started arbitrage bot {arbitrage_key}")
            print(f"Started arbitrage bot {arbitrage_key}")
            return True

    def stop_arbitrage_bot(self, user: object, exchange: str):
        """
        Stop a specific arbitrage bot for a user and exchange.
        """
        arbitrage_key = f"{user}_{exchange}_arbitrage"

        with self._lock:
            bot = self._arbitrage_bots.get(arbitrage_key)
            if bot:
                bot.stop_bot()
                del self._arbitrage_bots[arbitrage_key]
                self.logger.info(f"Stopped and removed arbitrage bot {arbitrage_key}")
                return True
            return False

    def get_arbitrage_bot(self, user: object, exchange: str):
        """
        Retrieve a specific arbitrage bot instance.
        """
        arbitrage_key = f"{user}_{exchange}_arbitrage"
        return self._arbitrage_bots.get(arbitrage_key)

    def create_bot(self, user: object, pair_config: Dict[str, Any], exchange: str):
        """
        Create a trading bot for a specific user and pair configuration.

        Args:
            user (object): Unique identifier for the user
            pair_config (dict): Configuration for the trading pair
            exchange (str): Exchange to trade on (e.g., 'binance', 'bybit')

        Returns:
            Bot instance for the given configuration
            :param user:
        """
        # Generate a unique bot identifier
        bot_key = f"{user}_{pair_config['pair_symbol']}_{exchange}"
        with self._lock:
            # Check if bot already exists
            if bot_key in self._bots:
                self.logger.warning(f"Bot {bot_key} already exists. Returning existing instance.")
                return self._bots[bot_key]

            # Create and store the bot
            if exchange == "binance":
                print('creating Binance bot')
                try:
                    # bot = BinanceBots(
                    #     user=user,
                    #     pair_config=pair_config
                    # )
                    # self._bots[bot_key] = bot
                    # self.logger.info(f"Created Binancebot for {bot_key}")
                    # return bot
                    pass
                except Exception as e:
                    self.logger.error(f"Failed to create Binance bot: {e}")
                    raise
            elif exchange == "bybit":
                print('creating bybit bot')
                try:
                    bot = BybitBots(
                        user=user,
                        pair_config=pair_config
                    )
                    self._bots[bot_key] = bot
                    self.logger.info(f"Created Bybit-bot for {bot_key}")
                    return bot
                except Exception as e:
                    self.logger.error(f"Failed to create Bybit-bot: {e}")
                    raise

            elif exchange == "mexc":
                print('creating bybit bot')
                try:
                    # bot = MexcBots(
                    #     user=user,
                    #     pair_config=pair_config
                    # )
                    # self._bots[bot_key] = bot
                    # self.logger.info(f"Created Mexc-bot for {bot_key}")
                    # return bot
                    pass
                except Exception as e:
                    self.logger.error(f"Failed to create Mexc-bot: {e}")
                    raise

            elif exchange == "kraken_spot":
                print('creating Kraken spot bot')
                try:
                    # bot = KrakenBots(
                    #     user=user,
                    #     pair_config=pair_config
                    # )
                    # self._bots[bot_key] = bot
                    # self.logger.info(f"Created Kraken-spot-bot for {bot_key}")
                    # return bot
                    pass
                except Exception as e:
                    self.logger.error(f"Failed to create Kraken-spot-bot: {e}")
                    raise

    def start_bot(self, user: object, pair_symbol: str, exchange: str):
        """
        Start a specific bot for a user and pair.

        Args:
            user_id (int): User identifier
            pair_symbol (str): Trading pair symbol
            exchange (str): Exchange name
            :param exchange:
            :param pair_symbol:
            :param user:
        """
        bot_key = f"{user}_{pair_symbol}_{exchange}"

        with self._lock:
            bot = self._bots.get(bot_key)
            if not bot:
                print(f"Bot {bot_key} not found")
                self.logger.warning(f"Bot {bot_key} not found")
                return False

            # Use threading to start bot asynchronously
            bot_thread = threading.Thread(target=bot.startBot)
            bot_thread.start()
            
            return True

    def stop_bot(self, user: object, pair_symbol: str, exchange: str):
        """
        Stop a specific bot for a user and pair.

        Args:
            user (object): User identifier
            pair_symbol (str): Trading pair symbol
            exchange (str): Exchange name
        """
        bot_key = f"{user}_{pair_symbol}_{exchange}"

        with self._lock:
            bot = self._bots.get(bot_key)
            if bot:
                bot.stop_bot()
                del self._bots[bot_key]
                self.logger.info(f"Stopped and removed bot {bot_key}")

    def get_bot(self, user_id: int, pair_symbol: str, exchange: str):
        """
        Retrieve a specific bot instance.

        Args:
            user_id (int): User identifier
            pair_symbol (str): Trading pair symbol
            exchange (str): Exchange name

        Returns:
            Bot instance or None
        """
        bot_key = f"{user_id}_{pair_symbol}_{exchange}"
        return self._bots.get(bot_key)

    def refresh_bot_config(self, user: object, pair_symbol: str, exchange: str):
        """
        Refresh the configuration of an existing bot from the database.
        
        Args:
            user (object): User object
            pair_symbol (str): Trading pair symbol
            exchange (str): Exchange name
            
        Returns:
            bool: True if bot was refreshed, False if bot doesn't exist
        """
        bot_key = f"{user}_{pair_symbol}_{exchange}"
        
        with self._lock:
            bot = self._bots.get(bot_key)
            if not bot:
                self.logger.warning(f"Bot {bot_key} not found for refresh")
                return False
            
            try:
                # Import here to avoid circular imports
                from apps.bots.models import PairConfig
                from apps.bots.serializers import PairConfigSerializer
                
                # Get fresh configuration from database
                pair_config = PairConfig.objects.get(
                    user=user,
                    pair_symbol=pair_symbol
                )
                
                # Convert to dictionary format
                pair_config_dict = PairConfigSerializer(pair_config)
                
                # Update bot's configuration
                bot.pair_config = pair_config_dict.data
                
                # Update conditions with new config
                if hasattr(bot, 'update_conditions'):
                    bot.update_conditions()
                
                self.logger.info(f"Refreshed configuration for bot {bot_key}")
                return True
                
            except Exception as e:
                self.logger.error(f"Failed to refresh bot {bot_key}: {e}")
                return False

    def refresh_all_bots_for_user(self, user: object):
        """
        Refresh configuration for all bots belonging to a specific user.
        
        Args:
            user (object): User object
            
        Returns:
            int: Number of bots refreshed
        """
        refreshed_count = 0
        
        with self._lock:
            # Find all bots for this user
            user_bots = {k: v for k, v in self._bots.items() if k.startswith(f"{user}_")}
            
            for bot_key, bot in user_bots.items():
                # Extract pair_symbol and exchange from bot_key
                parts = bot_key.split('_')
                if len(parts) >= 3:
                    pair_symbol = parts[1]
                    exchange = parts[2]
                    
                    if self.refresh_bot_config(user, pair_symbol, exchange):
                        refreshed_count += 1
        
        self.logger.info(f"Refreshed {refreshed_count} bots for user {user}")
        return refreshed_count


# Global singleton instance
trading_manager = TradingManager()