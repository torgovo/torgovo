import uuid
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from apps.exchanges.models import ExchangeCredentials
from core.models import SoftDeleteModel, TimeStampedModel
from core.utils import decrypt_api_key, encrypt_api_key, generate_secret_key, looks_encrypted

User = get_user_model()

# A5 (FUNCTIONAL_REQUIREMENTS.md §A5): allowed Quantum AI investment lock
# terms. Shared by QuantumAIFund.default_lock_days and InvestorLock.lock_days
# so both fields are validated against the same closed set.
QUANTUM_LOCK_DAYS_CHOICES = [
    (30, "30 days"),
    (90, "90 days"),
    (180, "180 days"),
    (365, "365 days"),
]

# ==================== SIGNAL BOT (TradingView Webhook) ====================


class SignalBot(SoftDeleteModel):
    """Signal Bot - receives trading signals from TradingView webhooks and executes trades"""

    class Meta:
        db_table = "bots_signal_bots"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "is_active"]),
            models.Index(fields=["exchange_name", "trading_pair"]),
        ]

    EXCHANGE_CHOICES = ExchangeCredentials.EXCHANGE_CHOICES

    MARKET_TYPE_CHOICES = [
        ("spot", "Spot Trading"),
        ("futures", "Futures Trading"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="signal_bots")

    subscription = models.ForeignKey(
        "payments.BotSubscription",
        on_delete=models.SET_NULL,
        related_name="signal_bots",
        null=True,
        blank=True,
    )

    # Bot identification
    bot_id = models.CharField(
        max_length=100,
        unique=True,
        blank=True,
        db_index=True,
        help_text="Unique bot ID in format xxxxx-xxxxx-xxxxx",
    )
    bot_name = models.CharField(max_length=255)

    # Webhook configuration
    webhook_url = models.URLField(blank=True)
    webhook_message = models.JSONField(
        blank=True,
        null=True,
        help_text="Auto-generated JSON template (TradingView placeholders). "
        "Editable for any platform: bot_id, secret, side, timestamp, Pair/pair/symbol.",
    )
    secret_key = models.CharField(max_length=64, blank=True)

    exchange_name = models.CharField(max_length=20, choices=EXCHANGE_CHOICES)
    market_type = models.CharField(max_length=20, choices=MARKET_TYPE_CHOICES, default="spot")
    trading_pair = models.CharField(max_length=20)

    # Trading settings
    default_amount = models.DecimalField(
        max_digits=20, decimal_places=8, validators=[MinValueValidator(0)]
    )
    use_tradingView_position_size = models.BooleanField(
        default=False,
        help_text="Use position size from the alert payload instead of default_amount",
    )
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
        """Generate a unique bot ID in format xxxxx-xxxxx-xxxxx"""
        return f"{uuid.uuid4().hex[:5]}-{uuid.uuid4().hex[:5]}-{uuid.uuid4().hex[:5]}"

    def create_message(self):
        """Generate JSON webhook message template with TradingView placeholders

        The template uses TradingView {{placeholders}} so it pastes straight into
        a TradingView alert. For other platforms (or hand-built bodies) the user
        may replace the template with any JSON containing: bot_id, secret, side,
        timestamp, and a pair (Pair/pair/symbol/ticker/market/currency).
        """
        from django.conf import settings

        # NOTE: bot_id is guaranteed to exist by save() before this is called.
        # Do NOT call self.save() here — that would cause infinite recursion.
        # Get webhook URL from settings or generate it
        site_url = getattr(settings, "SITE_URL", "https://yourdomain.com")
        if not site_url.startswith("http"):
            site_url = f"https://{site_url}"

        data = {
            "bot_id": self.bot_id,
            "secret": self.secret_key,
            "Pair": "{{syminfo.basecurrency}}/{{syminfo.currency}}",
            "position_size": "{{strategy.position_size}}",
            "exchange": self.exchange_name,
            "timestamp": "{{timenow}}",
            "side": "{{strategy.order.action}}",
            "order_id": "{{strategy.order.id}}",
        }
        return data

    def save(self, *args, **kwargs):
        """Override save to auto-generate bot_id and webhook_message"""
        # Generate bot_id if not exists
        if not self.bot_id:
            while True:
                new_id = self.generate_bot_id()
                if not SignalBot.objects.filter(bot_id=new_id).exists():
                    self.bot_id = new_id
                    break

        # Generate webhook URL and secret if not exists
        if not self.webhook_url:
            from django.conf import settings

            site_url = getattr(settings, "SITE_URL", "https://yourdomain.com")
            if not site_url.startswith("http"):
                site_url = f"https://{site_url}"
            self.webhook_url = f"{site_url}/api/webhooks/custombot/"

        if not self.secret_key:
            self.secret_key = generate_secret_key(32)

        # Generate webhook message template if not exists
        if not self.webhook_message:
            self.webhook_message = self.create_message()

        super().save(*args, **kwargs)

    def generate_webhook_credentials(self):
        """Generate unique webhook URL and secret on creation"""
        if not self.webhook_url:
            self.webhook_url = f"{settings.SITE_URL}/api/webhooks/custom/{self.id}/"
        if not self.secret_key:
            self.secret_key = generate_secret_key(32)
        self.save()

    def increment_signal_count(self):
        """Increment monthly signal counter"""
        self.signals_used_this_month += 1
        self.last_triggered = timezone.now()
        self.save()

    @property
    def signals_remaining(self):
        return max(0, self.signal_limit - self.signals_used_this_month)

    @property
    def success_rate(self):
        """Calculate success rate percentage"""
        if self.total_trades == 0:
            return 0
        return round((self.successful_trades / self.total_trades) * 100, 2)

    def __str__(self):
        return f"{self.bot_name} - {self.trading_pair}"


# ==================== GRID BOT ====================


class GridBot(SoftDeleteModel):
    """Grid trading bot with subscription support"""

    class Meta:
        db_table = "bots_grid_bots"
        ordering = ["-created_at"]
        # unique_together = ["subscription"] REMOVED 2026-10-18: Model C
        # users attach every bot to ONE shared subscription, so the DB
        # constraint blocked seat-eligible 2nd+ grids (IntegrityError 500).
        # Legacy still gets 1-per-sub from the view-level duplicate check
        # (source != "model_c" → 400). See docs/model-c-shared-sub-multi-bot.md.
        indexes = [
            models.Index(fields=["user", "is_running"]),
            models.Index(fields=["exchange_name", "trading_pair"]),
            models.Index(fields=["subscription"]),
        ]

    EXCHANGE_CHOICES = ExchangeCredentials.EXCHANGE_CHOICES

    AMOUNT_TYPE_CHOICES = [
        ("base", "Base Currency (Coins)"),
        ("quote", "Quote Currency (USDT/USDC)"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="grid_bots")

    subscription = models.ForeignKey(
        "payments.BotSubscription",
        on_delete=models.SET_NULL,
        related_name="grid_bots",
        null=True,
        blank=True,
    )

    bot_name = models.CharField(max_length=255)
    exchange_name = models.CharField(max_length=20, choices=EXCHANGE_CHOICES)
    trading_pair = models.CharField(max_length=20)

    # NEW: Initial amount field
    initial_amount = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    base_amount = models.DecimalField(max_digits=20, decimal_places=8)

    # Grid configuration
    favor_levels = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(50)])
    against_levels = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(50)])
    level_spacing_percent = models.DecimalField(max_digits=5, decimal_places=2, default=1.0)
    favor_level_qty = models.DecimalField(
        max_digits=20, decimal_places=8, default=Decimal("0"), null=True, blank=True
    )
    against_level_qty = models.DecimalField(
        max_digits=20, decimal_places=8, default=Decimal("0"), null=True, blank=True
    )

    # NEW: Level difference fields
    favor_level_difference = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Percentage difference between each favor level",
    )
    against_level_difference = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Percentage difference between each against level",
    )

    # NEW: Amount type selection
    amount_type = models.CharField(max_length=10, choices=AMOUNT_TYPE_CHOICES, default="quote")

    # Risk management
    take_profit_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    stop_loss_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    # Bot state
    is_running = models.BooleanField(default=False)
    started_at = models.DateTimeField(null=True, blank=True)
    stopped_at = models.DateTimeField(null=True, blank=True)
    last_heartbeat = models.DateTimeField(null=True, blank=True)

    # Persistence
    active_orders = models.JSONField(default=list)
    current_grid_levels = models.JSONField(default=dict)
    total_invested = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    current_profit_loss = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    total_trades_executed = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save_state(self, active_orders=None, grid_levels=None):
        """Save bot state directly. Called by BotEngine when needed."""
        if active_orders is not None:
            self.active_orders = active_orders
        if grid_levels is not None:
            self.current_grid_levels = grid_levels
        self.save(update_fields=["active_orders", "current_grid_levels", "updated_at"])

    def __str__(self):
        return f"{self.bot_name} - {self.trading_pair}"


class ActiveOrder(TimeStampedModel):
    """Individual active order for a GridBot (replaces JSONField)."""

    class Meta:
        db_table = "bots_active_orders"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["grid_bot", "status"]),
            models.Index(fields=["grid_bot", "side"]),
        ]

    SIDE_CHOICES = [("buy", "Buy"), ("sell", "Sell")]
    STATUS_CHOICES = [
        ("open", "Open"),
        ("filled", "Filled"),
        ("cancelled", "Cancelled"),
        ("expired", "Expired"),
    ]

    grid_bot = models.ForeignKey(
        GridBot,
        on_delete=models.CASCADE,
        related_name="active_orders_model",
    )
    side = models.CharField(max_length=5, choices=SIDE_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="open")
    quantity = models.DecimalField(max_digits=20, decimal_places=8)
    price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    filled_quantity = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    exchange_order_id = models.CharField(max_length=100, blank=True, db_index=True)
    level_index = models.IntegerField(
        default=0, help_text="Position in grid level (positive=favor, negative=against)"
    )

    def __str__(self):
        return f"{self.grid_bot.bot_name} {self.side} {self.quantity} @ {self.price}"


# ==================== MARTINGALE BOT ====================


class MartingaleBot(SoftDeleteModel):
    """Martingale bot with subscription support"""

    class Meta:
        db_table = "bots_martingale_bots"
        ordering = ["-created_at"]
        # unique_together = ["subscription"] REMOVED 2026-10-18: same reason
        # as GridBot — shared Model C subscription holds many bots; legacy
        # 1-per-sub stays enforced by the create-view 400 check.
        # See docs/model-c-shared-sub-multi-bot.md.
        indexes = [
            models.Index(fields=["user", "is_running"]),
            models.Index(fields=["exchange_name", "trading_pair"]),
            models.Index(fields=["subscription"]),
        ]

    EXCHANGE_CHOICES = ExchangeCredentials.EXCHANGE_CHOICES
    AMOUNT_TYPE_CHOICES = GridBot.AMOUNT_TYPE_CHOICES

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="martingale_bots")

    subscription = models.ForeignKey(
        "payments.BotSubscription",
        on_delete=models.SET_NULL,
        related_name="martingale_bots",
        null=True,
        blank=True,
    )

    bot_name = models.CharField(max_length=255)
    exchange_name = models.CharField(max_length=20, choices=EXCHANGE_CHOICES)
    trading_pair = models.CharField(max_length=20)

    # NEW: Initial amount field
    initial_amount = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    base_amount = models.DecimalField(max_digits=20, decimal_places=8)

    # Configuration
    favor_levels = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(50)])
    against_levels = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(50)])
    level_spacing_percent = models.DecimalField(max_digits=5, decimal_places=2, default=2.0)
    favor_level_qty = models.DecimalField(
        max_digits=20, decimal_places=8, default=Decimal("0"), null=True, blank=True
    )
    against_level_qty = models.DecimalField(
        max_digits=20, decimal_places=8, default=Decimal("0"), null=True, blank=True
    )

    # NEW: Level difference fields
    favor_level_difference = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    against_level_difference = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )

    # NEW: Amount type selection
    amount_type = models.CharField(max_length=10, choices=AMOUNT_TYPE_CHOICES, default="quote")

    multiplier_factor = models.DecimalField(max_digits=5, decimal_places=2, default=2.0)

    # Risk management
    take_profit_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    stop_loss_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    # Bot state
    is_running = models.BooleanField(default=False)
    started_at = models.DateTimeField(null=True, blank=True)
    stopped_at = models.DateTimeField(null=True, blank=True)
    last_heartbeat = models.DateTimeField(null=True, blank=True)

    # Level tracking
    current_level = models.IntegerField(default=0)
    max_level_reached = models.IntegerField(default=0)
    last_execution_price = models.DecimalField(
        max_digits=20, decimal_places=8, null=True, blank=True
    )

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
        db_table = "bots_quantum_ai_fund"
        verbose_name = "Quantum AI Master Fund"
        verbose_name_plural = "Quantum AI Master Funds"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, default="Master Trading Fund")
    trading_strategy = models.TextField(blank=True)
    risk_parameters = models.JSONField(
        default=dict, help_text="JSON: max_drawdown, stop_loss, etc."
    )

    # Master API keys (encrypted)
    master_api_key = models.TextField(help_text="Encrypted master API key")
    master_secret_key = models.TextField(help_text="Encrypted master secret key")
    master_passphrase = models.TextField(
        blank=True, null=True, help_text="Encrypted passphrase if needed"
    )

    # Fund Performance
    total_fund_value = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    total_profit = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    total_deposits = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    last_trade_at = models.DateTimeField(null=True, blank=True)

    # Smoothed return config (admin configurable)
    monthly_min_return = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=2.0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Minimum monthly return shown to users (floor, e.g. 2%)",
    )
    monthly_max_return = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=15.0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Maximum monthly return shown to users (cap, e.g. 15%)",
    )
    reserve_buffer_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=10.0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Target reserve as percentage of total deposits (e.g. 10%)",
    )

    # A5 (G3): default lock term applied when an investment creates an
    # InvestorLock without an explicit term (subscription / deposit approval).
    # Admin-editable → satisfies the Part B "DB-backed admin config" rule.
    default_lock_days = models.PositiveSmallIntegerField(
        choices=QUANTUM_LOCK_DAYS_CHOICES,
        default=30,
        help_text="Default lock term (days) for new Quantum AI investments (A5)",
    )

    # Admin Controls
    is_active = models.BooleanField(default=True)
    admin_notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        """Encrypt master keys on save if they aren't already encrypted.

        Uses looks_encrypted() (shared with ExchangeCredentials and the
        encrypt_quantum_fund_keys management command) to detect plaintext.
        This handles both creation and subsequent updates — any plaintext
        value found is encrypted before writing to the database.
        """
        if not looks_encrypted(self.master_api_key):
            self.master_api_key = encrypt_api_key(self.master_api_key)
        if not looks_encrypted(self.master_secret_key):
            self.master_secret_key = encrypt_api_key(self.master_secret_key)
        if self.master_passphrase and not looks_encrypted(self.master_passphrase):
            self.master_passphrase = encrypt_api_key(self.master_passphrase)
        super().save(*args, **kwargs)

    def get_decrypted_credentials(self):
        """Get decrypted master credentials for exchange API usage."""
        return {
            "api_key": decrypt_api_key(self.master_api_key),
            "secret_key": decrypt_api_key(self.master_secret_key),
            "passphrase": (
                decrypt_api_key(self.master_passphrase) if self.master_passphrase else None
            ),
        }

    def __str__(self):
        return f"{self.name} - ${self.total_fund_value:,.2f}"

    def calculate_smoothed_return(self, actual_return_pct: Decimal) -> Decimal:
        """
        Smooth actual return into what's shown to users.

        If actual < min  → show min (admin covers loss from reserve)
        If min ≤ actual ≤ max → show actual (pass-through)
        If actual > max  → show max (admin keeps excess)

        Args:
            actual_return_pct: Real return as decimal (e.g. 5.0 = 5%)

        Returns:
            Shown return as decimal (e.g. 2.0 = 2%)
        """
        return max(self.monthly_min_return, min(actual_return_pct, self.monthly_max_return))

    def calculate_excess_return(self, actual_return_pct: Decimal) -> Decimal:
        """
        Calculate the portion exceeding max return (goes to admin/reserve).
        Positive means admin keeps it. Negative means admin covers from reserve.
        """
        shown = self.calculate_smoothed_return(actual_return_pct)
        return actual_return_pct - shown


class ReserveFund(SoftDeleteModel):
    """
    Reserve buffer for smoothing Quantum AI returns.

    Admin deposits USDT here. When the bot underperforms (< min_return),
    the reserve covers the difference so users still get paid.
    When the bot overperforms (> max_return), excess flows here.
    """

    class Meta:
        db_table = "bots_reserve_fund"
        verbose_name = "Reserve Fund"
        verbose_name_plural = "Reserve Funds"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    fund = models.OneToOneField(QuantumAIFund, on_delete=models.CASCADE, related_name="reserve")
    balance = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    last_top_up = models.DateTimeField(null=True, blank=True)
    last_withdrawal = models.DateTimeField(null=True, blank=True)
    low_balance_alert_sent = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Reserve for {self.fund.name} — ${self.balance:,.2f}"

    def is_below_target(self) -> bool:
        """Check if reserve is below target percentage of deposits."""
        if self.fund.total_deposits == 0:
            return True
        target = self.fund.total_deposits * (self.fund.reserve_buffer_pct / Decimal("100"))
        return self.balance < target

    def can_cover(self, amount: Decimal) -> bool:
        """Check if reserve can cover a withdrawal."""
        return self.balance >= amount

    def record_transaction(
        self, balance_before: Decimal, amount: Decimal, txn_type: str, description: str = ""
    ):
        """
        Record a reserve movement with full audit trail.

        Args:
            balance_before: Balance before the change.
            amount: Amount moved (positive for deposits, negative for withdrawals).
            txn_type: One of ReserveTransaction.TRANSACTION_TYPES.
            description: Human-readable reason.
        """
        ReserveTransaction.objects.create(
            fund=self.fund,
            reserve=self,
            amount=amount,
            balance_before=balance_before,
            balance_after=balance_before + amount,
            transaction_type=txn_type,
            description=description,
        )


class ReserveTransaction(TimeStampedModel):
    """
    Audit trail for every movement in/out of the reserve fund.

    Every cover, deposit, top-up, and withdrawal writes a row here,
    making the reserve fully traceable for reconciliation and compliance.
    """

    class Meta:
        db_table = "bots_reserve_transactions"
        verbose_name = "Reserve Transaction"
        verbose_name_plural = "Reserve Transactions"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["fund", "-created_at"]),
            models.Index(fields=["transaction_type"]),
        ]

    TRANSACTION_TYPES = [
        ("top_up", "Admin Top-Up"),
        ("withdrawal", "Admin Withdrawal"),
        ("shortfall_cover", "Shortfall Cover (paid to users)"),
        ("excess_deposit", "Excess Return Deposit (from overperformance)"),
        ("smoothing_adj", "Smoothing Adjustment"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    fund = models.ForeignKey(
        QuantumAIFund, on_delete=models.CASCADE, related_name="reserve_transactions"
    )
    reserve = models.ForeignKey(ReserveFund, on_delete=models.CASCADE, related_name="transactions")
    amount = models.DecimalField(max_digits=20, decimal_places=8)
    balance_before = models.DecimalField(max_digits=20, decimal_places=8)
    balance_after = models.DecimalField(max_digits=20, decimal_places=8)
    transaction_type = models.CharField(max_length=30, choices=TRANSACTION_TYPES)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return (
            f"{self.transaction_type} — {self.amount} USDT "
            f"(balance: {self.balance_before} → {self.balance_after})"
        )


# ==================== QUANTUM AI BOT (Admin-Managed Trading Bot) ====================


class QuantumAIBot(SoftDeleteModel):
    """Admin-managed trading bot that trades using the QuantumAI strategy against the fund.

    Admin sees and configures this bot. Users only see their investment balance.
    """

    class Meta:
        db_table = "bots_quantum_ai_bots"
        verbose_name = "Quantum AI Bot"
        verbose_name_plural = "Quantum AI Bots"
        indexes = [
            models.Index(fields=["fund", "is_running"]),
            models.Index(fields=["exchange_name", "trading_pair"]),
        ]

    EXCHANGE_CHOICES = ExchangeCredentials.EXCHANGE_CHOICES

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    fund = models.ForeignKey(QuantumAIFund, on_delete=models.CASCADE, related_name="bots")

    bot_name = models.CharField(max_length=255)
    exchange_name = models.CharField(max_length=20, choices=EXCHANGE_CHOICES)
    trading_pair = models.CharField(max_length=20)

    # Strategy parameters
    strategy_parameters = models.JSONField(
        default=dict, help_text="Strategy-specific config: timeframes, indicators, thresholds, etc."
    )

    # Bot state
    is_running = models.BooleanField(default=False)
    started_at = models.DateTimeField(null=True, blank=True)
    stopped_at = models.DateTimeField(null=True, blank=True)
    last_heartbeat = models.DateTimeField(null=True, blank=True)

    # Performance tracking
    total_trades = models.PositiveIntegerField(default=0)
    total_profit_loss = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    last_trade_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        status = "Running" if self.is_running else "Stopped"
        return f"{self.bot_name} [{status}] - {self.trading_pair}"


# ==================== QUANTUM AI INVESTMENT (User-Facing) ====================


class InvestorPortfolio(SoftDeleteModel):
    """User's investment in Quantum AI fund"""

    class Meta:
        db_table = "bots_quantum_ai_investments"
        unique_together = ["user", "fund"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["fund", "status"]),
        ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="quantum_ai_investments")
    fund = models.ForeignKey(QuantumAIFund, on_delete=models.CASCADE, related_name="investments")

    # Link to subscription
    subscription = models.ForeignKey(
        "payments.BotSubscription",
        on_delete=models.CASCADE,
        related_name="quantum_ai_investments",
        null=True,
        blank=True,
    )

    amount = models.DecimalField(max_digits=20, decimal_places=8)
    share_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    deposited_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending Approval"),
            ("active", "Active"),
            ("withdrawn", "Withdrawn"),
            ("cancelled", "Cancelled"),
        ],
        default="pending",
    )

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
            return Decimal("0")
        return (self.amount / self.fund.total_deposits) * 100

    def calculate_profit_share(self, actual_return_pct: Decimal) -> Decimal:
        """
        Calculate user's share using smoothed return.

        Args:
            actual_return_pct: Real return as decimal percent (e.g. 5.0 = 5%)

        Returns:
            User's share in USDT
        """
        if self.status != "active" or self.fund.total_deposits == 0:
            return Decimal("0")

        shown_pct = self.fund.calculate_smoothed_return(actual_return_pct)
        user_portion = self.amount / self.fund.total_deposits
        return self.fund.total_deposits * (shown_pct / Decimal("100")) * user_portion


# ==================== QUANTUM DEPOSIT WALLETS (Keep Existing) ====================


class QuantumDepositWallet(SoftDeleteModel):
    """Admin-controlled deposit wallets for Quantum AI bot"""

    class Meta:
        db_table = "bots_quantum_wallets"
        unique_together = ["coin", "blockchain"]
        ordering = ["coin", "blockchain"]
        indexes = [
            models.Index(fields=["coin", "blockchain", "is_active"]),
        ]

    COIN_CHOICES = [
        ("USDT", "USDT"),
        ("USDC", "USDC"),
        ("BTC", "BTC"),
        ("ETH", "ETH"),
        ("BNB", "BNB"),
        ("SOL", "SOL"),
        ("APT", "APTOS"),
    ]

    BLOCKCHAIN_CHOICES = [
        ("SOL", "Solana"),
        ("BEP20", "BEP20"),
        ("APTOS", "Aptos"),
        ("ERC20", "ERC20"),
        ("TRC20", "TRC20"),
        ("BTC", "Bitcoin"),
        ("POLYGON", "Polygon"),
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
        db_table = "bots_quantum_deposits"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    STATUS_CHOICES = [
        ("pending", "Pending Approval"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("processing", "Processing"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="quantum_deposits")
    wallet = models.ForeignKey(
        QuantumDepositWallet, on_delete=models.PROTECT, related_name="deposits"
    )

    amount = models.DecimalField(max_digits=20, decimal_places=8)
    transaction_hash = models.CharField(max_length=100, unique=True, db_index=True)
    screenshot = models.ImageField(upload_to="quantum_deposits/%Y/%m/%d/")

    # Admin approval fields
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True
    )
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_quantum_deposits",
    )
    review_notes = models.TextField(blank=True)

    # Timestamps
    reviewed_at = models.DateTimeField(null=True, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.email} - {self.amount} {self.wallet.coin}"


# ==================== QUANTUM WEEKLY PROFIT (Keep Existing) ====================


class QuantumWeeklyProfit(SoftDeleteModel):
    """Weekly profit/loss distribution with 20/80 split"""

    class Meta:
        db_table = "bots_quantum_weekly_profits"
        unique_together = ["user", "week_start"]
        ordering = ["-week_start"]
        indexes = [
            models.Index(fields=["user", "-week_start", "is_distributed"]),
            models.Index(fields=["is_distributed", "-week_start"]),
        ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="quantum_weekly_profits")
    fund = models.ForeignKey(QuantumAIFund, on_delete=models.PROTECT, related_name="weekly_profits")

    week_start = models.DateField()
    week_end = models.DateField()
    total_deposited = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    realized_pnl = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    unrealized_pnl = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    user_share_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("20.0")
    )
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


# ==================== A5 QUANTUM AI INVESTMENT LOCKS (G3) ====================
# Implements FUNCTIONAL_REQUIREMENTS.md §A5 (locked 2026-10-14), replacing the
# biweekly reserve/smoothing distribution model:
#   * per-investor 30/90/180/365-day locks (hard rule: nothing withdrawable
#     while the lock window is running),
#   * admin-triggered credit at per-investor maturity: capital x (1 + %/100),
#     exactly one credit per term, credited capital rolls into the next term
#     (compounding), rate is lock-independent,
#   * post-lock withdrawal requests (any partial amount up to capital+profit),
#     admin approves within 7 days and enters the payout amount including
#     chain fees; the system debits the lock ledger (grill Q12).
# Accounting model: `amount` is the single balance-of-record (capital + rolled
# credit); profit_credited_total / withdrawn_total are cumulative reporting.


class InvestorLock(SoftDeleteModel):
    """A single investor's term-locked capital in the Quantum AI fund (A5)."""

    class Meta:
        db_table = "bots_investor_locks"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["fund", "status"]),
            models.Index(fields=["matures_at"]),  # admin "matured, awaiting credit" queue
        ]

    STATUS_CHOICES = [
        ("active", "Active"),  # lock running or matured awaiting credit/withdrawal
        ("cancelled", "Cancelled"),  # voided by admin (capital already 0/paid out)
        ("closed", "Closed"),  # capital fully withdrawn — terminal
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="quantum_locks")
    fund = models.ForeignKey(QuantumAIFund, on_delete=models.PROTECT, related_name="locks")

    # Optional provenance links (either may be absent: locks can also be
    # created directly by admin credit flows during migration from old data).
    subscription = models.ForeignKey(
        "payments.BotSubscription",
        on_delete=models.CASCADE,
        related_name="quantum_locks",
        null=True,
        blank=True,
    )
    deposit = models.ForeignKey(
        "payments.InvestorDeposit",
        on_delete=models.SET_NULL,
        related_name="locks",
        null=True,
        blank=True,
    )

    # --- capital accounting -------------------------------------------------
    amount = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        help_text="Current capital (balance-of-record): includes credited profit "
        "rolled into subsequent terms; reduced by approved withdrawals.",
    )
    lock_days = models.PositiveSmallIntegerField(choices=QUANTUM_LOCK_DAYS_CHOICES)

    # --- term tracking (one credit per maturity, then roll) -----------------
    term_number = models.PositiveIntegerField(
        default=1, help_text="Current term (1-based); bumped by each credit."
    )
    credited_term = models.PositiveIntegerField(
        default=0,
        help_text="Last term credited; 0 = never credited. "
        "Credit allowed only when is_matured and credited_term < term_number.",
    )
    profit_credited_total = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    withdrawn_total = models.DecimalField(max_digits=20, decimal_places=8, default=0)

    # --- lock window ---------------------------------------------------------
    starts_at = models.DateTimeField(default=timezone.now)
    matures_at = models.DateTimeField(db_index=True)  # derived state, G4-style

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    cancelled_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # --- derived state (no sweep task: state is computed, G4 lesson) ---------
    @property
    def is_matured(self) -> bool:
        """Lock window has elapsed — the only gate for credit/withdrawal."""
        return self.matures_at <= timezone.now()

    @property
    def is_withdrawable(self) -> bool:
        """A5 hard rule: nothing is ever withdrawable while the lock runs."""
        return self.status == "active" and self.is_matured and self.amount > 0

    @property
    def credit_available(self) -> bool:
        """True when this term's maturity has not been credited yet."""
        return self.is_matured and self.status == "active" and self.credited_term < self.term_number

    @property
    def available_balance(self) -> Decimal:
        """Withdrawable balance = current capital (incl. rolled credit)."""
        return self.amount

    @property
    def terms_credited(self) -> int:
        return self.credited_term

    def __str__(self):
        return f"{self.user.email} - {self.amount} USDT / {self.lock_days}d ({self.status})"


class QuantumProfitCredit(TimeStampedModel):
    """Audit row for one admin-triggered maturity credit (A5 mechanism step)."""

    class Meta:
        db_table = "bots_quantum_profit_credits"
        ordering = ["-created_at"]
        # DB-level backstop for "one credit per term" (guards alongside the
        # service's select_for_update — mirrors the G4 CAS pattern).
        constraints = [
            models.UniqueConstraint(fields=["lock", "term_number"], name="uniq_credit_per_term"),
        ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lock = models.ForeignKey(InvestorLock, on_delete=models.CASCADE, related_name="credits")
    term_number = models.PositiveIntegerField()  # term the credit applied to

    pct_entered = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Admin-entered profit % from actual P/L (2-5% is guidance only)",
    )
    profit_amount = models.DecimalField(max_digits=20, decimal_places=8)  # amount credited
    capital_before = models.DecimalField(max_digits=20, decimal_places=8)
    capital_after = models.DecimalField(max_digits=20, decimal_places=8)

    credited_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quantum_profit_credits",
    )

    def __str__(self):
        return (
            f"{self.lock_id} term {self.term_number}: +{self.pct_entered}% ({self.profit_amount})"
        )


class QuantumWithdrawalRequest(TimeStampedModel):
    """Post-lock withdrawal request with admin payout approval (A5)."""

    class Meta:
        db_table = "bots_quantum_withdrawal_requests"
        ordering = ["-requested_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["status", "-requested_at"]),  # admin queue + 7-day SLA age
        ]

    STATUS_CHOICES = [
        ("pending", "Pending"),  # awaiting admin decision (SLA: <= 7 days)
        ("approved", "Approved"),  # admin entered payout incl. chain fees; ledger debited
        ("rejected", "Rejected"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="quantum_withdrawal_requests"
    )
    lock = models.ForeignKey(
        InvestorLock, on_delete=models.CASCADE, related_name="withdrawal_requests"
    )

    amount_requested = models.DecimalField(max_digits=20, decimal_places=8)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True
    )

    # Admin decision fields (grill Q12: payout incl. chain fees entered by admin)
    admin_entered_payout = models.DecimalField(
        max_digits=20, decimal_places=8, null=True, blank=True
    )
    admin_notes = models.TextField(blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="decided_quantum_withdrawals",
    )
    payment_transaction = models.ForeignKey(
        "payments.PaymentTransaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quantum_withdrawal_requests",
    )

    requested_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.email} - {self.amount_requested} USDT ({self.status})"


# ==================== PAIR CONFIG (Keep Your Model) ====================


class PairConfig(TimeStampedModel):
    """Pair configuration model (preserved from your code)"""

    class Meta:
        db_table = "bots_pair_configs"
        unique_together = ["user", "pair_symbol", "bot_type"]

    amount_choices = [("coin", "Coins"), ("dollar", "$")]
    order_choices = [("market", "Market Order"), ("limit", "Limit Order")]
    SLTP_choices = [("percentage", "Percentage"), ("dollars", "Dollars")]
    entry_choices = [("buy", "BUY"), ("sell", "SELL"), ("both", "BOTH"), (None, "None")]
    exit_choices = [("tp", "TP"), ("sl", "SL"), ("both", "BOTH"), (None, "None")]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="pair_configs")
    pair_symbol = models.CharField(max_length=20, null=False, blank=False)
    slug = models.SlugField(null=True, blank=True)

    # NEW: Link to subscription
    subscription = models.ForeignKey(
        "payments.BotSubscription",
        on_delete=models.CASCADE,
        related_name="pair_configs",
        null=True,
        blank=True,
    )

    # NEW: Bot type this config belongs to
    bot_type = models.CharField(
        max_length=20,
        choices=[
            ("grid", "Grid Bot"),
            ("martingale", "Martingale Bot"),
            ("custom", "Custom Bot"),
        ],
        default="grid",
    )

    quantity = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    favor_levels = models.IntegerField(default=3, null=True, blank=True)
    against_levels = models.IntegerField(default=3, null=True, blank=True)
    favor_level_qty = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    against_level_qty = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    favor_level_difference = models.DecimalField(
        max_digits=8, decimal_places=4, null=True, blank=True
    )
    against_level_difference = models.DecimalField(
        max_digits=8, decimal_places=4, null=True, blank=True
    )

    Order_Type = models.CharField(max_length=10, default="market", choices=order_choices)
    Amount_Type = models.CharField(max_length=10, default="dollar", choices=amount_choices)
    SLTP_Type = models.CharField(max_length=10, default="dollar", choices=SLTP_choices)
    Stop_Loss = models.DecimalField(max_digits=20, decimal_places=8, blank=True, null=True)
    Take_Profit = models.DecimalField(max_digits=20, decimal_places=8, blank=True, null=True)

    RSI_Lower = models.FloatField(default=30, null=True, blank=True)
    RSI_Upper = models.FloatField(default=70, null=True, blank=True)

    RSI_Entry = models.CharField(max_length=10, choices=entry_choices, null=True, blank=True)
    BB_Entry = models.CharField(max_length=10, choices=entry_choices, null=True, blank=True)
    EMA_RSI_Entry = models.CharField(max_length=10, choices=entry_choices, null=True, blank=True)
    EMA_BB_Entry = models.CharField(max_length=10, choices=entry_choices, null=True, blank=True)
    BB_RSI_Entry = models.CharField(max_length=10, choices=entry_choices, null=True, blank=True)
    EMA_BB_RSI_Entry = models.CharField(max_length=10, choices=entry_choices, null=True, blank=True)

    BB_Exit = models.CharField(max_length=10, choices=exit_choices, null=True, blank=True)
    RSI_Exit = models.CharField(max_length=10, choices=exit_choices, null=True, blank=True)
    EMA_RSI_Exit = models.CharField(max_length=10, choices=exit_choices, null=True, blank=True)
    EMA_BB_Exit = models.CharField(max_length=10, choices=exit_choices, null=True, blank=True)
    BB_RSI_Exit = models.CharField(max_length=10, choices=exit_choices, null=True, blank=True)
    EMA_BB_RSI_Exit = models.CharField(max_length=10, choices=exit_choices, null=True, blank=True)
    SL_Exit = models.CharField(max_length=10, choices=exit_choices, null=True, blank=True)

    def __str__(self):
        return f"{self.slug} Config"


# ==================== INDICATOR (Keep Your Model) ====================


class Indicator(TimeStampedModel):
    """Technical indicator model (preserved from your code)"""

    class Meta:
        db_table = "bots_indicators"
        indexes = [models.Index(fields=["user", "Pair"])]

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
        return f"{self.user} {self.Pair} Indicator Data {self.id}"


# ==================== ORDER (Keep Your Model + New Links) ====================


class BotOrder(TimeStampedModel):
    """Bot execution order record (preserved from your code)."""

    class Meta:
        db_table = "bots_orders"
        ordering = ["-Time"]
        indexes = [
            models.Index(fields=["user", "Pair"]),
            models.Index(fields=["-Time"]),
        ]

    Time = models.DateTimeField()
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, null=True, blank=True, related_name="legacy_orders"
    )
    Pair = models.CharField(max_length=20, null=True, blank=True)

    # KEEP your relationships
    PairConfig = models.ForeignKey(PairConfig, on_delete=models.CASCADE, blank=True, null=True)
    Indicators = models.ForeignKey(Indicator, on_delete=models.CASCADE, blank=True, null=True)

    # Bot references (polymorphic)
    signal_bot = models.ForeignKey(
        SignalBot, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders"
    )
    grid_bot = models.ForeignKey(
        GridBot, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders"
    )
    martingale_bot = models.ForeignKey(
        MartingaleBot, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders"
    )
    quantum_ai_investment = models.ForeignKey(
        InvestorPortfolio, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders"
    )

    # Your existing fields
    Side = models.CharField(max_length=5, null=True, blank=True)
    Category = models.CharField(max_length=20, null=True, blank=True)
    Order_type = models.CharField(max_length=20, null=True, blank=True)
    Quantity = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    Price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    Exchange = models.CharField(max_length=20, blank=True, null=True)
    Take_Profit = models.DecimalField(max_digits=20, decimal_places=8, blank=True, null=True)
    Stop_Loss = models.DecimalField(max_digits=20, decimal_places=8, blank=True, null=True)
    Description = models.TextField(blank=True, null=True)
    Details = models.JSONField(blank=True, null=True)

    # --- Phase 1 (persistence): trade-record integrity --------------------
    # Additive + nullable only; never alters existing columns.  Lets a
    # restart attribute every order to its bot and tell open trades apart
    # from closed ones without re-querying the exchange.
    STATUS_CHOICES = [("open", "Open"), ("closed", "Closed")]
    bot_type = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        db_index=True,
        help_text="Owning bot kind: grid|martingale|quantum_ai|signal|custom",
    )
    bot_id = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        db_index=True,
        help_text="Uniform pointer to the owning bot's pk (see also signal_bot/"
        "grid_bot/martingale_bot FKs, which stay authoritative when resolvable)",
    )
    Reason = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Structured entry reason (strategy signal reason)",
    )
    Status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default="closed",
        help_text="open = trade still live, closed = flat. Default closed so "
        "legacy rows never masquerade as open trades.",
    )
    Realized_PnL = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        null=True,
        blank=True,
        help_text="Realized P/L of the trade this record closes (exit records)",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if self._state.adding:
            self.Time = timezone.now()

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user} - {self.Pair} - {self.Side} - {self.Price} - {self.Time}"
