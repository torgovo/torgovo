import pytest
from apps.trading.strategies.martingale import MartingaleStrategy


class TestMartingaleInitialization:
    def test_init_defaults(self):
        strategy = MartingaleStrategy({'symbol': 'BTC/USDT', 'base_amount': 0.01})
        assert strategy.name == 'Martingale'
        assert strategy.parameters['symbol'] == 'BTC/USDT'
        assert strategy.parameters['base_amount'] == 0.01
        assert strategy.parameters['multiplier'] == 2.0
        assert strategy.parameters['max_multiplications'] == 5
        assert strategy.parameters['take_profit_percentage'] == 1.0
        assert strategy.parameters['stop_loss_percentage'] == 1.0
        assert strategy.parameters['direction'] == 'both'
        assert strategy.current_level == 0
        assert strategy.consecutive_losses == 0
        assert strategy.last_trade_result is None

    def test_init_custom_parameters(self):
        strategy = MartingaleStrategy({
            'symbol': 'ETH/USDT',
            'base_amount': 0.1,
            'multiplier': 3.0,
            'max_multiplications': 3,
            'take_profit_percentage': 0.5,
            'stop_loss_percentage': 0.5,
            'direction': 'long',
        })
        assert strategy.parameters['multiplier'] == 3.0
        assert strategy.parameters['max_multiplications'] == 3
        assert strategy.parameters['direction'] == 'long'

    def test_init_missing_required_params(self):
        with pytest.raises(ValueError, match='Missing required parameters'):
            MartingaleStrategy({})

    def test_init_missing_symbol(self):
        with pytest.raises(ValueError, match='Missing required parameters.*symbol'):
            MartingaleStrategy({'base_amount': 0.01})

    def test_required_parameters(self):
        strategy = MartingaleStrategy({'symbol': 'BTC/USDT', 'base_amount': 0.01})
        assert 'symbol' in strategy.required_parameters
        assert 'base_amount' in strategy.required_parameters


class TestMartingalePositionSizing:
    def test_base_amount_first_trade(self):
        strategy = MartingaleStrategy({'symbol': 'BTC/USDT', 'base_amount': 0.01})
        market_data = {'ticker': {'last': 50000.0}, 'ohlcv': [{'close': 49000.0}, {'close': 50000.0}]}
        signal = strategy.execute(market_data, {})
        assert signal is not None
        assert signal.amount == 0.01
        assert signal.metadata['martingale_level'] == 0

    def test_doubling_after_loss(self):
        strategy = MartingaleStrategy({'symbol': 'BTC/USDT', 'base_amount': 0.01})
        strategy._register_loss()
        assert strategy.current_level == 1

        market_data = {'ticker': {'last': 50000.0}, 'ohlcv': [{'close': 49000.0}, {'close': 50000.0}]}
        signal = strategy.execute(market_data, {}, None)
        assert signal is not None
        assert signal.amount == 0.02
        assert signal.metadata['martingale_level'] == 1

    def test_doubling_multiple_losses(self):
        strategy = MartingaleStrategy({'symbol': 'BTC/USDT', 'base_amount': 0.01, 'multiplier': 2.0})
        strategy._register_loss()
        strategy._register_loss()
        strategy._register_loss()
        assert strategy.current_level == 3

        market_data = {'ticker': {'last': 50000.0}, 'ohlcv': [{'close': 49000.0}, {'close': 50000.0}]}
        signal = strategy.execute(market_data, {}, None)
        assert signal.amount == pytest.approx(0.08)

    def test_reset_after_win(self):
        strategy = MartingaleStrategy({'symbol': 'BTC/USDT', 'base_amount': 0.01})
        strategy._register_loss()
        strategy._register_loss()
        assert strategy.current_level == 2
        strategy._register_win()
        assert strategy.current_level == 0
        assert strategy.consecutive_losses == 0

    def test_max_multiplications_cap(self):
        strategy = MartingaleStrategy({
            'symbol': 'BTC/USDT',
            'base_amount': 0.01,
            'max_multiplications': 3,
        })
        for _ in range(5):
            strategy._register_loss()
        assert strategy.current_level == 5

        market_data = {'ticker': {'last': 50000.0}, 'ohlcv': [{'close': 49000.0}, {'close': 50000.0}]}
        signal = strategy.execute(market_data, {}, None)
        assert signal.amount == 0.01
        assert strategy.current_level == 0

    def test_exponential_growth(self):
        strategy = MartingaleStrategy({
            'symbol': 'BTC/USDT',
            'base_amount': 0.01,
            'multiplier': 2.0,
            'max_multiplications': 5,
        })
        for i in range(4):
            strategy._register_loss()
            market_data = {'ticker': {'last': 50000.0}, 'ohlcv': [{'close': 49000.0}, {'close': 50000.0}]}
            signal = strategy.execute(market_data, {}, None)
            expected = 0.01 * (2.0 ** (i + 1))
            assert signal.amount == pytest.approx(expected)

    def test_custom_multiplier(self):
        strategy = MartingaleStrategy({
            'symbol': 'BTC/USDT',
            'base_amount': 0.01,
            'multiplier': 3.0,
        })
        strategy._register_loss()
        market_data = {'ticker': {'last': 50000.0}, 'ohlcv': [{'close': 49000.0}, {'close': 50000.0}]}
        signal = strategy.execute(market_data, {}, None)
        assert signal.amount == pytest.approx(0.03)


class TestMartingaleEntryExit:
    def test_entry_long_direction(self):
        strategy = MartingaleStrategy({
            'symbol': 'BTC/USDT',
            'base_amount': 0.01,
            'direction': 'long',
        })
        market_data = {'ticker': {'last': 50000.0}}
        signal = strategy.execute(market_data, {}, None)
        assert signal.action == 'buy'
        assert signal.stop_loss is not None
        assert signal.take_profit is not None

    def test_entry_short_direction(self):
        strategy = MartingaleStrategy({
            'symbol': 'BTC/USDT',
            'base_amount': 0.01,
            'direction': 'short',
        })
        market_data = {'ticker': {'last': 50000.0}}
        signal = strategy.execute(market_data, {}, None)
        assert signal.action == 'sell'

    def test_entry_momentum_bullish(self):
        strategy = MartingaleStrategy({
            'symbol': 'BTC/USDT',
            'base_amount': 0.01,
            'direction': 'both',
        })
        market_data = {
            'ticker': {'last': 51000.0},
            'ohlcv': [{'close': 49000.0}, {'close': 51000.0}],
        }
        signal = strategy.execute(market_data, {}, None)
        assert signal.action == 'buy'

    def test_entry_momentum_bearish(self):
        strategy = MartingaleStrategy({
            'symbol': 'BTC/USDT',
            'base_amount': 0.01,
            'direction': 'both',
        })
        market_data = {
            'ticker': {'last': 49000.0},
            'ohlcv': [{'close': 51000.0}, {'close': 49000.0}],
        }
        signal = strategy.execute(market_data, {}, None)
        assert signal.action == 'sell'

    def test_entry_with_position_does_nothing(self):
        strategy = MartingaleStrategy({'symbol': 'BTC/USDT', 'base_amount': 0.01})
        current_position = {
            'symbol': 'BTC/USDT',
            'side': 'long',
            'contracts': 0.01,
            'entry_price': 50000.0,
        }
        market_data = {'ticker': {'last': 50100.0}}
        signal = strategy.execute(market_data, {}, current_position)
        assert signal is None

    def test_take_profit_long(self):
        strategy = MartingaleStrategy({
            'symbol': 'BTC/USDT',
            'base_amount': 0.01,
            'take_profit_percentage': 1.0,
        })
        current_position = {
            'symbol': 'BTC/USDT',
            'side': 'long',
            'contracts': 0.01,
            'entry_price': 50000.0,
        }
        market_data = {'ticker': {'last': 50550.0}}
        signal = strategy.execute(market_data, {}, current_position)
        assert signal is not None
        assert signal.metadata['result'] == 'win'
        assert strategy.current_level == 0
        assert strategy.last_trade_result == 'win'

    def test_stop_loss_long(self):
        strategy = MartingaleStrategy({
            'symbol': 'BTC/USDT',
            'base_amount': 0.01,
            'stop_loss_percentage': 1.0,
        })
        current_position = {
            'symbol': 'BTC/USDT',
            'side': 'long',
            'contracts': 0.01,
            'entry_price': 50000.0,
        }
        market_data = {'ticker': {'last': 49450.0}}
        signal = strategy.execute(market_data, {}, current_position)
        assert signal is not None
        assert signal.metadata['result'] == 'loss'
        assert strategy.current_level == 1
        assert strategy.last_trade_result == 'loss'

    def test_take_profit_short(self):
        strategy = MartingaleStrategy({
            'symbol': 'BTC/USDT',
            'base_amount': 0.01,
            'take_profit_percentage': 1.0,
            'direction': 'short',
        })
        current_position = {
            'symbol': 'BTC/USDT',
            'side': 'short',
            'contracts': 0.01,
            'entry_price': 50000.0,
        }
        market_data = {'ticker': {'last': 49450.0}}
        signal = strategy.execute(market_data, {}, current_position)
        assert signal is not None
        assert signal.metadata['result'] == 'win'

    def test_stop_loss_short(self):
        strategy = MartingaleStrategy({
            'symbol': 'BTC/USDT',
            'base_amount': 0.01,
            'stop_loss_percentage': 1.0,
            'direction': 'short',
        })
        current_position = {
            'symbol': 'BTC/USDT',
            'side': 'short',
            'contracts': 0.01,
            'entry_price': 50000.0,
        }
        market_data = {'ticker': {'last': 50550.0}}
        signal = strategy.execute(market_data, {}, current_position)
        assert signal is not None
        assert signal.metadata['result'] == 'loss'

    def test_no_signal_in_position_no_tp_sl_hit(self):
        strategy = MartingaleStrategy({
            'symbol': 'BTC/USDT',
            'base_amount': 0.01,
            'take_profit_percentage': 2.0,
            'stop_loss_percentage': 2.0,
        })
        current_position = {
            'symbol': 'BTC/USDT',
            'side': 'long',
            'contracts': 0.01,
            'entry_price': 50000.0,
        }
        market_data = {'ticker': {'last': 50100.0}}
        signal = strategy.execute(market_data, {}, current_position)
        assert signal is None

    def test_no_price_data(self):
        strategy = MartingaleStrategy({'symbol': 'BTC/USDT', 'base_amount': 0.01})
        market_data = {'ticker': {}}
        signal = strategy.execute(market_data, {}, None)
        assert signal is None

    def test_sl_tp_in_entry_signal(self):
        strategy = MartingaleStrategy({
            'symbol': 'BTC/USDT',
            'base_amount': 0.01,
            'stop_loss_percentage': 1.5,
            'take_profit_percentage': 2.0,
        })
        market_data = {'ticker': {'last': 50000.0}}
        signal = strategy.execute(market_data, {}, None)
        assert signal.stop_loss == pytest.approx(49250.0)
        assert signal.take_profit == pytest.approx(51000.0)

    def test_close_side_on_tp_long(self):
        strategy = MartingaleStrategy({
            'symbol': 'BTC/USDT',
            'base_amount': 0.01,
            'take_profit_percentage': 1.0,
        })
        current_position = {
            'side': 'long',
            'contracts': 0.01,
            'entry_price': 50000.0,
        }
        market_data = {'ticker': {'last': 50550.0}}
        signal = strategy.execute(market_data, {}, current_position)
        assert signal.action == 'sell'

    def test_close_side_on_sl_short(self):
        strategy = MartingaleStrategy({
            'symbol': 'BTC/USDT',
            'base_amount': 0.01,
            'stop_loss_percentage': 1.0,
        })
        current_position = {
            'side': 'short',
            'contracts': 0.01,
            'entry_price': 50000.0,
        }
        market_data = {'ticker': {'last': 50550.0}}
        signal = strategy.execute(market_data, {}, current_position)
        assert signal.action == 'buy'


class TestMartingaleStateManagement:
    def test_register_win_resets_state(self):
        strategy = MartingaleStrategy({'symbol': 'BTC/USDT', 'base_amount': 0.01})
        strategy.current_level = 3
        strategy.consecutive_losses = 3
        strategy._register_win()
        assert strategy.current_level == 0
        assert strategy.consecutive_losses == 0
        assert strategy.last_trade_result == 'win'

    def test_register_loss_increments(self):
        strategy = MartingaleStrategy({'symbol': 'BTC/USDT', 'base_amount': 0.01})
        strategy._register_loss()
        assert strategy.current_level == 1
        assert strategy.consecutive_losses == 1
        assert strategy.last_trade_result == 'loss'

    def test_reset(self):
        strategy = MartingaleStrategy({'symbol': 'BTC/USDT', 'base_amount': 0.01})
        strategy.current_level = 4
        strategy.consecutive_losses = 4
        strategy.last_trade_result = 'loss'
        strategy.reset()
        assert strategy.current_level == 0
        assert strategy.consecutive_losses == 0
        assert strategy.last_trade_result is None

    def test_consecutive_losses_tracking(self):
        strategy = MartingaleStrategy({'symbol': 'BTC/USDT', 'base_amount': 0.01})
        for _ in range(5):
            strategy._register_loss()
        assert strategy.consecutive_losses == 5
        assert strategy.current_level == 5


class TestMartingaleStatus:
    def test_get_status(self):
        strategy = MartingaleStrategy({'symbol': 'BTC/USDT', 'base_amount': 0.01})
        strategy._register_loss()
        status = strategy.get_status()
        assert status['current_level'] == 1
        assert status['consecutive_losses'] == 1
        assert status['current_multiplier'] == 2.0
        assert status['next_position_size'] == 0.02

    def test_get_status_base_fields(self):
        strategy = MartingaleStrategy({'symbol': 'BTC/USDT', 'base_amount': 0.01})
        status = strategy.get_status()
        assert status['name'] == 'Martingale'
        assert 'is_running' in status
        assert 'signals_generated' in status
        assert 'signals_executed' in status

    def test_get_status_after_win(self):
        strategy = MartingaleStrategy({'symbol': 'BTC/USDT', 'base_amount': 0.01})
        strategy._register_loss()
        strategy._register_loss()
        strategy._register_win()
        status = strategy.get_status()
        assert status['current_level'] == 0
        assert status['consecutive_losses'] == 0
        assert status['next_position_size'] == 0.01


class TestMartingaleScenarios:
    def test_series_of_losses_then_win(self):
        strategy = MartingaleStrategy({
            'symbol': 'BTC/USDT',
            'base_amount': 10,
            'multiplier': 2.0,
            'max_multiplications': 4,
        })
        for i in range(3):
            strategy._register_loss()
        market_data = {'ticker': {'last': 50000.0}, 'ohlcv': [{'close': 49000.0}, {'close': 50000.0}]}
        signal = strategy.execute(market_data, {}, None)
        assert signal.amount == 80.0

        strategy._register_win()
        signal = strategy.execute(market_data, {}, None)
        assert signal.amount == 10.0

    def test_direction_long_only(self):
        strategy = MartingaleStrategy({
            'symbol': 'BTC/USDT',
            'base_amount': 0.01,
            'direction': 'long',
        })
        market_data = {'ticker': {'last': 50000.0}}
        signal = strategy.execute(market_data, {}, None)
        assert signal.action == 'buy'

        market_data = {'ticker': {'last': 49000.0}}
        signal = strategy.execute(market_data, {}, None)
        assert signal.action == 'buy'  # Still buy for long-only

    def test_momentum_with_insufficient_data(self):
        strategy = MartingaleStrategy({
            'symbol': 'BTC/USDT',
            'base_amount': 0.01,
            'direction': 'both',
        })
        market_data = {'ticker': {'last': 50000.0}, 'ohlcv': [{'close': 50000.0}]}
        signal = strategy.execute(market_data, {}, None)
        assert signal.action == 'buy'
