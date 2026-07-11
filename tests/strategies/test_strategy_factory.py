import pytest
from apps.trading.strategies import (
    get_strategy,
    BaseStrategy,
    QuantumAIStrategy,
    GridTradingStrategy,
    MartingaleStrategy,
    WebhookAlertStrategy,
)


class TestStrategyFactory:
    def test_get_quantum_ai_strategy(self):
        strategy_class = get_strategy('quantum_ai')
        assert strategy_class == QuantumAIStrategy
        assert issubclass(strategy_class, BaseStrategy)

    def test_get_grid_strategy(self):
        strategy_class = get_strategy('grid')
        assert strategy_class == GridTradingStrategy
        assert issubclass(strategy_class, BaseStrategy)

    def test_get_martingale_strategy(self):
        strategy_class = get_strategy('martingale')
        assert strategy_class == MartingaleStrategy
        assert issubclass(strategy_class, BaseStrategy)

    def test_get_webhook_strategy(self):
        strategy_class = get_strategy('webhook')
        assert strategy_class == WebhookAlertStrategy
        assert issubclass(strategy_class, BaseStrategy)

    def test_case_insensitivity(self):
        assert get_strategy('QUANTUM_AI') == QuantumAIStrategy
        assert get_strategy('Grid') == GridTradingStrategy
        assert get_strategy('MARTINGALE') == MartingaleStrategy
        assert get_strategy('Webhook') == WebhookAlertStrategy

    def test_unsupported_strategy(self):
        with pytest.raises(ValueError, match='Unsupported strategy'):
            get_strategy('unknown')

    def test_unsupported_strategy_empty(self):
        with pytest.raises(ValueError, match='Unsupported strategy'):
            get_strategy('')

    def test_unsupported_strategy_none(self):
        with pytest.raises((ValueError, AttributeError)):
            get_strategy(None)

    def test_instantiate_via_factory(self):
        strategy_class = get_strategy('grid')
        strategy = strategy_class({'symbol': 'BTC/USDT', 'amount_per_grid': 10})
        assert strategy.name == 'Grid Trading'
        assert strategy.parameters['symbol'] == 'BTC/USDT'

    def test_instantiate_quantum_ai_via_factory(self):
        strategy_class = get_strategy('quantum_ai')
        strategy = strategy_class({'symbol': 'BTC/USDT'})
        assert strategy.name == 'Quantum AI'

    def test_all_strategies_returned(self):
        names = ['quantum_ai', 'grid', 'martingale', 'webhook']
        classes = [QuantumAIStrategy, GridTradingStrategy, MartingaleStrategy, WebhookAlertStrategy]
        for name, cls in zip(names, classes):
            assert get_strategy(name) == cls

    def test_all_strategies_are_base_strategy_subclasses(self):
        for name in ['quantum_ai', 'grid', 'martingale', 'webhook']:
            cls = get_strategy(name)
            assert issubclass(cls, BaseStrategy), f"{name} is not a BaseStrategy subclass"
