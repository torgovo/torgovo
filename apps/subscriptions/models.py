"""
Telegram signals subscription models
"""
import uuid
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from core.models import TimeStampedModel, SoftDeleteModel


class TelegramSignalPlan(TimeStampedModel):
    """
    Available Telegram signal subscription plans.
    """
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True)
    description = models.TextField()
    price_monthly = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    price_quarterly = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    price_yearly = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    features = models.JSONField(default=list)
    signals_per_day = models.PositiveIntegerField(default=10)
    exchanges_covered = models.JSONField(default=list)
    risk_level = models.CharField(
        max_length=20,
        choices=[
            ('conservative', 'Conservative'),
            ('moderate', 'Moderate'),
            ('aggressive', 'Aggressive'),
        ],
        default='moderate'
    )
    success_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    max_subscribers = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    trial_days = models.PositiveIntegerField(default=7)

    class Meta:
        db_table = 'subscriptions_telegram_plans'
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['is_active']),
            models.Index(fields=['risk_level']),
        ]

    def __str__(self):
        return f"{self.name} (${self.price_monthly}/month)"


class TelegramChannel(TimeStampedModel):
    """
    Telegram channels for signal distribution.
    """
    CHANNEL_TYPES = [
        ('signals', 'Trading Signals'),
        ('analysis', 'Market Analysis'),
        ('news', 'Market News'),
        ('education', 'Trading Education'),
        ('premium', 'Premium Content'),
    ]

    name = models.CharField(max_length=100, unique=True)
    channel_id = models.CharField(max_length=50, unique=True)  # @channel_username
    channel_type = models.CharField(max_length=20, choices=CHANNEL_TYPES)
    invite_link = models.URLField()
    description = models.TextField()
    member_count = models.PositiveIntegerField(default=0)
    is_private = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    required_plan_id = models.PositiveIntegerField(null=True, blank=True)
    admin_bot_token = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = 'subscriptions_telegram_channels'
        indexes = [
            models.Index(fields=['channel_id']),
            models.Index(fields=['channel_type']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.name} (@{self.channel_id})"


class TelegramSubscription(SoftDeleteModel):
    """
    User subscriptions to Telegram signal channels.
    """
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
        ('suspended', 'Suspended'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='telegram_subscriptions'
    )
    plan = models.ForeignKey(
        TelegramSignalPlan,
        on_delete=models.CASCADE,
        related_name='subscriptions'
    )
    channels = models.ManyToManyField(TelegramChannel, through='TelegramSubscriptionChannel')
    telegram_handle = models.CharField(max_length=50, help_text="@username without @")
    telegram_user_id = models.BigIntegerField(null=True, blank=True)

    # Subscription details
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    auto_renew = models.BooleanField(default=True)

    # Billing
    billing_cycle = models.CharField(
        max_length=20,
        choices=[
            ('monthly', 'Monthly'),
            ('quarterly', 'Quarterly'),
            ('yearly', 'Yearly'),
        ],
        default='monthly'
    )
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(
        max_length=20,
        choices=[
            ('stripe', 'Stripe'),
            ('crypto', 'Cryptocurrency'),
            ('bank', 'Bank Transfer'),
        ],
        default='stripe'
    )
    stripe_subscription_id = models.CharField(max_length=100, blank=True)

    # Usage tracking
    signals_received = models.PositiveIntegerField(default=0)
    last_signal_date = models.DateTimeField(null=True, blank=True)
    success_rate_tracked = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta:
        db_table = 'subscriptions_telegram_subscriptions'
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['plan', 'status']),
            models.Index(fields=['end_date']),
            models.Index(fields=['telegram_handle']),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.plan.name} ({self.status})"

    @property
    def is_active(self):
        """Check if subscription is currently active."""
        from django.utils import timezone
        return (
            self.status == 'active' and
            self.end_date >= timezone.now().date()
        )

    def extend_subscription(self, days):
        """Extend subscription by specified days."""
        from django.utils import timezone
        import datetime

        if self.end_date < timezone.now().date():
            self.end_date = timezone.now().date()

        self.end_date += datetime.timedelta(days=days)
        self.status = 'active'
        self.save()


class TelegramSubscriptionChannel(TimeStampedModel):
    """
    Many-to-many relationship between subscriptions and channels.
    """
    subscription = models.ForeignKey(TelegramSubscription, on_delete=models.CASCADE)
    channel = models.ForeignKey(TelegramChannel, on_delete=models.CASCADE)
    joined_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'subscriptions_subscription_channels'
        unique_together = ['subscription', 'channel']


class TradingSignal(TimeStampedModel):
    """
    Individual trading signals distributed to subscribers.
    """
    SIGNAL_TYPES = [
        ('buy', 'Buy Signal'),
        ('sell', 'Sell Signal'),
        ('hold', 'Hold Signal'),
        ('close', 'Close Position'),
        ('warning', 'Market Warning'),
    ]

    TIMEFRAMES = [
        ('1m', '1 Minute'),
        ('5m', '5 Minutes'),
        ('15m', '15 Minutes'),
        ('1h', '1 Hour'),
        ('4h', '4 Hours'),
        ('1d', '1 Day'),
        ('1w', '1 Week'),
    ]

    plan = models.ForeignKey(TelegramSignalPlan, on_delete=models.CASCADE)
    channels = models.ManyToManyField(TelegramChannel)

    # Signal details
    signal_type = models.CharField(max_length=10, choices=SIGNAL_TYPES)
    trading_pair = models.CharField(max_length=20)
    exchange = models.CharField(max_length=20)
    timeframe = models.CharField(max_length=5, choices=TIMEFRAMES)

    # Price information
    entry_price = models.DecimalField(max_digits=20, decimal_places=8)
    stop_loss = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    take_profit_1 = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    take_profit_2 = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    take_profit_3 = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)

    # Additional details
    confidence_level = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        default=7,
        help_text="1-10 confidence score"
    )
    risk_reward_ratio = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    analysis = models.TextField()
    chart_image_url = models.URLField(blank=True)

    # Signal metadata
    source = models.CharField(max_length=50, default='manual')
    ai_generated = models.BooleanField(default=False)
    success_prediction = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    # Tracking
    published_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    total_views = models.PositiveIntegerField(default=0)
    total_clicks = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'subscriptions_trading_signals'
        indexes = [
            models.Index(fields=['plan', 'published_at']),
            models.Index(fields=['signal_type', 'published_at']),
            models.Index(fields=['trading_pair']),
            models.Index(fields=['expires_at']),
        ]

    def __str__(self):
        return f"{self.signal_type.upper()} {self.trading_pair} - {self.plan.name}"

    @property
    def is_expired(self):
        """Check if signal has expired."""
        from django.utils import timezone
        return timezone.now() > self.expires_at


class SignalResult(TimeStampedModel):
    """
    Results and performance tracking for trading signals.
    """
    signal = models.OneToOneField(TradingSignal, on_delete=models.CASCADE)

    # Result details
    result_type = models.CharField(
        max_length=20,
        choices=[
            ('profit', 'Profit'),
            ('loss', 'Loss'),
            ('breakeven', 'Break Even'),
            ('expired', 'Expired'),
            ('cancelled', 'Cancelled'),
        ]
    )
    entry_price_actual = models.DecimalField(max_digits=20, decimal_places=8)
    exit_price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    profit_loss = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    profit_loss_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    # Timing
    entry_time = models.DateTimeField()
    exit_time = models.DateTimeField(null=True, blank=True)
    duration_hours = models.PositiveIntegerField(null=True, blank=True)

    # Performance metrics
    max_profit = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    max_loss = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    hit_take_profit = models.BooleanField(default=False)
    hit_stop_loss = models.BooleanField(default=False)

    # Verification
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_signals'
    )
    verification_notes = models.TextField(blank=True)

    class Meta:
        db_table = 'subscriptions_signal_results'
        indexes = [
            models.Index(fields=['signal', 'result_type']),
            models.Index(fields=['result_type']),
            models.Index(fields=['exit_time']),
        ]

    def __str__(self):
        return f"{self.signal} - {self.result_type} ({self.profit_loss_percent}%)"


class SignalStatistics(TimeStampedModel):
    """
    Aggregated statistics for signal performance.
    """
    plan = models.ForeignKey(TelegramSignalPlan, on_delete=models.CASCADE)
    date = models.DateField()

    # Daily stats
    total_signals = models.PositiveIntegerField(default=0)
    successful_signals = models.PositiveIntegerField(default=0)
    profit_signals = models.PositiveIntegerField(default=0)
    loss_signals = models.PositiveIntegerField(default=0)

    # Performance
    total_profit_loss = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    average_profit_loss = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    win_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    max_profit_loss = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    min_profit_loss = models.DecimalField(max_digits=20, decimal_places=8, default=0)

    # Engagement
    total_subscribers = models.PositiveIntegerField(default=0)
    active_subscribers = models.PositiveIntegerField(default=0)
    total_views = models.PositiveIntegerField(default=0)
    total_clicks = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'subscriptions_signal_statistics'
        unique_together = ['plan', 'date']
        indexes = [
            models.Index(fields=['plan', 'date']),
            models.Index(fields=['date']),
        ]

    def __str__(self):
        return f"{self.plan.name} - {self.date} ({self.total_signals} signals)"