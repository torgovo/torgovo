"""
Binance exchange integration
"""
import logging
from .base import BaseExchangeBot
import ccxt

logger = logging.getLogger('trading')


class BinanceBot(BaseExchangeBot):
    """
    Binance exchange bot implementation.
    Supports both spot and futures trading.
    """

    def _create_exchange(self, api_key: str, secret_key: str, passphrase: str = None):
        """
        Create Binance CCXT exchange instance.

        Args:
            api_key: Binance API key
            secret_key: Binance secret key
            passphrase: Not used for Binance

        Returns:
            CCXT Binance exchange instance
        """
        try:
            exchange = ccxt.binance({
                'apiKey': api_key,
                'secret': secret_key,
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'spot',  # Can be 'spot', 'future', 'margin'
                    'test': self.is_testnet,
                },
                'sandbox': self.is_testnet,
            })

            if self.is_testnet:
                exchange.set_sandbox_mode(True)

            return exchange

        except Exception as e:
            logger.error(f"Error creating Binance exchange instance: {e}")
            raise

    def set_market_type(self, market_type: str = 'spot'):
        """
        Set the market type (spot, futures, margin).

        Args:
            market_type: Market type ('spot', 'future', 'margin')
        """
        try:
            self.exchange.options['defaultType'] = market_type

            # Recreate exchange with new market type
            self.exchange = ccxt.binance({
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

            logger.info(f"Set Binance market type to {market_type}")

        except Exception as e:
            logger.error(f"Error setting market type to {market_type}: {e}")
            raise

    def get_leverage(self, symbol: str) -> float:
        """
        Get current leverage for a symbol (futures only).

        Args:
            symbol: Trading symbol

        Returns:
            Current leverage
        """
        try:
            if self.exchange.options['defaultType'] == 'future':
                return self._make_request('fetch_leverage', symbol)
            else:
                return 1.0  # No leverage in spot trading

        except Exception as e:
            logger.error(f"Error fetching leverage for {symbol}: {e}")
            return 1.0

    def set_leverage(self, symbol: str, leverage: float) -> bool:
        """
        Set leverage for a symbol (futures only).

        Args:
            symbol: Trading symbol
            leverage: Leverage multiplier

        Returns:
            True if successful
        """
        try:
            if self.exchange.options['defaultType'] == 'future':
                self._make_request('set_leverage', leverage, symbol)
                logger.info(f"Set leverage to {leverage}x for {symbol}")
                return True
            else:
                logger.warning("Leverage can only be set in futures market")
                return False

        except Exception as e:
            logger.error(f"Error setting leverage for {symbol}: {e}")
            return False

    def get_position(self, symbol: str) -> dict:
        """
        Get current position for a symbol (futures only).

        Args:
            symbol: Trading symbol

        Returns:
            Position information
        """
        try:
            if self.exchange.options['defaultType'] == 'future':
                positions = self._make_request('fetch_positions', [symbol])

                for position in positions:
                    if position['symbol'] == symbol and float(position['contracts']) != 0:
                        return {
                            'symbol': position['symbol'],
                            'side': position['side'],
                            'contracts': position['contracts'],
                            'contract_size': position['contractSize'],
                            'unrealized_pnl': position['unrealizedPnl'],
                            'leverage': position['leverage'],
                            'entry_price': position['entryPrice'],
                            'mark_price': position['markPrice'],
                        }

                return None
            else:
                return None

        except Exception as e:
            logger.error(f"Error fetching position for {symbol}: {e}")
            return None

    def get_account_info(self) -> dict:
        """
        Get detailed account information.

        Returns:
            Account information including trading permissions
        """
        try:
            account = self._make_request('fetch_account')

            # Add trading permissions based on account type
            info = {
                'account_type': account.get('type', 'spot'),
                'can_trade': True,
                'can_withdraw': True,
                'can_deposit': True,
                'update_time': account.get('datetime'),
                'account_level': account.get('tier', 0),
            }

            if self.exchange.options['defaultType'] == 'future':
                info.update({
                    'total_initial_margin': account.get('info', {}).get('totalInitialMargin', 0),
                    'total_maint_margin': account.get('info', {}).get('totalMaintMargin', 0),
                    'total_wallet_balance': account.get('info', {}).get('totalWalletBalance', 0),
                    'total_unrealized_pnl': account.get('info', {}).get('totalUnrealizedProfit', 0),
                })

            return info

        except Exception as e:
            logger.error(f"Error fetching account info: {e}")
            raise

    def get_withdraw_history(self, currency: str = None) -> list:
        """
        Get withdrawal history.

        Args:
            currency: Currency symbol (optional)

        Returns:
            List of withdrawal records
        """
        try:
            withdrawals = self._make_request('fetch_withdrawals', currency)
            return [
                {
                    'id': w.get('id'),
                    'currency': w.get('currency'),
                    'amount': w.get('amount'),
                    'fee': w.get('fee'),
                    'address': w.get('address'),
                    'tag': w.get('tag'),
                    'txid': w.get('txid'),
                    'timestamp': w.get('timestamp'),
                    'datetime': w.get('datetime'),
                    'status': w.get('status'),
                }
                for w in withdrawals
            ]

        except Exception as e:
            logger.error(f"Error fetching withdrawal history: {e}")
            raise

    def get_deposit_history(self, currency: str = None) -> list:
        """
        Get deposit history.

        Args:
            currency: Currency symbol (optional)

        Returns:
            List of deposit records
        """
        try:
            deposits = self._make_request('fetch_deposits', currency)
            return [
                {
                    'id': d.get('id'),
                    'currency': d.get('currency'),
                    'amount': d.get('amount'),
                    'address': d.get('address'),
                    'tag': d.get('tag'),
                    'txid': d.get('txid'),
                    'timestamp': d.get('timestamp'),
                    'datetime': d.get('datetime'),
                    'status': d.get('status'),
                }
                for d in deposits
            ]

        except Exception as e:
            logger.error(f"Error fetching deposit history: {e}")
            raise

    def create_oco_order(self, symbol: str, side: str, amount: float, price: float,
                        stop_price: float, stop_limit_price: float = None) -> dict:
        """
        Create OCO (One-Cancels-Other) order.

        Args:
            symbol: Trading symbol
            side: 'buy' or 'sell'
            amount: Order amount
            price: Limit price
            stop_price: Stop loss trigger price
            stop_limit_price: Stop loss limit price (optional)

        Returns:
            Order information
        """
        try:
            order = self._make_request('create_oco_order', symbol, side, amount, price, stop_price, stop_limit_price)
            return {
                'id': order.get('id'),
                'symbol': order.get('symbol'),
                'side': order.get('side'),
                'type': 'oco',
                'amount': order.get('amount'),
                'price': order.get('price'),
                'stop_price': order.get('stopPrice'),
                'stop_limit_price': order.get('stopLimitPrice'),
                'orders': order.get('orders', []),
                'status': order.get('status'),
                'timestamp': order.get('timestamp'),
            }

        except Exception as e:
            logger.error(f"Error creating OCO order: {e}")
            raise

    def get_klines(self, symbol: str, timeframe: str = '1h', limit: int = 100) -> list:
        """
        Get candlestick/kline data.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe (1m, 5m, 1h, 4h, 1d, etc.)
            limit: Number of candles

        Returns:
            List of OHLCV data
        """
        try:
            ohlcv = self._make_request('fetch_ohlcv', symbol, timeframe, None, limit)

            return [
                {
                    'timestamp': candle[0],
                    'datetime': candle[1],
                    'open': candle[2],
                    'high': candle[3],
                    'low': candle[4],
                    'close': candle[5],
                    'volume': candle[6],
                }
                for candle in ohlcv
            ]

        except Exception as e:
            logger.error(f"Error fetching klines for {symbol}: {e}")
            raise

    def get_24hr_ticker(self, symbol: str = None) -> dict:
        """
        Get 24 hour ticker price change statistics.

        Args:
            symbol: Trading symbol (optional)

        Returns:
            24hr ticker data
        """
        try:
            ticker = self._make_request('fetch_ticker', symbol) if symbol else self._make_request('fetch_tickers')

            if symbol:
                return {
                    'symbol': ticker.get('symbol'),
                    'price_change': ticker.get('change'),
                    'price_change_percent': ticker.get('percentage'),
                    'weighted_avg_price': ticker.get('vwap'),
                    'prev_close_price': ticker.get('previousClose'),
                    'last_price': ticker.get('last'),
                    'last_qty': ticker.get('info', {}).get('Q', 0),
                    'bid_price': ticker.get('bid'),
                    'bid_qty': ticker.get('bidVolume', 0),
                    'ask_price': ticker.get('ask'),
                    'ask_qty': ticker.get('askVolume', 0),
                    'open_price': ticker.get('open'),
                    'high_price': ticker.get('high'),
                    'low_price': ticker.get('low'),
                    'volume': ticker.get('baseVolume'),
                    'quote_volume': ticker.get('quoteVolume'),
                    'open_time': ticker.get('timestamp'),
                    'close_time': ticker.get('timestamp'),
                    'count': ticker.get('info', {}).get('count', 0),
                }
            else:
                return {
                    symbol_data['symbol']: {
                        'price_change': symbol_data.get('change'),
                        'price_change_percent': symbol_data.get('percentage'),
                        'last_price': symbol_data.get('last'),
                        'volume': symbol_data.get('baseVolume'),
                    }
                    for symbol_data in ticker
                }

        except Exception as e:
            logger.error(f"Error fetching 24hr ticker: {e}")
            raise