"""
Trading models for Torgovo Crypto Trading Platform

This module re-exports Exchange and TradingPair from apps.exchanges for
backward-compatibility. The ONLY unique model defined here is StrategyConfig
(strategy presets for the trading engine).

Exchange data (Exchange, TradingPair) — use apps.exchanges.models.
ExchangeCredentials — use apps.exchanges.models (imported below).
Investment/display models (SupportedBlockchain, ExchangeRate, ExchangeStatus)
— use apps.investments.models.
"""

from django.db import models

# Canonical models live in apps.exchanges — re-exported here for backward-compat
# so apps/trading/ views/serializers/admin still resolve them.
from apps.exchanges.models import Exchange  # noqa: F401
from apps.exchanges.models import ExchangeCredentials  # noqa: F401
from apps.exchanges.models import TradingPair  # noqa: F401
from core.models import SoftDeleteModel

# =============================================================================
# STRATEGY CONFIG (Default Presets)
# =============================================================================


class StrategyConfig(SoftDeleteModel):
    """
    Strategy configuration templates / default presets.

    Each bot type (SignalBot, GridBot, MartingaleBot) has its own per-user params.
    StrategyConfig provides reusable defaults so if a user doesn't set custom
    values, these are used. Admin can create presets like:
    - "Quantum AI Aggressive"
    - "Grid Conservative"
    - "Martingale High Risk"
    """

    STRATEGY_CHOICES = [
        ("quantum_ai", "Quantum AI"),
        ("grid", "Grid Trading"),
        ("martingale", "Martingale"),
        ("signal", "Signal Bot"),
    ]

    name = models.CharField(max_length=100, help_text="e.g., 'Quantum AI Aggressive'")
    strategy = models.CharField(max_length=20, choices=STRATEGY_CHOICES)
    default_parameters = models.JSONField(default=dict, help_text="Default strategy parameters")
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "trading_strategy_configs"
        indexes = [
            models.Index(fields=["strategy", "is_active"]),
        ]

    def __str__(self):
        return f"{self.name} - {self.get_strategy_display()}"
