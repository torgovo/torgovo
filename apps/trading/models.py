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


# =============================================================================
# BOT RUNTIME STATE (crash-recovery anchor — persistence Phase 2)
# =============================================================================


class BotRuntimeState(models.Model):
    """
    Latest known runtime state of ONE bot engine (persistence Phase 2).

    Addressed by the same uniform ``(bot_type, bot_id)`` pair BotOrder uses, so
    recovery never needs a join and the quantum_ai / InvestorPortfolio FK
    mismatch cannot corrupt rows here. The UNIQUE constraint makes every write
    an upsert.

    Lifecycle ``status``:
      * ``running``   — engine alive (or left behind by a crashed worker)
      * ``stopping``  — a stop was requested, engine winding down
      * ``stopped``   — clean shutdown; recovery must ignore this row

    Rows still marked ``running`` after a worker death are exactly what the
    Phase 4 recovery task picks up. ``heartbeat_at`` is the liveness timestamp
    the Phase 5 watchdog reads.
    """

    BOT_TYPE_CHOICES = [
        ("quantum_ai", "Quantum AI"),
        ("grid", "Grid Trading"),
        ("martingale", "Martingale"),
        ("signal", "Signal Bot"),
        ("custom", "Custom"),
    ]

    STATUS_RUNNING = "running"
    STATUS_STOPPING = "stopping"
    STATUS_STOPPED = "stopped"
    STATUS_CHOICES = [
        (STATUS_RUNNING, "Running"),
        (STATUS_STOPPING, "Stopping"),
        (STATUS_STOPPED, "Stopped"),
    ]

    bot_type = models.CharField(max_length=20, choices=BOT_TYPE_CHOICES)
    bot_id = models.CharField(max_length=64, db_index=True)
    status = models.CharField(
        max_length=12, choices=STATUS_CHOICES, default=STATUS_RUNNING, db_index=True
    )
    # Opaque engine snapshot (current side, reason, grid maps, counters, …).
    # Shape is owned by apps/trading/state.py + snapshot/restore (Phase 3).
    state = models.JSONField(default=dict, blank=True)
    # Which worker/engine instance owns this row (double-run guard).
    worker = models.CharField(max_length=255, blank=True, default="")
    heartbeat_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "trading_bot_runtime_states"
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["bot_type", "bot_id"], name="uniq_trading_bot_runtime_state"
            ),
        ]

    def __str__(self):
        return f"{self.bot_type}:{self.bot_id} [{self.status}]"
