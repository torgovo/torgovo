"""
Trading strategies for automated trading
"""
from .base import BaseTradingStrategy
from .grid_bot import GridTradingStrategy
from .martingale_bot import MartingaleTradingStrategy
from .quantum_ai_bot import QuantumAITradingStrategy

__all__ = [
    'BaseTradingStrategy',
    'GridTradingStrategy',
    'MartingaleTradingStrategy',
    'QuantumAITradingStrategy',
]