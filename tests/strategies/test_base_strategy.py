import pytest
from datetime import datetime
from apps.trading.strategies.base import Signal, BaseStrategy


class TestSignal:
    def test_init_defaults(self):
        signal = Signal('buy', 'BTC/USDT', 0.01)
        assert signal.action == 'buy'
        assert signal.symbol == 'BTC/USDT'
        assert signal.amount == 0.01
        assert signal.price is None
        assert signal.order_type == 'market'
        assert signal.stop_loss is None
        assert signal.take_profit is None
        assert signal.reason == ''
        assert signal.metadata == {}
        assert isinstance(signal.timestamp, datetime)

    def test_init_with_all_fields(self):
        signal = Signal(
            action='SELL',
            symbol='ETH/USDT',
            amount=0.5,
            price=3000.0,
            order_type='LIMIT',
            stop_loss=3100.0,
            take_profit=2800.0,
            reason='Test signal',
            metadata={'indicator': 'RSI'}
        )
        assert signal.action == 'sell'
        assert signal.amount == 0.5
        assert signal.price == 3000.0
        assert signal.order_type == 'limit'
        assert signal.stop_loss == 3100.0
        assert signal.take_profit == 2800.0
        assert signal.reason == 'Test signal'
        assert signal.metadata == {'indicator': 'RSI'}

    def test_init_action_normalization(self):
        assert Signal('BUY', 'XRP/USDT', 100).action == 'buy'
        assert Signal('Sell', 'XRP/USDT', 100).action == 'sell'
        assert Signal('Close', 'XRP/USDT', 100).action == 'close'
        assert Signal('HoLd', 'XRP/USDT', 100).action == 'hold'

    def test_init_amount_conversion(self):
        signal = Signal('buy', 'BTC/USDT', 10.5)
        assert isinstance(signal.amount, float)
        assert signal.amount == 10.5

    def test_init_price_none(self):
        signal = Signal('buy', 'BTC/USDT', 1)
        assert signal.price is None

    def test_init_price_conversion(self):
        signal = Signal('buy', 'BTC/USDT', 1, price='50000.5')
        assert signal.price == 50000.5
        assert isinstance(signal.price, float)

    def test_init_stop_loss_take_profit_conversion(self):
        signal = Signal('buy', 'BTC/USDT', 1, stop_loss='48000', take_profit='52000')
        assert signal.stop_loss == 48000.0
        assert signal.take_profit == 52000.0

    def test_to_dict(self):
        signal = Signal('buy', 'BTC/USDT', 0.01, price=50000.0,
                        stop_loss=48000.0, take_profit=52000.0,
                        reason='RSI oversold', metadata={'rsi': 25})
        d = signal.to_dict()
        assert d['action'] == 'buy'
        assert d['symbol'] == 'BTC/USDT'
        assert d['amount'] == 0.01
        assert d['price'] == 50000.0
        assert d['type'] == 'market'
        assert d['stop_loss'] == 48000.0
        assert d['take_profit'] == 52000.0
        assert d['reason'] == 'RSI oversold'
        assert d['metadata'] == {'rsi': 25}
        assert 'timestamp' in d
        assert d['timestamp'] == signal.timestamp.isoformat()

    def test_to_dict_no_price(self):
        signal = Signal('hold', 'BTC/USDT', 0)
        d = signal.to_dict()
        assert d['action'] == 'hold'
        assert d['price'] is None
        assert d['stop_loss'] is None
        assert d['take_profit'] is None

    def test_repr_market(self):
        signal = Signal('buy', 'BTC/USDT', 0.01)
        assert repr(signal) == "Signal(buy 0.01 BTC/USDT @ market)"

    def test_repr_limit(self):
        signal = Signal('sell', 'ETH/USDT', 0.5, price=3000.0)
        assert repr(signal) == "Signal(sell 0.5 ETH/USDT @ 3000.0)"

    def test_metadata_default_empty_dict(self):
        signal = Signal('buy', 'BTC/USDT', 1, metadata=None)
        assert signal.metadata == {}

    def test_timestamp_set_at_creation(self):
        before = datetime.utcnow()
        signal = Signal('buy', 'BTC/USDT', 0.01)
        after = datetime.utcnow()
        assert before <= signal.timestamp <= after


class TestBaseStrategy:
    def test_init_defaults(self):
        class ConcreteStrategy(BaseStrategy):
            @property
            def name(self):
                return 'Test'

            def execute(self, market_data, account_info, current_position=None):
                pass

        s = ConcreteStrategy()
        assert s.parameters == {}
        assert s.is_running is False
        assert s.last_signal is None
        assert s.signals_generated == 0
        assert s.signals_executed == 0

    def test_init_with_parameters(self):
        class ConcreteStrategy(BaseStrategy):
            @property
            def name(self):
                return 'Test'

            def execute(self, market_data, account_info, current_position=None):
                pass

        s = ConcreteStrategy({'symbol': 'BTC/USDT', 'risk_percentage': 5})
        assert s.parameters == {'symbol': 'BTC/USDT', 'risk_percentage': 5}

    def test_required_parameters_defaults_empty(self):
        class ConcreteStrategy(BaseStrategy):
            @property
            def name(self):
                return 'Test'

            def execute(self, market_data, account_info, current_position=None):
                pass

        s = ConcreteStrategy()
        assert s.required_parameters == []

    def test_required_parameters_validated(self):
        class ConcreteStrategy(BaseStrategy):
            @property
            def name(self):
                return 'Test'

            @property
            def required_parameters(self):
                return ['symbol', 'amount']

            def execute(self, market_data, account_info, current_position=None):
                pass

        with pytest.raises(ValueError, match='Missing required parameters'):
            ConcreteStrategy({'symbol': 'BTC/USDT'})

    def test_required_parameters_all_present(self):
        class ConcreteStrategy(BaseStrategy):
            @property
            def name(self):
                return 'Test'

            @property
            def required_parameters(self):
                return ['symbol', 'amount']

            def execute(self, market_data, account_info, current_position=None):
                pass

        s = ConcreteStrategy({'symbol': 'BTC/USDT', 'amount': 100})
        assert s.parameters['symbol'] == 'BTC/USDT'

    def test_required_missing_multiple(self):
        class ConcreteStrategy(BaseStrategy):
            @property
            def name(self):
                return 'Test'

            @property
            def required_parameters(self):
                return ['a', 'b', 'c']

            def execute(self, market_data, account_info, current_position=None):
                pass

        with pytest.raises(ValueError, match="Missing required parameters: \\['a', 'b', 'c'\\]"):
            ConcreteStrategy({})

    def test_strategy_is_abstract_cannot_instantiate(self):
        with pytest.raises(TypeError):
            BaseStrategy()

    def test_abstract_methods_must_be_implemented(self):
        class IncompleteStrategy(BaseStrategy):
            pass

        with pytest.raises(TypeError):
            IncompleteStrategy()

    def test_should_enter_long_default(self):
        class ConcreteStrategy(BaseStrategy):
            @property
            def name(self):
                return 'Test'

            def execute(self, market_data, account_info, current_position=None):
                pass

        s = ConcreteStrategy()
        assert s.should_enter_long({}, {}) is False

    def test_should_enter_short_default(self):
        class ConcreteStrategy(BaseStrategy):
            @property
            def name(self):
                return 'Test'

            def execute(self, market_data, account_info, current_position=None):
                pass

        s = ConcreteStrategy()
        assert s.should_enter_short({}, {}) is False

    def test_should_exit_long_default(self):
        class ConcreteStrategy(BaseStrategy):
            @property
            def name(self):
                return 'Test'

            def execute(self, market_data, account_info, current_position=None):
                pass

        s = ConcreteStrategy()
        assert s.should_exit_long({}, {}) is False

    def test_should_exit_short_default(self):
        class ConcreteStrategy(BaseStrategy):
            @property
            def name(self):
                return 'Test'

            def execute(self, market_data, account_info, current_position=None):
                pass

        s = ConcreteStrategy()
        assert s.should_exit_short({}, {}) is False

    def test_calculate_position_size_default_risk(self):
        class ConcreteStrategy(BaseStrategy):
            @property
            def name(self):
                return 'Test'

            def execute(self, market_data, account_info, current_position=None):
                pass

        s = ConcreteStrategy()
        account_info = {'balance': {'free': {'USDT': 1000}}}
        size = s.calculate_position_size(account_info, 100, 'BTC/USDT')
        assert size == pytest.approx(1.0)  # 10% of 1000 = 100, / 100 = 1.0

    def test_calculate_position_size_custom_risk(self):
        class ConcreteStrategy(BaseStrategy):
            @property
            def name(self):
                return 'Test'

            def execute(self, market_data, account_info, current_position=None):
                pass

        s = ConcreteStrategy({'risk_percentage': 25})
        account_info = {'balance': {'free': {'USDT': 2000}}}
        size = s.calculate_position_size(account_info, 200, 'BTC/USDT')
        assert size == pytest.approx(2.5)  # 25% of 2000 = 500, / 200 = 2.5

    def test_calculate_position_size_zero_balance(self):
        class ConcreteStrategy(BaseStrategy):
            @property
            def name(self):
                return 'Test'

            def execute(self, market_data, account_info, current_position=None):
                pass

        s = ConcreteStrategy()
        account_info = {'balance': {'free': {'USDT': 0}}}
        size = s.calculate_position_size(account_info, 100, 'BTC/USDT')
        assert size == 0.0

    def test_calculate_position_size_no_quote_currency(self):
        class ConcreteStrategy(BaseStrategy):
            @property
            def name(self):
                return 'Test'

            def execute(self, market_data, account_info, current_position=None):
                pass

        s = ConcreteStrategy()
        account_info = {'balance': {'free': {}}}
        size = s.calculate_position_size(account_info, 100, 'BTC/USDT')
        assert size == 0.0

    def test_calculate_position_size_no_symbol_slash(self):
        class ConcreteStrategy(BaseStrategy):
            @property
            def name(self):
                return 'Test'

            def execute(self, market_data, account_info, current_position=None):
                pass

        s = ConcreteStrategy()
        account_info = {'balance': {'free': {'USDT': 500}}}
        size = s.calculate_position_size(account_info, 50, 'BTCUSDT')
        assert size == pytest.approx(1.0)

    def test_calculate_stop_loss_long_default(self):
        class ConcreteStrategy(BaseStrategy):
            @property
            def name(self):
                return 'Test'

            def execute(self, market_data, account_info, current_position=None):
                pass

        s = ConcreteStrategy()
        sl = s.calculate_stop_loss(100.0, 'long')
        assert sl == pytest.approx(98.0)  # 2% below entry

    def test_calculate_stop_loss_short_default(self):
        class ConcreteStrategy(BaseStrategy):
            @property
            def name(self):
                return 'Test'

            def execute(self, market_data, account_info, current_position=None):
                pass

        s = ConcreteStrategy()
        sl = s.calculate_stop_loss(100.0, 'short')
        assert sl == pytest.approx(102.0)  # 2% above entry

    def test_calculate_stop_loss_custom_pct(self):
        class ConcreteStrategy(BaseStrategy):
            @property
            def name(self):
                return 'Test'

            def execute(self, market_data, account_info, current_position=None):
                pass

        s = ConcreteStrategy({'stop_loss_percentage': 5})
        sl = s.calculate_stop_loss(200.0, 'long')
        assert sl == pytest.approx(190.0)

    def test_calculate_stop_loss_zero_pct(self):
        class ConcreteStrategy(BaseStrategy):
            @property
            def name(self):
                return 'Test'

            def execute(self, market_data, account_info, current_position=None):
                pass

        s = ConcreteStrategy({'stop_loss_percentage': 0})
        sl = s.calculate_stop_loss(100.0, 'long')
        assert sl == pytest.approx(100.0)

    def test_calculate_take_profit_long_default(self):
        class ConcreteStrategy(BaseStrategy):
            @property
            def name(self):
                return 'Test'

            def execute(self, market_data, account_info, current_position=None):
                pass

        s = ConcreteStrategy()
        tp = s.calculate_take_profit(100.0, 'long')
        assert tp == pytest.approx(105.0)  # 5% above entry

    def test_calculate_take_profit_short_default(self):
        class ConcreteStrategy(BaseStrategy):
            @property
            def name(self):
                return 'Test'

            def execute(self, market_data, account_info, current_position=None):
                pass

        s = ConcreteStrategy()
        tp = s.calculate_take_profit(100.0, 'short')
        assert tp == pytest.approx(95.0)  # 5% below entry

    def test_calculate_take_profit_custom_pct(self):
        class ConcreteStrategy(BaseStrategy):
            @property
            def name(self):
                return 'Test'

            def execute(self, market_data, account_info, current_position=None):
                pass

        s = ConcreteStrategy({'take_profit_percentage': 10})
        tp = s.calculate_take_profit(50.0, 'long')
        assert tp == pytest.approx(55.0)

    def test_get_status_default(self):
        class ConcreteStrategy(BaseStrategy):
            @property
            def name(self):
                return 'Test'

            def execute(self, market_data, account_info, current_position=None):
                pass

        s = ConcreteStrategy({'option': 'value'})
        status = s.get_status()
        assert status['name'] == 'Test'
        assert status['is_running'] is False
        assert status['signals_generated'] == 0
        assert status['signals_executed'] == 0
        assert status['last_signal'] is None
        assert status['parameters'] == {'option': 'value'}

    def test_get_status_with_last_signal(self):
        class ConcreteStrategy(BaseStrategy):
            @property
            def name(self):
                return 'Test'

            def execute(self, market_data, account_info, current_position=None):
                pass

        s = ConcreteStrategy()
        s.last_signal = Signal('buy', 'BTC/USDT', 0.01, price=50000)
        status = s.get_status()
        assert status['last_signal']['action'] == 'buy'
        assert status['last_signal']['symbol'] == 'BTC/USDT'

    def test_update_parameters(self):
        class ConcreteStrategy(BaseStrategy):
            @property
            def name(self):
                return 'Test'

            def execute(self, market_data, account_info, current_position=None):
                pass

        s = ConcreteStrategy({'symbol': 'BTC/USDT'})
        s.update_parameters({'risk_percentage': 15})
        assert s.parameters['symbol'] == 'BTC/USDT'
        assert s.parameters['risk_percentage'] == 15

    def test_update_parameters_triggers_validation(self):
        class ConcreteStrategy(BaseStrategy):
            @property
            def name(self):
                return 'Test'

            @property
            def required_parameters(self):
                return ['symbol']

            def execute(self, market_data, account_info, current_position=None):
                pass

        s = ConcreteStrategy({'symbol': 'BTC/USDT'})
        s.update_parameters({'risk': 10})
        assert s.parameters['symbol'] == 'BTC/USDT'
        assert s.parameters['risk'] == 10

        with pytest.raises(ValueError):
            s.parameters.pop('symbol')
            s._validate_parameters()

    def test_str(self):
        class ConcreteStrategy(BaseStrategy):
            @property
            def name(self):
                return 'Momentum'

            def execute(self, market_data, account_info, current_position=None):
                pass

        s = ConcreteStrategy()
        s.is_running = True
        assert str(s) == 'Momentum(running=True)'

    def test_repr(self):
        class ConcreteStrategy(BaseStrategy):
            @property
            def name(self):
                return 'Test'

            def execute(self, market_data, account_info, current_position=None):
                pass

        s = ConcreteStrategy({'symbol': 'BTC/USDT'})
        assert repr(s) == "ConcreteStrategy(parameters={'symbol': 'BTC/USDT'})"

    def test_execute_not_implemented(self):
        class NoExecuteStrategy(BaseStrategy):
            @property
            def name(self):
                return 'Bad'

        with pytest.raises(TypeError):
            NoExecuteStrategy()

    def test_signal_tracking(self):
        class ConcreteStrategy(BaseStrategy):
            @property
            def name(self):
                return 'Test'

            def execute(self, market_data, account_info, current_position=None):
                return Signal('buy', 'BTC/USDT', 0.01)

        s = ConcreteStrategy()
        result = s.execute({}, {})
        s.signals_generated += 1
        assert s.signals_generated == 1
        assert result is not None

    def test_calculate_position_size_negative_price(self):
        class ConcreteStrategy(BaseStrategy):
            @property
            def name(self):
                return 'Test'

            def execute(self, market_data, account_info, current_position=None):
                pass

        s = ConcreteStrategy()
        account_info = {'balance': {'free': {'USDT': 500}}}
        size = s.calculate_position_size(account_info, -1, 'BTC/USDT')
        assert size == 0.0

    def test_calculate_position_size_zero_price(self):
        class ConcreteStrategy(BaseStrategy):
            @property
            def name(self):
                return 'Test'

            def execute(self, market_data, account_info, current_position=None):
                pass

        s = ConcreteStrategy()
        account_info = {'balance': {'free': {'USDT': 500}}}
        size = s.calculate_position_size(account_info, 0, 'BTC/USDT')
        assert size == 0.0
