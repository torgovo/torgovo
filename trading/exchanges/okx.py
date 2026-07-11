"""
OKX exchange integration
"""
import logging
from .base import BaseExchangeBot
import ccxt

logger = logging.getLogger('trading')


class OKXBot(BaseExchangeBot):
    """
    OKX exchange bot implementation.
    Supports spot, futures, and options trading.
    """

    def _create_exchange(self, api_key: str, secret_key: str, passphrase: str = None):
        """Create OKX CCXT exchange instance."""
        try:
            exchange = ccxt.okx({
                'apiKey': api_key,
                'secret': secret_key,
                'password': passphrase,  # OKX requires passphrase
                'enableRateLimit': True,
                'sandbox': self.is_testnet,
            })

            return exchange

        except Exception as e:
            logger.error(f"Error creating OKX exchange instance: {e}")
            raise