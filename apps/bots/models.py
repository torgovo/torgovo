"""
Bot models for Torgovo Crypto Trading Platform
"""
import uuid
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.utils import timezone
from core.models import TimeStampedModel, SoftDeleteModel


class WebhookAlert(SoftDeleteModel):
    """
    TradingView webhook alert bot.
    Receives webhook signals and executes trades automatically.
    """
    EXCHANGE_CHOICES = [
        ('binance', 'Binance'),
        ('bybit', 'Bybit'),
        ('okx', 'OKX'),
        ('mexc', 'MEXC'),
        ('alpaca', 'Alpaca'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='webhook_alerts'
    )
    bot_name = models.CharField(max_length=255)
    webhook_url =  models.URLField(unique=True, blank=True)
    secret_key = models.CharField(max_length=255, blank=True)
    exchange_name = models.CharField(max_length=50, choices=EXCHANGE_CHOICES)
    trading_pair = models.CharField(max_length=20)  # e.g., BTC/USDT
    
    # Trading settings
    default_amount = models.DecimalField(max_digits=20, decimal_places=8)
    take_profit_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    stop_loss_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    
    # Status tracking
    is_active = models.BooleanField(default=True)
    last_triggered = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    
    # Statistics
    total_trades = models.PositiveIntegerField(default=0)
    successful_trades = models.PositiveIntegerField(default=0)
    total_profit_loss = models.DecimalField(max_digits=20, decimal_places=8, default=0)

    class Meta:
        db_table = 'bots_webhook_alerts'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['exchange_name', 'trading_pair']),
        ]
    
    def __str__(self):
        return f"{self.bot_name} - {self.trading_pair}"
    
    @property
    def success_rate(self):
        """Calculate success rate percentage."""
        if self.total_trades == 0:
            return 0
        return round((self.successful_trades / self.total_trades) * 100, 2)


class GridBot(SoftDeleteModel):
    """
    Grid trading bot with favor and against levels.
    """
    EXCHANGE_CHOICES = WebhookAlert.EXCHANGE_CHOICES

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='grid_bots'
    )
    bot_name = models.CharField(max_length=255)
    exchange_name = models.CharField(max_length=50, choices=EXCHANGE_CHOICES)
    trading_pair = models.CharField(max_length=20)
    
    # Grid configuration
    base_amount = models.DecimalField(max_digits=20, decimal_places=8)
    favor_levels = models.PositiveIntegerField()  # Number of buy levels
    against_levels = models.PositiveIntegerField()  # Number of sell levels
    level_spacing_percent = models.DecimalField(max_digits=5, decimal_places=2)
    
    # Risk management
    take_profit_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    stop_loss_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    
    # Bot state
    is_running = models.BooleanField(default=False)
    started_at = models.DateTimeField(null=True, blank=True)
    stopped_at = models.DateTimeField(null=True, blank=True)
    
    # Statistics
    current_profit_loss = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    total_invested = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    total_trades_executed = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'bots_grid_bots'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_running']),
            models.Index(fields=['exchange_name', 'trading_pair']),
        ]
    
    def __str__(self):
        return f"{self.bot_name} - {self.trading_pair}"


class MartingaleBot(SoftDeleteModel):
    """
    Martingale trading bot with doubling logic on against levels.
    """
    EXCHANGE_CHOICES = WebhookAlert.EXCHANGE_CHOICES

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='martingale_bots'
    )
    bot_name = models.CharField(max_length=255)
    exchange_name = models.CharField(max_length=50, choices=EXCHANGE_CHOICES)
    trading_pair = models.CharField(max_length=20)
    
    # Martingale configuration
    base_amount = models.DecimalField(max_digits=20, decimal_places=8)
    favor_levels = models.PositiveIntegerField()
    against_levels = models.PositiveIntegerField()
    level_spacing_percent = models.DecimalField(max_digits=5, decimal_places=2)
    multiplier_factor = models.DecimalField(max_digits=5, decimal_places=2, default=2.0)  # Doubling factor
    
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
    current_profit_loss = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    total_invested = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    total_trades_executed = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'bots_martingale_bots'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_running']),
            models.Index(fields=['exchange_name', 'trading_pair']),
        ]
    
    def __str__(self):
        return f"{self.bot_name} - {self.trading_pair}"


class QuantumAIBot(SoftDeleteModel):
    """
    Quantum AI bot for deposit-based P&L tracking.
    Users deposit funds and track profit/loss.
    """
    RISK_LEVELS = [
        ('low', 'Low Risk'),
        ('medium', 'Medium Risk'),
        ('high', 'High Risk'),
    ]
    
    COMPOUND_FREQUENCIES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='quantum_ai_bots'
    )
    bot_name = models.CharField(max_length=255)
    
    # Bot settings
    auto_compound = models.BooleanField(default=False)
    compound_frequency = models.CharField(max_length=20, choices=COMPOUND_FREQUENCIES, default='monthly')
    risk_level = models.CharField(max_length=20, choices=RISK_LEVELS, default='medium')
    
    # Financial tracking
    total_deposited = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    current_profit_loss = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    
    # Status
    is_active = models.BooleanField(default=False)
    last_profit_update = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'bots_quantum_ai_bots'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.bot_name} - {self.user.email}"
    
    @property
    def roi_percent(self):
        """Calculate ROI percentage."""
        if self.total_deposited == 0:
            return 0
        return round((self.current_profit_loss / self.total_deposited) * 100, 2)


class Indicator(TimeStampedModel):
    """
    Simplified indicator snapshot model for bot trading state tracking.
    Stores indicator values at the time of order execution.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    Pair = models.CharField(max_length=20)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='indicators'
    )
    
    # Indicator values
    EMA = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    RSI = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    Prev_RSI = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    Color = models.CharField(max_length=20, blank=True)  # RSI color state
    Prev_Color = models.CharField(max_length=20, blank=True)
    BB = models.CharField(max_length=100, blank=True)  # Bollinger Band state
    TSI = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    ADX = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        db_table = 'bots_indicators'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'Pair']),
            models.Index(fields=['-created_at']),
        ]
    
    def __str__(self):
        return f"Indicators for {self.Pair} - {self.user.email}"


    def __str__(self):
        return f"Indicators for {self.Pair} - {self.user.email}"


class PairConfig(TimeStampedModel):
    amount_choices = [
        ('coin', 'Coins'),
        ('dollar', '$')
    ]
    order_choices = [
        ('market', 'Market Order'),
        ('limit', 'Limit Order')
    ]
    SLTP_choices = [
        ('percentage', 'Percentage'),
        ('dollars', 'Dollars'),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    entry_choices = [('buy', 'BUY'), ('sell', 'SELL'), ('both', 'BOTH'), (None, 'None')]
    exit_choices = [('tp', 'TP'), ('sl', 'SL'), ('both', 'BOTH'), (None, 'None')]

    pair_symbol = models.CharField(max_length=20, null=False, blank=False)
    slug = models.SlugField(null=True,blank=True)
    quantity = models.FloatField(null=True, blank=True)

    # Number of favor and against levels
    favor_levels = models.IntegerField(default=3, null=True, blank=True)
    against_levels = models.IntegerField(default=3, null=True, blank=True)

    # Amount of favor and against Levels
    favor_level_qty  = models.FloatField(null=True, blank=True)
    against_level_qty = models.FloatField(null=True, blank=True)

    # Percentage difference among each level (favor+ against)
    favor_level_difference = models.FloatField(null=True, blank=True)
    against_level_difference = models.FloatField(null=True, blank=True)

    Order_Type = models.CharField(max_length=10, default='market', choices=order_choices, blank=False, null=False)
    Amount_Type = models.CharField(max_length=10, default='dollar', choices=amount_choices, blank=False, null=False)

    SLTP_Type = models.CharField(max_length=10, default='dollar', choices=SLTP_choices, blank=False, null=False)
    Stop_Loss = models.FloatField(blank=True, null=True)
    Take_Profit = models.FloatField(blank=True, null=True)

    """ RSI Values"""
    RSI_Lower = models.FloatField(default=30, null=True, blank=True)
    RSI_Upper = models.FloatField(default=70, null=True, blank=True)
    """ Possible Combo
    EMA + RSI
    EMA + BB
    BB + RSI

    """
    RSI_Entry = models.CharField(max_length=10, default='None', choices=entry_choices, null=True, blank=True)
    BB_Entry = models.CharField(max_length=10,default='None', choices=entry_choices, null=True, blank=True)
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

    class Meta:
        db_table = 'bots_pair_configs'

    def __str__(self):
        return f"{self.slug} Config"


class Order(TimeStampedModel):
    """
    Trading order executed by bots or webhooks.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('filled', 'Filled'),
        ('cancelled', 'Cancelled'),
        ('failed', 'Failed'),
    ]
    
    SIDE_CHOICES = [
        ('buy', 'Buy'),
        ('sell', 'Sell'),
    ]
    
    ORDER_TYPE_CHOICES = [
        ('market', 'Market'),
        ('limit', 'Limit'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    Time = models.DateTimeField(default=timezone.now)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='orders'
    )
    
    # Order details
    Pair = models.CharField(max_length=20)
    PairConfig = models.ForeignKey(
        'PairConfig',
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name='orders'
    )
    Indicators = models.ForeignKey(
        'Indicator',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders'
    )
    Side = models.CharField(max_length=10, choices=SIDE_CHOICES)
    Category = models.CharField(max_length=50, blank=True)
    Order_type = models.CharField(max_length=20, choices=ORDER_TYPE_CHOICES, default='market')
    Quantity = models.DecimalField(max_digits=20, decimal_places=8)
    Price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    Exchange = models.CharField(max_length=50)
    
    # Risk management
    Take_Profit = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    Stop_Loss = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    
    # Execution details
    executed_price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    fees = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    Description = models.TextField(blank=True)
    Details = models.JSONField(default=dict, blank=True)
    
    # Bot associations (nullable - order can be manual or from any bot type)
    webhook_alert = models.ForeignKey(
        'WebhookAlert',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders'
    )
    grid_bot = models.ForeignKey(
        'GridBot',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders'
    )
    martingale_bot = models.ForeignKey(
        'MartingaleBot',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders'
    )
    quantum_bot = models.ForeignKey(
        'QuantumAIBot',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders'
    )

    class Meta:
        db_table = 'bots_orders'
        ordering = ['-Time']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['Exchange', 'Pair']),
            models.Index(fields=['-Time']),
        ]
    
    def __str__(self):
        return f"{self.Side} {self.Quantity} {self.pair} @ {self.Exchange}"


class TechnicalIndicator(TimeStampedModel):
    """
    Store technical indicator values (EMA, RSI, BB, etc.) from TradingView.
    """
    INDICATOR_TYPES = [
        ('ema', 'EMA'),
        ('rsi', 'RSI'),
        ('bb', 'Bollinger Bands'),
        ('macd', 'MACD'),
        ('adx', 'ADX'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pair = models.CharField(max_length=20)
    exchange = models.CharField(max_length=50)
    indicator_type = models.CharField(max_length=20, choices=INDICATOR_TYPES)
    timeframe = models.CharField(max_length=10)  # e.g., '1h', '4h', '1d'
    value = models.DecimalField(max_digits=20, decimal_places=8)
    timestamp = models.DateTimeField(default=timezone.now)
    additional_data = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'bots_technical_indicators'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['pair', 'exchange', 'indicator_type']),
            models.Index(fields=['-timestamp']),
        ]
    
    def __str__(self):
        return f"{self.indicator_type.upper()} for {self.pair} @ {self.exchange}"


class Signal(TimeStampedModel):
    indicator1 = models.CharField(max_length=30, null=True, blank=True)
    indicator2 = models.CharField(max_length=30, null=True, blank=True)
    message = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'bots_signals'


class RunningThreads(TimeStampedModel):
    thread_id = models.CharField(max_length=255, null=True, blank=True)
    keyPair = models.TextField(null=True,blank=True)

    class Meta:
        db_table = 'bots_running_threads'




