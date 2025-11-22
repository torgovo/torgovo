"""
MEXC exchange integration
"""
import logging
from .base import BaseExchangeBot
import ccxt

logger = logging.getLogger('trading')


class MEXCBot(BaseExchangeBot):
    """
    MEXC exchange bot implementation.
    Supports spot and futures trading.
    """

    def _create_exchange(self, api_key: str, secret_key: str, passphrase: str = None):
        """Create MEXC CCXT exchange instance."""
        try:
            exchange = ccxt.mexc({
                'apiKey': api_key,
                'secret': secret_key,
                'enableRateLimit': True,
                'sandbox': self.is_testnet,
            })

            return exchange

        except Exception as e:
            logger.error(f"Error creating MEXC exchange instance: {e}")
            raise