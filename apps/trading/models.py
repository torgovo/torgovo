"""
Trading models for Torgovo Crypto Trading Platform

This module contains all database models related to trading functionality:
- Exchange configuration and credentials
- Trading pairs and exchange status
- Bot configurations
"""
import uuid
from django.db import models
from django.conf import settings
from core.models import TimeStampedModel, SoftDeleteModel
from core.utils import encrypt_api_key, decrypt_api_key

# Canonical ExchangeCredentials lives in apps.exchanges — import here for
# backward-compat so apps/trading/ views/serializers/admin still resolve it.
from apps.exchanges.models import ExchangeCredentials  # noqa: F401


# =============================================================================
# EXCHANGE MODELS
# =============================================================================

class Exchange(TimeStampedModel):
    """
    Configuration for supported cryptocurrency exchanges.
    """
    name = models.CharField(max_length=20, unique=True)
    display_name = models.CharField(max_length=50)
    api_base_url = models.URLField(blank=True)
    websocket_url = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)
    supports_testnet = models.BooleanField(default=True)
    supported_features = models.JSONField(
        default=list,
        help_text="List of supported features (spot, futures, etc.)"
    )
    rate_limit_per_minute = models.PositiveIntegerField(default=1200)
    fee_rates = models.JSONField(default=dict, help_text="Standard fee rates")

    class Meta:
        db_table = 'trading_exchange'
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return self.display_name


# ExchangeCredentials removed from this module — use apps.exchanges.models.ExchangeCredentials
# (imported above for backward compatibility)


class ExchangeStatus(TimeStampedModel):
    """
    Track exchange API status and health.
    """
    exchange_name = models.CharField(max_length=20)
    status = models.CharField(
        max_length=20,
        choices=[
            ('online', 'Online'),
            ('degraded', 'Degraded Performance'),
            ('offline', 'Offline'),
            ('maintenance', 'Maintenance'),
        ],
        default='online'
    )
    response_time_ms = models.IntegerField(null=True, blank=True)
    last_check = models.DateTimeField(auto_now=True)
    error_message = models.TextField(blank=True)
    api_limits = models.JSONField(default=dict, help_text="Current API usage and limits")

    class Meta:
        db_table = 'trading_exchange_status'
        indexes = [
            models.Index(fields=['exchange_name']),
            models.Index(fields=['status']),
            models.Index(fields=['last_check']),
        ]

    def __str__(self):
        return f"{self.exchange_name} - {self.status}"


class TradingPair(TimeStampedModel):
    """
    Available trading pairs on each exchange.
    """
    exchange_name = models.CharField(max_length=20)
    symbol = models.CharField(max_length=20)
    base_asset = models.CharField(max_length=10)
    quote_asset = models.CharField(max_length=10)
    is_active = models.BooleanField(default=True)
    min_order_size = models.DecimalField(max_digits=20, decimal_places=8, default=0.00000001)
    max_order_size = models.DecimalField(max_digits=20, decimal_places=8, default=1000000)
    price_precision = models.PositiveIntegerField(default=8)
    quantity_precision = models.PositiveIntegerField(default=8)
    maker_fee = models.DecimalField(max_digits=6, decimal_places=4, default=0.0010)
    taker_fee = models.DecimalField(max_digits=6, decimal_places=4, default=0.0010)
    min_notional = models.DecimalField(max_digits=20, decimal_places=8, default=10.0)

    class Meta:
        db_table = 'trading_pairs'
        unique_together = ['exchange_name', 'symbol']
        indexes = [
            models.Index(fields=['exchange_name', 'symbol']),
            models.Index(fields=['is_active']),
            models.Index(fields=['base_asset', 'quote_asset']),
        ]

    def __str__(self):
        return f"{self.symbol} on {self.exchange_name}"


class SupportedBlockchain(TimeStampedModel):
    """
    Supported blockchains for cryptocurrency deposits.
    """
    BLOCKCHAIN_CHOICES = [
        ('BEP20', 'Binance Smart Chain'),
        ('ERC20', 'Ethereum'),
        ('TRC20', 'TRON'),
        ('SOL', 'Solana'),
        ('APTOS', 'Aptos'),
        ('POLYGON', 'Polygon'),
        ('ARBITRUM', 'Arbitrum'),
        ('OPTIMISM', 'Optimism'),
        ('AVALANCHE', 'Avalanche'),
        ('FANTOM', 'Fantom'),
        ('Bitcoin', 'Bitcoin Network'),
    ]

    name = models.CharField(max_length=50, unique=True)
    blockchain_code = models.CharField(max_length=20, choices=BLOCKCHAIN_CHOICES, unique=True)
    native_coin = models.CharField(max_length=10)
    explorer_url = models.URLField(blank=True)
    confirmation_blocks = models.PositiveIntegerField(default=12)
    transaction_fee_type = models.CharField(
        max_length=20,
        choices=[
            ('fixed', 'Fixed Fee'),
            ('percentage', 'Percentage'),
            ('dynamic', 'Dynamic'),
        ],
        default='dynamic'
    )
    average_fee = models.DecimalField(max_digits=10, decimal_places=8, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'trading_supported_blockchains'
        indexes = [
            models.Index(fields=['blockchain_code']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.name} ({self.blockchain_code})"


class ExchangeRate(TimeStampedModel):
    """
    Exchange rates between different cryptocurrencies.
    """
    from_currency = models.CharField(max_length=10)
    to_currency = models.CharField(max_length=10)
    rate = models.DecimalField(max_digits=20, decimal_places=8)
    exchange_name = models.CharField(max_length=20, default='aggregated')
    source = models.CharField(max_length=50, default='api')
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'trading_exchange_rates'
        unique_together = ['from_currency', 'to_currency', 'exchange_name']
        indexes = [
            models.Index(fields=['from_currency', 'to_currency']),
            models.Index(fields=['timestamp']),
        ]

    def __str__(self):
        return f"1 {self.from_currency} = {self.rate} {self.to_currency}"



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
        ('quantum_ai', 'Quantum AI'),
        ('grid', 'Grid Trading'),
        ('martingale', 'Martingale'),
        ('signal', 'Signal Bot'),
    ]
    
    name = models.CharField(max_length=100, help_text="e.g., 'Quantum AI Aggressive'")
    strategy = models.CharField(max_length=20, choices=STRATEGY_CHOICES)
    default_parameters = models.JSONField(default=dict, help_text="Default strategy parameters")
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'trading_strategy_configs'
        indexes = [
            models.Index(fields=['strategy', 'is_active']),
        ]

    def __str__(self):
        return f"{self.name} - {self.get_strategy_display()}"