"""
Investment Models for Torgovo Crypto Trading Platform
Fixed: BotBase is now concrete, ExchangeCredential has unique related_name
"""
import uuid
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.translation import gettext_lazy as _

User = settings.AUTH_USER_MODEL


# ========== EXCHANGE INTEGRATION ==========

class Exchange(models.Model):
    """Supported cryptocurrency exchanges"""
    EXCHANGE_CHOICES = [
        ('binance', 'Binance'),
        ('bybit', 'Bybit'),
        ('okx', 'OKX'),
        ('mexc', 'MEXC'),
        ('alpaca', 'Alpaca'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=20, unique=True, choices=EXCHANGE_CHOICES)
    display_name = models.CharField(max_length=50)
    status = models.CharField(max_length=20, default='active')
    supported_features = models.JSONField(default=list)  # ["spot", "futures", "margin"]
    requires_passphrase = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'investment_exchanges'
    
    def __str__(self):
        return self.display_name


class ExchangeCredential(models.Model):
    """User exchange API credentials (encrypted storage recommended)"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # FIX: Unique related_name to avoid clash with exchanges app
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='investment_exchange_credentials')
    exchange = models.ForeignKey(Exchange, on_delete=models.PROTECT)
    
    # Store these encrypted in production!
    api_key = models.CharField(max_length=255)
    secret_key = models.CharField(max_length=255)
    passphrase = models.CharField(max_length=255, blank=True, null=True)
    
    is_testnet = models.BooleanField(default=True)
    is_connected = models.BooleanField(default=False)
    last_connected = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'investment_exchange_credentials'
        unique_together = ['user', 'exchange']
    
    def __str__(self):
        return f"{self.user.username} - {self.exchange.name}"


# ========== ASSET MANAGEMENT ==========

class TradingPair(models.Model):
    """Tradable pairs across exchanges"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    symbol = models.CharField(max_length=50)  # BTC/USDT
    base_asset = models.CharField(max_length=20)  # BTC
    quote_asset = models.CharField(max_length=20)  # USDT
    exchange = models.ForeignKey(Exchange, on_delete=models.PROTECT)
    
    current_price = models.DecimalField(max_digits=20, decimal_places=8, null=True)
    high_24h = models.DecimalField(max_digits=20, decimal_places=8, null=True)
    low_24h = models.DecimalField(max_digits=20, decimal_places=8, null=True)
    volume_24h = models.DecimalField(max_digits=30, decimal_places=8, null=True)
    price_change_24h = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    price_change_percent_24h = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    
    is_active = models.BooleanField(default=True)
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'investment_trading_pairs'
        unique_together = ['symbol', 'exchange']
    
    def __str__(self):
        return f"{self.symbol} ({self.exchange.name})"


# ========== BOT STRATEGIES ==========

# FIX: BotBase is now CONCRETE (not abstract) to allow ForeignKey
class BotBase(models.Model):
    """Base model for all trading bots - NOW CONCRETE"""
    BOT_STATUS = [
        ('stopped', 'Stopped'),
        ('running', 'Running'),
        ('paused', 'Paused'),
        ('error', 'Error'),
    ]
    
    BOT_CATEGORIES = [
        ('webhook', 'Webhook Alert'),
        ('grid', 'Grid Bot'),
        ('martingale', 'Martingale Bot'),
        ('quantum_ai', 'Quantum AI Bot'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bots')
    bot_name = models.CharField(max_length=100)
    category = models.CharField(max_length=20, choices=BOT_CATEGORIES)
    
    exchange = models.ForeignKey(Exchange, on_delete=models.PROTECT)
    trading_pair = models.ForeignKey(TradingPair, on_delete=models.PROTECT)
    
    status = models.CharField(max_length=10, choices=BOT_STATUS, default='stopped')
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    stopped_at = models.DateTimeField(null=True, blank=True)
    
    # Performance metrics
    total_trades = models.IntegerField(default=0)
    successful_trades = models.IntegerField(default=0)
    total_profit_loss = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    total_volume = models.DecimalField(max_digits=30, decimal_places=8, default=0)
    
    # Risk management
    take_profit_percent = models.DecimalField(max_digits=5, decimal_places=2, default=5.0)
    stop_loss_percent = models.DecimalField(max_digits=5, decimal_places=2, default=3.0)
    max_position_size = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    
    class Meta:
        db_table = 'investment_bot_bases'
        # REMOVED: abstract = True (this was the problem)
    
    def __str__(self):
        return f"{self.bot_name} ({self.category})"
    
    def update_performance(self, profit_loss, success=True):
        """Update bot performance metrics"""
        self.total_trades += 1
        if success:
            self.successful_trades += 1
        self.total_profit_loss += profit_loss
        self.save()


class WebhookAlertBot(models.Model):
    """TradingView webhook alert bots"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bot_base = models.OneToOneField(BotBase, on_delete=models.CASCADE, related_name='webhook_bot')
    webhook_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    secret_key = models.CharField(max_length=64, unique=True, editable=False)
    webhook_url = models.URLField()
    
    default_amount = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    last_triggered = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'investment_webhook_bots'
    
    def save(self, *args, **kwargs):
        if not self.webhook_url:
            self.webhook_url = f"https://api.torgovo.com/api/webhooks/tradingview/{self.webhook_id}/"
        super().save(*args, **kwargs)


class GridBot(models.Model):
    """Grid trading strategy bots"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bot_base = models.OneToOneField(BotBase, on_delete=models.CASCADE, related_name='grid_bot')
    
    base_amount = models.DecimalField(max_digits=20, decimal_places=8)  # Amount per grid level
    favor_levels = models.IntegerField(default=5, validators=[MinValueValidator(1), MaxValueValidator(100)])
    against_levels = models.IntegerField(default=5, validators=[MinValueValidator(1), MaxValueValidator(100)])
    level_spacing_percent = models.DecimalField(max_digits=5, decimal_places=2, default=1.0)
    
    # Grid state
    current_grid_level = models.IntegerField(default=0)
    total_invested = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    
    class Meta:
        db_table = 'investment_grid_bots'


class MartingaleBot(models.Model):
    """Martingale strategy bots"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bot_base = models.OneToOneField(BotBase, on_delete=models.CASCADE, related_name='martingale_bot')
    
    base_amount = models.DecimalField(max_digits=20, decimal_places=8)
    favor_levels = models.IntegerField(default=3)
    against_levels = models.IntegerField(default=3)
    level_spacing_percent = models.DecimalField(max_digits=5, decimal_places=2, default=2.0)
    multiplier_factor = models.DecimalField(max_digits=5, decimal_places=2, default=2.0)  # 2x, 3x etc
    
    # Martingale state
    current_level = models.IntegerField(default=0)
    consecutive_losses = models.IntegerField(default=0)
    
    class Meta:
        db_table = 'investment_martingale_bots'


class QuantumAIBot(models.Model):
    """AI-powered portfolio management bots"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bot_base = models.OneToOneField(BotBase, on_delete=models.CASCADE, related_name='quantum_ai_bot')
    
    auto_compound = models.BooleanField(default=False)
    compound_frequency = models.CharField(max_length=20, choices=[
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
    ], default='weekly')
    risk_level = models.CharField(max_length=20, choices=[
        ('conservative', 'Conservative'),
        ('moderate', 'Moderate'),
        ('aggressive', 'Aggressive'),
    ], default='moderate')
    
    # Quantum AI specific
    blockchain_addresses = models.JSONField(default=dict)  # Store deposit addresses
    last_compound = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'investment_quantum_ai_bots'


# ========== ORDER EXECUTION ==========

class Order(models.Model):
    """Executed and pending orders"""
    ORDER_TYPES = [
        ('market', 'Market'),
        ('limit', 'Limit'),
        ('stop_limit', 'Stop Limit'),
    ]
    
    ORDER_SIDES = [
        ('buy', 'Buy'),
        ('sell', 'Sell'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='investment_orders')
    # FIX: Use concrete BotBase model
    bot = models.ForeignKey(BotBase, on_delete=models.SET_NULL, null=True, blank=True)
    
    exchange = models.ForeignKey(Exchange, on_delete=models.PROTECT)
    trading_pair = models.ForeignKey(TradingPair, on_delete=models.PROTECT)
    
    order_type = models.CharField(max_length=20, choices=ORDER_TYPES, default='market')
    side = models.CharField(max_length=10, choices=ORDER_SIDES)
    
    quantity = models.DecimalField(max_digits=20, decimal_places=8)
    price = models.DecimalField(max_digits=20, decimal_places=8)
    filled_quantity = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    average_price = models.DecimalField(max_digits=20, decimal_places=8, null=True)
    
    # TP/SL
    take_profit = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    stop_loss = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    
    # Status
    status = models.CharField(max_length=20, default='pending')  # pending, open, closed, cancelled
    profit_loss = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    
    # Metadata
    description = models.TextField(blank=True)
    executed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'investment_orders'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.side.upper()} {self.quantity} {self.trading_pair.symbol} @ {self.price}"


# ========== TECHNICAL INDICATORS ==========

class TechnicalIndicator(models.Model):
    """Store technical indicator data from TradingView webhooks"""
    INDICATOR_TYPES = [
        ('EMA', 'Exponential Moving Average'),
        ('RSI', 'Relative Strength Index'),
        ('MACD', 'MACD'),
        ('BB', 'Bollinger Bands'),
        ('VWAP', 'Volume Weighted Average Price'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    indicator_type = models.CharField(max_length=20, choices=INDICATOR_TYPES)
    trading_pair = models.ForeignKey(TradingPair, on_delete=models.PROTECT)
    exchange = models.ForeignKey(Exchange, on_delete=models.PROTECT)
    
    # Indicator values (stored as JSON for flexibility)
    values = models.JSONField()
    
    color = models.CharField(max_length=20, blank=True)  # For RSI color changes
    prev_color = models.CharField(max_length=20, blank=True)
    
    triggered_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'investment_indicators'
        ordering = ['-triggered_at']
    
    def __str__(self):
        return f"{self.indicator_type} - {self.trading_pair.symbol}"


# ========== USER POSITIONS ==========

class Position(models.Model):
    """Current open positions"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='investment_positions')
    # FIX: Use concrete BotBase model
    bot = models.ForeignKey(BotBase, on_delete=models.SET_NULL, null=True, blank=True)
    
    exchange = models.ForeignKey(Exchange, on_delete=models.PROTECT)
    trading_pair = models.ForeignKey(TradingPair, on_delete=models.PROTECT)
    
    side = models.CharField(max_length=10, choices=[('long', 'Long'), ('short', 'Short')])
    
    entry_price = models.DecimalField(max_digits=20, decimal_places=8)
    quantity = models.DecimalField(max_digits=20, decimal_places=8)
    leverage = models.IntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(125)])
    
    # Current status
    mark_price = models.DecimalField(max_digits=20, decimal_places=8, null=True)
    unrealized_pnl = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    unrealized_pnl_percent = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    
    # TP/SL
    take_profit = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    stop_loss = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    
    # Risk
    liquidation_price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    
    opened_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'investment_positions'
        unique_together = ['user', 'exchange', 'trading_pair', 'side']
    
    def __str__(self):
        return f"{self.side} {self.quantity} {self.trading_pair.symbol} @ {self.entry_price}"
    
    def update_pnl(self):
        """Update unrealized P&L"""
        if self.mark_price:
            if self.side == 'long':
                self.unrealized_pnl = (self.mark_price - self.entry_price) * self.quantity
            else:
                self.unrealized_pnl = (self.entry_price - self.mark_price) * self.quantity
            
            self.unrealized_pnl_percent = (self.unrealized_pnl / (self.entry_price * self.quantity)) * 100
            self.save()


# ========== USER BALANCE ==========

class UserBalance(models.Model):
    """User balance across exchanges"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='investment_balances')
    exchange = models.ForeignKey(Exchange, on_delete=models.PROTECT)
    
    currency = models.CharField(max_length=10)  # USDT, BTC, etc.
    available = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    locked = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    total = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'investment_balances'
        unique_together = ['user', 'exchange', 'currency']
    
    def __str__(self):
        return f"{self.user.username} - {self.total} {self.currency} ({self.exchange.name})"