"""
Exchange adapters module.

This module provides adapters for different cryptocurrency exchanges.
Each adapter translates standard trading commands into exchange-specific API calls.
"""

import os

from .alpaca import AlpacaAdapter
from .base_adapter import BaseAdapter
from .binance import BinanceAdapter
from .bybit import BybitAdapter
from .coinbase import CoinbaseAdapter
from .mexc import MEXCAdapter
from .mock_adapter import MockAdapter
from .okx import OKXAdapter

__all__ = [
    "BaseAdapter",
    "BinanceAdapter",
    "BybitAdapter",
    "CoinbaseAdapter",
    "OKXAdapter",
    "MEXCAdapter",
    "AlpacaAdapter",
    "MockAdapter",
    "ExchangeDisabledError",
    "get_adapter",
    "disabled_exchanges",
]

# Environment variable that acts as a kill-switch / feature flag for
# individual exchanges. Comma-separated list of exchange names that must not
# be used for live trading. Kept in this pure-Python module (no Django
# imports) so every consumer of the adapter factory is covered, including
# celery tasks and the trading engine. The mock adapter is intentionally
# exempt so demo/testing flows keep working during an incident.
DISABLED_EXCHANGES_ENV = "DISABLED_EXCHANGES"


class ExchangeDisabledError(ValueError):
    """
    Raised by :func:`get_adapter` when the requested exchange is disabled via
    the ``DISABLED_EXCHANGES`` environment variable (kill-switch).
    """


def disabled_exchanges() -> set:
    """
    Return the set of exchange names disabled by the kill-switch env var.

    Reads ``DISABLED_EXCHANGES`` (comma-separated, whitespace-trimmed,
    case-insensitive) on every call so operators can flip the switch without
    restarting the process.

    Returns:
        Set of lowercase exchange names currently disabled.
    """
    raw = os.environ.get(DISABLED_EXCHANGES_ENV, "")
    return {name.strip().lower() for name in raw.split(",") if name.strip()}


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
        ExchangeDisabledError: If the exchange is disabled via the kill-switch
        ValueError: If exchange is not supported
    """
    adapters = {
        "binance": BinanceAdapter,
        "bybit": BybitAdapter,
        "coinbase": CoinbaseAdapter,
        "okx": OKXAdapter,
        "mexc": MEXCAdapter,
        "alpaca": AlpacaAdapter,
    }

    if not exchange_name:
        raise ValueError(f"Unsupported exchange: {exchange_name}")
    normalized_name = exchange_name.lower()
    adapter_class = adapters.get(normalized_name)
    if not adapter_class:
        raise ValueError(f"Unsupported exchange: {exchange_name}")

    # Demo/sandbox fallback runs first so the MockAdapter (used for exchanges
    # without a sandbox API) is exempt from the kill-switch — demo and testing
    # flows keep working even during an incident.
    if demo_mode and exchange_name.lower() in ("mexc", "coinbase"):
        logger = __import__("logging").getLogger("trading.exchanges")
        logger.warning(
            f"{exchange_name} does not have a demo/sandbox API. "
            f"Falling back to MockAdapter for testing."
        )
        return MockAdapter(credentials)

    # Kill-switch guard: refuse to create adapters for disabled exchanges.
    if normalized_name in disabled_exchanges():
        raise ExchangeDisabledError(
            f"Exchange {exchange_name} is disabled by the " f"{DISABLED_EXCHANGES_ENV} kill-switch."
        )

    return adapter_class(credentials, demo_mode)
