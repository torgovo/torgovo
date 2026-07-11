import pytest
from unittest.mock import MagicMock, patch

import ccxt

from apps.trading.exchanges.okx import OKXAdapter
from apps.trading.exchanges.mexc import MEXCAdapter
from apps.trading.exchanges.alpaca import AlpacaAdapter


# ==============================================================================
# OKX TESTS
# ==============================================================================

@pytest.fixture
def mock_ccxt_okx():
    with patch('apps.trading.exchanges.okx.ccxt.okx') as mock_exchange_class:
        mock_exchange = MagicMock(spec=ccxt.okx)
        mock_exchange.id = 'okx'
        mock_exchange.options = {'defaultType': 'spot'}
        mock_exchange.markets = {
            'BTC/USDT': {
                'limits': {'amount': {'min': 0.0001, 'max': 1000}},
                'precision': {'amount': 4, 'price': 2},
            },
            'BTC/USDT:USDT': {
                'limits': {'amount': {'min': 0.0001, 'max': 1000}},
                'precision': {'amount': 4, 'price': 2},
            },
        }
        mock_exchange.amount_to_precision = MagicMock(side_effect=lambda s, a: f"{a:.4f}")
        mock_exchange.price_to_precision = MagicMock(side_effect=lambda s, p: f"{p:.2f}")
        mock_exchange_class.return_value = mock_exchange
        yield mock_exchange_class


@pytest.fixture
def okx_adapter(mock_ccxt_okx):
    a = OKXAdapter(
        credentials={'api_key': 'ok', 'secret_key': 'osk', 'passphrase': 'opass'},
        demo_mode=False
    )
    a.exchange = mock_ccxt_okx.return_value
    return a


class TestOKXAdapter:
    def test_exchange_name(self, okx_adapter):
        assert okx_adapter.exchange_name == 'okx'

    def test_initialize_exchange_with_passphrase(self, mock_ccxt_okx):
        a = OKXAdapter(
            credentials={'api_key': 'ak', 'secret_key': 'sk', 'passphrase': 'pp'},
            demo_mode=False
        )
        config = mock_ccxt_okx.call_args[0][0]
        assert config['apiKey'] == 'ak'
        assert config['secret'] == 'sk'
        assert config['password'] == 'pp'
        assert config['options']['defaultType'] == 'spot'

    def test_initialize_exchange_demo_mode(self, mock_ccxt_okx):
        a = OKXAdapter(
            credentials={'api_key': 'ak', 'secret_key': 'sk', 'passphrase': 'pp'},
            demo_mode=True
        )
        config = mock_ccxt_okx.call_args[0][0]
        assert config['sandbox'] is True

    def test_initialize_load_markets(self, mock_ccxt_okx):
        a = OKXAdapter(
            credentials={'api_key': 'ak', 'secret_key': 'sk', 'passphrase': 'pp'},
            demo_mode=False
        )
        a.exchange.load_markets.assert_called_once()

    def test_initialize_load_markets_failure(self, mock_ccxt_okx):
        mock_ccxt_okx.return_value.load_markets.side_effect = Exception('load fail')
        a = OKXAdapter(
            credentials={'api_key': 'ak', 'secret_key': 'sk', 'passphrase': 'pp'},
            demo_mode=False
        )
        assert a.exchange is not None

    def test_str_repr(self, okx_adapter):
        assert str(okx_adapter) == "OKXAdapter(demo=False)"
        assert repr(okx_adapter) == "OKXAdapter(exchange=okx, demo=False)"

    def test_default_symbol_format_no_change(self, okx_adapter):
        assert okx_adapter.format_symbol('BTC/USDT') == 'BTC/USDT'

    def test_swap_symbol_format(self, okx_adapter):
        okx_adapter.exchange.options['defaultType'] = 'swap'
        result = okx_adapter.format_symbol('BTC/USDT')
        assert result == 'BTC/USDT:USDT'

    def test_swap_symbol_already_formatted(self, okx_adapter):
        okx_adapter.exchange.options['defaultType'] = 'swap'
        assert okx_adapter.format_symbol('BTC/USDT:USDT') == 'BTC/USDT:USDT'

    def test_swap_symbol_has_swap_suffix(self, okx_adapter):
        okx_adapter.exchange.options['defaultType'] = 'swap'
        assert okx_adapter.format_symbol('BTC/USDT-SWAP') == 'BTC/USDT-SWAP'

    def test_set_market_type(self, okx_adapter):
        okx_adapter.set_market_type('swap')
        assert okx_adapter.exchange.options['defaultType'] == 'swap'
        okx_adapter.set_market_type('spot')
        assert okx_adapter.exchange.options['defaultType'] == 'spot'

    def test_set_leverage(self, okx_adapter):
        okx_adapter.exchange.set_leverage = MagicMock(return_value={'leverage': 10})
        okx_adapter.format_symbol = MagicMock(return_value='BTC/USDT')
        result = okx_adapter.set_leverage('BTC/USDT', 10)
        assert result['leverage'] == 10
        okx_adapter.exchange.set_leverage.assert_called_once_with(10, 'BTC/USDT', {'mgnMode': 'cross'})

    def test_set_leverage_isolated(self, okx_adapter):
        okx_adapter.exchange.set_leverage = MagicMock(return_value={'leverage': 5})
        okx_adapter.format_symbol = MagicMock(return_value='BTC/USDT')
        result = okx_adapter.set_leverage('BTC/USDT', 5, margin_mode='isolated')
        okx_adapter.exchange.set_leverage.assert_called_once_with(5, 'BTC/USDT', {'mgnMode': 'isolated'})

    def test_get_account_config(self, okx_adapter):
        okx_adapter.exchange.fetch_account_configuration = MagicMock(return_value={'acctLv': '1'})
        result = okx_adapter.get_account_config()
        assert result['acctLv'] == '1'

    def test_fetch_ticker_works(self, okx_adapter):
        okx_adapter.exchange.fetch_ticker = MagicMock(return_value={
            'symbol': 'BTC/USDT', 'last': 50000, 'bid': 49900, 'ask': 50100,
            'high': 51000, 'low': 49000, 'baseVolume': 1000, 'quoteVolume': 50000000,
            'change': 200, 'percentage': 0.4, 'timestamp': 1234567890000,
        })
        result = okx_adapter.fetch_ticker('BTC/USDT')
        assert result['last'] == 50000.0

    def test_create_market_order_works(self, okx_adapter):
        okx_adapter.exchange.create_market_order = MagicMock(return_value={
            'id': 'okx1', 'symbol': 'BTC/USDT', 'side': 'buy', 'type': 'market',
            'amount': 1.0, 'filled': 1.0, 'remaining': 0.0, 'cost': 50000.0,
            'status': 'closed', 'timestamp': 0, 'fee': {},
        })
        okx_adapter.amount_to_precision = MagicMock(return_value=1.0)
        result = okx_adapter.create_market_order('BTC/USDT', 'buy', 1.0)
        assert result['id'] == 'okx1'


# ==============================================================================
# MEXC TESTS
# ==============================================================================

@pytest.fixture
def mock_ccxt_mexc():
    with patch('apps.trading.exchanges.mexc.ccxt.mexc') as mock_exchange_class:
        mock_exchange = MagicMock(spec=ccxt.mexc)
        mock_exchange.id = 'mexc'
        mock_exchange.options = {'defaultType': 'spot'}
        mock_exchange.markets = {
            'BTC/USDT': {
                'limits': {'amount': {'min': 0.00001, 'max': 1000}},
                'precision': {'amount': 5, 'price': 2},
            },
        }
        mock_exchange.amount_to_precision = MagicMock(side_effect=lambda s, a: f"{a:.5f}")
        mock_exchange.price_to_precision = MagicMock(side_effect=lambda s, p: f"{p:.2f}")
        mock_exchange_class.return_value = mock_exchange
        yield mock_exchange_class


@pytest.fixture
def mexc_adapter(mock_ccxt_mexc):
    a = MEXCAdapter(
        credentials={'api_key': 'mk', 'secret_key': 'msk'},
        demo_mode=False
    )
    a.exchange = mock_ccxt_mexc.return_value
    return a


class TestMEXCAdapter:
    def test_exchange_name(self, mexc_adapter):
        assert mexc_adapter.exchange_name == 'mexc'

    def test_initialize_exchange_defaults(self, mock_ccxt_mexc):
        a = MEXCAdapter(
            credentials={'api_key': 'ak', 'secret_key': 'sk'},
            demo_mode=False
        )
        config = mock_ccxt_mexc.call_args[0][0]
        assert config['apiKey'] == 'ak'
        assert config['secret'] == 'sk'
        assert config['enableRateLimit'] is True
        assert config['options']['defaultType'] == 'spot'

    def test_initialize_exchange_demo_mode(self, mock_ccxt_mexc):
        a = MEXCAdapter(
            credentials={'api_key': 'ak', 'secret_key': 'sk'},
            demo_mode=True
        )
        config = mock_ccxt_mexc.call_args[0][0]
        assert config['sandbox'] is True

    def test_initialize_load_markets(self, mock_ccxt_mexc):
        a = MEXCAdapter(
            credentials={'api_key': 'ak', 'secret_key': 'sk'},
            demo_mode=False
        )
        a.exchange.load_markets.assert_called_once()

    def test_initialize_load_markets_failure(self, mock_ccxt_mexc):
        mock_ccxt_mexc.return_value.load_markets.side_effect = Exception('load fail')
        a = MEXCAdapter(
            credentials={'api_key': 'ak', 'secret_key': 'sk'},
            demo_mode=False
        )
        assert a.exchange is not None

    def test_str_repr(self, mexc_adapter):
        assert str(mexc_adapter) == "MEXCAdapter(demo=False)"
        assert repr(mexc_adapter) == "MEXCAdapter(exchange=mexc, demo=False)"

    def test_default_symbol_format(self, mexc_adapter):
        assert mexc_adapter.format_symbol('BTC/USDT') == 'BTC/USDT'

    def test_set_market_type(self, mexc_adapter):
        mexc_adapter.set_market_type('swap')
        assert mexc_adapter.exchange.options['defaultType'] == 'swap'
        mexc_adapter.set_market_type('spot')
        assert mexc_adapter.exchange.options['defaultType'] == 'spot'

    def test_fetch_ticker_works(self, mexc_adapter):
        mexc_adapter.exchange.fetch_ticker = MagicMock(return_value={
            'symbol': 'BTC/USDT', 'last': 50000, 'bid': 49900, 'ask': 50100,
            'high': 51000, 'low': 49000, 'baseVolume': 1000, 'quoteVolume': 50000000,
            'change': 200, 'percentage': 0.4, 'timestamp': 1234567890000,
        })
        result = mexc_adapter.fetch_ticker('BTC/USDT')
        assert result['last'] == 50000.0

    def test_create_limit_order_works(self, mexc_adapter):
        mexc_adapter.exchange.create_limit_order = MagicMock(return_value={
            'id': 'mexc1', 'symbol': 'BTC/USDT', 'side': 'buy', 'type': 'limit',
            'amount': 0.5, 'price': 49000.0, 'filled': 0.0, 'remaining': 0.5,
            'cost': 0.0, 'status': 'open', 'timestamp': 0, 'fee': {},
        })
        mexc_adapter.amount_to_precision = MagicMock(return_value=0.5)
        mexc_adapter.price_to_precision = MagicMock(return_value=49000.0)
        result = mexc_adapter.create_limit_order('BTC/USDT', 'buy', 0.5, 49000.0)
        assert result['id'] == 'mexc1'


# ==============================================================================
# ALPACA TESTS
# ==============================================================================

@pytest.fixture
def mock_ccxt_alpaca():
    with patch('apps.trading.exchanges.alpaca.ccxt.alpaca') as mock_exchange_class:
        mock_exchange = MagicMock(spec=ccxt.alpaca)
        mock_exchange.id = 'alpaca'
        mock_exchange.options = {}
        mock_exchange.markets = {
            'BTC/USDT': {
                'limits': {'amount': {'min': 0.0001, 'max': 1000}},
                'precision': {'amount': 4, 'price': 2},
            },
        }
        mock_exchange.amount_to_precision = MagicMock(side_effect=lambda s, a: f"{a:.4f}")
        mock_exchange.price_to_precision = MagicMock(side_effect=lambda s, p: f"{p:.2f}")
        mock_exchange_class.return_value = mock_exchange
        yield mock_exchange_class


@pytest.fixture
def alpaca_adapter(mock_ccxt_alpaca):
    a = AlpacaAdapter(
        credentials={'api_key': 'apk', 'secret_key': 'apsk'},
        demo_mode=False
    )
    a.exchange = mock_ccxt_alpaca.return_value
    return a


class TestAlpacaAdapter:
    def test_exchange_name(self, alpaca_adapter):
        assert alpaca_adapter.exchange_name == 'alpaca'

    def test_initialize_exchange_defaults(self, mock_ccxt_alpaca):
        a = AlpacaAdapter(
            credentials={'api_key': 'ak', 'secret_key': 'sk'},
            demo_mode=False
        )
        config = mock_ccxt_alpaca.call_args[0][0]
        assert config['apiKey'] == 'ak'
        assert config['secret'] == 'sk'
        assert config['enableRateLimit'] is True

    def test_initialize_exchange_demo_mode(self, mock_ccxt_alpaca):
        a = AlpacaAdapter(
            credentials={'api_key': 'ak', 'secret_key': 'sk'},
            demo_mode=True
        )
        config = mock_ccxt_alpaca.call_args[0][0]
        assert config['sandbox'] is True

    def test_initialize_load_markets(self, mock_ccxt_alpaca):
        a = AlpacaAdapter(
            credentials={'api_key': 'ak', 'secret_key': 'sk'},
            demo_mode=False
        )
        a.exchange.load_markets.assert_called_once()

    def test_initialize_load_markets_failure(self, mock_ccxt_alpaca):
        mock_ccxt_alpaca.return_value.load_markets.side_effect = Exception('load fail')
        a = AlpacaAdapter(
            credentials={'api_key': 'ak', 'secret_key': 'sk'},
            demo_mode=False
        )
        assert a.exchange is not None

    def test_str_repr(self, alpaca_adapter):
        assert str(alpaca_adapter) == "AlpacaAdapter(demo=False)"
        assert repr(alpaca_adapter) == "AlpacaAdapter(exchange=alpaca, demo=False)"

    def test_default_symbol_format(self, alpaca_adapter):
        assert alpaca_adapter.format_symbol('BTC/USDT') == 'BTC/USDT'

    def test_is_market_open_returns_true(self, alpaca_adapter):
        alpaca_adapter.exchange.fetch_time = MagicMock(return_value=1234567890)
        assert alpaca_adapter.is_market_open() is True
        alpaca_adapter.exchange.fetch_time.assert_called_once()

    def test_is_market_open_exception_returns_false(self, alpaca_adapter):
        alpaca_adapter.exchange.fetch_time = MagicMock(side_effect=Exception('API down'))
        assert alpaca_adapter.is_market_open() is False

    def test_fetch_ticker_works(self, alpaca_adapter):
        alpaca_adapter.exchange.fetch_ticker = MagicMock(return_value={
            'symbol': 'BTC/USDT', 'last': 50000, 'bid': 49900, 'ask': 50100,
            'high': 51000, 'low': 49000, 'baseVolume': 1000, 'quoteVolume': 50000000,
            'change': 200, 'percentage': 0.4, 'timestamp': 1234567890000,
        })
        result = alpaca_adapter.fetch_ticker('BTC/USDT')
        assert result['last'] == 50000.0

    def test_get_account_info_works(self, alpaca_adapter):
        alpaca_adapter.exchange.fetch_balance = MagicMock(return_value={
            'total': {'USDT': 50000, 'BTC': 0.1},
            'free': {'USDT': 30000, 'BTC': 0.05},
            'used': {'USDT': 20000, 'BTC': 0.05},
        })
        result = alpaca_adapter.get_account_info()
        assert result['exchange'] == 'alpaca'
        assert result['demo_mode'] is False
        assert result['balance']['total']['USDT'] == 50000
