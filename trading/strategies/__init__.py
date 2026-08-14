"""
Trading Strategies Package
Exchange-AGNOSTIC trading logic
"""

from .quantum_ai import QuantumAIStrategy

# Will add more strategies:
# from .grid_bot import GridBotStrategy
# from .martingale_bot import MartingaleBotStrategy
# from .custom_bot import CustomBotStrategy

__all__ = [
    "QuantumAIStrategy",
]
