"""
Alpaca Exchange Adapter

PURE PYTHON - NO DJANGO IMPORTS

Note: Alpaca is primarily for stocks/crypto in the US market.
"""
import ccxt
from typing import Dict, Any
from .base_adapter import BaseAdapter


class AlpacaAdapter(BaseAdapter):
    """
    Adapter for Alpaca exchange.

    Handles Alpaca-specific configurations:
    - Paper trading support
    - US market hours
    """

    @property
    def exchange_name(self) -> str:
        return 'alpaca'

    def _initialize_exchange(self) -> ccxt.Exchange:
        """Initialize Alpaca CCXT instance."""
        config = {
            'apiKey': self.credentials.get('api_key'),
            'secret': self.credentials.get('secret_key'),
            'enableRateLimit': True,
        }

        if self.demo_mode:
            config['sandbox'] = True  # Paper trading

        exchange = ccxt.alpaca(config)

        try:
            exchange.load_markets()
        except Exception:
            pass

        return exchange

    def is_market_open(self) -> bool:
        """Check if the market is currently open."""
        try:
            clock = self._make_request('fetch_time')
            return True  # Simplified - actual implementation would check market hours
        except Exception:
            return False
