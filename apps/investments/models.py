"""
Investment App Models for Torgovo Crypto Trading Platform

Portfolio/display models — tracks orders, positions, balances, exchange rates,
and exchange health for the user-facing investments API.
Bot models (GridBot, MartingaleBot, SignalBot) belong in apps.bots.
"""

from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.exchanges.models import Exchange, TradingPair
from core.models import TimeStampedModel

# ──────────────────────────────────────────────────────────────────────────────
# ExchangeStatus — exchange health display
# ──────────────────────────────────────────────────────────────────────────────


class ExchangeStatus(TimeStampedModel):
    """Track exchange API status and health (displayed in investments UI)."""

    exchange_name = models.CharField(max_length=20)
    status = models.CharField(
        max_length=20,
        choices=[
            ("online", "Online"),
            ("degraded", "Degraded Performance"),
            ("offline", "Offline"),
            ("maintenance", "Maintenance"),
        ],
        default="online",
    )
    response_time_ms = models.IntegerField(null=True, blank=True)
    last_check = models.DateTimeField(auto_now=True)
    error_message = models.TextField(blank=True)
    api_limits = models.JSONField(default=dict, help_text="Current API usage and limits")

    class Meta:
        db_table = "investments_exchange_status"
        indexes = [
            models.Index(fields=["exchange_name"]),
            models.Index(fields=["status"]),
            models.Index(fields=["last_check"]),
        ]

    def __str__(self):
        return f"{self.exchange_name} - {self.status}"


# ──────────────────────────────────────────────────────────────────────────────
# SupportedBlockchain — deposit blockchain options
# ──────────────────────────────────────────────────────────────────────────────


class SupportedBlockchain(TimeStampedModel):
    """
    Supported blockchains for cryptocurrency deposits.
    Used by the investments UI to show users which chains are accepted.
    """

    BLOCKCHAIN_CHOICES = [
        ("BEP20", "Binance Smart Chain"),
        ("ERC20", "Ethereum"),
        ("TRC20", "TRON"),
        ("SOL", "Solana"),
        ("APTOS", "Aptos"),
        ("POLYGON", "Polygon"),
        ("ARBITRUM", "Arbitrum"),
        ("OPTIMISM", "Optimism"),
        ("AVALANCHE", "Avalanche"),
        ("FANTOM", "Fantom"),
        ("Bitcoin", "Bitcoin Network"),
    ]

    name = models.CharField(max_length=50, unique=True)
    blockchain_code = models.CharField(max_length=20, choices=BLOCKCHAIN_CHOICES, unique=True)
    native_coin = models.CharField(max_length=10)
    explorer_url = models.URLField(blank=True)
    confirmation_blocks = models.PositiveIntegerField(default=12)
    transaction_fee_type = models.CharField(
        max_length=20,
        choices=[
            ("fixed", "Fixed Fee"),
            ("percentage", "Percentage"),
            ("dynamic", "Dynamic"),
        ],
        default="dynamic",
    )
    average_fee = models.DecimalField(max_digits=10, decimal_places=8, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "investments_supported_blockchains"
        indexes = [
            models.Index(fields=["blockchain_code"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.blockchain_code})"


# ──────────────────────────────────────────────────────────────────────────────
# ExchangeRate — rates for portfolio valuation
# ──────────────────────────────────────────────────────────────────────────────


class ExchangeRate(TimeStampedModel):
    """
    Exchange rates between different cryptocurrencies.
    Used by the investments UI for portfolio valuation display.
    """

    from_currency = models.CharField(max_length=10)
    to_currency = models.CharField(max_length=10)
    rate = models.DecimalField(max_digits=20, decimal_places=8)
    exchange_name = models.CharField(max_length=20, default="aggregated")
    source = models.CharField(max_length=50, default="api")
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "investments_exchange_rates"
        unique_together = ["from_currency", "to_currency", "exchange_name"]
        indexes = [
            models.Index(fields=["from_currency", "to_currency"]),
            models.Index(fields=["timestamp"]),
        ]

    def __str__(self):
        return f"1 {self.from_currency} = {self.rate} {self.to_currency}"


# Bot models (GridBot, MartingaleBot, WebhookAlertBot) belong in apps.bots
# where the real trading execution lives. This app only keeps display/portfolio models.


# ──────────────────────────────────────────────────────────────────────────────
# Order
# ──────────────────────────────────────────────────────────────────────────────


class Order(TimeStampedModel):
    """Trade order execution and history."""

    SIDE_CHOICES = [("buy", "Buy"), ("sell", "Sell")]
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("filled", "Filled"),
        ("partially_filled", "Partially Filled"),
        ("cancelled", "Cancelled"),
        ("failed", "Failed"),
    ]
    ORDER_TYPE_CHOICES = [
        ("market", "Market"),
        ("limit", "Limit"),
        ("stop_limit", "Stop Limit"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="investment_orders",
    )
    exchange = models.ForeignKey(
        Exchange, on_delete=models.CASCADE, related_name="investment_orders"
    )
    trading_pair = models.ForeignKey(
        TradingPair, on_delete=models.CASCADE, related_name="investment_orders"
    )

    order_type = models.CharField(max_length=20, choices=ORDER_TYPE_CHOICES)
    side = models.CharField(max_length=5, choices=SIDE_CHOICES)

    quantity = models.DecimalField(max_digits=20, decimal_places=8)
    price = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal("0"))
    filled_quantity = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal("0"))
    average_price = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal("0"))

    take_profit = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    stop_loss = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    profit_loss = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal("0"))
    description = models.TextField(blank=True, default="")

    executed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "investments_order"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.side} {self.quantity} @ {self.price}"


# ──────────────────────────────────────────────────────────────────────────────
# Position
# ──────────────────────────────────────────────────────────────────────────────


class Position(TimeStampedModel):
    """Represents an open trading position."""

    SIDE_CHOICES = [("long", "Long"), ("short", "Short")]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="investment_positions",
    )
    exchange = models.ForeignKey(
        Exchange, on_delete=models.CASCADE, related_name="investment_positions"
    )
    trading_pair = models.ForeignKey(
        TradingPair, on_delete=models.CASCADE, related_name="investment_positions"
    )

    side = models.CharField(max_length=5, choices=SIDE_CHOICES, default="long")
    entry_price = models.DecimalField(max_digits=20, decimal_places=8)
    current_price = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal("0"))
    quantity = models.DecimalField(max_digits=20, decimal_places=8)
    leverage = models.PositiveIntegerField(default=1)

    unrealized_pnl = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal("0"))
    unrealized_pnl_percent = models.DecimalField(
        max_digits=10, decimal_places=4, default=Decimal("0")
    )
    liquidation_price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)

    opened_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "investments_position"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.side} {self.quantity} @ {self.entry_price}"


# ──────────────────────────────────────────────────────────────────────────────
# TechnicalIndicator
# ──────────────────────────────────────────────────────────────────────────────


class TechnicalIndicator(TimeStampedModel):
    """Stores technical indicator data received from webhooks."""

    INDICATOR_CHOICES = [
        ("EMA", "Exponential Moving Average"),
        ("RSI", "Relative Strength Index"),
        ("MACD", "MACD"),
        ("BB", "Bollinger Bands"),
    ]

    indicator_type = models.CharField(max_length=10, choices=INDICATOR_CHOICES)
    trading_pair = models.ForeignKey(
        TradingPair, on_delete=models.CASCADE, related_name="investment_indicators"
    )
    exchange = models.ForeignKey(
        Exchange, on_delete=models.CASCADE, related_name="investment_indicators"
    )
    values = models.JSONField(default=dict)
    color = models.CharField(max_length=20, blank=True, null=True)
    prev_color = models.CharField(max_length=20, blank=True, null=True)
    triggered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "investments_technical_indicator"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["trading_pair", "indicator_type", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.indicator_type} — {self.trading_pair}"


# ──────────────────────────────────────────────────────────────────────────────
# UserBalance
# ──────────────────────────────────────────────────────────────────────────────


class InvestmentBalance(TimeStampedModel):
    """Tracks user wallet balances per exchange and currency."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="investment_balances",
    )
    exchange = models.ForeignKey(
        Exchange, on_delete=models.CASCADE, related_name="investment_balances"
    )
    currency = models.CharField(max_length=10, default="USDT")
    available = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal("0"))
    locked = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal("0"))
    total = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal("0"))

    class Meta:
        db_table = "investments_user_balance"
        unique_together = ["user", "exchange", "currency"]

    def __str__(self):
        return f"{self.user} — {self.currency}: {self.total}"
