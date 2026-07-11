import pytest
from unittest.mock import patch, MagicMock

from apps.trading.exchanges import get_adapter
from apps.trading.exchanges.binance import BinanceAdapter
from apps.trading.exchanges.bybit import BybitAdapter
from apps.trading.exchanges.okx import OKXAdapter
from apps.trading.exchanges.mexc import MEXCAdapter
from apps.trading.exchanges.alpaca import AlpacaAdapter


class TestGetAdapter:
    @patch('apps.trading.exchanges.binance.BinanceAdapter._initialize_exchange')
    def test_binance_adapter(self, mock_init):
        mock_init.return_value = MagicMock()
        adapter = get_adapter('binance', {'api_key': 'ak', 'secret_key': 'sk'})
        assert isinstance(adapter, BinanceAdapter)
        assert adapter.credentials == {'api_key': 'ak', 'secret_key': 'sk'}
        assert adapter.demo_mode is False

    @patch('apps.trading.exchanges.bybit.BybitAdapter._initialize_exchange')
    def test_bybit_adapter(self, mock_init):
        mock_init.return_value = MagicMock()
        adapter = get_adapter('bybit', {'api_key': 'ak', 'secret_key': 'sk'})
        assert isinstance(adapter, BybitAdapter)

    @patch('apps.trading.exchanges.okx.OKXAdapter._initialize_exchange')
    def test_okx_adapter(self, mock_init):
        mock_init.return_value = MagicMock()
        adapter = get_adapter('okx', {'api_key': 'ak', 'secret_key': 'sk', 'passphrase': 'pp'})
        assert isinstance(adapter, OKXAdapter)

    @patch('apps.trading.exchanges.mexc.MEXCAdapter._initialize_exchange')
    def test_mexc_adapter(self, mock_init):
        mock_init.return_value = MagicMock()
        adapter = get_adapter('mexc', {'api_key': 'ak', 'secret_key': 'sk'})
        assert isinstance(adapter, MEXCAdapter)

    @patch('apps.trading.exchanges.alpaca.AlpacaAdapter._initialize_exchange')
    def test_alpaca_adapter(self, mock_init):
        mock_init.return_value = MagicMock()
        adapter = get_adapter('alpaca', {'api_key': 'ak', 'secret_key': 'sk'})
        assert isinstance(adapter, AlpacaAdapter)

    def test_case_insensitive_exchange_name(self):
        adapters = {
            'Binance': BinanceAdapter,
            'BINANCE': BinanceAdapter,
            'Bybit': BybitAdapter,
            'BYBIT': BybitAdapter,
            'OKX': OKXAdapter,
            'okx': OKXAdapter,
            'MEXC': MEXCAdapter,
            'mexc': MEXCAdapter,
            'Alpaca': AlpacaAdapter,
            'ALPACA': AlpacaAdapter,
        }
        for name, expected_cls in adapters.items():
            with patch.object(expected_cls, '_initialize_exchange', return_value=MagicMock()):
                adapter = get_adapter(name, {'api_key': 'ak', 'secret_key': 'sk'})
                assert isinstance(adapter, expected_cls), f"Failed for {name}"

    def test_unknown_exchange_raises_value_error(self):
        with pytest.raises(ValueError, match='Unsupported exchange'):
            get_adapter('unknown_exchange', {'api_key': 'ak', 'secret_key': 'sk'})

    def test_empty_exchange_name_raises_value_error(self):
        with pytest.raises(ValueError, match='Unsupported exchange'):
            get_adapter('', {'api_key': 'ak', 'secret_key': 'sk'})

    def test_none_exchange_name_raises_value_error(self):
        with pytest.raises(ValueError, match='Unsupported exchange'):
            get_adapter(None, {'api_key': 'ak', 'secret_key': 'sk'})


class TestGetAdapterWithCredentials:
    @patch('apps.trading.exchanges.binance.BinanceAdapter._initialize_exchange')
    def test_passes_credentials_correctly(self, mock_init):
        mock_init.return_value = MagicMock()
        credentials = {'api_key': 'my_key', 'secret_key': 'my_secret'}
        adapter = get_adapter('binance', credentials, demo_mode=True)
        assert adapter.credentials == credentials
        assert adapter.demo_mode is True

    @patch('apps.trading.exchanges.binance.BinanceAdapter._initialize_exchange')
    def test_demo_mode_defaults_to_false(self, mock_init):
        mock_init.return_value = MagicMock()
        adapter = get_adapter('binance', {'api_key': 'ak', 'secret_key': 'sk'})
        assert adapter.demo_mode is False

    @patch('apps.trading.exchanges.binance.BinanceAdapter._initialize_exchange')
    def test_demo_mode_true(self, mock_init):
        mock_init.return_value = MagicMock()
        adapter = get_adapter('binance', {'api_key': 'ak', 'secret_key': 'sk'}, demo_mode=True)
        assert adapter.demo_mode is True

    @patch('apps.trading.exchanges.okx.OKXAdapter._initialize_exchange')
    def test_okx_passphrase_included(self, mock_init):
        mock_init.return_value = MagicMock()
        credentials = {'api_key': 'ak', 'secret_key': 'sk', 'passphrase': 'my_pass'}
        adapter = get_adapter('okx', credentials)
        assert adapter.credentials['passphrase'] == 'my_pass'


class TestGetAdapterEdgeCases:
    @patch('apps.trading.exchanges.bybit.BybitAdapter._initialize_exchange')
    def test_bybit_with_extra_credentials_fields(self, mock_init):
        mock_init.return_value = MagicMock()
        credentials = {
            'api_key': 'ak',
            'secret_key': 'sk',
            'passphrase': '',
            'extra_field': 'ignored',
        }
        adapter = get_adapter('bybit', credentials)
        assert isinstance(adapter, BybitAdapter)
        assert 'extra_field' in adapter.credentials

    @patch('apps.trading.exchanges.binance.BinanceAdapter._initialize_exchange')
    def test_binance_initialization_with_empty_credentials(self, mock_init):
        mock_init.return_value = MagicMock()
        adapter = get_adapter('binance', {'api_key': '', 'secret_key': ''})
        assert isinstance(adapter, BinanceAdapter)
