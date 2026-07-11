"""
Investment App Models for Torgovo Crypto Trading Platform

Self-contained model definitions for the investments API layer.
These models have the exact field shapes that the investments serializers
and views expect.  They live in their own DB tables (prefixed investments_)
and do NOT interfere with models in apps.bots or apps.exchanges.
"""
import uuid
from decimal import Decimal
from django.db import models
from django.conf import settings
from core.models import TimeStampedModel, SoftDeleteModel


# ──────────────────────────────────────────────────────────────────────────────
# Exchange
# ──────────────────────────────────────────────────────────────────────────────

class Exchange(TimeStampedModel):
    """Supported cryptocurrency exchange."""
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('maintenance', 'Maintenance'),
        ('inactive', 'Inactive'),
    ]

    name = models.CharField(max_length=20, unique=True)
    display_name = models.CharField(max_length=50)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    api_base_url = models.URLField(blank=True)
    websocket_url = models.URLField(blank=True)
    supported_features = models.JSONField(default=list)
    requires_passphrase = models.BooleanField(default=False)

    class Meta:
        db_table = 'investments_exchange'

    def __str__(self):
        return self.display_name


# ──────────────────────────────────────────────────────────────────────────────
# TradingPair
# ──────────────────────────────────────────────────────────────────────────────

class TradingPair(TimeStampedModel):
    """Available trading pairs on each exchange."""
    exchange = models.ForeignKey(Exchange, on_delete=models.CASCADE, related_name='trading_pairs')
    symbol = models.CharField(max_length=20)
    base_asset = models.CharField(max_length=10)
    quote_asset = models.CharField(max_length=10)
    is_active = models.BooleanField(default=True)
    current_price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    price_change_24h = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal('0'))
    price_change_percent_24h = models.DecimalField(max_digits=10, decimal_places=4, default=Decimal('0'))
    volume_24h = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal('0'))
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'investments_trading_pair'
        unique_together = ['exchange', 'symbol']

    def __str__(self):
        return f"{self.symbol} on {self.exchange.name}"


# ──────────────────────────────────────────────────────────────────────────────
# ExchangeCredential
# ──────────────────────────────────────────────────────────────────────────────

class ExchangeCredential(SoftDeleteModel):
    """User API credentials for an exchange."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='investment_credentials',
    )
    exchange = models.ForeignKey(
        Exchange, on_delete=models.CASCADE,
        related_name='investment_credentials',
    )
    api_key = models.TextField(help_text="Encrypted API key")
    secret_key = models.TextField(help_text="Encrypted secret key")
    passphrase = models.TextField(blank=True, null=True)
    is_testnet = models.BooleanField(default=True)
    is_connected = models.BooleanField(default=False)
    last_connected = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'investments_exchange_credential'
        unique_together = ['user', 'exchange']

    def __str__(self):
        return f"{self.user} — {self.exchange.name}"


# ──────────────────────────────────────────────────────────────────────────────
# BotBase — common fields for all bot types
# ──────────────────────────────────────────────────────────────────────────────

class BotBase(SoftDeleteModel):
    """Common fields shared by all trading bot types."""
    BOT_STATUS_CHOICES = [
        ('idle', 'Idle'),
        ('running', 'Running'),
        ('paused', 'Paused'),
        ('stopped', 'Stopped'),
        ('error', 'Error'),
    ]
    CATEGORY_CHOICES = [
        ('webhook', 'Webhook Alert'),
        ('grid', 'Grid'),
        ('martingale', 'Martingale'),
        ('quantum_ai', 'Quantum AI'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='%(class)s_bots',
    )
    bot_name = models.CharField(max_length=100)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='webhook')
    exchange = models.ForeignKey(
        Exchange, on_delete=models.CASCADE, related_name='%(class)s_bots',
    )
    trading_pair = models.ForeignKey(
        TradingPair, on_delete=models.CASCADE, related_name='%(class)s_bots',
    )

    status = models.CharField(max_length=20, choices=BOT_STATUS_CHOICES, default='idle')
    is_active = models.BooleanField(default=True)

    # Performance
    total_trades = models.PositiveIntegerField(default=0)
    successful_trades = models.PositiveIntegerField(default=0)
    total_profit_loss = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal('0'))
    total_volume = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal('0'))

    # Risk parameters
    take_profit_percent = models.DecimalField(max_digits=8, decimal_places=4, default=Decimal('2.0'))
    stop_loss_percent = models.DecimalField(max_digits=8, decimal_places=4, default=Decimal('1.0'))
    max_position_size = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal('1000'))

    # Timestamps
    started_at = models.DateTimeField(null=True, blank=True)
    stopped_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'investments_bot_base'

    def __str__(self):
        return f"{self.bot_name} ({self.category})"


# ──────────────────────────────────────────────────────────────────────────────
# WebhookAlertBot
# ──────────────────────────────────────────────────────────────────────────────

class WebhookAlertBot(BotBase):
    """A bot triggered by TradingView webhook alerts."""
    webhook_id = models.UUIDField(default=uuid.uuid4, unique=True)
    webhook_url = models.URLField(blank=True)
    secret_key = models.CharField(max_length=64, blank=True)
    default_amount = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal('10'))
    last_triggered = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'investments_webhook_alert_bot'

    def __str__(self):
        return f"Webhook Bot: {self.bot_name}"


# ──────────────────────────────────────────────────────────────────────────────
# GridBot
# ──────────────────────────────────────────────────────────────────────────────

class GridBot(BotBase):
    """Grid trading bot."""
    base_amount = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal('100'))
    favor_levels = models.PositiveIntegerField(default=5)
    against_levels = models.PositiveIntegerField(default=5)
    level_spacing_percent = models.DecimalField(max_digits=8, decimal_places=4, default=Decimal('1.0'))
    current_grid_level = models.IntegerField(default=0)
    total_invested = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal('0'))

    class Meta:
        db_table = 'investments_grid_bot'

    def __str__(self):
        return f"Grid Bot: {self.bot_name}"


# ──────────────────────────────────────────────────────────────────────────────
# MartingaleBot
# ──────────────────────────────────────────────────────────────────────────────

class MartingaleBot(BotBase):
    """Martingale trading bot."""
    base_amount = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal('100'))
    favor_levels = models.PositiveIntegerField(default=5)
    against_levels = models.PositiveIntegerField(default=5)
    level_spacing_percent = models.DecimalField(max_digits=8, decimal_places=4, default=Decimal('1.0'))
    multiplier_factor = models.DecimalField(max_digits=8, decimal_places=4, default=Decimal('2.0'))
    current_level = models.IntegerField(default=0)
    consecutive_losses = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'investments_martingale_bot'

    def __str__(self):
        return f"Martingale Bot: {self.bot_name}"


# ──────────────────────────────────────────────────────────────────────────────
# QuantumAIBot
# ──────────────────────────────────────────────────────────────────────────────

class QuantumAIBot(BotBase):
    """Quantum AI trading bot."""
    RISK_LEVEL_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ]
    COMPOUND_FREQUENCY_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
    ]

    auto_compound = models.BooleanField(default=False)
    compound_frequency = models.CharField(
        max_length=20, choices=COMPOUND_FREQUENCY_CHOICES, default='weekly',
    )
    risk_level = models.CharField(max_length=10, choices=RISK_LEVEL_CHOICES, default='medium')
    blockchain_addresses = models.JSONField(default=dict, blank=True)
    last_compound = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'investments_quantum_ai_bot'

    def __str__(self):
        return f"Quantum AI Bot: {self.bot_name}"


# ──────────────────────────────────────────────────────────────────────────────
# Order
# ──────────────────────────────────────────────────────────────────────────────

class Order(TimeStampedModel):
    """Trade order execution and history."""
    SIDE_CHOICES = [('buy', 'Buy'), ('sell', 'Sell')]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('filled', 'Filled'),
        ('partially_filled', 'Partially Filled'),
        ('cancelled', 'Cancelled'),
        ('failed', 'Failed'),
    ]
    ORDER_TYPE_CHOICES = [
        ('market', 'Market'),
        ('limit', 'Limit'),
        ('stop_limit', 'Stop Limit'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='investment_orders',
    )
    bot = models.ForeignKey(
        BotBase, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='orders',
    )
    exchange = models.ForeignKey(Exchange, on_delete=models.CASCADE, related_name='investment_orders')
    trading_pair = models.ForeignKey(TradingPair, on_delete=models.CASCADE, related_name='investment_orders')

    order_type = models.CharField(max_length=20, choices=ORDER_TYPE_CHOICES)
    side = models.CharField(max_length=5, choices=SIDE_CHOICES)

    quantity = models.DecimalField(max_digits=20, decimal_places=8)
    price = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal('0'))
    filled_quantity = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal('0'))
    average_price = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal('0'))

    take_profit = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    stop_loss = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    profit_loss = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal('0'))
    description = models.TextField(blank=True, default='')

    executed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'investments_order'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.side} {self.quantity} @ {self.price}"


# ──────────────────────────────────────────────────────────────────────────────
# Position
# ──────────────────────────────────────────────────────────────────────────────

class Position(TimeStampedModel):
    """Represents an open trading position."""
    SIDE_CHOICES = [('long', 'Long'), ('short', 'Short')]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='investment_positions',
    )
    exchange = models.ForeignKey(Exchange, on_delete=models.CASCADE, related_name='investment_positions')
    trading_pair = models.ForeignKey(TradingPair, on_delete=models.CASCADE, related_name='investment_positions')
    bot = models.ForeignKey(BotBase, on_delete=models.SET_NULL, null=True, blank=True, related_name='positions')

    side = models.CharField(max_length=5, choices=SIDE_CHOICES, default='long')
    entry_price = models.DecimalField(max_digits=20, decimal_places=8)
    current_price = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal('0'))
    quantity = models.DecimalField(max_digits=20, decimal_places=8)
    leverage = models.PositiveIntegerField(default=1)

    unrealized_pnl = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal('0'))
    unrealized_pnl_percent = models.DecimalField(max_digits=10, decimal_places=4, default=Decimal('0'))
    liquidation_price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)

    opened_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'investments_position'

    def __str__(self):
        return f"{self.side} {self.quantity} @ {self.entry_price}"


# ──────────────────────────────────────────────────────────────────────────────
# TechnicalIndicator
# ──────────────────────────────────────────────────────────────────────────────

class TechnicalIndicator(TimeStampedModel):
    """Stores technical indicator data received from webhooks."""
    INDICATOR_CHOICES = [
        ('EMA', 'Exponential Moving Average'),
        ('RSI', 'Relative Strength Index'),
        ('MACD', 'MACD'),
        ('BB', 'Bollinger Bands'),
    ]

    indicator_type = models.CharField(max_length=10, choices=INDICATOR_CHOICES)
    trading_pair = models.ForeignKey(TradingPair, on_delete=models.CASCADE, related_name='investment_indicators')
    exchange = models.ForeignKey(Exchange, on_delete=models.CASCADE, related_name='investment_indicators')
    values = models.JSONField(default=dict)
    color = models.CharField(max_length=20, blank=True, null=True)
    prev_color = models.CharField(max_length=20, blank=True, null=True)
    triggered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'investments_technical_indicator'

    def __str__(self):
        return f"{self.indicator_type} — {self.trading_pair}"


# ──────────────────────────────────────────────────────────────────────────────
# UserBalance
# ──────────────────────────────────────────────────────────────────────────────

class UserBalance(TimeStampedModel):
    """Tracks user wallet balances per exchange and currency."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='investment_balances',
    )
    exchange = models.ForeignKey(Exchange, on_delete=models.CASCADE, related_name='investment_balances')
    currency = models.CharField(max_length=10, default='USDT')
    available = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal('0'))
    locked = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal('0'))
    total = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal('0'))

    class Meta:
        db_table = 'investments_user_balance'
        unique_together = ['user', 'exchange', 'currency']

    def __str__(self):
        return f"{self.user} — {self.currency}: {self.total}"
