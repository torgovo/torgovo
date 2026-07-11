import pytest
import time
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime

from apps.trading.engines.execution import (
    BotExecutor, run_bot, stop_bot,
    _is_bot_running, _mark_bot_starting, _mark_bot_stopped, _running_bots,
)


@pytest.fixture
def mock_strategy():
    strategy = MagicMock()
    strategy.name = 'TestStrategy'
    strategy.execute.return_value = None
    strategy.get_status.return_value = {'name': 'TestStrategy', 'is_running': False}
    return strategy


@pytest.fixture
def mock_adapter():
    adapter = MagicMock()
    adapter.exchange_name = 'bybit'
    adapter.fetch_ticker.return_value = {
        'symbol': 'BTC/USDT', 'last': 50000.0, 'bid': 49900.0, 'ask': 50100.0,
        'high': 51000.0, 'low': 49000.0, 'volume': 1000.0, 'timestamp': 1234567890000,
    }
    adapter.fetch_ohlcv.return_value = [
        {'timestamp': 1234567800000, 'open': 40000.0, 'high': 41000.0,
         'low': 39000.0, 'close': 40500.0, 'volume': 1000.0},
    ]
    adapter.fetch_order_book.return_value = {
        'symbol': 'BTC/USDT', 'bids': [[50000, 1.0]], 'asks': [[50100, 1.5]],
        'timestamp': 1234567890000,
    }
    adapter.get_account_info.return_value = {
        'balance': {'total': {'USDT': 10000}, 'free': {'USDT': 8000}, 'used': {'USDT': 2000}},
        'exchange': 'bybit', 'demo_mode': False,
    }
    adapter.fetch_positions.return_value = []
    adapter.execute_order.return_value = {
        'id': 'exec1', 'symbol': 'BTC/USDT', 'side': 'buy', 'type': 'market',
        'amount': 1.0, 'filled': 1.0, 'remaining': 0.0, 'cost': 50000.0,
        'status': 'closed', 'timestamp': 1234567890000, 'fee': {},
    }
    return adapter


class TestBotExecutorInit:
    def test_initializes_with_strategy_and_adapter(self, mock_strategy, mock_adapter):
        executor = BotExecutor(strategy=mock_strategy, adapter=mock_adapter, symbol='BTC/USDT')
        assert executor.strategy == mock_strategy
        assert executor.adapter == mock_adapter
        assert executor.symbol == 'BTC/USDT'
        assert executor.is_running is False
        assert executor.execution_count == 0
        assert executor.last_execution is None
        assert executor.errors == []

    def test_requires_symbol(self, mock_strategy, mock_adapter):
        with pytest.raises(ValueError, match='Symbol must be provided'):
            BotExecutor(strategy=mock_strategy, adapter=mock_adapter)

    def test_accepts_bot_config_dict(self, mock_strategy, mock_adapter):
        config = {'bot_id': '123', 'user_id': '1'}
        executor = BotExecutor(strategy=mock_strategy, adapter=mock_adapter,
                               bot_config=config, symbol='BTC/USDT')
        assert executor.bot_config == config
        assert executor.symbol == 'BTC/USDT'


class TestBotExecutorFromConfig:
    def test_from_config_creates_strategy_and_adapter(self):
        config = {
            'strategy': 'grid',
            'symbol': 'BTC/USDT',
            'exchange_name': 'bybit',
            'api_key': 'test_key',
            'secret_key': 'test_secret',
            'passphrase': '',
            'is_testnet': True,
            'parameters': {'amount_per_grid': 10, 'grid_levels': 5},
        }

        with patch('apps.trading.strategies.get_strategy') as mock_get_strat:
            with patch('apps.trading.exchanges.get_adapter') as mock_get_adapter:
                mock_strategy_class = MagicMock()
                mock_strategy_instance = MagicMock()
                mock_strategy_class.return_value = mock_strategy_instance
                mock_strategy_instance.name = 'Grid Trading'
                mock_get_strat.return_value = mock_strategy_class

                mock_adapter_instance = MagicMock()
                mock_adapter_instance.exchange_name = 'bybit'
                mock_get_adapter.return_value = mock_adapter_instance

                executor = BotExecutor.from_config(config)

                mock_get_strat.assert_called_once_with('grid')
                mock_strategy_class.assert_called_once_with(parameters={
                    'symbol': 'BTC/USDT',
                    'amount_per_grid': 10,
                    'grid_levels': 5,
                })

                mock_get_adapter.assert_called_once_with(
                    exchange_name='bybit',
                    credentials={'api_key': 'test_key', 'secret_key': 'test_secret', 'passphrase': ''},
                    demo_mode=True
                )

                assert executor.strategy == mock_strategy_instance
                assert executor.adapter == mock_adapter_instance
                assert executor.symbol == 'BTC/USDT'

    def test_from_config_default_strategy(self):
        config = {
            'symbol': 'BTC/USDT',
            'exchange_name': 'bybit',
            'api_key': 'k', 'secret_key': 's',
            'parameters': {},
        }

        with patch('apps.trading.strategies.get_strategy') as mock_get_strat:
            with patch('apps.trading.exchanges.get_adapter'):
                mock_strategy_class = MagicMock()
                mock_strategy_class.return_value = MagicMock()
                mock_get_strat.return_value = mock_strategy_class
                BotExecutor.from_config(config)
                mock_get_strat.assert_called_once_with('quantum_ai')

    def test_from_config_default_exchange(self):
        config = {
            'symbol': 'BTC/USDT',
            'api_key': 'k', 'secret_key': 's',
            'parameters': {},
        }

        with patch('apps.trading.strategies.get_strategy') as mock_get_strat:
            with patch('apps.trading.exchanges.get_adapter') as mock_get_adapter:
                mock_strategy_class = MagicMock()
                mock_strategy_class.return_value = MagicMock()
                mock_get_strat.return_value = mock_strategy_class
                mock_adapter_instance = MagicMock()
                mock_get_adapter.return_value = mock_adapter_instance

                BotExecutor.from_config(config)

                mock_get_adapter.assert_called_once_with(
                    exchange_name='bybit',
                    credentials={'api_key': 'k', 'secret_key': 's', 'passphrase': ''},
                    demo_mode=False
                )


class TestBotExecutorRunOnce:
    def test_run_once_with_no_signal(self, mock_strategy, mock_adapter):
        mock_strategy.execute.return_value = None
        executor = BotExecutor(strategy=mock_strategy, adapter=mock_adapter, symbol='BTC/USDT')
        result = executor.run_once()

        assert result['success'] is True
        assert result['signal'] is None
        assert result['order'] is None
        assert result['error'] is None
        assert executor.execution_count == 1

    def test_run_once_with_signal(self, mock_strategy, mock_adapter):
        from apps.trading.strategies.base import Signal
        signal = Signal(action='buy', symbol='BTC/USDT', amount=1.0,
                        reason='Test signal')
        mock_strategy.execute.return_value = signal
        executor = BotExecutor(strategy=mock_strategy, adapter=mock_adapter, symbol='BTC/USDT')
        result = executor.run_once()

        assert result['success'] is True
        assert result['signal']['action'] == 'buy'
        assert result['order']['id'] == 'exec1'
        mock_adapter.execute_order.assert_called_once_with(signal.to_dict())
        assert executor.execution_count == 1

    def test_run_once_with_error(self, mock_strategy, mock_adapter):
        mock_strategy.execute.side_effect = ValueError('Strategy error')
        executor = BotExecutor(strategy=mock_strategy, adapter=mock_adapter, symbol='BTC/USDT')
        result = executor.run_once()

        assert result['success'] is False
        assert 'Strategy error' in result['error']
        assert len(executor.errors) == 1

    def test_run_once_with_signal_and_bot_config(self, mock_strategy, mock_adapter):
        from apps.trading.strategies.base import Signal
        signal = Signal(action='buy', symbol='BTC/USDT', amount=1.0,
                        reason='DB test')
        mock_strategy.execute.return_value = signal

        with patch.object(BotExecutor, '_log_trade') as mock_log:
            executor = BotExecutor(strategy=mock_strategy, adapter=mock_adapter,
                                   bot_config={'user_id': '1'}, symbol='BTC/USDT')
            result = executor.run_once()

        assert result['success'] is True
        mock_log.assert_called_once()

    def test_run_once_with_error_and_bot_config(self, mock_strategy, mock_adapter):
        mock_strategy.execute.side_effect = ValueError('fail')
        with patch.object(BotExecutor, '_handle_error') as mock_handle:
            executor = BotExecutor(strategy=mock_strategy, adapter=mock_adapter,
                                   bot_config={'user_id': '1'}, symbol='BTC/USDT')
            result = executor.run_once()

        mock_handle.assert_called_once()


class TestBotExecutorRunLoop:
    def test_run_loop_executes_iterations(self, mock_strategy, mock_adapter):
        mock_strategy.execute.return_value = None
        executor = BotExecutor(strategy=mock_strategy, adapter=mock_adapter, symbol='BTC/USDT')

        with patch('time.sleep') as mock_sleep:
            executor.run_loop(interval_seconds=0.01, max_iterations=3)

        assert executor.is_running is False
        assert executor.execution_count == 3

    def test_run_loop_stops_when_is_running_false(self, mock_strategy, mock_adapter):
        mock_strategy.execute.return_value = None
        executor = BotExecutor(strategy=mock_strategy, adapter=mock_adapter, symbol='BTC/USDT')

        def stop_after_two(*args, **kwargs):
            executor.stop()
            return None
        mock_strategy.execute.side_effect = stop_after_two

        with patch('time.sleep'):
            executor.run_loop(interval_seconds=0.01, max_iterations=10)

        assert executor.execution_count == 1


class TestBotExecutorStop:
    def test_stop_sets_is_running_false(self, mock_strategy, mock_adapter):
        executor = BotExecutor(strategy=mock_strategy, adapter=mock_adapter, symbol='BTC/USDT')
        executor.is_running = True
        executor.stop()
        assert executor.is_running is False


class TestBotExecutorFetchMarketData:
    def test_fetch_market_data(self, mock_strategy, mock_adapter):
        executor = BotExecutor(strategy=mock_strategy, adapter=mock_adapter, symbol='BTC/USDT')
        data = executor._fetch_market_data()

        assert 'ticker' in data
        assert 'ohlcv' in data
        assert 'orderbook' in data
        assert data['ticker']['last'] == 50000.0
        mock_adapter.fetch_ticker.assert_called_once_with('BTC/USDT')
        mock_adapter.fetch_ohlcv.assert_called_once_with('BTC/USDT', '1h', limit=100)
        mock_adapter.fetch_order_book.assert_called_once_with('BTC/USDT', limit=10)


class TestBotExecutorGetCurrentPosition:
    def test_get_current_position_returns_first(self, mock_strategy, mock_adapter):
        mock_adapter.fetch_positions.return_value = [{
            'symbol': 'BTC/USDT', 'side': 'long', 'contracts': 1.0,
            'entry_price': 50000, 'unrealized_pnl': 500,
        }]
        executor = BotExecutor(strategy=mock_strategy, adapter=mock_adapter, symbol='BTC/USDT')
        position = executor._get_current_position()
        assert position is not None
        assert position['symbol'] == 'BTC/USDT'

    def test_get_current_position_none(self, mock_strategy, mock_adapter):
        mock_adapter.fetch_positions.return_value = []
        executor = BotExecutor(strategy=mock_strategy, adapter=mock_adapter, symbol='BTC/USDT')
        position = executor._get_current_position()
        assert position is None

    def test_get_current_position_exception(self, mock_strategy, mock_adapter):
        mock_adapter.fetch_positions.side_effect = Exception('API error')
        executor = BotExecutor(strategy=mock_strategy, adapter=mock_adapter, symbol='BTC/USDT')
        position = executor._get_current_position()
        assert position is None


class TestBotExecutorHandleError:
    def test_handle_error_below_threshold(self, mock_strategy, mock_adapter):
        executor = BotExecutor(strategy=mock_strategy, adapter=mock_adapter,
                               bot_config={'bot_id': '1', 'bot_type': 'grid'},
                               symbol='BTC/USDT')
        with patch.object(BotExecutor, '_update_bot_status') as mock_update:
            executor._handle_error(ValueError('test'))
            mock_update.assert_not_called()

    def test_handle_error_above_threshold(self, mock_strategy, mock_adapter):
        executor = BotExecutor(strategy=mock_strategy, adapter=mock_adapter,
                               bot_config={'bot_id': '1', 'bot_type': 'grid'},
                               symbol='BTC/USDT')
        executor.errors = [{'error': 'e1'}, {'error': 'e2'}, {'error': 'e3'},
                           {'error': 'e4'}, {'error': 'e5'}]

        with patch.object(BotExecutor, '_update_bot_status') as mock_update:
            executor._handle_error(ValueError('test'))
            mock_update.assert_called_once_with('1', 'grid', 'error')

    def test_handle_error_no_bot_config(self, mock_strategy, mock_adapter):
        executor = BotExecutor(strategy=mock_strategy, adapter=mock_adapter, symbol='BTC/USDT')
        executor.errors = [{'error': 'e1'}] * 5
        executor._handle_error(ValueError('test'))

    def test_handle_error_update_fails_gracefully(self, mock_strategy, mock_adapter):
        executor = BotExecutor(strategy=mock_strategy, adapter=mock_adapter,
                               bot_config={'bot_id': '1', 'bot_type': 'grid'},
                               symbol='BTC/USDT')
        executor.errors = [{'error': 'e1'}] * 5
        with patch.object(BotExecutor, '_update_bot_status', side_effect=Exception('DB error')):
            executor._handle_error(ValueError('test'))


class TestBotExecutorLogTrade:
    def test_log_trade_skips_without_user_id(self, mock_strategy, mock_adapter):
        executor = BotExecutor(strategy=mock_strategy, adapter=mock_adapter,
                               bot_config={}, symbol='BTC/USDT')
        from apps.trading.strategies.base import Signal
        signal = Signal(action='buy', symbol='BTC/USDT', amount=1.0)
        executor._log_trade(signal, {'id': 'o1'})

    def test_log_trade_db_failure_graceful(self, mock_strategy, mock_adapter):
        executor = BotExecutor(strategy=mock_strategy, adapter=mock_adapter,
                               bot_config={'user_id': '1'}, symbol='BTC/USDT')
        from apps.trading.strategies.base import Signal
        signal = Signal(action='buy', symbol='BTC/USDT', amount=1.0)

        with patch('django.contrib.auth.get_user_model') as mock_get_user:
            mock_get_user.side_effect = Exception('DB fail')
            executor._log_trade(signal, {'id': 'o1'})


class TestBotExecutorUpdateBotStatus:
    def test_update_bot_status_grid(self):
        with patch('apps.bots.models.GridBot.objects.filter') as mock_filter:
            BotExecutor._update_bot_status('1', 'grid', 'error')
            mock_filter.assert_called_once_with(id='1')
            mock_filter.return_value.update.assert_called_once_with(is_running=False)

    def test_update_bot_status_martingale(self):
        with patch('apps.bots.models.MartingaleBot.objects.filter') as mock_filter:
            BotExecutor._update_bot_status('1', 'martingale', 'error')
            mock_filter.assert_called_once_with(id='1')

    def test_update_bot_status_signal(self):
        with patch('apps.bots.models.SignalBot.objects.filter') as mock_filter:
            BotExecutor._update_bot_status('1', 'signal', 'error')
            mock_filter.assert_called_once_with(id='1')

    def test_update_bot_status_db_failure(self):
        with patch('apps.bots.models.GridBot.objects.filter',
                   side_effect=Exception('DB error')):
            BotExecutor._update_bot_status('1', 'grid', 'error')


class TestBotExecutorGetStatus:
    def test_get_status(self, mock_strategy, mock_adapter):
        executor = BotExecutor(strategy=mock_strategy, adapter=mock_adapter, symbol='BTC/USDT')
        executor.is_running = True
        executor.execution_count = 5

        status = executor.get_status()

        assert status['is_running'] is True
        assert status['symbol'] == 'BTC/USDT'
        assert status['exchange'] == 'bybit'
        assert status['strategy'] == 'TestStrategy'
        assert status['execution_count'] == 5
        assert status['error_count'] == 0

    def test_get_status_last_execution(self, mock_strategy, mock_adapter):
        executor = BotExecutor(strategy=mock_strategy, adapter=mock_adapter, symbol='BTC/USDT')
        executor.last_execution = datetime(2025, 1, 1, 12, 0, 0)
        status = executor.get_status()
        assert status['last_execution'] is not None

    def test_get_status_last_execution_none(self, mock_strategy, mock_adapter):
        executor = BotExecutor(strategy=mock_strategy, adapter=mock_adapter, symbol='BTC/USDT')
        status = executor.get_status()
        assert status['last_execution'] is None


class TestRunBotFunction:
    def test_run_bot_quantum_ai(self):
        mock_bot = MagicMock()
        mock_bot.id = 'q1'
        mock_bot.bot_name = 'QAIBot'
        mock_bot.trading_pair = 'BTC/USDT'
        mock_bot.exchange_name = 'bybit'
        mock_bot.strategy_parameters = {'param1': 'val1'}
        mock_bot.is_running = False

        mock_fund = MagicMock()
        mock_fund.master_api_key = 'enc_key'
        mock_fund.master_secret_key = 'enc_secret'
        mock_fund.master_passphrase = 'enc_pass'
        mock_bot.fund = mock_fund

        mock_engine = MagicMock()
        mock_engine.reason = 'test signal'
        mock_engine.current_side = 'Buy'

        with patch('apps.bots.models.QuantumAIBot.objects.select_related') as mock_qs:
            mock_qs.return_value.get.return_value = mock_bot
            with patch('core.utils.decrypt_api_key') as mock_decrypt:
                mock_decrypt.side_effect = lambda x: f"decrypted_{x}"
                with patch('apps.trading.engines.bot_engine.BotEngine') as MockEngine:
                    MockEngine.return_value = mock_engine

                    result = run_bot('q1', 'quantum_ai')

                assert result['success'] is True
                assert result['signal'] == 'test signal'
                assert result['side'] == 'Buy'
                MockEngine.assert_called_once()
                mock_engine.startBot.assert_called_once()

    def test_run_bot_grid(self):
        mock_bot = MagicMock()
        mock_bot.id = 'g1'
        mock_bot.bot_name = 'GridBot'
        mock_bot.trading_pair = 'BTC/USDT'
        mock_bot.exchange_name = 'bybit'
        mock_bot.favor_levels = 3
        mock_bot.against_levels = 3
        mock_bot.favor_level_qty = 10.0
        mock_bot.against_level_qty = 10.0
        mock_bot.favor_level_difference = 0.5
        mock_bot.against_level_difference = 0.5
        mock_bot.take_profit_percent = 3.0
        mock_bot.stop_loss_percent = -2.0
        mock_bot.amount_type = 'quote'
        mock_bot.base_amount = 100.0
        mock_bot.is_running = False
        mock_bot.user = MagicMock()
        mock_bot.user.id = 'u1'

        mock_creds = MagicMock()
        mock_creds.is_testnet = True
        mock_creds.get_decrypted_credentials.return_value = {
            'api_key': 'dec_key',
            'secret_key': 'dec_secret',
            'passphrase': 'dec_pass',
        }

        mock_engine = MagicMock()
        mock_engine.reason = 'grid signal'
        mock_engine.current_side = 'Sell'

        with patch('apps.bots.models.GridBot.objects.select_related') as mock_qs:
            mock_qs.return_value.get.return_value = mock_bot
            with patch('apps.exchanges.models.ExchangeCredentials.objects.get') as mock_creds_qs:
                mock_creds_qs.return_value = mock_creds
                with patch('apps.trading.engines.bot_engine.BotEngine') as MockEngine:
                    MockEngine.return_value = mock_engine

                    result = run_bot('g1', 'grid')

                assert result['success'] is True
                assert result['signal'] == 'grid signal'
                MockEngine.assert_called_once()
                mock_engine.startBot.assert_called_once()

    def test_run_bot_unknown_type(self):
        result = run_bot('b1', 'unknown_type')
        assert result['success'] is False
        assert 'Unknown bot_type' in result['error']

    def test_run_bot_general_exception(self):
        with patch('apps.bots.models.QuantumAIBot.objects.select_related',
                   side_effect=Exception('DB failure')):
            result = run_bot('b1', 'quantum_ai')
            assert result['success'] is False
            assert 'DB failure' in result['error']

    def test_run_bot_signal_type(self):
        mock_bot = MagicMock()
        mock_bot.id = 's1'
        mock_bot.trading_pair = 'ETH/USDT'
        mock_bot.exchange_name = 'bybit'
        mock_bot.is_running = False

        mock_creds = MagicMock()
        mock_creds.is_testnet = False
        with patch('apps.bots.models.SignalBot.objects.select_related') as mock_qs:
            mock_qs.return_value.get.return_value = mock_bot
            with patch('apps.exchanges.models.ExchangeCredentials.objects.get') as mock_creds_qs:
                mock_creds_qs.return_value = mock_creds
                with patch('apps.trading.engines.bot_engine.BotExecutor.from_config') as mock_from_config:
                    mock_executor = MagicMock()
                    mock_executor.run_once.return_value = {'success': True}
                    mock_from_config.return_value = mock_executor

                    result = run_bot('s1', 'signal')

                assert result['success'] is True
                mock_from_config.assert_called_once()
                mock_executor.run_once.assert_called_once()

class TestDuplicatePrevention:
    def setup_method(self):
        _running_bots.clear()

    def test_mark_bot_starting_returns_true_first_time(self):
        assert _mark_bot_starting('bot-1') is True

    def test_mark_bot_starting_returns_false_on_duplicate(self):
        _mark_bot_starting('bot-1')
        assert _mark_bot_starting('bot-1') is False

    def test_mark_bot_stopped_removes_from_set(self):
        _mark_bot_starting('bot-1')
        _mark_bot_stopped('bot-1')
        assert _is_bot_running('bot-1') is False

    def test_is_bot_running_after_start(self):
        _mark_bot_starting('bot-1')
        assert _is_bot_running('bot-1') is True

    def test_mark_bot_stopped_idempotent(self):
        _mark_bot_stopped('nonexistent')
        assert _is_bot_running('nonexistent') is False

    def test_run_bot_returns_error_on_duplicate(self):
        _mark_bot_starting('dup-bot')
        result = run_bot('dup-bot', 'quantum_ai')
        assert result['success'] is False
        assert 'already running' in result['error']

    def test_run_bot_db_flag_check(self):
        mock_bot = MagicMock()
        mock_bot.id = 'q1'
        mock_bot.is_running = True  # DB says already running
        mock_bot.trading_pair = 'BTC/USDT'
        mock_bot.exchange_name = 'bybit'
        mock_bot.strategy_parameters = {}
        mock_bot.bot_name = 'QBot'
        mock_fund = MagicMock()
        mock_fund.master_api_key = 'enc_key'
        mock_fund.master_secret_key = 'enc_secret'
        mock_fund.master_passphrase = ''

        with patch('apps.bots.models.QuantumAIBot.objects.select_related') as mock_qs:
            mock_qs.return_value.get.return_value = mock_bot
            with patch('core.utils.decrypt_api_key') as mock_decrypt:
                mock_decrypt.return_value = 'decrypted_key'
                with patch('apps.trading.engines.bot_engine.BotEngine') as MockEngine:
                    result = run_bot('q1', 'quantum_ai')
                    assert result['success'] is False
                    assert 'DB flag' in result['error']
                    MockEngine.assert_not_called()


class TestStopBot:
    def setup_method(self):
        _running_bots.clear()

    def test_stop_bot_unknown_bot_is_noop(self):
        result = stop_bot('nonexistent', 'quantum_ai')
        assert result['success'] is True

    def test_stop_bot_signals_engine(self):
        _mark_bot_starting('bot-stop-1')
        mock_engine = MagicMock()
        with patch('apps.trading.engines.execution._running_engines', {'bot-stop-1': mock_engine}):
            with patch('apps.bots.models.QuantumAIBot.objects.filter') as mock_filter:
                mock_filter.return_value.update.return_value = 1
                result = stop_bot('bot-stop-1', 'quantum_ai')

            assert result['success'] is True
            mock_engine.stop_bot.assert_called_once()

    def test_stop_bot_updates_db_flag(self):
        _mark_bot_starting('bot-db')
        mock_engine = MagicMock()
        with patch('apps.trading.engines.execution._running_engines', {'bot-db': mock_engine}):
            with patch('apps.bots.models.QuantumAIBot.objects.filter') as mock_filter:
                mock_filter.return_value.update.return_value = 1
                stop_bot('bot-db', 'quantum_ai')
                mock_filter.assert_called_once_with(id='bot-db')
                update_kwargs = mock_filter.return_value.update.call_args[1]
                assert update_kwargs['is_running'] is False

    def test_stop_bot_clears_running_set(self):
        _mark_bot_starting('bot-clear')
        mock_engine = MagicMock()
        with patch('apps.trading.engines.execution._running_engines', {'bot-clear': mock_engine}):
            with patch('apps.bots.models.QuantumAIBot.objects.filter'):
                stop_bot('bot-clear', 'quantum_ai')
            assert _is_bot_running('bot-clear') is False

    def test_stop_bot_handles_db_error_gracefully(self):
        _mark_bot_starting('bot-err')
        mock_engine = MagicMock()
        with patch('apps.trading.engines.execution._running_engines', {'bot-err': mock_engine}):
            with patch('apps.bots.models.QuantumAIBot.objects.filter', side_effect=Exception('DB err')):
                result = stop_bot('bot-err', 'quantum_ai')
            assert result['success'] is True  # still succeeds
            mock_engine.stop_bot.assert_called_once()


class TestRunBotQuantumAI:
    def test_run_bot_martingale(self):
        mock_bot = MagicMock()
        mock_bot.id = 'm1'
        mock_bot.bot_name = 'MartingaleBot'
        mock_bot.trading_pair = 'BTC/USDT'
        mock_bot.exchange_name = 'bybit'
        mock_bot.favor_levels = 5
        mock_bot.against_levels = 5
        mock_bot.favor_level_qty = 5.0
        mock_bot.base_amount = 50.0
        mock_bot.is_running = False
        mock_bot.user = MagicMock()
        mock_bot.user.id = 'u1'

        mock_creds = MagicMock()
        mock_creds.is_testnet = True
        mock_creds.get_decrypted_credentials.return_value = {
            'api_key': 'dk', 'secret_key': 'ds',
        }

        mock_engine = MagicMock()
        mock_engine.reason = 'martingale signal'

        with patch('apps.bots.models.MartingaleBot.objects.select_related') as mock_qs:
            mock_qs.return_value.get.return_value = mock_bot
            with patch('apps.exchanges.models.ExchangeCredentials.objects.get') as mock_creds_qs:
                mock_creds_qs.return_value = mock_creds
                with patch('apps.trading.engines.bot_engine.BotEngine') as MockEngine:
                    MockEngine.return_value = mock_engine
                    result = run_bot('m1', 'martingale')
                assert result['success'] is True
