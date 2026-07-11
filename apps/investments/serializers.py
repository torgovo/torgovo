"""
Investment App Serializers for Torgovo Crypto Trading Platform
Comprehensive serializer implementation matching DOCUMENTATION.md
"""
import uuid
from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone
from rest_framework import serializers, validators
from decimal import Decimal
import logging

from .models import (
    Exchange, ExchangeCredential, TradingPair, BotBase,
    WebhookAlertBot, GridBot, MartingaleBot, QuantumAIBot,
    Order, Position, TechnicalIndicator, UserBalance
)

logger = logging.getLogger(__name__)
User = get_user_model()


# ========== BASE & UTILITY SERIALIZERS ==========

class ExchangeNestedSerializer(serializers.ModelSerializer):
    """Lightweight exchange info for nested representations"""
    class Meta:
        model = Exchange
        fields = ['id', 'name', 'display_name']

class TradingPairNestedSerializer(serializers.ModelSerializer):
    """Lightweight trading pair info for nested representations"""
    exchange = ExchangeNestedSerializer(read_only=True)

    class Meta:
        model = TradingPair
        fields = ['id', 'symbol', 'base_asset', 'quote_asset', 'exchange', 'current_price']

class UserNestedSerializer(serializers.ModelSerializer):
    """Lightweight user info for nested representations"""
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']


# ========== EXCHANGE SERIALIZERS ==========

class ExchangeSerializer(serializers.ModelSerializer):
    """Full exchange details"""
    class Meta:
        model = Exchange
        fields = '__all__'
        read_only_fields = ['id', 'created_at']

class ExchangeListSerializer(serializers.ModelSerializer):
    """Exchange list for API documentation format"""
    supported_features = serializers.JSONField(default=list)

    class Meta:
        model = Exchange
        fields = ['name', 'display_name', 'status', 'supported_features']


class ExchangeCredentialSerializer(serializers.ModelSerializer):
    """Exchange API credentials (with security features)"""
    user = UserNestedSerializer(read_only=True)
    exchange = ExchangeNestedSerializer(read_only=True)
    exchange_id = serializers.PrimaryKeyRelatedField(
        queryset=Exchange.objects.all(),
        source='exchange',
        write_only=True
    )

    # Security: Make credentials write-only
    api_key = serializers.CharField(write_only=True, min_length=10)
    secret_key = serializers.CharField(write_only=True, min_length=10)
    passphrase = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        allow_null=True
    )

    # Read-only display fields
    exchange_name = serializers.CharField(source='exchange.name', read_only=True)
    is_connected_display = serializers.BooleanField(source='is_connected', read_only=True)

    class Meta:
        model = ExchangeCredential
        fields = [
            'id', 'user', 'exchange', 'exchange_id', 'exchange_name',
            'api_key', 'secret_key', 'passphrase',
            'is_testnet', 'is_connected', 'is_connected_display',
            'last_connected', 'created_at'
        ]
        read_only_fields = ['id', 'user', 'is_connected', 'last_connected', 'created_at']

    def create(self, validated_data):
        """Auto-assign user from request context"""
        validated_data['user'] = self.context['request'].user

        # Prevent duplicate credentials per exchange
        if ExchangeCredential.objects.filter(
            user=validated_data['user'],
            exchange=validated_data['exchange']
        ).exists():
            raise serializers.ValidationError({
                'error': 'Credentials for this exchange already exist'
            })

        return super().create(validated_data)

    def validate(self, data):
        """Validate exchange requirements"""
        exchange = data.get('exchange')
        if exchange and exchange.requires_passphrase and not data.get('passphrase'):
            raise serializers.ValidationError({
                'passphrase': f'{exchange.name} requires a passphrase'
            })
        return data


# ========== TRADING PAIR SERIALIZERS ==========

class TradingPairSerializer(serializers.ModelSerializer):
    """Full trading pair details"""
    exchange = ExchangeNestedSerializer(read_only=True)
    exchange_id = serializers.PrimaryKeyRelatedField(
        queryset=Exchange.objects.all(),
        source='exchange',
        write_only=True
    )

    # Price change calculations
    change_24h = serializers.DecimalField(
        source='price_change_24h',
        max_digits=20,
        decimal_places=8,
        read_only=True
    )
    change_percent_24h = serializers.DecimalField(
        source='price_change_percent_24h',
        max_digits=10,
        decimal_places=4,
        read_only=True
    )

    class Meta:
        model = TradingPair
        fields = '__all__'
        read_only_fields = ['id', 'last_updated']

    def validate_symbol(self, value):
        """Ensure symbol format (e.g., BTC/USDT)"""
        if '/' not in value:
            raise serializers.ValidationError('Symbol must be in format BASE/QUOTE (e.g., BTC/USDT)')
        return value.upper()


# ========== BOT BASE SERIALIZERS ==========

class BaseBotSerializer(serializers.ModelSerializer):
    """Common fields for all bot types"""
    user = UserNestedSerializer(read_only=True)
    exchange = ExchangeNestedSerializer(read_only=True)
    trading_pair = TradingPairNestedSerializer(read_only=True)

    # Writable IDs
    exchange_id = serializers.UUIDField(write_only=True)
    trading_pair_id = serializers.UUIDField(write_only=True)

    # Display fields
    exchange_name = serializers.CharField(source='exchange.name', read_only=True)
    trading_pair_symbol = serializers.CharField(source='trading_pair.symbol', read_only=True)

    # Performance metrics
    success_rate = serializers.SerializerMethodField()
    total_trades_display = serializers.IntegerField(source='total_trades', read_only=True)

    class Meta:
        model = BotBase
        # Define fields explicitly as a list to allow inheritance
        fields = [
            'id', 'user', 'bot_name', 'category', 'exchange', 'exchange_id', 'exchange_name',
            'trading_pair', 'trading_pair_id', 'trading_pair_symbol',
            'status', 'is_active', 'success_rate', 'total_trades_display',
            'total_trades', 'successful_trades', 'total_profit_loss', 'total_volume',
            'take_profit_percent', 'stop_loss_percent', 'max_position_size',
            'created_at', 'started_at', 'stopped_at'
        ]
        read_only_fields = [
            'id', 'user', 'created_at', 'started_at', 'stopped_at',
            'total_trades', 'successful_trades', 'total_profit_loss', 'total_volume'
        ]

    def get_success_rate(self, obj):
        """Calculate trade success rate percentage"""
        if obj.total_trades > 0:
            return round((obj.successful_trades / obj.total_trades) * 100, 2)
        return 0.0

    def validate(self, data):
        """Validate bot configuration"""
        # Validate risk parameters
        if data.get('take_profit_percent', 2.0) <= 0:
            raise serializers.ValidationError({
                'take_profit_percent': 'Take profit must be positive'
            })

        if data.get('stop_loss_percent', 1.0) <= 0:
            raise serializers.ValidationError({
                'stop_loss_percent': 'Stop loss must be positive'
            })

        return data


class WebhookAlertBotSerializer(BaseBotSerializer):
    """TradingView Webhook Alert Bot serializer"""
    webhook_url = serializers.CharField(read_only=True)
    secret_key = serializers.CharField(read_only=True)

    class Meta(BaseBotSerializer.Meta):
        model = WebhookAlertBot
        # Override fields completely with explicit list (no concatenation)
        fields = [
            # From BaseBotSerializer
            'id', 'user', 'bot_name', 'category', 'exchange', 'exchange_id', 'exchange_name',
            'trading_pair', 'trading_pair_id', 'trading_pair_symbol',
            'status', 'is_active', 'success_rate', 'total_trades_display',
            'total_trades', 'successful_trades', 'total_profit_loss', 'total_volume',
            'take_profit_percent', 'stop_loss_percent', 'max_position_size',
            'created_at', 'started_at', 'stopped_at',
            # Webhook-specific fields
            'webhook_id', 'webhook_url', 'secret_key', 'default_amount', 'last_triggered'
        ]
        read_only_fields = BaseBotSerializer.Meta.read_only_fields + [
            'webhook_id', 'webhook_url', 'secret_key', 'last_triggered'
        ]

    def create(self, validated_data):
        """Auto-generate webhook_id and secret_key"""
        validated_data['webhook_id'] = uuid.uuid4()
        validated_data['secret_key'] = uuid.uuid4().hex

        # Set category
        validated_data['category'] = 'webhook'

        return super().create(validated_data)


class GridBotSerializer(BaseBotSerializer):
    """Grid Trading Bot serializer"""
    class Meta(BaseBotSerializer.Meta):
        model = GridBot
        # Override fields completely (no concatenation)
        fields = [
            # From BaseBotSerializer
            'id', 'user', 'bot_name', 'category', 'exchange', 'exchange_id', 'exchange_name',
            'trading_pair', 'trading_pair_id', 'trading_pair_symbol',
            'status', 'is_active', 'success_rate', 'total_trades_display',
            'total_trades', 'successful_trades', 'total_profit_loss', 'total_volume',
            'take_profit_percent', 'stop_loss_percent', 'max_position_size',
            'created_at', 'started_at', 'stopped_at',
            # Grid-specific fields
            'base_amount', 'favor_levels', 'against_levels', 'level_spacing_percent',
            'current_grid_level', 'total_invested'
        ]
        read_only_fields = BaseBotSerializer.Meta.read_only_fields + [
            'current_grid_level', 'total_invested'
        ]

    def validate_favor_levels(self, value):
        if not (1 <= value <= 100):
            raise serializers.ValidationError('Favor levels must be between 1 and 100')
        return value

    def validate_against_levels(self, value):
        if not (1 <= value <= 100):
            raise serializers.ValidationError('Against levels must be between 1 and 100')
        return value

    def create(self, validated_data):
        validated_data['category'] = 'grid'
        return super().create(validated_data)


class MartingaleBotSerializer(BaseBotSerializer):
    """Martingale Trading Bot serializer"""
    class Meta(BaseBotSerializer.Meta):
        model = MartingaleBot
        # Override fields completely (no concatenation)
        fields = [
            # From BaseBotSerializer
            'id', 'user', 'bot_name', 'category', 'exchange', 'exchange_id', 'exchange_name',
            'trading_pair', 'trading_pair_id', 'trading_pair_symbol',
            'status', 'is_active', 'success_rate', 'total_trades_display',
            'total_trades', 'successful_trades', 'total_profit_loss', 'total_volume',
            'take_profit_percent', 'stop_loss_percent', 'max_position_size',
            'created_at', 'started_at', 'stopped_at',
            # Martingale-specific fields
            'base_amount', 'favor_levels', 'against_levels', 'level_spacing_percent',
            'multiplier_factor', 'current_level', 'consecutive_losses'
        ]
        read_only_fields = BaseBotSerializer.Meta.read_only_fields + [
            'current_level', 'consecutive_losses'
        ]

    def validate_multiplier_factor(self, value):
        if value < 1.0:
            raise serializers.ValidationError('Multiplier factor must be >= 1.0')
        return value

    def create(self, validated_data):
        validated_data['category'] = 'martingale'
        return super().create(validated_data)


class QuantumAIBotSerializer(BaseBotSerializer):
    """Quantum AI Bot serializer"""
    blockchain_addresses = serializers.JSONField(read_only=True)

    class Meta(BaseBotSerializer.Meta):
        model = QuantumAIBot
        # Override fields completely (no concatenation)
        fields = [
            # From BaseBotSerializer
            'id', 'user', 'bot_name', 'category', 'exchange', 'exchange_id', 'exchange_name',
            'trading_pair', 'trading_pair_id', 'trading_pair_symbol',
            'status', 'is_active', 'success_rate', 'total_trades_display',
            'total_trades', 'successful_trades', 'total_profit_loss', 'total_volume',
            'take_profit_percent', 'stop_loss_percent', 'max_position_size',
            'created_at', 'started_at', 'stopped_at',
            # Quantum AI-specific fields
            'auto_compound', 'compound_frequency', 'risk_level',
            'blockchain_addresses', 'last_compound'
        ]
        read_only_fields = BaseBotSerializer.Meta.read_only_fields + [
            'blockchain_addresses', 'last_compound'
        ]

    def create(self, validated_data):
        validated_data['category'] = 'quantum_ai'
        return super().create(validated_data)


# ========== ORDER & TRADE SERIALIZERS ==========

class OrderSerializer(serializers.ModelSerializer):
    """Order execution and history serializer"""
    # Nested data
    user = UserNestedSerializer(read_only=True)
    exchange = ExchangeNestedSerializer(read_only=True)
    trading_pair = TradingPairNestedSerializer(read_only=True)

    # Writable IDs
    exchange_id = serializers.UUIDField(write_only=True)
    trading_pair_id = serializers.UUIDField(write_only=True)
    bot_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)

    # Display fields
    exchange_name = serializers.CharField(source='exchange.name', read_only=True)
    pair = serializers.CharField(source='trading_pair.symbol', read_only=True)
    category = serializers.CharField(source='bot.category', read_only=True, allow_null=True)

    # Timestamp formatting (API docs use capital 'Time')
    Time = serializers.DateTimeField(source='created_at', read_only=True)

    # Price formatting
    Price = serializers.DecimalField(
        source='price',
        max_digits=20,
        decimal_places=8,
        read_only=True
    )
    Take_Profit = serializers.DecimalField(
        source='take_profit',
        max_digits=20,
        decimal_places=8,
        read_only=True,
        allow_null=True
    )
    Stop_Loss = serializers.DecimalField(
        source='stop_loss',
        max_digits=20,
        decimal_places=8,
        read_only=True,
        allow_null=True
    )

    # Capitalised aliases for API docs compatibility
    Side = serializers.SerializerMethodField()
    Description = serializers.SerializerMethodField()

    # P&L field
    profit_loss = serializers.DecimalField(max_digits=20, decimal_places=8, read_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 'user', 'bot', 'bot_id', 'category',
            'exchange', 'exchange_id', 'exchange_name',
            'trading_pair', 'trading_pair_id', 'pair',
            'order_type', 'Side', 'quantity', 'Price',
            'filled_quantity', 'average_price',
            'Take_Profit', 'Stop_Loss',
            'status', 'profit_loss', 'Description',
            'executed_at', 'Time', 'created_at'
        ]
        read_only_fields = [
            'id', 'user', 'bot', 'filled_quantity', 'average_price',
            'profit_loss', 'executed_at', 'created_at'
        ]
        extra_kwargs = {
            'order_type': {'required': True},
            'quantity': {'required': True},
            'price': {'required': True},
        }

    def get_Side(self, obj):
        """Capitalize side for API docs compatibility"""
        return obj.side.capitalize() if obj.side else None

    def get_Description(self, obj):
        """Capitalize description field for API docs"""
        return obj.description or ''

    def validate_quantity(self, value):
        """Ensure positive quantity"""
        if value <= 0:
            raise serializers.ValidationError('Quantity must be positive')
        return value

    def validate_price(self, value):
        """Ensure non-negative price"""
        if value < 0:
            raise serializers.ValidationError('Price cannot be negative')
        return value

    def create(self, validated_data):
        """Auto-assign user and validate bot ownership"""
        validated_data['user'] = self.context['request'].user

        # Validate bot belongs to user
        bot_id = validated_data.get('bot_id')
        if bot_id:
            try:
                from .models import BotBase
                bot = BotBase.objects.get(id=bot_id, user=validated_data['user'])
                validated_data['bot'] = bot
            except BotBase.DoesNotExist:
                raise serializers.ValidationError({
                    'bot_id': 'Bot not found or does not belong to you'
                })

        return super().create(validated_data)


# ========== POSITION SERIALIZER ==========

class PositionSerializer(serializers.ModelSerializer):
    """Open positions serializer"""
    user = UserNestedSerializer(read_only=True)
    exchange = ExchangeNestedSerializer(read_only=True)
    trading_pair = TradingPairNestedSerializer(read_only=True)

    exchange_id = serializers.UUIDField(write_only=True)
    trading_pair_id = serializers.UUIDField(write_only=True)

    exchange_name = serializers.CharField(source='exchange.name', read_only=True)
    pair = serializers.CharField(source='trading_pair.symbol', read_only=True)

    # P&L calculations
    unrealized_pnl_display = serializers.DecimalField(
        source='unrealized_pnl',
        max_digits=20,
        decimal_places=8,
        read_only=True
    )
    unrealized_pnl_percent_display = serializers.DecimalField(
        source='unrealized_pnl_percent',
        max_digits=10,
        decimal_places=4,
        read_only=True
    )

    class Meta:
        model = Position
        fields = '__all__'

    def validate_leverage(self, value):
        """Leverage bounds check"""
        if not (1 <= value <= 125):
            raise serializers.ValidationError('Leverage must be between 1x and 125x')
        return value

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


# ========== TECHNICAL INDICATOR SERIALIZER ==========

class TechnicalIndicatorSerializer(serializers.ModelSerializer):
    """Technical indicator webhook data"""
    exchange = ExchangeNestedSerializer(read_only=True)
    trading_pair = TradingPairNestedSerializer(read_only=True)

    exchange_name = serializers.CharField(source='exchange.name', read_only=True)
    pair = serializers.CharField(source='trading_pair.symbol', read_only=True)

    class Meta:
        model = TechnicalIndicator
        fields = '__all__'
        read_only_fields = ['id', 'triggered_at']


# ========== BALANCE SERIALIZER ==========

class UserBalanceSerializer(serializers.ModelSerializer):
    """User balance across exchanges"""
    user = UserNestedSerializer(read_only=True)
    exchange = ExchangeNestedSerializer(read_only=True)

    exchange_name = serializers.CharField(source='exchange.name', read_only=True)
    currency_display = serializers.CharField(source='currency', read_only=True)

    class Meta:
        model = UserBalance
        fields = '__all__'
        read_only_fields = ['id', 'user', 'updated_at']

    def validate(self, data):
        """Ensure total = available + locked"""
        if 'available' in data and 'locked' in data:
            data['total'] = data['available'] + data['locked']
        elif 'available' in data and 'total' not in data:
            data['total'] = data['available']
        return data

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


# ========== COMPOSITE SERIALIZER ==========

class UserPortfolioSerializer(serializers.Serializer):
    """
    Composite serializer for user dashboard
    Aggregates multiple data sources
    """
    user_profile = serializers.SerializerMethodField()
    balances = serializers.SerializerMethodField()
    open_positions = serializers.SerializerMethodField()
    active_bots = serializers.SerializerMethodField()
    recent_orders = serializers.SerializerMethodField()

    def get_user_profile(self, obj):
        """Get user trading profile"""
        request = self.context['request']
        user = request.user

        total_trades = Order.objects.filter(user=user).count()
        total_volume = Order.objects.filter(user=user).aggregate(
            total=models.Sum('quantity')
        )['total'] or 0

        return {
            'id': str(user.id),
            'user_email': user.email,
            'user_full_name': user.get_full_name(),
            'subscription_plan': getattr(user, 'subscription_plan', 'basic'),
            'max_bots_allowed': getattr(user, 'max_bots_allowed', 10),
            'timezone': getattr(user, 'timezone', 'UTC'),
            'demo_trading_enabled': getattr(user, 'demo_trading_enabled', True),
            'email_notifications': getattr(user, 'email_notifications', True),
            'is_subscription_active': getattr(user, 'is_subscription_active', True),
            'total_trades_executed': total_trades,
            'total_volume_traded': str(total_volume)
        }

    def get_balances(self, obj):
        """Get all user balances"""
        request = self.context['request']
        balances = UserBalance.objects.filter(user=request.user)
        total_usdt = sum(balance.total for balance in balances if balance.currency == 'USDT')

        return {
            'total_usdt_value': str(total_usdt),
            'balances': UserBalanceSerializer(balances, many=True).data
        }

    def get_open_positions(self, obj):
        """Get open positions with P&L"""
        request = self.context['request']
        positions = Position.objects.filter(user=request.user)
        return PositionSerializer(positions, many=True).data

    def get_active_bots(self, obj):
        """Get active trading bots"""
        request = self.context['request']
        bots = BotBase.objects.filter(
            user=request.user,
            status='running',
            is_active=True
        )
        return BaseBotSerializer(bots, many=True).data

    def get_recent_orders(self, obj):
        """Get recent 20 orders"""
        request = self.context['request']
        orders = Order.objects.filter(user=request.user).order_by('-created_at')[:20]
        return OrderSerializer(orders, many=True).data

    class Meta:
        fields = ['user_profile', 'balances', 'open_positions', 'active_bots', 'recent_orders']
        read_only_fields = fields