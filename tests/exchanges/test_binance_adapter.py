import pytest
from unittest.mock import MagicMock, patch, PropertyMock

import ccxt

from apps.trading.exchanges.binance import BinanceAdapter


@pytest.fixture
def mock_ccxt_binance():
    with patch('apps.trading.exchanges.binance.ccxt.binance') as mock_exchange_class:
        mock_exchange = MagicMock(spec=ccxt.binance)
        mock_exchange.id = 'binance'
        mock_exchange.options = {'defaultType': 'spot', 'adjustForTimeDifference': True}
        mock_exchange.markets = {
            'BTC/USDT': {
                'limits': {'amount': {'min': 0.0001, 'max': 9000}},
                'precision': {'amount': 4, 'price': 2},
            }
        }
        mock_exchange.amount_to_precision = MagicMock(side_effect=lambda s, a: f"{a:.4f}")
        mock_exchange.price_to_precision = MagicMock(side_effect=lambda s, p: f"{p:.2f}")
        mock_exchange_class.return_value = mock_exchange
        yield mock_exchange_class


@pytest.fixture
def adapter(mock_ccxt_binance):
    a = BinanceAdapter(
        credentials={'api_key': 'test_key', 'secret_key': 'test_secret'},
        demo_mode=False
    )
    a.exchange = mock_ccxt_binance.return_value
    return a


class TestBinanceInitialization:
    def test_exchange_name(self, adapter):
        assert adapter.exchange_name == 'binance'

    def test_initialize_exchange_spot_default(self, mock_ccxt_binance):
        a = BinanceAdapter(
            credentials={'api_key': 'ak', 'secret_key': 'sk'},
            demo_mode=False
        )
        config = mock_ccxt_binance.call_args[0][0]
        assert config['apiKey'] == 'ak'
        assert config['secret'] == 'sk'
        assert config['options']['defaultType'] == 'spot'
        assert config['enableRateLimit'] is True

    def test_initialize_exchange_demo_mode(self, mock_ccxt_binance):
        a = BinanceAdapter(
            credentials={'api_key': 'ak', 'secret_key': 'sk'},
            demo_mode=True
        )
        config = mock_ccxt_binance.call_args[0][0]
        assert config['sandbox'] is True
        assert 'testnet.binance.vision' in config['urls']['api']['public']

    def test_initialize_exchange_load_markets(self, mock_ccxt_binance):
        a = BinanceAdapter(
            credentials={'api_key': 'ak', 'secret_key': 'sk'},
            demo_mode=False
        )
        a.exchange.load_markets.assert_called_once()

    def test_initialize_exchange_load_markets_failure(self, mock_ccxt_binance):
        mock_ccxt_binance.return_value.load_markets.side_effect = Exception('market load fail')
        a = BinanceAdapter(
            credentials={'api_key': 'ak', 'secret_key': 'sk'},
            demo_mode=False
        )
        assert a.exchange is not None

    def test_rate_limit_settings(self, adapter):
        assert adapter.rate_limit_delay == 0.05
        assert adapter.max_retries == 3

    def test_str_repr(self, adapter):
        assert str(adapter) == "BinanceAdapter(demo=False)"
        assert repr(adapter) == "BinanceAdapter(exchange=binance, demo=False)"


class TestBinanceSymbolFormat:
    def test_default_symbol_no_change(self, adapter):
        assert adapter.format_symbol('BTC/USDT') == 'BTC/USDT'

    def test_format_symbol_on_fetch(self, adapter):
        adapter.exchange.fetch_ticker = MagicMock(return_value={
            'symbol': 'BTC/USDT', 'last': 50000, 'bid': 49900, 'ask': 50100,
            'high': 51000, 'low': 49000, 'baseVolume': 1000, 'quoteVolume': 50000000,
            'change': 200, 'percentage': 0.4, 'timestamp': 1234567890000,
        })
        result = adapter.fetch_ticker('BTC/USDT')
        assert result['last'] == 50000.0


class TestBinanceSetMarketType:
    def test_set_market_type_spot(self, adapter):
        adapter.set_market_type('spot')
        assert adapter.exchange.options['defaultType'] == 'spot'

    def test_set_market_type_futures(self, adapter):
        adapter.set_market_type('futures')
        assert adapter.exchange.options['defaultType'] == 'futures'


class TestBinanceSetLeverage:
    def test_set_leverage_calls_exchange(self, adapter):
        adapter.exchange.set_leverage = MagicMock(return_value={'leverage': 10})
        adapter.format_symbol = MagicMock(return_value='BTC/USDT')
        result = adapter.set_leverage('BTC/USDT', 10)
        assert result['leverage'] == 10
        adapter.exchange.set_leverage.assert_called_once_with(10, 'BTC/USDT')


class TestBinanceSetMarginMode:
    def test_set_margin_mode_cross(self, adapter):
        adapter.exchange.set_margin_mode = MagicMock(return_value={'mode': 'cross'})
        adapter.format_symbol = MagicMock(return_value='BTC/USDT')
        result = adapter.set_margin_mode('BTC/USDT', 'cross')
        assert result['mode'] == 'cross'
        adapter.exchange.set_margin_mode.assert_called_once_with('cross', 'BTC/USDT')


class TestBinanceStopLossOrder:
    def test_create_stop_loss_order(self, adapter):
        adapter.exchange.create_order = MagicMock(return_value={
            'id': 'sl1', 'symbol': 'BTC/USDT', 'side': 'sell', 'type': 'STOP_MARKET',
            'amount': 1.0, 'price': None, 'filled': 0.0, 'remaining': 1.0,
            'cost': 0.0, 'status': 'open', 'timestamp': 0, 'fee': {},
        })
        adapter.amount_to_precision = MagicMock(return_value=1.0)
        adapter.price_to_precision = MagicMock(return_value=49000.0)

        result = adapter.create_stop_loss_order('BTC/USDT', 'sell', 1.0, 49000.0)

        assert result['id'] == 'sl1'
        assert result['type'] == 'STOP_MARKET'
        args = adapter.exchange.create_order.call_args[0]
        assert args[1] == 'BTC/USDT'
        assert args[2] == 'STOP_MARKET'
        assert args[3] == 'sell'
        assert args[4] == 1.0
        assert args[5] is None
        assert args[6]['stopPrice'] == 49000.0

    def test_create_stop_loss_with_extra_params(self, adapter):
        adapter.exchange.create_order = MagicMock(return_value={
            'id': 'sl2', 'symbol': 'BTC/USDT', 'side': 'sell', 'type': 'STOP_MARKET',
            'amount': 1.0, 'filled': 0.0, 'remaining': 1.0,
            'cost': 0.0, 'status': 'open', 'timestamp': 0, 'fee': {},
        })
        adapter.amount_to_precision = MagicMock(return_value=1.0)
        adapter.price_to_precision = MagicMock(return_value=49000.0)

        result = adapter.create_stop_loss_order('BTC/USDT', 'sell', 1.0, 49000.0,
                                                params={'reduceOnly': True})
        args = adapter.exchange.create_order.call_args[0]
        assert args[6]['reduceOnly'] is True
        assert args[6]['stopPrice'] == 49000.0


class TestBinanceTakeProfitOrder:
    def test_create_take_profit_order(self, adapter):
        adapter.exchange.create_order = MagicMock(return_value={
            'id': 'tp1', 'symbol': 'BTC/USDT', 'side': 'buy', 'type': 'TAKE_PROFIT_MARKET',
            'amount': 0.5, 'price': None, 'filled': 0.0, 'remaining': 0.5,
            'cost': 0.0, 'status': 'open', 'timestamp': 0, 'fee': {},
        })
        adapter.amount_to_precision = MagicMock(return_value=0.5)
        adapter.price_to_precision = MagicMock(return_value=52000.0)

        result = adapter.create_take_profit_order('BTC/USDT', 'buy', 0.5, 52000.0)

        assert result['id'] == 'tp1'
        assert result['type'] == 'TAKE_PROFIT_MARKET'
        args = adapter.exchange.create_order.call_args[0]
        assert args[2] == 'TAKE_PROFIT_MARKET'
        assert args[6]['stopPrice'] == 52000.0


class TestBinanceGetFundingRate:
    def test_get_funding_rate(self, adapter):
        adapter.exchange.fetch_funding_rate = MagicMock(return_value={
            'fundingRate': 0.0001,
            'fundingTimestamp': 1234567890000,
            'nextFundingTimestamp': 1234567980000,
        })
        adapter.format_symbol = MagicMock(return_value='BTC/USDT')
        result = adapter.get_funding_rate('BTC/USDT')
        assert result['symbol'] == 'BTC/USDT'
        assert result['funding_rate'] == 0.0001
        assert result['funding_timestamp'] == 1234567890000
        assert result['next_funding_timestamp'] == 1234567980000


class TestBinanceErrorHandling:
    def test_network_error_retry(self, adapter):
        adapter.max_retries = 3
        adapter.retry_delay = 0.01
        mock = MagicMock(side_effect=[
            ccxt.NetworkError('timeout'),
            {'last': 50000},
        ])
        adapter.exchange.fetch_ticker = mock
        with patch('time.sleep'):
            result = adapter._make_request('fetch_ticker', 'BTC/USDT')
        assert result['last'] == 50000

    def test_authentication_error(self, adapter):
        adapter.exchange.fetch_balance = MagicMock(side_effect=ccxt.AuthenticationError('invalid key'))
        with pytest.raises(ccxt.AuthenticationError):
            adapter._make_request('fetch_balance')

    def test_order_failure_exchange_error(self, adapter):
        adapter.exchange.create_limit_order = MagicMock(side_effect=ccxt.ExchangeError('insufficient balance'))
        adapter.amount_to_precision = MagicMock(return_value=1.0)
        adapter.price_to_precision = MagicMock(return_value=50000.0)
        with pytest.raises(ccxt.ExchangeError):
            adapter.create_limit_order('BTC/USDT', 'buy', 1.0, 50000.0)

    def test_rate_limit_retry(self, adapter):
        adapter.max_retries = 2
        adapter.retry_delay = 0.01
        mock = MagicMock(side_effect=[
            ccxt.RateLimitExceeded('too fast'),
            {'id': 'o1'},
        ])
        adapter.exchange.create_market_order = mock
        adapter.amount_to_precision = MagicMock(return_value=1.0)
        with patch('time.sleep'):
            result = adapter.create_market_order('BTC/USDT', 'buy', 1.0)
        assert result['id'] == 'o1'
