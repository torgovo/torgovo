import pytest
from unittest.mock import MagicMock, patch

import ccxt

from apps.trading.exchanges.bybit import BybitAdapter


@pytest.fixture
def mock_ccxt_bybit():
    with patch('apps.trading.exchanges.bybit.ccxt.bybit') as mock_exchange_class:
        mock_exchange = MagicMock(spec=ccxt.bybit)
        mock_exchange.id = 'bybit'
        mock_exchange.options = {'defaultType': 'swap', 'adjustForTimeDifference': True}
        mock_exchange.markets = {
            'BTC/USDT:USDT': {
                'limits': {'amount': {'min': 0.001, 'max': 1000}},
                'precision': {'amount': 4, 'price': 2},
            },
            'BTC/USDT': {
                'limits': {'amount': {'min': 0.001, 'max': 1000}},
                'precision': {'amount': 4, 'price': 2},
            },
        }
        mock_exchange.amount_to_precision = MagicMock(side_effect=lambda s, a: f"{a:.4f}")
        mock_exchange.price_to_precision = MagicMock(side_effect=lambda s, p: f"{p:.2f}")
        mock_exchange_class.return_value = mock_exchange
        yield mock_exchange_class


@pytest.fixture
def adapter(mock_ccxt_bybit):
    a = BybitAdapter(
        credentials={'api_key': 'test_key', 'secret_key': 'test_secret'},
        demo_mode=False
    )
    a.exchange = mock_ccxt_bybit.return_value
    return a


class TestBybitInitialization:
    def test_exchange_name(self, adapter):
        assert adapter.exchange_name == 'bybit'

    def test_initialize_exchange_default_swap(self, mock_ccxt_bybit):
        a = BybitAdapter(
            credentials={'api_key': 'ak', 'secret_key': 'sk'},
            demo_mode=False
        )
        config = mock_ccxt_bybit.call_args[0][0]
        assert config['apiKey'] == 'ak'
        assert config['secret'] == 'sk'
        assert config['options']['defaultType'] == 'swap'
        assert config['enableRateLimit'] is True

    def test_initialize_exchange_demo_mode(self, mock_ccxt_bybit):
        a = BybitAdapter(
            credentials={'api_key': 'ak', 'secret_key': 'sk'},
            demo_mode=True
        )
        config = mock_ccxt_bybit.call_args[0][0]
        assert config['sandbox'] is True

    def test_initialize_load_markets(self, mock_ccxt_bybit):
        a = BybitAdapter(
            credentials={'api_key': 'ak', 'secret_key': 'sk'},
            demo_mode=False
        )
        a.exchange.load_markets.assert_called_once()

    def test_initialize_load_markets_failure(self, mock_ccxt_bybit):
        mock_ccxt_bybit.return_value.load_markets.side_effect = Exception('load fail')
        a = BybitAdapter(
            credentials={'api_key': 'ak', 'secret_key': 'sk'},
            demo_mode=False
        )
        assert a.exchange is not None

    def test_str_repr(self, adapter):
        assert str(adapter) == "BybitAdapter(demo=False)"
        assert repr(adapter) == "BybitAdapter(exchange=bybit, demo=False)"


class TestBybitSymbolFormat:
    def test_swap_format_adds_settlement(self, adapter):
        assert adapter.format_symbol('BTC/USDT') == 'BTC/USDT:USDT'

    def test_swap_format_already_has_colon(self, adapter):
        assert adapter.format_symbol('BTC/USDT:USDT') == 'BTC/USDT:USDT'

    def test_spot_format_unchanged(self, adapter):
        adapter.exchange.options['defaultType'] = 'spot'
        assert adapter.format_symbol('BTC/USDT') == 'BTC/USDT'

    def test_format_symbol_single_part(self, adapter):
        assert adapter.format_symbol('BTC') == 'BTC'


class TestBybitSetMarketType:
    def test_set_market_type_swap(self, adapter):
        adapter.set_market_type('spot')
        assert adapter.exchange.options['defaultType'] == 'spot'

    def test_set_market_type_spot(self, adapter):
        adapter.set_market_type('swap')
        assert adapter.exchange.options['defaultType'] == 'swap'


class TestBybitSetLeverage:
    def test_set_leverage_no_side(self, adapter):
        adapter.exchange.set_leverage = MagicMock(return_value={'leverage': 5})
        adapter.format_symbol = MagicMock(return_value='BTC/USDT:USDT')
        result = adapter.set_leverage('BTC/USDT', 5)
        assert result['leverage'] == 5
        adapter.exchange.set_leverage.assert_called_once_with(5, 'BTC/USDT:USDT', {})

    def test_set_leverage_with_side_long(self, adapter):
        adapter.exchange.set_leverage = MagicMock(return_value={'leverage': 10})
        adapter.format_symbol = MagicMock(return_value='BTC/USDT:USDT')
        result = adapter.set_leverage('BTC/USDT', 10, side='long')
        adapter.exchange.set_leverage.assert_called_once_with(10, 'BTC/USDT:USDT', {'side': 'Buy'})

    def test_set_leverage_with_side_short(self, adapter):
        adapter.exchange.set_leverage = MagicMock(return_value={'leverage': 15})
        adapter.format_symbol = MagicMock(return_value='BTC/USDT:USDT')
        result = adapter.set_leverage('BTC/USDT', 15, side='short')
        adapter.exchange.set_leverage.assert_called_once_with(15, 'BTC/USDT:USDT', {'side': 'Sell'})


class TestBybitSetPositionMode:
    def test_set_position_mode_one_way(self, adapter):
        adapter.exchange.set_position_mode = MagicMock(return_value={})
        result = adapter.set_position_mode(hedged=False)
        adapter.exchange.set_position_mode.assert_called_once_with(False)

    def test_set_position_mode_hedged(self, adapter):
        adapter.exchange.set_position_mode = MagicMock(return_value={})
        result = adapter.set_position_mode(hedged=True)
        adapter.exchange.set_position_mode.assert_called_once_with(True)


class TestBybitCreateMarketOrder:
    def test_create_market_order_buy(self, adapter):
        adapter.exchange.create_market_order = MagicMock(return_value={
            'id': 'mo1', 'symbol': 'BTC/USDT:USDT', 'side': 'buy', 'type': 'market',
            'amount': 1.0, 'filled': 1.0, 'remaining': 0.0, 'cost': 50000.0,
            'status': 'closed', 'timestamp': 0, 'fee': {},
        })
        adapter.amount_to_precision = MagicMock(return_value=1.0)
        adapter.format_symbol = MagicMock(return_value='BTC/USDT:USDT')

        result = adapter.create_market_order('BTC/USDT', 'buy', 1.0)
        assert result['id'] == 'mo1'
        assert result['side'] == 'buy'
        adapter.exchange.create_market_order.assert_called_once_with(
            'BTC/USDT:USDT', 'buy', 1.0, params={}
        )

    def test_create_market_order_with_params(self, adapter):
        adapter.exchange.create_market_order = MagicMock(return_value={
            'id': 'mo2', 'symbol': 'BTC/USDT:USDT', 'side': 'sell', 'type': 'market',
            'amount': 0.5, 'filled': 0.5, 'remaining': 0.0, 'cost': 25000.0,
            'status': 'closed', 'timestamp': 0, 'fee': {},
        })
        adapter.amount_to_precision = MagicMock(return_value=0.5)
        adapter.format_symbol = MagicMock(return_value='BTC/USDT:USDT')

        adapter.create_market_order('BTC/USDT', 'sell', 0.5, params={'reduceOnly': True})
        adapter.exchange.create_market_order.assert_called_once_with(
            'BTC/USDT:USDT', 'sell', 0.5, params={'reduceOnly': True}
        )


class TestBybitCreateLimitOrder:
    def test_create_limit_order_buy(self, adapter):
        adapter.exchange.create_limit_order = MagicMock(return_value={
            'id': 'lo1', 'symbol': 'BTC/USDT:USDT', 'side': 'buy', 'type': 'limit',
            'amount': 1.0, 'price': 49000.0, 'filled': 0.0, 'remaining': 1.0,
            'cost': 0.0, 'status': 'open', 'timestamp': 0, 'fee': {},
        })
        adapter.amount_to_precision = MagicMock(return_value=1.0)
        adapter.price_to_precision = MagicMock(return_value=49000.0)
        adapter.format_symbol = MagicMock(return_value='BTC/USDT:USDT')

        result = adapter.create_limit_order('BTC/USDT', 'buy', 1.0, 49000.0)
        assert result['id'] == 'lo1'
        assert result['type'] == 'limit'
        assert result['price'] == 49000.0
        adapter.exchange.create_limit_order.assert_called_once_with(
            'BTC/USDT:USDT', 'buy', 1.0, 49000.0, params={}
        )


class TestBybitStopLossOrder:
    def test_create_stop_loss_order(self, adapter):
        adapter.exchange.create_order = MagicMock(return_value={
            'id': 'sl1', 'symbol': 'BTC/USDT:USDT', 'side': 'sell', 'type': 'market',
            'amount': 1.0, 'filled': 0.0, 'remaining': 1.0, 'cost': 0.0,
            'status': 'open', 'timestamp': 0, 'fee': {},
        })
        adapter.amount_to_precision = MagicMock(return_value=1.0)
        adapter.price_to_precision = MagicMock(return_value=48000.0)
        adapter.format_symbol = MagicMock(return_value='BTC/USDT:USDT')

        result = adapter.create_stop_loss_order('BTC/USDT', 'sell', 1.0, 48000.0)
        assert result['id'] == 'sl1'
        args = adapter.exchange.create_order.call_args[0]
        assert args[1] == 'BTC/USDT:USDT'
        assert args[2] == 'market'
        assert args[6]['stopLoss']['triggerPrice'] == 48000.0

    def test_create_stop_loss_with_extra_params(self, adapter):
        adapter.exchange.create_order = MagicMock(return_value={
            'id': 'sl2', 'symbol': 'BTC/USDT:USDT', 'side': 'sell', 'type': 'market',
            'amount': 1.0, 'filled': 0.0, 'remaining': 1.0, 'cost': 0.0,
            'status': 'open', 'timestamp': 0, 'fee': {},
        })
        adapter.amount_to_precision = MagicMock(return_value=1.0)
        adapter.price_to_precision = MagicMock(return_value=48000.0)
        adapter.format_symbol = MagicMock(return_value='BTC/USDT:USDT')

        adapter.create_stop_loss_order('BTC/USDT', 'sell', 1.0, 48000.0, params={'reduceOnly': True})
        args = adapter.exchange.create_order.call_args[0]
        assert args[6]['reduceOnly'] is True
        assert args[6]['stopLoss']['triggerPrice'] == 48000.0


class TestBybitTakeProfitOrder:
    def test_create_take_profit_order(self, adapter):
        adapter.exchange.create_order = MagicMock(return_value={
            'id': 'tp1', 'symbol': 'BTC/USDT:USDT', 'side': 'buy', 'type': 'market',
            'amount': 0.5, 'filled': 0.0, 'remaining': 0.5, 'cost': 0.0,
            'status': 'open', 'timestamp': 0, 'fee': {},
        })
        adapter.amount_to_precision = MagicMock(return_value=0.5)
        adapter.price_to_precision = MagicMock(return_value=52000.0)
        adapter.format_symbol = MagicMock(return_value='BTC/USDT:USDT')

        result = adapter.create_take_profit_order('BTC/USDT', 'buy', 0.5, 52000.0)
        assert result['id'] == 'tp1'
        args = adapter.exchange.create_order.call_args[0]
        assert args[2] == 'market'
        assert args[6]['takeProfit']['triggerPrice'] == 52000.0


class TestBybitGetWalletBalance:
    def test_get_wallet_balance_default_unified(self, adapter):
        adapter.exchange.fetch_balance = MagicMock(return_value={
            'total': {'USDT': 10000},
            'free': {'USDT': 8000},
            'used': {'USDT': 2000},
        })
        result = adapter.get_wallet_balance()
        assert result['total'] == {'USDT': 10000}
        adapter.exchange.fetch_balance.assert_called_once_with({'accountType': 'UNIFIED'})

    def test_get_wallet_balance_contract(self, adapter):
        adapter.exchange.fetch_balance = MagicMock(return_value={
            'total': {'USDT': 5000},
            'free': {'USDT': 3000},
            'used': {'USDT': 2000},
        })
        result = adapter.get_wallet_balance(account_type='CONTRACT')
        adapter.exchange.fetch_balance.assert_called_once_with({'accountType': 'CONTRACT'})


class TestBybitGetFundingRate:
    def test_get_funding_rate_success(self, adapter):
        adapter.exchange.fetch_funding_rate = MagicMock(return_value={
            'fundingRate': 0.0001,
            'fundingTimestamp': 1234567890000,
        })
        adapter.format_symbol = MagicMock(return_value='BTC/USDT:USDT')
        result = adapter.get_funding_rate('BTC/USDT')
        assert result['symbol'] == 'BTC/USDT'
        assert result['funding_rate'] == 0.0001
        assert result['funding_timestamp'] == 1234567890000

    def test_get_funding_rate_failure_returns_defaults(self, adapter):
        adapter.exchange.fetch_funding_rate = MagicMock(side_effect=Exception('API error'))
        adapter.format_symbol = MagicMock(return_value='BTC/USDT:USDT')
        result = adapter.get_funding_rate('BTC/USDT')
        assert result['symbol'] == 'BTC/USDT'
        assert result['funding_rate'] == 0
        assert result['funding_timestamp'] is None


class TestBybitGetPositionInfo:
    def test_get_position_info_returns_first_position(self, adapter):
        adapter.fetch_positions = MagicMock(return_value=[{
            'symbol': 'BTC/USDT:USDT', 'side': 'long', 'contracts': 1.0,
            'entry_price': 50000, 'unrealized_pnl': 500,
        }])
        adapter.format_symbol = MagicMock(return_value='BTC/USDT:USDT')
        result = adapter.get_position_info('BTC/USDT')
        assert result['symbol'] == 'BTC/USDT:USDT'
        assert result['contracts'] == 1.0

    def test_get_position_info_no_position_returns_empty(self, adapter):
        adapter.fetch_positions = MagicMock(return_value=[])
        adapter.format_symbol = MagicMock(return_value='BTC/USDT:USDT')
        result = adapter.get_position_info('BTC/USDT')
        assert result['symbol'] == 'BTC/USDT:USDT'
        assert result['side'] is None
        assert result['contracts'] == 0


class TestBybitErrorHandling:
    def test_network_error_retry_then_success(self, adapter):
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

    def test_exchange_error_create_order(self, adapter):
        adapter.exchange.create_market_order = MagicMock(side_effect=ccxt.ExchangeError('insufficient margin'))
        adapter.amount_to_precision = MagicMock(return_value=1.0)
        with pytest.raises(ccxt.ExchangeError):
            adapter.create_market_order('BTC/USDT', 'buy', 1.0)
