"""
Trading bot models for Torgovo Crypto Trading Platform
"""
import uuid
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from core.models import TimeStampedModel, SoftDeleteModel
from core.utils import generate_secret_key, validate_trading_pair


class Exchange(models.Model):
    """Supported cryptocurrency exchanges."""
    EXCHANGE_CHOICES = [
        ('binance', 'Binance'),
        ('bybit', 'Bybit'),
        ('okx', 'OKX'),
        ('mexc', 'MEXC'),
        ('alpaca', 'Alpaca'),
    ]

    name = models.CharField(max_length=20, choices=EXCHANGE_CHOICES, unique=True)
    display_name = models.CharField(max_length=50)
    api_base_url = models.URLField()
    websocket_url = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)
    supports_testnet = models.BooleanField(default=True)
    supported_features = models.JSONField(default=list)  # ['spot', 'futures', 'margin']
    rate_limit_per_minute = models.PositiveIntegerField(default=1200)
    fee_rates = models.JSONField(default=dict)  # {'maker': 0.001, 'taker': 0.001}
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bots_exchanges'

    def __str__(self):
        return self.display_name


class TradingPair(TimeStampedModel):
    """Trading pairs available on exchanges."""
    exchange = models.ForeignKey(Exchange, on_delete=models.CASCADE, related_name='pairs')
    symbol = models.CharField(max_length=20)
    base_asset = models.CharField(max_length=10)
    quote_asset = models.CharField(max_length=10)
    is_active = models.BooleanField(default=True)
    min_order_size = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal('0.001'))
    max_order_size = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal('1000000'))
    price_precision = models.PositiveIntegerField(default=8)
    quantity_precision = models.PositiveIntegerField(default=8)
    maker_fee = models.DecimalField(max_digits=6, decimal_places=4, default=Decimal('0.001'))
    taker_fee = models.DecimalField(max_digits=6, decimal_places=4, default=Decimal('0.001'))

    class Meta:
        db_table = 'bots_trading_pairs'
        unique_together = ['exchange', 'symbol']
        indexes = [
            models.Index(fields=['exchange', 'symbol']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.symbol} on {self.exchange.name}"


class WebhookAlert(SoftDeleteModel):
    """TradingView webhook alert configuration."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='webhook_alerts'
    )
    bot_name = models.CharField(max_length=100)
    webhook_url = models.URLField(unique=True)
    secret_key = models.CharField(max_length=64, unique=True)
    exchange_name = models.CharField(max_length=20, choices=Exchange.EXCHANGE_CHOICES)
    trading_pair = models.CharField(max_length=20)
    default_amount = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        validators=[MinValueValidator(Decimal('0.00000001'))]
    )
    take_profit_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('5.00'),
        validators=[MinValueValidator(Decimal('0.1')), MaxValueValidator(Decimal('100'))]
    )
    stop_loss_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('3.00'),
        validators=[MinValueValidator(Decimal('0.1')), MaxValueValidator(Decimal('100'))]
    )
    is_active = models.BooleanField(default=True)
    last_triggered = models.DateTimeField(null=True, blank=True)
    total_trades = models.PositiveIntegerField(default=0)
    successful_trades = models.PositiveIntegerField(default=0)
    total_profit_loss = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal('0'))
    last_error = models.TextField(blank=True)

    class Meta:
        db_table = 'bots_webhook_alerts'
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['exchange_name']),
            models.Index(fields=['secret_key']),
        ]

    def __str__(self):
        return f"{self.bot_name} - {self.user.email}"

    def save(self, *args, **kwargs):
        """Generate webhook URL and secret key if not exists."""
        if not self.secret_key:
            self.secret_key = generate_secret_key(64)

        if not self.webhook_url:
            self.webhook_url = f"{settings.BASE_URL}/api/webhooks/tradingview/{self.id}/"

        super().save(*args, **kwargs)

    @property
    def success_rate(self):
        """Calculate success rate of trades."""
        if self.total_trades == 0:
            return 0.0
        return (self.successful_trades / self.total_trades) * 100


class GridBot(SoftDeleteModel):
    """Grid trading bot configuration."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='grid_bots'
    )
    bot_name = models.CharField(max_length=100)
    exchange_name = models.CharField(max_length=20, choices=Exchange.EXCHANGE_CHOICES)
    trading_pair = models.CharField(max_length=20)
    base_amount = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        validators=[MinValueValidator(Decimal('0.00000001'))]
    )
    favor_levels = models.PositiveIntegerField(
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(50)]
    )
    against_levels = models.PositiveIntegerField(
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(50)]
    )
    level_spacing_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('1.00'),
        validators=[MinValueValidator(Decimal('0.1')), MaxValueValidator(Decimal('50'))]
    )
    take_profit_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('5.00'),
        validators=[MinValueValidator(Decimal('0.1')), MaxValueValidator(Decimal('100'))]
    )
    stop_loss_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('3.00'),
        validators=[MinValueValidator(Decimal('0.1')), MaxValueValidator(Decimal('100'))]
    )
    is_running = models.BooleanField(default=False)
    started_at = models.DateTimeField(null=True, blank=True)
    stopped_at = models.DateTimeField(null=True, blank=True)
    current_profit_loss = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal('0'))
    total_invested = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal('0'))
    total_trades_executed = models.PositiveIntegerField(default=0)
    current_grid_levels = models.JSONField(default=list)  # Active grid levels
    last_execution_price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)

    class Meta:
        db_table = 'bots_grid'
        indexes = [
            models.Index(fields=['user', 'is_running']),
            models.Index(fields=['exchange_name', 'trading_pair']),
        ]

    def __str__(self):
        return f"{self.bot_name} - {self.user.email}"

    def calculate_grid_levels(self, current_price):
        """Calculate grid levels based on current price."""
        spacing = current_price * (self.level_spacing_percent / Decimal('100'))
        levels = []

        # Calculate favor levels (below current price)
        for i in range(1, self.favor_levels + 1):
            level_price = current_price - (i * spacing)
            levels.append({
                'price': level_price,
                'type': 'buy',
                'amount': self.base_amount,
                'executed': False
            })

        # Calculate against levels (above current price)
        for i in range(1, self.against_levels + 1):
            level_price = current_price + (i * spacing)
            levels.append({
                'price': level_price,
                'type': 'sell',
                'amount': self.base_amount,
                'executed': False
            })

        return sorted(levels, key=lambda x: x['price'])


class MartingaleBot(SoftDeleteModel):
    """Martingale trading bot configuration."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='martingale_bots'
    )
    bot_name = models.CharField(max_length=100)
    exchange_name = models.CharField(max_length=20, choices=Exchange.EXCHANGE_CHOICES)
    trading_pair = models.CharField(max_length=20)
    base_amount = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        validators=[MinValueValidator(Decimal('0.00000001'))]
    )
    favor_levels = models.PositiveIntegerField(
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(20)]
    )
    against_levels = models.PositiveIntegerField(
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(20)]
    )
    level_spacing_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('1.50'),
        validators=[MinValueValidator(Decimal('0.1')), MaxValueValidator(Decimal('50'))]
    )
    multiplier_factor = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('2.00'),
        validators=[MinValueValidator(Decimal('1.1')), MaxValueValidator(Decimal('10'))]
    )
    take_profit_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('8.00'),
        validators=[MinValueValidator(Decimal('0.1')), MaxValueValidator(Decimal('100'))]
    )
    stop_loss_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('5.00'),
        validators=[MinValueValidator(Decimal('0.1')), MaxValueValidator(Decimal('100'))]
    )
    is_running = models.BooleanField(default=False)
    started_at = models.DateTimeField(null=True, blank=True)
    stopped_at = models.DateTimeField(null=True, blank=True)
    current_profit_loss = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal('0'))
    total_invested = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal('0'))
    total_trades_executed = models.PositiveIntegerField(default=0)
    current_level = models.PositiveIntegerField(default=0)  # Current martingale level
    max_level_reached = models.PositiveIntegerField(default=0)
    last_execution_price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)

    class Meta:
        db_table = 'bots_martingale'
        indexes = [
            models.Index(fields=['user', 'is_running']),
            models.Index(fields=['exchange_name', 'trading_pair']),
        ]

    def __str__(self):
        return f"{self.bot_name} - {self.user.email}"

    def calculate_position_size(self, level):
        """Calculate position size for martingale level."""
        base_amount = float(self.base_amount)
        multiplier = float(self.multiplier_factor)
        return base_amount * (multiplier ** level)


class QuantumAIBot(SoftDeleteModel):
    """Quantum AI trading bot configuration."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='quantum_ai_bots'
    )
    bot_name = models.CharField(max_length=100)
    total_deposited = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        default=Decimal('0')
    )
    current_profit_loss = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal('0'))
    is_active = models.BooleanField(default=True)
    last_profit_update = models.DateTimeField(null=True, blank=True)
    auto_compound = models.BooleanField(default=False)
    compound_frequency = models.CharField(
        max_length=20,
        choices=[
            ('daily', 'Daily'),
            ('weekly', 'Weekly'),
            ('monthly', 'Monthly'),
        ],
        default='weekly'
    )
    risk_level = models.CharField(
        max_length=20,
        choices=[
            ('conservative', 'Conservative'),
            ('moderate', 'Moderate'),
            ('aggressive', 'Aggressive'),
        ],
        default='moderate'
    )

    class Meta:
        db_table = 'bots_quantum_ai'
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['risk_level']),
        ]

    def __str__(self):
        return f"{self.bot_name} - {self.user.email}"

    @property
    def roi_percent(self):
        """Calculate Return on Investment percentage."""
        if self.total_deposited == 0:
            return 0.0
        return (self.current_profit_loss / self.total_deposited) * 100


class BlockchainAddress(TimeStampedModel):
    """Blockchain addresses for Quantum AI deposits."""
    COIN_CHOICES = [
        ('USDT', 'Tether'),
        ('USDC', 'USD Coin'),
        ('BTC', 'Bitcoin'),
        ('ETH', 'Ethereum'),
        ('BNB', 'Binance Coin'),
    ]

    BLOCKCHAIN_CHOICES = [
        ('BEP20', 'Binance Smart Chain'),
        ('ERC20', 'Ethereum'),
        ('TRC20', 'TRON'),
        ('SOL', 'Solana'),
        ('APTOS', 'Aptos'),
        ('POLYGON', 'Polygon'),
        ('Bitcoin', 'Bitcoin Network'),
    ]

    coin_type = models.CharField(max_length=10, choices=COIN_CHOICES)
    blockchain = models.CharField(max_length=20, choices=BLOCKCHAIN_CHOICES)
    address = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    admin_only_configurable = models.BooleanField(default=True)

    class Meta:
        db_table = 'bots_blockchain_addresses'
        unique_together = ['coin_type', 'blockchain']

    def __str__(self):
        return f"{self.coin_type} on {self.blockchain}"


class Deposit(SoftDeleteModel):
    """Cryptocurrency deposits for Quantum AI bots."""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='deposits'
    )
    quantum_bot = models.ForeignKey(
        QuantumAIBot,
        on_delete=models.CASCADE,
        related_name='deposits'
    )
    amount = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        validators=[MinValueValidator(Decimal('0.00000001'))]
    )
    coin_type = models.CharField(max_length=10, choices=BlockchainAddress.COIN_CHOICES)
    blockchain = models.CharField(max_length=20, choices=BlockchainAddress.BLOCKCHAIN_CHOICES)
    from_address = models.CharField(max_length=255)
    transaction_hash = models.CharField(max_length=255, unique=True)
    screenshot = models.ImageField(
        upload_to='deposits/screenshots/%Y/%m/%d/',
        blank=True,
        null=True
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    admin_notes = models.TextField(blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_deposits'
    )
    verified_on_blockchain = models.BooleanField(default=False)
    blockchain_confirmation_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'bots_deposits'
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['quantum_bot', 'status']),
            models.Index(fields=['transaction_hash']),
        ]

    def __str__(self):
        return f"{self.amount} {self.coin_type} - {self.user.email}"


class Order(TimeStampedModel):
    """Trade execution records."""
    CATEGORY_CHOICES = [
        ('webhook', 'Webhook Alert'),
        ('grid', 'Grid Bot'),
        ('martingale', 'Martingale Bot'),
        ('quantum', 'Quantum AI Bot'),
    ]

    SIDE_CHOICES = [
        ('buy', 'Buy'),
        ('sell', 'Sell'),
    ]

    ORDER_TYPE_CHOICES = [
        ('market', 'Market'),
        ('limit', 'Limit'),
        ('stop', 'Stop'),
        ('stop_limit', 'Stop Limit'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='orders'
    )
    pair = models.CharField(max_length=20)
    exchange = models.CharField(max_length=20, choices=Exchange.EXCHANGE_CHOICES)
    side = models.CharField(max_length=5, choices=SIDE_CHOICES)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    order_type = models.CharField(max_length=20, choices=ORDER_TYPE_CHOICES, default='market')
    quantity = models.DecimalField(max_digits=20, decimal_places=8)
    price = models.DecimalField(max_digits=20, decimal_places=8)
    executed_price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    exchange_order_id = models.CharField(max_length=100, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('filled', 'Filled'),
            ('cancelled', 'Cancelled'),
            ('failed', 'Failed'),
        ],
        default='pending'
    )
    take_profit = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    stop_loss = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    profit_loss = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal('0'))
    fees = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal('0'))
    description = models.TextField(blank=True)
    details = models.JSONField(default=dict)  # Additional trade data

    # Foreign keys to specific bot types (optional)
    webhook_alert = models.ForeignKey(
        WebhookAlert,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders'
    )
    grid_bot = models.ForeignKey(
        GridBot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders'
    )
    martingale_bot = models.ForeignKey(
        MartingaleBot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders'
    )
    quantum_bot = models.ForeignKey(
        QuantumAIBot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders'
    )

    class Meta:
        db_table = 'bots_orders'
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['pair', 'exchange']),
            models.Index(fields=['category', 'status']),
            models.Index(fields=['exchange_order_id']),
        ]

    def __str__(self):
        return f"{self.side} {self.quantity} {self.pair} - {self.user.email}"


class TechnicalIndicator(TimeStampedModel):
    """Technical indicators for trading analysis."""
    INDICATOR_TYPES = [
        ('EMA', 'Exponential Moving Average'),
        ('SMA', 'Simple Moving Average'),
        ('RSI', 'Relative Strength Index'),
        ('MACD', 'MACD'),
        ('BB', 'Bollinger Bands'),
        ('ATR', 'Average True Range'),
        ('ADX', 'Average Directional Index'),
        ('STOCH', 'Stochastic'),
        ('CCI', 'Commodity Channel Index'),
    ]

    pair = models.CharField(max_length=20)
    exchange = models.CharField(max_length=20, choices=Exchange.EXCHANGE_CHOICES)
    indicator_type = models.CharField(max_length=10, choices=INDICATOR_TYPES)
    timeframe = models.CharField(max_length=10)  # 1m, 5m, 1h, etc.
    value = models.DecimalField(max_digits=20, decimal_places=8)
    timestamp = models.DateTimeField()
    additional_data = models.JSONField(default=dict)  # Extra indicator-specific data

    class Meta:
        db_table = 'bots_technical_indicators'
        indexes = [
            models.Index(fields=['pair', 'exchange', 'indicator_type', 'timeframe']),
            models.Index(fields=['timestamp']),
        ]

    def __str__(self):
        return f"{self.indicator_type} {self.pair} - {self.value}"


class BotExecutionLog(TimeStampedModel):
    """Bot execution logs for monitoring and debugging."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='bot_execution_logs'
    )
    bot_type = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    bot_id = models.UUIDField()  # UUID of the specific bot
    action = models.CharField(max_length=50)  # start, stop, trade, error, etc.
    message = models.TextField()
    level = models.CharField(
        max_length=10,
        choices=[
            ('info', 'Info'),
            ('warning', 'Warning'),
            ('error', 'Error'),
            ('debug', 'Debug'),
        ],
        default='info'
    )
    data = models.JSONField(default=dict)  # Additional log data

    class Meta:
        db_table = 'bots_execution_logs'
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['bot_type', 'bot_id']),
            models.Index(fields=['level']),
        ]

    def __str__(self):
        return f"{self.bot_type} {self.bot_id} - {self.action}"


class PairConfig(TimeStampedModel):
    """Quantum AI pair configuration model for admin setup."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='pair_configs'
    )
    pair_symbol = models.CharField(max_length=20)
    slug = models.SlugField(max_length=50, unique=True)

    # Trading parameters
    quantity = models.FloatField(null=True, blank=True)
    favor_levels = models.IntegerField(default=3)
    against_levels = models.IntegerField(default=3)
    favor_level_qty = models.FloatField(null=True, blank=True)
    against_level_qty = models.FloatField(null=True, blank=True)
    favor_level_difference = models.FloatField(null=True, blank=True)
    against_level_difference = models.FloatField(null=True, blank=True)

    # Order configuration
    Order_Type = models.CharField(
        max_length=10,
        choices=[
            ('market', 'Market'),
            ('limit', 'Limit'),
        ],
        default='market'
    )
    Amount_Type = models.CharField(
        max_length=10,
        choices=[
            ('coin', 'Coin'),
            ('dollar', 'Dollar'),
        ],
        default='dollar'
    )
    SLTP_Type = models.CharField(
        max_length=20,
        choices=[
            ('percentage', 'Percentage'),
            ('dollars', 'Dollars'),
        ],
        default='dollars'
    )
    Stop_Loss = models.FloatField(null=True, blank=True)
    Take_Profit = models.FloatField(null=True, blank=True)

    # RSI Configuration
    RSI_Lower = models.FloatField(default=30.0)
    RSI_Upper = models.FloatField(default=70.0)
    RSI_Entry = models.CharField(
        max_length=10,
        choices=[
            ('buy', 'Buy'),
            ('sell', 'Sell'),
            ('both', 'Both'),
            ('None', 'None'),
        ],
        default='None'
    )

    # Bollinger Bands Configuration
    BB_Entry = models.CharField(
        max_length=10,
        choices=[
            ('buy', 'Buy'),
            ('sell', 'Sell'),
            ('both', 'Both'),
            ('None', 'None'),
        ],
        default='None'
    )

    # Combined Entry Signals
    EMA_RSI_Entry = models.CharField(
        max_length=10,
        choices=[
            ('buy', 'Buy'),
            ('sell', 'Sell'),
            ('both', 'Both'),
            ('None', 'None'),
        ],
        default='None'
    )
    EMA_BB_Entry = models.CharField(
        max_length=10,
        choices=[
            ('buy', 'Buy'),
            ('sell', 'Sell'),
            ('both', 'Both'),
            ('None', 'None'),
        ],
        default='None'
    )
    BB_RSI_Entry = models.CharField(
        max_length=10,
        choices=[
            ('buy', 'Buy'),
            ('sell', 'Sell'),
            ('both', 'Both'),
            ('None', 'None'),
        ],
        default='None'
    )
    EMA_BB_RSI_Entry = models.CharField(
        max_length=10,
        choices=[
            ('buy', 'Buy'),
            ('sell', 'Sell'),
            ('both', 'Both'),
            ('None', 'None'),
        ],
        default='None'
    )

    # Exit Signals
    BB_Exit = models.CharField(
        max_length=10,
        choices=[
            ('tp', 'Take Profit'),
            ('sl', 'Stop Loss'),
            ('both', 'Both'),
            ('None', 'None'),
        ],
        default='None'
    )
    RSI_Exit = models.CharField(
        max_length=10,
        choices=[
            ('tp', 'Take Profit'),
            ('sl', 'Stop Loss'),
            ('both', 'Both'),
            ('None', 'None'),
        ],
        default='None'
    )
    EMA_RSI_Exit = models.CharField(
        max_length=10,
        choices=[
            ('tp', 'Take Profit'),
            ('sl', 'Stop Loss'),
            ('both', 'Both'),
            ('None', 'None'),
        ],
        default='None'
    )
    EMA_BB_Exit = models.CharField(
        max_length=10,
        choices=[
            ('tp', 'Take Profit'),
            ('sl', 'Stop Loss'),
            ('both', 'Both'),
            ('None', 'None'),
        ],
        default='None'
    )
    BB_RSI_Exit = models.CharField(
        max_length=10,
        choices=[
            ('tp', 'Take Profit'),
            ('sl', 'Stop Loss'),
            ('both', 'Both'),
            ('None', 'None'),
        ],
        default='None'
    )
    EMA_BB_RSI_Exit = models.CharField(
        max_length=10,
        choices=[
            ('tp', 'Take Profit'),
            ('sl', 'Stop Loss'),
            ('both', 'Both'),
            ('None', 'None'),
        ],
        default='None'
    )
    SL_Exit = models.CharField(
        max_length=10,
        choices=[
            ('tp', 'Take Profit'),
            ('sl', 'Stop Loss'),
            ('both', 'Both'),
            ('None', 'None'),
        ],
        default='None'
    )

    class Meta:
        db_table = 'bots_pair_configs'
        unique_together = ['user', 'pair_symbol']
        indexes = [
            models.Index(fields=['user', 'pair_symbol']),
            models.Index(fields=['slug']),
        ]

    def save(self, *args, **kwargs):
        """Generate slug if not exists."""
        if not self.slug:
            self.slug = f"{self.user.username}-{self.pair_symbol.lower().replace('/', '-')}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} - {self.pair_symbol}"