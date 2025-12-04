"""
Exchange integration models for Torgovo Crypto Trading Platform
"""
import uuid
from django.db import models
from django.conf import settings
from django.core.validators import RegexValidator
from core.models import TimeStampedModel, SoftDeleteModel
from core.utils import encrypt_api_key, decrypt_api_key



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
    supported_features = models.JSONField(default=list, help_text="List of supported features (spot, futures, etc.)")
    rate_limit_per_minute = models.PositiveIntegerField(default=1200)
    fee_rates = models.JSONField(default=dict, help_text="Standard fee rates")

    class Meta:
        db_table = 'exchanges_exchange'
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return self.display_name


class ExchangeCredentials(SoftDeleteModel):
    """
    Encrypted storage for exchange API credentials.
    """
    EXCHANGE_CHOICES = [
        ('binance', 'Binance'),
        ('bybit', 'Bybit'),
        ('okx', 'OKX'),
        ('mexc', 'MEXC'),
        ('alpaca', 'Alpaca'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='exchange_credentials'
    )
    exchange_name = models.CharField(max_length=20, choices=EXCHANGE_CHOICES)
    api_key = models.TextField(help_text="Encrypted API key")
    secret_key = models.TextField(help_text="Encrypted secret key")
    passphrase = models.TextField(
        blank=True,
        null=True,
        help_text="Encrypted passphrase (required for some exchanges)"
    )
    is_active = models.BooleanField(default=True)
    is_testnet = models.BooleanField(default=True, help_text="Use testnet/sandbox mode")
    permissions = models.JSONField(
        default=dict,
        help_text="Trading permissions (spot, futures, margin, etc.)"
    )
    last_verified = models.DateTimeField(null=True, blank=True)
    verification_status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('verified', 'Verified'),
            ('failed', 'Failed'),
        ],
        default='pending'
    )
    trading_enabled = models.BooleanField(default=True)
    withdrawal_enabled = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'exchanges_credentials'
        unique_together = ['user', 'exchange_name']
        indexes = [
            models.Index(fields=['user', 'exchange_name']),
            models.Index(fields=['is_active']),
            models.Index(fields=['verification_status']),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.exchange_name}"

    def save(self, *args, **kwargs):
        """Encrypt credentials before saving."""
        if not self.pk:  # Only encrypt on creation
            self.api_key = encrypt_api_key(self.api_key)
            self.secret_key = encrypt_api_key(self.secret_key)
            if self.passphrase:
                self.passphrase = encrypt_api_key(self.passphrase)
        super().save(*args, **kwargs)

    def get_decrypted_credentials(self):
        """Get decrypted credentials for exchange API usage."""
        return {
            'api_key': decrypt_api_key(self.api_key),
            'secret_key': decrypt_api_key(self.secret_key),
            'passphrase': decrypt_api_key(self.passphrase) if self.passphrase else None,
            'is_testnet': self.is_testnet,
        }

    def has_permission(self, permission):
        """Check if credentials have specific trading permission."""
        return self.permissions.get(permission, False)


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
        db_table = 'exchanges_status'
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
        db_table = 'exchanges_trading_pairs'
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
        db_table = 'exchanges_supported_blockchains'
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
        db_table = 'exchanges_rates'
        unique_together = ['from_currency', 'to_currency', 'exchange_name']
        indexes = [
            models.Index(fields=['from_currency', 'to_currency']),
            models.Index(fields=['timestamp']),
        ]

    def __str__(self):
        return f"1 {self.from_currency} = {self.rate} {self.to_currency}"