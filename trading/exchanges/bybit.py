"""
Bybit exchange integration
"""
import logging
from .base import BaseExchangeBot
import ccxt

logger = logging.getLogger('trading')


class BybitBot(BaseExchangeBot):
    """
    Bybit exchange bot implementation.
    Supports both linear and inverse futures.
    """

    def _create_exchange(self, api_key: str, secret_key: str, passphrase: str = None):
        """
        Create Bybit CCXT exchange instance.

        Args:
            api_key: Bybit API key
            secret_key: Bybit secret key
            passphrase: Not used for Bybit

        Returns:
            CCXT Bybit exchange instance
        """
        try:
            exchange = ccxt.bybit({
                'apiKey': api_key,
                'secret': secret_key,
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'linear',  # Can be 'linear', 'inverse', 'spot'
                    'test': self.is_testnet,
                },
                'sandbox': self.is_testnet,
            })

            if self.is_testnet:
                exchange.set_sandbox_mode(True)

            return exchange

        except Exception as e:
            logger.error(f"Error creating Bybit exchange instance: {e}")
            raise

    def set_market_type(self, market_type: str = 'linear'):
        """
        Set the market type (linear, inverse, spot).

        Args:
            market_type: Market type ('linear', 'inverse', 'spot')
        """
        try:
            self.exchange.options['defaultType'] = market_type

            # Recreate exchange with new market type
            self.exchange = ccxt.bybit({
                'apiKey': self.exchange.apiKey,
                'secret': self.exchange.secret,
                'enableRateLimit': True,
                'options': {
                    'defaultType': market_type,
                    'test': self.is_testnet,
                },
                'sandbox': self.is_testnet,
            })

            if self.is_testnet:
                exchange.set_sandbox_mode(True)

            logger.info(f"Set Bybit market type to {market_type}")

        except Exception as e:
            logger.error(f"Error setting market type to {market_type}: {e}")
            raise

    def get_position_info(self, symbol: str = None) -> list:
        """
        Get position information.

        Args:
            symbol: Trading symbol (optional)

        Returns:
            List of position information
        """
        try:
            positions = self._make_request('fetch_positions', [symbol]) if symbol else self._make_request('fetch_positions')

            return [
                {
                    'symbol': position['symbol'],
                    'side': position['side'],
                    'contracts': position['contracts'],
                    'contract_size': position['contractSize'],
                    'unrealized_pnl': position['unrealizedPnl'],
                    'leverage': position['leverage'],
                    'entry_price': position['entryPrice'],
                    'mark_price': position['markPrice'],
                    'liquidation_price': position['liquidationPrice'],
                    'take_profit_price': position['takeProfitPrice'],
                    'stop_loss_price': position['stopLossPrice'],
                    'percentage': position['percentage'],
                }
                for position in positions
                if float(position['contracts']) != 0  # Only return positions with size
            ]

        except Exception as e:
            logger.error(f"Error fetching position info: {e}")
            raise

    def set_position_mode(self, symbol: str, mode: str = 'hedge') -> bool:
        """
        Set position mode for a symbol.

        Args:
            symbol: Trading symbol
            mode: 'hedge' or 'one-way'

        Returns:
            True if successful
        """
        try:
            self._make_request('set_position_mode', symbol, mode)
            logger.info(f"Set position mode to {mode} for {symbol}")
            return True

        except Exception as e:
            logger.error(f"Error setting position mode for {symbol}: {e}")
            return False

    def set_leverage(self, symbol: str, leverage: float) -> bool:
        """
        Set leverage for a symbol.

        Args:
            symbol: Trading symbol
            leverage: Leverage multiplier

        Returns:
            True if successful
        """
        try:
            self._make_request('set_leverage', leverage, symbol)
            logger.info(f"Set leverage to {leverage}x for {symbol}")
            return True

        except Exception as e:
            logger.error(f"Error setting leverage for {symbol}: {e}")
            return False

    def set_take_profit(self, symbol: str, side: str, amount: float, take_profit_price: float) -> dict:
        """
        Set take profit order.

        Args:
            symbol: Trading symbol
            side: 'buy' or 'sell'
            amount: Order amount
            take_profit_price: Take profit price

        Returns:
            Order information
        """
        try:
            order = self._make_request('create_take_profit_order', symbol, side, amount, take_profit_price)
            return self._format_order(order)

        except Exception as e:
            logger.error(f"Error setting take profit: {e}")
            raise

    def set_stop_loss(self, symbol: str, side: str, amount: float, stop_loss_price: float) -> dict:
        """
        Set stop loss order.

        Args:
            symbol: Trading symbol
            side: 'buy' or 'sell'
            amount: Order amount
            stop_loss_price: Stop loss price

        Returns:
            Order information
        """
        try:
            order = self._make_request('create_stop_order', symbol, side, amount, stop_loss_price)
            return self._format_order(order)

        except Exception as e:
            logger.error(f"Error setting stop loss: {e}")
            raise

    def get_trading_limits(self, symbol: str) -> dict:
        """
        Get trading limits for a symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Trading limits information
        """
        try:
            markets = self._make_request('fetch_markets')
            for market in markets:
                if market['symbol'] == symbol:
                    return {
                        'amount': {
                            'min': market['limits']['amount']['min'],
                            'max': market['limits']['amount']['max'],
                        },
                        'price': {
                            'min': market['limits']['price']['min'],
                            'max': market['limits']['price']['max'],
                        },
                        'cost': {
                            'min': market['limits']['cost']['min'],
                            'max': market['limits']['cost']['max'],
                        },
                        'leverage': {
                            'min': market['info'].get('leverage_filter', {}).get('min_leverage', 1),
                            'max': market['info'].get('leverage_filter', {}).get('max_leverage', 100),
                        }
                    }

            return None

        except Exception as e:
            logger.error(f"Error fetching trading limits for {symbol}: {e}")
            return None

    def get_last_traded_price(self, symbol: str) -> float:
        """
        Get last traded price for a symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Last traded price
        """
        try:
            ticker = self._make_request('fetch_ticker', symbol)
            return float(ticker.get('last', 0))

        except Exception as e:
            logger.error(f"Error fetching last price for {symbol}: {e}")
            return 0

    def get_mark_price(self, symbol: str) -> float:
        """
        Get mark price for a symbol (futures only).

        Args:
            symbol: Trading symbol

        Returns:
            Mark price
        """
        try:
            ticker = self._make_request('fetch_ticker', symbol)
            return float(ticker.get('mark_price', 0))

        except Exception as e:
            logger.error(f"Error fetching mark price for {symbol}: {e}")
            return 0

    def get_funding_rate(self, symbol: str) -> dict:
        """
        Get funding rate information.

        Args:
            symbol: Trading symbol

        Returns:
            Funding rate information
        """
        try:
            funding_rate = self._make_request('fetch_funding_rate', symbol)
            return {
                'symbol': symbol,
                'funding_rate': funding_rate.get('fundingRate'),
                'funding_timestamp': funding_rate.get('timestamp'),
                'funding_datetime': funding_rate.get('datetime'),
            }

        except Exception as e:
            logger.error(f"Error fetching funding rate for {symbol}: {e}")
            return None

    def get_server_time(self) -> dict:
        """
        Get Bybit server time.

        Returns:
            Server time information
        """
        try:
            server_time = self._make_request('fetch_time')
            return {
                'timestamp': server_time,
                'datetime': server_time / 1000,  # Convert to seconds
            }

        except Exception as e:
            logger.error(f"Error fetching server time: {e}")
            raise

    def get_orderbook(self, symbol: str, limit: int = 20) -> dict:
        """
        Get order book for a symbol.

        Args:
            symbol: Trading symbol
            limit: Number of bids/asks to return

        Returns:
            Order book data
        """
        try:
            orderbook = self._make_request('fetch_order_book', symbol, limit)
            return {
                'symbol': symbol,
                'bids': orderbook.get('bids', [])[:limit],
                'asks': orderbook.get('asks', [])[:limit],
                'timestamp': orderbook.get('timestamp'),
                'datetime': orderbook.get('datetime'),
            }

        except Exception as e:
            logger.error(f"Error fetching order book for {symbol}: {e}")
            raise

    def create_conditional_order(self, symbol: str, side: str, order_type: str,
                               amount: float, price: float = None,
                               trigger_price: float = None,
                               take_profit: float = None,
                               stop_loss: float = None) -> dict:
        """
        Create conditional order.

        Args:
            symbol: Trading symbol
            side: 'buy' or 'sell'
            order_type: Order type ('limit', 'market', 'stop', 'stop_limit')
            amount: Order amount
            price: Order price (for limit orders)
            trigger_price: Trigger price (for stop orders)
            take_profit: Take profit price
            stop_loss: Stop loss price

        Returns:
            Order information
        """
        try:
            params = {}
            if trigger_price:
                params['triggerPrice'] = trigger_price
            if take_profit:
                params['takeProfitPrice'] = take_profit
            if stop_loss:
                params['stopLossPrice'] = stop_loss

            order = self._make_request('create_order', symbol, order_type, side, amount, price, params)
            return self._format_order(order)

        except Exception as e:
            logger.error(f"Error creating conditional order: {e}")
            raise

    def get_api_key_info(self) -> dict:
        """
        Get API key information and permissions.

        Returns:
            API key information
        """
        try:
            info = self._make_request('fetch_balance')
            # Bybit doesn't have a direct method to get API key info
            # We can infer from successful balance fetch that the key is valid
            return {
                'status': 'active',
                'permissions': {
                    'read': True,
                    'trade': True,
                    'withdraw': True,  # This may need separate verification
                }
            }

        except Exception as e:
            logger.error(f"Error fetching API key info: {e}")
            raise