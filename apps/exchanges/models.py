"""
Exchange integration models for Torgovo Crypto Trading Platform

Canonical location for trading data models: Exchange definitions,
ExchangeCredentials (encrypted API keys), and TradingPair definitions.
"""

from decimal import Decimal

from django.conf import settings
from django.db import models

from core.models import SoftDeleteModel, TimeStampedModel
from core.utils import decrypt_api_key, encrypt_api_key, looks_encrypted


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
        default=list, help_text="List of supported features (spot, futures, etc.)"
    )
    rate_limit_per_minute = models.PositiveIntegerField(default=1200)
    fee_rates = models.JSONField(default=dict, help_text="Standard fee rates")

    class Meta:
        db_table = "exchanges_exchange"
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return self.display_name


class ExchangeCredentials(SoftDeleteModel):
    """
    Encrypted storage for exchange API credentials.
    """

    EXCHANGE_CHOICES = [
        ("binance", "Binance"),
        ("bybit", "Bybit"),
        ("okx", "OKX"),
        ("mexc", "MEXC"),
        ("alpaca", "Alpaca"),
        ("coinbase", "Coinbase"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="exchanges_credentials",
    )
    exchange_name = models.CharField(max_length=20, choices=EXCHANGE_CHOICES)
    api_key = models.TextField(help_text="Encrypted API key")
    secret_key = models.TextField(help_text="Encrypted secret key")
    passphrase = models.TextField(
        blank=True, null=True, help_text="Encrypted passphrase (required for some exchanges)"
    )
    is_active = models.BooleanField(default=True)
    is_testnet = models.BooleanField(default=True, help_text="Use testnet/sandbox mode")
    is_demo = models.BooleanField(
        default=False,
        help_text="Use demo trading (simulated funds, real API keys). "
        "Distinct from testnet which uses separate testnet API keys.",
    )
    permissions = models.JSONField(
        default=dict, help_text="Trading permissions (spot, futures, margin, etc.)"
    )
    last_verified = models.DateTimeField(null=True, blank=True)
    verification_status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("verified", "Verified"),
            ("failed", "Failed"),
        ],
        default="pending",
    )
    trading_enabled = models.BooleanField(default=True)
    withdrawal_enabled = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "exchanges_credentials"
        unique_together = ["user", "exchange_name"]
        indexes = [
            models.Index(fields=["user", "exchange_name"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["verification_status"]),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.exchange_name}"

    def save(self, *args, **kwargs):
        """
        Encrypt credentials on first save AND when they have been replaced.
        """
        if not looks_encrypted(self.api_key):
            self.api_key = encrypt_api_key(self.api_key)
        if not looks_encrypted(self.secret_key):
            self.secret_key = encrypt_api_key(self.secret_key)
        if self.passphrase and not looks_encrypted(self.passphrase):
            self.passphrase = encrypt_api_key(self.passphrase)
        super().save(*args, **kwargs)

    def get_decrypted_credentials(self):
        """Get decrypted credentials for exchange API usage."""
        return {
            "api_key": decrypt_api_key(self.api_key),
            "secret_key": decrypt_api_key(self.secret_key),
            "passphrase": decrypt_api_key(self.passphrase) if self.passphrase else None,
            "is_testnet": self.is_testnet,
            "is_demo": self.is_demo,
        }

    def has_permission(self, permission):
        """Check if credentials have specific trading permission."""
        return self.permissions.get(permission, False)


class TradingPair(TimeStampedModel):
    """
    Available trading pairs on each exchange.
    """

    exchange_name = models.CharField(max_length=20)
    symbol = models.CharField(max_length=20)
    base_asset = models.CharField(max_length=10)
    quote_asset = models.CharField(max_length=10)
    is_active = models.BooleanField(default=True)
    min_order_size = models.DecimalField(
        max_digits=20, decimal_places=8, default=Decimal("0.00000001")
    )
    max_order_size = models.DecimalField(
        max_digits=20, decimal_places=8, default=Decimal("1000000")
    )
    price_precision = models.PositiveIntegerField(default=8)
    quantity_precision = models.PositiveIntegerField(default=8)
    maker_fee = models.DecimalField(max_digits=6, decimal_places=4, default=Decimal("0.0010"))
    taker_fee = models.DecimalField(max_digits=6, decimal_places=4, default=Decimal("0.0010"))
    min_notional = models.DecimalField(max_digits=20, decimal_places=8, default=10.0)

    class Meta:
        db_table = "exchanges_trading_pairs"
        unique_together = ["exchange_name", "symbol"]
        indexes = [
            models.Index(fields=["exchange_name", "symbol"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["base_asset", "quote_asset"]),
        ]

    def __str__(self):
        return f"{self.symbol} on {self.exchange_name}"
