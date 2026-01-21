"""
OKX Exchange Adapter

PURE PYTHON - NO DJANGO IMPORTS
"""
import ccxt
from typing import Dict, Any, Optional
from .base_adapter import BaseAdapter


class OKXAdapter(BaseAdapter):
    """
    Adapter for OKX exchange.

    Handles OKX-specific configurations:
    - Requires passphrase for authentication
    - Symbol formatting
    - Testnet configuration
    """

    @property
    def exchange_name(self) -> str:
        return 'okx'

    def _initialize_exchange(self) -> ccxt.Exchange:
        """Initialize OKX CCXT instance."""
        config = {
            'apiKey': self.credentials.get('api_key'),
            'secret': self.credentials.get('secret_key'),
            'password': self.credentials.get('passphrase'),  # OKX requires passphrase
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot',
            }
        }

        if self.demo_mode:
            config['sandbox'] = True

        exchange = ccxt.okx(config)

        try:
            exchange.load_markets()
        except Exception:
            pass

        return exchange

    def set_market_type(self, market_type: str = 'spot'):
        """
        Set the market type.

        Args:
            market_type: 'spot', 'swap', 'futures', 'option'
        """
        self.exchange.options['defaultType'] = market_type

    def format_symbol(self, symbol: str) -> str:
        """Format symbol for OKX perpetual swaps."""
        if self.exchange.options.get('defaultType') == 'swap':
            if ':' not in symbol and '-SWAP' not in symbol:
                base_quote = symbol.split('/')
                if len(base_quote) == 2:
                    return f"{symbol}:{base_quote[1]}"
        return symbol

    def set_leverage(self, symbol: str, leverage: int, margin_mode: str = 'cross') -> Dict[str, Any]:
        """Set leverage for a symbol."""
        formatted_symbol = self.format_symbol(symbol)
        params = {'mgnMode': margin_mode}
        return self._make_request('set_leverage', leverage, formatted_symbol, params)

    def get_account_config(self) -> Dict[str, Any]:
        """Get account configuration."""
        return self._make_request('fetch_account_configuration')
