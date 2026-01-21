"""
Bybit Exchange Adapter

PURE PYTHON - NO DJANGO IMPORTS
"""
import ccxt
from typing import Dict, Any, List, Optional
from .base_adapter import BaseAdapter


class BybitAdapter(BaseAdapter):
    """
    Adapter for Bybit exchange.

    Handles Bybit-specific configurations:
    - Symbol formatting (BTC/USDT:USDT for perpetual futures)
    - Testnet configuration
    - Unified account support
    """

    @property
    def exchange_name(self) -> str:
        return 'bybit'

    def _initialize_exchange(self) -> ccxt.Exchange:
        """Initialize Bybit CCXT instance."""
        config = {
            'apiKey': self.credentials.get('api_key'),
            'secret': self.credentials.get('secret_key'),
            'enableRateLimit': True,
            'options': {
                'defaultType': 'swap',  # Perpetual futures by default
                'adjustForTimeDifference': True,
            }
        }

        if self.demo_mode:
            config['sandbox'] = True

        exchange = ccxt.bybit(config)

        # Load markets
        try:
            exchange.load_markets()
        except Exception:
            pass

        return exchange

    def format_symbol(self, symbol: str) -> str:
        """
        Format symbol for Bybit.

        Bybit perpetual futures use format: BTC/USDT:USDT
        Spot uses standard format: BTC/USDT
        """
        if self.exchange.options.get('defaultType') == 'swap':
            # For perpetual futures, add settlement currency
            if ':' not in symbol:
                base_quote = symbol.split('/')
                if len(base_quote) == 2:
                    return f"{symbol}:{base_quote[1]}"
        return symbol

    def set_market_type(self, market_type: str = 'swap'):
        """
        Set the market type.

        Args:
            market_type: 'spot', 'swap' (perpetual), 'future', 'option'
        """
        self.exchange.options['defaultType'] = market_type

    def set_leverage(self, symbol: str, leverage: int, side: str = None) -> Dict[str, Any]:
        """
        Set leverage for a symbol.

        Args:
            symbol: Trading pair
            leverage: Leverage multiplier
            side: 'long', 'short', or None for both

        Returns:
            Response from exchange
        """
        formatted_symbol = self.format_symbol(symbol)

        params = {}
        if side:
            params['side'] = 'Buy' if side.lower() == 'long' else 'Sell'

        return self._make_request('set_leverage', leverage, formatted_symbol, params)

    def set_position_mode(self, hedged: bool = False) -> Dict[str, Any]:
        """
        Set position mode.

        Args:
            hedged: True for hedge mode (separate long/short), False for one-way

        Returns:
            Response from exchange
        """
        mode = 'BothSide' if hedged else 'MergedSingle'
        return self._make_request('set_position_mode', hedged)

    def create_market_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Create a market order with Bybit-specific handling.

        Bybit requires 'Buy'/'Sell' for perpetual futures.
        """
        formatted_symbol = self.format_symbol(symbol)
        amount = self.amount_to_precision(symbol, amount)

        # Bybit uses capitalized sides for some endpoints
        bybit_side = side.lower()

        order_params = params or {}

        order = self._make_request(
            'create_market_order',
            formatted_symbol,
            bybit_side,
            amount,
            params=order_params
        )
        return self._normalize_order(order)

    def create_limit_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float,
        params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Create a limit order with Bybit-specific handling."""
        formatted_symbol = self.format_symbol(symbol)
        amount = self.amount_to_precision(symbol, amount)
        price = self.price_to_precision(symbol, price)

        bybit_side = side.lower()
        order_params = params or {}

        order = self._make_request(
            'create_limit_order',
            formatted_symbol,
            bybit_side,
            amount,
            price,
            params=order_params
        )
        return self._normalize_order(order)

    def create_stop_loss_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        stop_price: float,
        params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Create a stop-loss order."""
        formatted_symbol = self.format_symbol(symbol)
        amount = self.amount_to_precision(symbol, amount)
        stop_price = self.price_to_precision(symbol, stop_price)

        order_params = {
            'stopLoss': {
                'triggerPrice': stop_price,
            }
        }
        if params:
            order_params.update(params)

        order = self._make_request(
            'create_order',
            formatted_symbol,
            'market',
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
        """Create a take-profit order."""
        formatted_symbol = self.format_symbol(symbol)
        amount = self.amount_to_precision(symbol, amount)
        take_profit_price = self.price_to_precision(symbol, take_profit_price)

        order_params = {
            'takeProfit': {
                'triggerPrice': take_profit_price,
            }
        }
        if params:
            order_params.update(params)

        order = self._make_request(
            'create_order',
            formatted_symbol,
            'market',
            side.lower(),
            amount,
            None,
            order_params
        )
        return self._normalize_order(order)

    def get_wallet_balance(self, account_type: str = 'UNIFIED') -> Dict[str, Any]:
        """
        Get wallet balance for Bybit unified account.

        Args:
            account_type: 'UNIFIED', 'CONTRACT', 'SPOT'

        Returns:
            Balance information
        """
        params = {'accountType': account_type}
        balance = self._make_request('fetch_balance', params)
        return {
            'total': balance.get('total', {}),
            'free': balance.get('free', {}),
            'used': balance.get('used', {}),
        }

    def get_funding_rate(self, symbol: str) -> Dict[str, Any]:
        """Get current funding rate for perpetual."""
        formatted_symbol = self.format_symbol(symbol)
        try:
            funding = self._make_request('fetch_funding_rate', formatted_symbol)
            return {
                'symbol': symbol,
                'funding_rate': float(funding.get('fundingRate', 0)),
                'funding_timestamp': funding.get('fundingTimestamp'),
            }
        except Exception:
            return {
                'symbol': symbol,
                'funding_rate': 0,
                'funding_timestamp': None,
            }

    def get_position_info(self, symbol: str) -> Dict[str, Any]:
        """Get detailed position information."""
        positions = self.fetch_positions(symbol)
        if positions:
            return positions[0]
        return {
            'symbol': symbol,
            'side': None,
            'contracts': 0,
            'entry_price': 0,
            'unrealized_pnl': 0,
        }
