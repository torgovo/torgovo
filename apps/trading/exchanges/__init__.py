"""
Exchange adapters module.

This module provides adapters for different cryptocurrency exchanges.
Each adapter translates standard trading commands into exchange-specific API calls.
"""
from .base_adapter import BaseAdapter
from .binance import BinanceAdapter
from .bybit import BybitAdapter
from .okx import OKXAdapter
from .mexc import MEXCAdapter
from .alpaca import AlpacaAdapter

__all__ = [
    'BaseAdapter',
    'BinanceAdapter',
    'BybitAdapter',
    'OKXAdapter',
    'MEXCAdapter',
    'AlpacaAdapter',
]


def get_adapter(exchange_name: str, credentials: dict, demo_mode: bool = False):
    """
    Factory function to get the appropriate adapter for an exchange.

    Args:
        exchange_name: Name of the exchange (binance, bybit, etc.)
        credentials: Dict with api_key, secret_key, and optionally passphrase
        demo_mode: Whether to use testnet/sandbox mode

    Returns:
        BaseAdapter subclass instance

    Raises:
        ValueError: If exchange is not supported
    """
    adapters = {
        'binance': BinanceAdapter,
        'bybit': BybitAdapter,
        'okx': OKXAdapter,
        'mexc': MEXCAdapter,
        'alpaca': AlpacaAdapter,
    }

    adapter_class = adapters.get(exchange_name.lower())
    if not adapter_class:
        raise ValueError(f"Unsupported exchange: {exchange_name}")

    return adapter_class(credentials, demo_mode)
