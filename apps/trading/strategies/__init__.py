"""
Trading strategies module.

This module provides trading strategies that are completely exchange-agnostic.
Strategies receive market data and account info, return signals.
They never directly call exchange APIs.
"""
from .base import BaseStrategy
from .quantum_ai import QuantumAIStrategy
from .grid_trading import GridTradingStrategy
from .martingale import MartingaleStrategy
from .webhook_alerts import WebhookAlertStrategy

__all__ = [
    'BaseStrategy',
    'QuantumAIStrategy',
    'GridTradingStrategy',
    'MartingaleStrategy',
    'WebhookAlertStrategy',
]


def get_strategy(strategy_name: str, parameters: dict = None):
    """
    Factory function to get a strategy class by name.

    Args:
        strategy_name: Name of the strategy (quantum_ai, grid, martingale, webhook)
        parameters: Strategy-specific parameters

    Returns:
        Strategy class (not instance)

    Raises:
        ValueError: If strategy is not supported
    """
    strategies = {
        'quantum_ai': QuantumAIStrategy,
        'grid': GridTradingStrategy,
        'martingale': MartingaleStrategy,
        'webhook': WebhookAlertStrategy,
    }

    strategy_class = strategies.get(strategy_name.lower())
    if not strategy_class:
        raise ValueError(f"Unsupported strategy: {strategy_name}")

    return strategy_class
