"""
Alpaca exchange integration
"""
import logging
from .base import BaseExchangeBot
import ccxt

logger = logging.getLogger('trading')


class AlpacaBot(BaseExchangeBot):
    """
    Alpaca exchange bot implementation.
    Supports stock and crypto trading.
    """

    def _create_exchange(self, api_key: str, secret_key: str, passphrase: str = None):
        """Create Alpaca CCXT exchange instance."""
        try:
            exchange = ccxt.alpaca({
                'apiKey': api_key,
                'secret': secret_key,
                'enableRateLimit': True,
                'sandbox': self.is_testnet,
            })

            return exchange

        except Exception as e:
            logger.error(f"Error creating Alpaca exchange instance: {e}")
            raise