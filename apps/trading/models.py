"""
Complete Trading Models for Torgovo Platform

Includes:
- Exchange management
- All bot types (Custom, Grid, Martingale, Quantum AI)
- Investment & fund management
- Order & indicator tracking
- Telegram signal subscriptions
"""

import uuid
import pytz
from decimal import Decimal
from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone

from config import settings
from core.models import TimeStampedModel, SoftDeleteModel
from core.utils import encrypt_api_key, decrypt_api_key, generate_secret_key

User = get_user_user_model()


# =============================================================================
# EXCHANGE MODELS (Keep from trading app)
# =============================================================================

class Exchange(TimeStampedModel):
    """Configuration for supported cryptocurrency exchanges."""
    name = models.CharField(max_length=20, unique=True)
    display_name = models.CharField(max_length=50)
    api_base_url = models.URLField(blank=True)
    websocket_url = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)
    supports_testnet = models.BooleanField(default=True)
    supported_features = models.JSONField(default=list)
    rate_limit_per_minute = models.PositiveIntegerField(default=1200)
    fee_rates = models.JSONField(default=dict)

    class Meta:
        db_table = 'trading_exchange'
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return self.display_name


class ExchangeCredentials(SoftDeleteModel):
    """Encrypted storage for exchange API credentials."""
    EXCHANGE_CHOICES = [
        ('binance', 'Binance'),
        ('bybit', 'Bybit'),
        ('okx', 'OKX'),
        ('mexc', 'MEXC'),
        ('alpaca', 'Alpaca'),
        ('coinbase', 'Coinbase'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='trading_credentials'
    )
    nickname = models.CharField(max_length=100, default="Default Account")
    exchange_name = models.CharField(max_length=20, choices=EXCHANGE_CHOICES)
    api_key = models.TextField(help_text="Encrypted API key")
    secret_key = models.TextField(help_text="Encrypted secret key")
    passphrase = models.TextField(blank=True, null=True, help_text="Encrypted passphrase")
    is_active = models.BooleanField(default=True)
    is_testnet = models.BooleanField(default=True, help_text="Use testnet/sandbox mode")
    permissions = models.JSONField(default=dict)
    last_verified = models.DateTimeField(null=True, blank=True)
    verification_status = models.CharField(
        max_length=20,
        choices=[('pending', 'Pending'), ('verified', 'Verified'), ('failed', 'Failed')],
        default='pending'
    )
    trading_enabled = models.BooleanField(default=True)
    withdrawal_enabled = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'trading_credentials'
        unique_together = ['user', 'exchange_name']
        indexes = [
            models.Index(fields=['user', 'exchange_name']),
            models.Index(fields=['is_active']),
            models.Index(fields=['verification_status']),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.exchange_name}" if self.user else f"{self.exchange_name}"

    def save(self, *args, **kwargs):
        if not self.pk:
            self.api_key = encrypt_api_key(self.api_key)
            self.secret_key = encrypt_api_key(self.secret_key)
            if self.passphrase:
                self.passphrase = encrypt_api_key(self.passphrase)
        super().save(*args, **kwargs)

    def get_decrypted_credentials(self):
        return {
            'api_key': decrypt_api_key(self.api_key),
            'secret_key': decrypt_api_key(self.secret_key),
            'passphrase': decrypt_api_key(self.passphrase) if self.passphrase else None,
            'is_testnet': self.is_testnet,
        }

    def has_permission(self, permission):
        return self.permissions.get(permission, False)


class ExchangeRate(TimeStampedModel):
    """Exchange rates between different cryptocurrencies."""
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
# STRATEGY MODELS (Keep from trading app)
# =============================================================================

class StrategyConfig(SoftDeleteModel):
    """Strategy configuration templates."""
    STRATEGY_CHOICES = [
        ('quantum_ai', 'Quantum AI'),
        ('grid_trading', 'Grid Trading'),
        ('martingale', 'Martingale'),
        ('webhook_alerts', 'Webhook Alerts'),
    ]

    name = models.CharField(max_length=100, help_text="e.g., 'Quantum AI Aggressive'")
    strategy = models.CharField(max_length=20, choices=STRATEGY_CHOICES)
    default_parameters = models.JSONField(default=dict, help_text="Default strategy parameters")
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'trading_strategy_configs'
        indexes = [
            models.Index(fields=['strategy']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.name} - {self.get_strategy_display()}"


# =============================================================================
# ALL BOT MODELS (Merge from bots app)
# =============================================================================

# ==================== CUSTOM BOT (TradingView Webhook) ====================

class CustomBot(SoftDeleteModel):
    """Custom Trading Bot (TradingView Webhook Alerts)"""

    class Meta:
        db_table = 'bots_custom_bots'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['exchange_name', 'trading_pair']),
            models.Index(fields=['bot_id']),
        ]

    EXCHANGE_CHOICES = ExchangeCredentials.EXCHANGE_CHOICES

    MARKET_TYPE_CHOICES = [
        ('spot', 'Spot Trading'),
        ('futures', 'Futures Trading'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='custom_bots')
    subscription = models.ForeignKey(
        'payments.BotSubscription',
        on_delete=models.CASCADE,
        related_name='custom_bots',
        null=True,
        blank=True
    )

    bot_id = models.CharField(max_length=100, unique=True, blank=True, db_index=True, help_text="Unique bot ID")
    bot_name = models.CharField(max_length=255)

    # Webhook configuration
    webhook_url = models.URLField(unique=True, blank=True)
    webhook_message = models.JSONField(blank=True, null=True, help_text="TradingView template")
    secret_key = models.CharField(max_length=64, blank=True)

    exchange_credentials = models.ForeignKey(
        ExchangeCredentials,
        on_delete=models.CASCADE,
        related_name='custom_bots'
    )

    market_type = models.CharField(max_length=20, choices=MARKET_TYPE_CHOICES, default='spot')
    trading_pair = models.CharField(max_length=20)

    # Trading settings
    default_amount = models.DecimalField(max_digits=20, decimal_places=8, validators=[MinValueValidator(0)])
    use_tradingView_position_size = models.BooleanField(default=False)
    take_profit_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    stop_loss_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    # Status tracking
    is_active = models.BooleanField(default=True)
    signals_used_this_month = models.IntegerField(default=0)
    signal_limit = models.IntegerField(default=1000)
    last_reset_date = models.DateField(auto_now_add=True)
    last_triggered = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    # Statistics
    total_trades = models.PositiveIntegerField(default=0)
    successful_trades = models.PositiveIntegerField(default=0)
    total_profit_loss = models.DecimalField(max_digits=20, decimal_places=8, default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def generate_bot_id(self):
        return f"{uuid.uuid4().hex[:5]}-{uuid.uuid4().hex[:5]}-{uuid.uuid4().hex[:5]}"

    def create_message(self):
        """Generate TradingView webhook template"""
        return {
            "bot_id": self.bot_id,
            "secret": self.secret_key,
            "Pair": "{{ticker}}",
            "position_size": "{{strategy.order.contracts}}",
            "exchange": self.exchange_credentials.exchange_name,
            "timestamp": "{{timenow}}",
            "side": "{{strategy.order.action}}"
        }

    def save(self, *args, **kwargs):
        # Generate bot_id if not exists
        if not self.bot_id:
            while True:
                new_id = self.generate_bot_id()
                if not CustomBot.objects.filter(bot_id=new_id).exists():
                    self.bot_id = new_id
                    break

        # Generate webhook URL and secret
        if not self.webhook_url:
            site_url = getattr(settings, 'SITE_URL', 'https://yourdomain.com')
            self.webhook_url = f"{site_url}/api/webhooks/custombot/{self.bot_id}/"

        if not self.secret_key:
            self.secret_key = generate_secret_key(32)

        # Generate template if not exists
        if not self.webhook_message:
            self.webhook_message = self.create_message()

        super().save(*args, **kwargs)

    def increment_signal_count(self):
        self.signals_used_this_month += 1
        self.last_triggered = timezone.now()
        self.save()

    @property
    def signals_remaining(self):
        return max(0, self.signal_limit - self.signals_used_this_month)

    @property
    def success_rate(self):
        if self.total_trades == 0:
            return 0
        return round((self.successful_trades / self.total_trades) * 100, 2)

    def __str__(self):
        return f"{self.bot_name} - {self.trading_pair}"


# ==================== GRID BOT ====================

class GridBot(SoftDeleteModel):
    """Grid trading bot"""

    class Meta:
        db_table = 'bots_grid_bots'
        ordering = ['-created_at']
        unique_together = ['subscription']  # 1 bot per subscription
        indexes = [
            models.Index(fields=['user', 'is_running']),
            models.Index(fields=['exchange_credentials', 'trading_pair']),
            models.Index(fields=['subscription']),
        ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='grid_bots')
    subscription = models.ForeignKey(
        'payments.BotSubscription',
        on_delete=models.CASCADE,
        related_name='grid_bots',
        null=True,
        blank=True
    )

    bot_name = models.CharField(max_length=255)
    exchange_credentials = models.ForeignKey(
        ExchangeCredentials,
        on_delete=models.CASCADE,
        related_name='grid_bots'
    )
    trading_pair = models.CharField(max_length=20)

    AMOUNT_TYPE_CHOICES = [
        ('base', 'Base Currency (Coins)'),
        ('quote', 'Quote Currency (USDT/USDC)'),
    ]

    initial_amount = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    base_amount = models.DecimalField(max_digits=20, decimal_places=8)
    amount_type = models.CharField(max_length=10, choices=AMOUNT_TYPE_CHOICES, default='quote')

    # Grid configuration
    favor_levels = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(50)])
    against_levels = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(50)])
    level_spacing_percent = models.DecimalField(max_digits=5, decimal_places=2, default=1.0)
    favor_level_qty = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal('0'), null=True, blank=True)
    against_level_qty = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal('0'), null=True, blank=True)
    favor_level_difference = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    against_level_difference = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    # Risk management
    take_profit_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    stop_loss_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    # Bot state
    is_running = models.BooleanField(default=False)
    started_at = models.DateTimeField(null=True, blank=True)
    stopped_at = models.DateTimeField(null=True, blank=True)

    # Persistence
    active_orders = models.JSONField(default=list)
    current_grid_levels = models.JSONField(default=dict)
    total_invested = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    current_profit_loss = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    total_trades_executed = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.bot_name} - {self.trading_pair}"


# ==================== MARTINGALE BOT ====================

class MartingaleBot(SoftDeleteModel):
    """Martingale trading bot"""

    class Meta:
        db_table = 'bots_martingale_bots'
        ordering = ['-created_at']
        unique_together = ['subscription']
        indexes = [
            models.Index(fields=['user', 'is_running']),
            models.Index(fields=['exchange_credentials', 'trading_pair']),
            models.Index(fields=['subscription']),
        ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='martingale_bots')
    subscription = models.ForeignKey(
        'payments.BotSubscription',
        on_delete=models.CASCADE,
        related_name='martingale_bots',
        null=True,
        blank=True
    )

    bot_name = models.CharField(max_length=255)
    exchange_credentials = models.ForeignKey(
        ExchangeCredentials,
        on_delete=models.CASCADE,
        related_name='martingale_bots'
    )
    trading_pair = models.CharField(max_length=20)

    AMOUNT_TYPE_CHOICES = GridBot.AMOUNT_TYPE_CHOICES
    initial_amount = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    base_amount = models.DecimalField(max_digits=20, decimal_places=8)
    amount_type = models.CharField(max_length=10, choices=AMOUNT_TYPE_CHOICES, default='quote')

    # Configuration
    favor_levels = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(50)])
    against_levels = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(50)])
    level_spacing_percent = models.DecimalField(max_digits=5, decimal_places=2, default=2.0)
    favor_level_qty = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal('0'), null=True, blank=True)
    against_level_qty = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal('0'), null=True, blank=True)
    favor_level_difference = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    against_level_difference = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    multiplier_factor = models.DecimalField(max_digits=5, decimal_places=2, default=2.0)

    # Risk management
    take_profit_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    stop_loss_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    # Bot state
    is_running = models.BooleanField(default=False)
    started_at = models.DateTimeField(null=True, blank=True)
    stopped_at = models.DateTimeField(null=True, blank=True)

    # Level tracking
    current_level = models.IntegerField(default=0)
    max_level_reached = models.IntegerField(default=0)
    last_execution_price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)

    # Statistics
    active_orders = models.JSONField(default=list)
    current_profit_loss = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    total_invested = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    total_trades_executed = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.bot_name} - {self.trading_pair}"


# ==================== QUANTUM AI FUND (Admin-Managed) ====================

class QuantumAIFund(SoftDeleteModel):
    """Admin-managed master fund for Quantum AI trading"""

    class Meta:
        db_table = 'bots_quantum_ai_fund'
        verbose_name = "Quantum AI Master Fund"
        verbose_name_plural = "Quantum AI Master Funds"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, default="Master Trading Fund")
    trading_strategy = models.TextField(blank=True)
    risk_parameters = models.JSONField(default=dict, help_text="JSON: max_drawdown, stop_loss, etc.")

    # Master API keys (encrypted)
    master_api_key = models.TextField(help_text="Encrypted master API key")
    master_secret_key = models.TextField(help_text="Encrypted master secret key")
    master_passphrase = models.TextField(blank=True, null=True, help_text="Encrypted passphrase if needed")

    # Fund Performance
    total_fund_value = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    total_profit = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    total_deposits = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    last_trade_at = models.DateTimeField(null=True, blank=True)

    # Admin Controls
    is_active = models.BooleanField(default=True)
    admin_notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - ${self.total_fund_value:,.2f}"

    def calculate_profit_to_distribute(self):
        """Calculate 20% of profit for distribution"""
        if self.total_profit <= 0:
            return Decimal('0')
        return self.total_profit * Decimal('0.20')


# ==================== QUANTUM AI INVESTMENT (User-Facing) ====================

class QuantumAIInvestment(SoftDeleteModel):
    """User's investment in Quantum AI fund"""

    class Meta:
        db_table = 'bots_quantum_ai_investments'
        unique_together = ['user', 'fund']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['fund', 'status']),
        ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='quantum_ai_investments')
    fund = models.ForeignKey(QuantumAIFund, on_delete=models.CASCADE, related_name='investments')

    # Link to subscription
    subscription = models.ForeignKey(
        'payments.BotSubscription',
        on_delete=models.CASCADE,
        related_name='quantum_ai_investments',
        null=True,
        blank=True
    )

    amount = models.DecimalField(max_digits=20, decimal_places=8)
    share_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    deposited_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending Approval'),
        ('active', 'Active'),
        ('withdrawn', 'Withdrawn'),
        ('cancelled', 'Cancelled'),
    ], default='pending')

    # Calculated fields
    accrued_profit = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    total_payouts = models.DecimalField(max_digits=20, decimal_places=8, default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.email} - {self.amount} USDT"

    def calculate_share_percentage(self):
        """Calculate user's share of total fund"""
        if self.fund.total_deposits == 0:
            return Decimal('0')
        return (self.amount / self.fund.total_deposits) * 100

    def calculate_profit_share(self):
        """Calculate user's share of 20% fund profit"""
        if self.status != 'active':
            return Decimal('0')

        distributable_profit = self.fund.calculate_profit_to_distribute()
        return (distributable_profit * self.share_percentage) / 100


# ==================== QUANTUM DEPOSIT WALLETS ====================

class QuantumDepositWallet(SoftDeleteModel):
    """Admin-controlled deposit wallets for Quantum AI bot"""

    class Meta:
        db_table = 'bots_quantum_wallets'
        unique_together = ['coin', 'blockchain']
        ordering = ['coin', 'blockchain']
        indexes = [
            models.Index(fields=['coin', 'blockchain', 'is_active']),
        ]

    COIN_CHOICES = [
        ('USDT', 'USDT'), ('USDC', 'USDC'), ('BTC', 'BTC'),
        ('ETH', 'ETH'), ('BNB', 'BNB'), ('SOL', 'SOL'), ('APT', 'APTOS')
    ]

    BLOCKCHAIN_CHOICES = [
        ('SOL', 'Solana'), ('BEP20', 'BEP20'), ('APTOS', 'Aptos'),
        ('ERC20', 'ERC20'), ('TRC20', 'TRC20'), ('BTC', 'Bitcoin'),
        ('POLYGON', 'Polygon')
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    coin = models.CharField(max_length=10, choices=COIN_CHOICES)
    blockchain = models.CharField(max_length=20, choices=BLOCKCHAIN_CHOICES)
    address = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.coin} ({self.blockchain}): {self.address[:12]}..."


class QuantumDeposit(SoftDeleteModel):
    """User deposits for Quantum AI with admin approval workflow"""

    class Meta:
        db_table = 'bots_quantum_deposits'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status', '-created_at']),
            models.Index(fields=['status', '-created_at']),
        ]

    STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('processing', 'Processing'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='quantum_deposits')
    wallet = models.ForeignKey(QuantumDepositWallet, on_delete=models.PROTECT, related_name='deposits')

    amount = models.DecimalField(max_digits=20, decimal_places=8)
    transaction_hash = models.CharField(max_length=100, unique=True, db_index=True)
    screenshot = models.ImageField(upload_to='quantum_deposits/%Y/%m/%d/')

    # Admin approval fields
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_quantum_deposits')
    review_notes = models.TextField(blank=True)

    # Timestamps
    reviewed_at = models.DateTimeField(null=True, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.email} - {self.amount} {self.wallet.coin}"


# ==================== QUANTUM WEEKLY PROFIT ====================

class QuantumWeeklyProfit(SoftDeleteModel):
    """Weekly profit/loss distribution with 20/80 split"""

    class Meta:
        db_table = 'bots_quantum_weekly_profits'
        unique_together = ['user', 'week_start']
        ordering = ['-week_start']
        indexes = [
            models.Index(fields=['user', '-week_start', 'is_distributed']),
            models.Index(fields=['is_distributed', '-week_start']),
        ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='quantum_weekly_profits')
    fund = models.ForeignKey(QuantumAIFund, on_delete=models.PROTECT, related_name='weekly_profits')

    week_start = models.DateField()
    week_end = models.DateField()
    total_deposited = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    realized_pnl = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    unrealized_pnl = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    user_share_percent = models.DecimalField(max_digits=5, decimal_places=2, default=20.0)
    is_distributed = models.BooleanField(default=False, db_index=True)
    distributed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def total_pnl(self):
        return self.realized_pnl + self.unrealized_pnl

    @property
    def user_share_amount(self):
        if self.total_pnl <= 0:
            return 0
        return (self.total_pnl * self.user_share_percent) / 100

    @property
    def admin_share_amount(self):
        if self.total_pnl <= 0:
            return 0
        return (self.total_pnl * (100 - self.user_share_percent)) / 100

    @property
    def roi_percentage(self):
        if self.total_deposited == 0:
            return 0
        return round((self.total_pnl / self.total_deposited) * 100, 2)

    def __str__(self):
        return f"Week of {self.week_start} - {self.user.email}"


# =============================================================================
# TRADING DATA MODELS (Keep from bots app)
# =============================================================================

class PairConfig(TimeStampedModel):
    """Pair configuration model (preserved from your code)"""

    class Meta:
        db_table = 'bots_pair_configs'
        unique_together = ['user', 'pair_symbol', 'bot_type']
        indexes = [
            models.Index(fields=['user', 'bot_type']),
            models.Index(fields=['pair_symbol']),
        ]

    amount_choices = [('coin', 'Coins'), ('dollar', '$')]
    order_choices = [('market', 'Market Order'), ('limit', 'Limit Order')]
    SLTP_choices = [('percentage', 'Percentage'), ('dollars', 'Dollars')]
    entry_choices = [('buy', 'BUY'), ('sell', 'SELL'), ('both', 'BOTH'), (None, 'None')]
    exit_choices = [('tp', 'TP'), ('sl', 'SL'), ('both', 'BOTH'), (None, 'None')]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    pair_symbol = models.CharField(max_length=20, null=False, blank=False)
    slug = models.SlugField(null=True, blank=True)

    subscription = models.ForeignKey(
        'payments.BotSubscription',
        on_delete=models.CASCADE,
        related_name='pair_configs',
        null=True,
        blank=True
    )

    bot_type = models.CharField(max_length=20, choices=[
        ('grid', 'Grid Bot'),
        ('martingale', 'Martingale Bot'),
        ('custom', 'Custom Bot'),
    ], default='grid')

    quantity = models.FloatField(null=True, blank=True)
    favor_levels = models.IntegerField(default=3, null=True, blank=True)
    against_levels = models.IntegerField(default=3, null=True, blank=True)
    favor_level_qty = models.FloatField(null=True, blank=True)
    against_level_qty = models.FloatField(null=True, blank=True)
    favor_level_difference = models.FloatField(null=True, blank=True)
    against_level_difference = models.FloatField(null=True, blank=True)

    Order_Type = models.CharField(max_length=10, default='market', choices=order_choices)
    Amount_Type = models.CharField(max_length=10, default='dollar', choices=amount_choices)
    SLTP_Type = models.CharField(max_length=10, default='dollar', choices=SLTP_choices)
    Stop_Loss = models.FloatField(blank=True, null=True)
    Take_Profit = models.FloatField(blank=True, null=True)

    RSI_Lower = models.FloatField(default=30, null=True, blank=True)
    RSI_Upper = models.FloatField(default=70, null=True, blank=True)

    RSI_Entry = models.CharField(max_length=10, default='None', choices=entry_choices, null=True, blank=True)
    BB_Entry = models.CharField(max_length=10, default='None', choices=entry_choices, null=True, blank=True)
    EMA_RSI_Entry = models.CharField(max_length=10, default='None', choices=entry_choices, null=True, blank=True)
    EMA_BB_Entry = models.CharField(max_length=10, default='None', choices=entry_choices, null=True, blank=True)
    BB_RSI_Entry = models.CharField(max_length=10, default='None', choices=entry_choices, null=True, blank=True)
    EMA_BB_RSI_Entry = models.CharField(max_length=10, default='None', choices=entry_choices, null=True, blank=True)

    BB_Exit = models.CharField(max_length=10, default='None', choices=exit_choices, null=True, blank=True)
    RSI_Exit = models.CharField(max_length=10, default='None', choices=exit_choices, null=True, blank=True)
    EMA_RSI_Exit = models.CharField(max_length=10, default='None', choices=exit_choices, null=True, blank=True)
    EMA_BB_Exit = models.CharField(max_length=10, default='None', choices=exit_choices, null=True, blank=True)
    BB_RSI_Exit = models.CharField(max_length=10, default='None', choices=exit_choices, null=True, blank=True)
    EMA_BB_RSI_Exit = models.CharField(max_length=10, default='None', choices=exit_choices, null=True, blank=True)
    SL_Exit = models.CharField(max_length=10, default='None', choices=exit_choices, null=True, blank=True)

    def __str__(self):
        return f"{self.slug} Config"


class Indicator(TimeStampedModel):
    """Technical indicator model (preserved from your code)"""

    class Meta:
        db_table = 'bots_indicators'
        indexes = [models.Index(fields=['user', 'Pair'])]

    Pair = models.CharField(max_length=20, null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    EMA = models.FloatField(blank=True, null=True)
    RSI = models.FloatField(blank=True, null=True)
    Prev_RSI = models.FloatField(blank=True, null=True)
    Color = models.CharField(max_length=6, blank=True, null=True)
    Prev_Color = models.CharField(max_length=6, blank=True, null=True)
    BB = models.CharField(max_length=30, blank=True, null=True)
    TSI = models.FloatField(blank=True, null=True)
    ADX = models.FloatField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.user} {self.Pair} Indicator Data {self.id}'


class Order(TimeStampedModel):
    """Unified order model (preserved from your code)"""

    class Meta:
        db_table = 'bots_orders'
        ordering = ['-Time']
        indexes = [
            models.Index(fields=['user', 'Pair']),
            models.Index(fields=['-Time']),
        ]

    Time = models.DateTimeField()
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    Pair = models.CharField(max_length=20, null=True, blank=True)

    # KEEP your relationships
    PairConfig = models.ForeignKey(PairConfig, on_delete=models.CASCADE, blank=True, null=True)
    Indicators = models.ForeignKey(Indicator, on_delete=models.CASCADE, blank=True, null=True)

    # Polymorphic bot references
    custom_bot = models.ForeignKey(CustomBot, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    grid_bot = models.ForeignKey(GridBot, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    martingale_bot = models.ForeignKey(MartingaleBot, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    quantum_ai_investment = models.ForeignKey(QuantumAIInvestment, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')

    # Your existing fields
    Side = models.CharField(max_length=5, null=True, blank=True)
    Category = models.CharField(max_length=20, null=True, blank=True)
    Order_type = models.CharField(max_length=20, null=True, blank=True)
    Quantity = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    Price = models.FloatField(null=True, blank=True)
    Exchange = models.CharField(max_length=20, blank=True, null=True)
    Take_Profit = models.FloatField(blank=True, null=True)
    Stop_Loss = models.FloatField(blank=True, null=True)
    Description = models.TextField(blank=True, null=True)
    Details = models.JSONField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        # Timezone override
        if not self.id:
            pakistan_tz = pytz.timezone('Asia/Karachi')
            self.Time = timezone.now().astimezone(pakistan_tz)

        # Ensure Time is set if empty
        if not self.Time:
            self.Time = timezone.now()

        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.user} - {self.Pair} - {self.Side} - {self.Price} - {self.Time}'


class TelegramSignalPlan(SoftDeleteModel):
    """Telegram signal subscription plans"""

    class Meta:
        db_table = 'bots_telegram_plans'
        ordering = ['price_usd']
        indexes = [
            models.Index(fields=['is_active', 'price_usd']),
        ]

    name = models.CharField(max_length=50, unique=True)
    description = models.TextField()
    duration_days = models.IntegerField()
    price_usd = models.DecimalField(max_digits=10, decimal_places=2)
    features = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - ${self.price_usd}"


class TelegramSignalSubscription(SoftDeleteModel):
    """User subscriptions to Telegram signals"""

    class Meta:
        db_table = 'bots_telegram_subscriptions'
        ordering = ['-subscribed_at']
        indexes = [
            models.Index(fields=['status', '-subscribed_at']),
            models.Index(fields=['expires_at', 'status']),
        ]

    STATUS_CHOICES = [
        ('pending', 'Pending Admin Approval'),
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Link to unified BotSubscription
    bot_subscription = models.OneToOneField(
        'payments.BotSubscription',
        on_delete=models.CASCADE,
        related_name='telegram_subscription',
        null=True,
        blank=True
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='telegram_subscription')
    plan = models.ForeignKey(TelegramSignalPlan, on_delete=models.PROTECT)
    telegram_handle = models.CharField(max_length=50, unique=True, db_index=True)
    invitation_link = models.URLField(null=True, blank=True)

    # Join tracking
    joined_channel = models.BooleanField(default=False)
    joined_at = models.DateTimeField(null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    subscribed_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()

    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_telegram_subs')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def check_and_update_status(self):
        """Auto-update status based on expiry"""
        now = timezone.now()
        if self.status == 'active' and now > self.expires_at:
            self.status = 'expired'
            self.save(update_fields=['status'])
        return self.status

    @property
    def is_active(self):
        """Check if subscription is currently active"""
        if not self.approved_at:
            return False
        return timezone.now() < self.expires_at and self.status == 'active'

    def __str__(self):
        return f"{self.user.email} - {self.telegram_handle}"