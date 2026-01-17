"""
Trading Adapters Package
Exchange-specific adapters that translate standard commands to exchange APIs
"""
from .base import BaseExchangeAdapter
from .bybit import BybitAdapter
from .binance import BinanceAdapter
from .okx import OKXAdapter
from .mexc import MEXCAdapter
from .coinbase import CoinbaseAdapter
from .alpaca import AlpacaAdapter

# Exchange adapter factory
EXCHANGE_ADAPTERS = {
    'bybit': BybitAdapter,
    'binance': BinanceAdapter,
    'okx': OKXAdapter,
    'mexc': MEXCAdapter,
    'coinbase': CoinbaseAdapter,
    'alpaca': AlpacaAdapter,
}


def get_exchange_adapter(exchange_name: str, credentials: dict, demo_mode: bool = False) -> BaseExchangeAdapter:
    """
    Factory function to get the appropriate exchange adapter.
    
    Args:
        exchange_name: Name of exchange (e.g., 'bybit', 'binance')
        credentials: Dict with 'api_key', 'secret_key', optionally 'passphrase'
        demo_mode: Whether to use testnet
        
    Returns:
        Exchange adapter instance
        
    Raises:
        ValueError: If exchange not supported
    """
    exchange_name = exchange_name.lower()
    
    if exchange_name not in EXCHANGE_ADAPTERS:
        raise ValueError(f"Unsupported exchange: {exchange_name}. Supported: {list(EXCHANGE_ADAPTERS.keys())}")
    
    adapter_class = EXCHANGE_ADAPTERS[exchange_name]
    return adapter_class(credentials, demo_mode)


__all__ = [
    'BaseExchangeAdapter',
    'BybitAdapter',
    'BinanceAdapter',
    'OKXAdapter',
    'MEXCAdapter',
    'CoinbaseAdapter',
    'AlpacaAdapter',
    'get_exchange_adapter',
    'EXCHANGE_ADAPTERS',
]
