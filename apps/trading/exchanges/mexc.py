"""
MEXC Exchange Adapter

PURE PYTHON - NO DJANGO IMPORTS
"""
import ccxt
from typing import Dict, Any
from .base_adapter import BaseAdapter


class MEXCAdapter(BaseAdapter):
    """
    Adapter for MEXC exchange.

    Handles MEXC-specific configurations.
    """

    @property
    def exchange_name(self) -> str:
        return 'mexc'

    def _initialize_exchange(self) -> ccxt.Exchange:
        """Initialize MEXC CCXT instance."""
        config = {
            'apiKey': self.credentials.get('api_key'),
            'secret': self.credentials.get('secret_key'),
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot',
            }
        }

        if self.demo_mode:
            config['sandbox'] = True

        exchange = ccxt.mexc(config)

        try:
            exchange.load_markets()
        except Exception:
            pass

        return exchange

    def set_market_type(self, market_type: str = 'spot'):
        """Set the market type."""
        self.exchange.options['defaultType'] = market_type
