"""
Binance Exchange Adapter

PURE PYTHON - NO DJANGO IMPORTS
"""
import ccxt
from typing import Dict, Any, List, Optional
from .base_adapter import BaseAdapter


class BinanceAdapter(BaseAdapter):
    """
    Adapter for Binance exchange.

    Handles Binance-specific configurations:
    - Symbol formatting (standard format)
    - Testnet configuration
    - Rate limiting (1200 requests/minute)
    """

    @property
    def exchange_name(self) -> str:
        return 'binance'

    def _initialize_exchange(self) -> ccxt.Exchange:
        """Initialize Binance CCXT instance."""
        config = {
            'apiKey': self.credentials.get('api_key'),
            'secret': self.credentials.get('secret_key'),
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot',
                'adjustForTimeDifference': True,
            }
        }

        if self.demo_mode:
            config['sandbox'] = True
            # Binance testnet URLs
            config['urls'] = {
                'api': {
                    'public': 'https://testnet.binance.vision/api/v3',
                    'private': 'https://testnet.binance.vision/api/v3',
                }
            }

        exchange = ccxt.binance(config)

        # Load markets
        try:
            exchange.load_markets()
        except Exception:
            pass  # Markets will be loaded on first request

        return exchange

    def set_market_type(self, market_type: str = 'spot'):
        """
        Set the market type (spot, futures, margin).

        Args:
            market_type: 'spot', 'futures', or 'margin'
        """
        self.exchange.options['defaultType'] = market_type

    def set_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        """
        Set leverage for futures trading.

        Args:
            symbol: Trading pair
            leverage: Leverage multiplier (1-125)

        Returns:
            Response from exchange
        """
        formatted_symbol = self.format_symbol(symbol)
        return self._make_request('set_leverage', leverage, formatted_symbol)

    def set_margin_mode(self, symbol: str, mode: str = 'cross') -> Dict[str, Any]:
        """
        Set margin mode for futures trading.

        Args:
            symbol: Trading pair
            mode: 'cross' or 'isolated'

        Returns:
            Response from exchange
        """
        formatted_symbol = self.format_symbol(symbol)
        return self._make_request('set_margin_mode', mode, formatted_symbol)

    def create_stop_loss_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        stop_price: float,
        params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Create a stop-loss order.

        Args:
            symbol: Trading pair
            side: 'buy' or 'sell'
            amount: Order amount
            stop_price: Trigger price

        Returns:
            Order response
        """
        formatted_symbol = self.format_symbol(symbol)
        amount = self.amount_to_precision(symbol, amount)
        stop_price = self.price_to_precision(symbol, stop_price)

        order_params = {
            'stopPrice': stop_price,
            'type': 'STOP_MARKET',
        }
        if params:
            order_params.update(params)

        order = self._make_request(
            'create_order',
            formatted_symbol,
            'STOP_MARKET',
            side.lower(),
            amount,
            None,
            order_params
        )
        return self._normalize_order(order)

    def create_take_profit_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        take_profit_price: float,
        params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Create a take-profit order.

        Args:
            symbol: Trading pair
            side: 'buy' or 'sell'
            amount: Order amount
            take_profit_price: Trigger price

        Returns:
            Order response
        """
        formatted_symbol = self.format_symbol(symbol)
        amount = self.amount_to_precision(symbol, amount)
        take_profit_price = self.price_to_precision(symbol, take_profit_price)

        order_params = {
            'stopPrice': take_profit_price,
            'type': 'TAKE_PROFIT_MARKET',
        }
        if params:
            order_params.update(params)

        order = self._make_request(
            'create_order',
            formatted_symbol,
            'TAKE_PROFIT_MARKET',
            side.lower(),
            amount,
            None,
            order_params
        )
        return self._normalize_order(order)

    def get_funding_rate(self, symbol: str) -> Dict[str, Any]:
        """Get current funding rate for perpetual futures."""
        formatted_symbol = self.format_symbol(symbol)
        funding = self._make_request('fetch_funding_rate', formatted_symbol)
        return {
            'symbol': symbol,
            'funding_rate': float(funding.get('fundingRate', 0)),
            'funding_timestamp': funding.get('fundingTimestamp'),
            'next_funding_timestamp': funding.get('nextFundingTimestamp'),
        }
