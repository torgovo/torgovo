"""
Serializers for trading bots
"""
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import WebhookAlert, GridBot, MartingaleBot, QuantumAIBot, Order, TechnicalIndicator, PairConfig

User = get_user_model()


class WebhookAlertSerializer(serializers.ModelSerializer):
    """Serializer for WebhookAlert model."""
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    success_rate = serializers.ReadOnlyField()

    class Meta:
        model = WebhookAlert
        fields = [
            'id', 'user', 'bot_name', 'webhook_url', 'secret_key', 'exchange_name',
            'trading_pair', 'default_amount', 'take_profit_percent',
            'stop_loss_percent', 'is_active', 'last_triggered', 'total_trades',
            'successful_trades', 'total_profit_loss', 'created_at',
            'updated_at', 'success_rate', 'last_error'
        ]
        read_only_fields = [
            'id', 'user', 'webhook_url', 'secret_key', 'created_at', 'updated_at',
            'last_triggered', 'total_trades', 'successful_trades',
            'total_profit_loss', 'success_rate', 'last_error'
        ]


class WebhookAlertCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating WebhookAlert."""
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = WebhookAlert
        fields = [
            'bot_name', 'exchange_name', 'trading_pair',
            'default_amount', 'take_profit_percent', 'stop_loss_percent'
        ]

    def validate_exchange_name(self, value):
        """Validate that exchange is supported."""
        supported_exchanges = ['binance', 'bybit', 'okx', 'mexc', 'alpaca']
        if value.lower() not in supported_exchanges:
            raise serializers.ValidationError(
                f"Exchange '{value}' is not supported. "
                f"Supported exchanges: {', '.join(supported_exchanges)}"
            )
        return value

    def validate_trading_pair(self, value):
        """Validate trading pair format."""
        if '/' not in value:
            raise serializers.ValidationError(
                "Trading pair must be in format 'BASE/QUOTE' (e.g., 'BTC/USDT')"
            )
        return value.upper()


class GridBotSerializer(serializers.ModelSerializer):
    """Serializer for GridBot model."""
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    is_running = serializers.BooleanField(read_only=True)
    current_profit_loss = serializers.ReadOnlyField()
    total_invested = serializers.ReadOnlyField()
    total_trades_executed = serializers.ReadOnlyField()

    class Meta:
        model = GridBot
        fields = [
            'id', 'user', 'bot_name', 'exchange_name', 'trading_pair',
            'base_amount', 'favor_levels', 'against_levels',
            'level_spacing_percent', 'take_profit_percent',
            'stop_loss_percent', 'is_running', 'started_at',
            'stopped_at', 'current_profit_loss', 'total_invested',
            'total_trades_executed', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'user', 'is_running', 'started_at', 'stopped_at',
            'current_profit_loss', 'total_invested', 'total_trades_executed',
            'created_at', 'updated_at'
        ]


class GridBotCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating GridBot."""
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = GridBot
        fields = [
            'bot_name', 'exchange_name', 'trading_pair',
            'base_amount', 'favor_levels', 'against_levels',
            'level_spacing_percent', 'take_profit_percent', 'stop_loss_percent'
        ]


class MartingaleBotSerializer(serializers.ModelSerializer):
    """Serializer for MartingaleBot model."""
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    is_running = serializers.BooleanField(read_only=True)
    current_profit_loss = serializers.ReadOnlyField()
    total_invested = serializers.ReadOnlyField()
    total_trades_executed = serializers.ReadOnlyField()

    class Meta:
        model = MartingaleBot
        fields = [
            'id', 'user', 'bot_name', 'exchange_name', 'trading_pair',
            'base_amount', 'favor_levels', 'against_levels',
            'level_spacing_percent', 'multiplier_factor',
            'take_profit_percent', 'stop_loss_percent',
            'is_running', 'started_at', 'stopped_at',
            'current_profit_loss', 'total_invested',
            'total_trades_executed', 'current_level',
            'max_level_reached', 'last_execution_price',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'user', 'is_running', 'started_at', 'stopped_at',
            'current_profit_loss', 'total_invested', 'total_trades_executed',
            'current_level', 'max_level_reached', 'last_execution_price',
            'created_at', 'updated_at'
        ]


class MartingaleBotCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating MartingaleBot."""
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = MartingaleBot
        fields = [
            'bot_name', 'exchange_name', 'trading_pair',
            'base_amount', 'favor_levels', 'against_levels',
            'level_spacing_percent', 'multiplier_factor',
            'take_profit_percent', 'stop_loss_percent'
        ]


class QuantumAIBotSerializer(serializers.ModelSerializer):
    """Serializer for QuantumAIBot model."""
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    is_active = serializers.BooleanField(read_only=True)
    total_deposited = serializers.ReadOnlyField()
    current_profit_loss = serializers.ReadOnlyField()
    roi_percent = serializers.ReadOnlyField()

    class Meta:
        model = QuantumAIBot
        fields = [
            'id', 'user', 'bot_name', 'total_deposited', 'current_profit_loss',
            'is_active', 'last_profit_update', 'auto_compound',
            'compound_frequency', 'risk_level', 'created_at',
            'updated_at', 'roi_percent'
        ]
        read_only_fields = [
            'id', 'user', 'total_deposited', 'current_profit_loss',
            'is_active', 'last_profit_update', 'created_at', 'updated_at', 'roi_percent'
        ]


class QuantumAIBotCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating QuantumAIBot."""
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = QuantumAIBot
        fields = ['bot_name', 'auto_compound', 'compound_frequency', 'risk_level']


class PairConfigSerializer(serializers.ModelSerializer):
    """Serializer for PairConfig model."""
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = PairConfig
        fields = '__all__'


class OrderSerializer(serializers.ModelSerializer):
    """Serializer for Order model."""
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    user_info = serializers.SerializerMethodField()
    webhook_alert = serializers.SerializerMethodField()
    grid_bot = serializers.SerializerMethodField()
    martingale_bot = serializers.SerializerMethodField()
    quantum_bot = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
        fields = [
            'id', 'Time', 'user', 'user_info', 'Pair', 'PairConfig', 'Side',
            'Category', 'Order_type', 'Quantity', 'Price',
            'Exchange', 'Take_Profit', 'Stop_Loss', 'Description',
            'Details', 'executed_price', 'fees', 'status',
            'webhook_alert', 'grid_bot', 'martingale_bot', 'quantum_bot'
        ]
        read_only_fields = ['id', 'Time', 'executed_price', 'fees', 'Details']

    def get_user_info(self, obj):
        """Get user information."""
        if obj.user:
            return {
                'id': str(obj.user.id),
                'email': obj.user.email,
                'username': obj.user.username
            }
        return None

    def get_webhook_alert(self, obj):
        """Get webhook alert information."""
        if obj.webhook_alert:
            return {
                'id': str(obj.webhook_alert.id),
                'bot_name': obj.webhook_alert.bot_name
            }
        return None

    def get_grid_bot(self, obj):
        """Get grid bot information."""
        if obj.grid_bot:
            return {
                'id': str(obj.grid_bot.id),
                'bot_name': obj.grid_bot.bot_name
            }
        return None

    def get_martingale_bot(self, obj):
        """Get martingale bot information."""
        if obj.martingale_bot:
            return {
                'id': str(obj.martingale_bot.id),
                'bot_name': obj.martingale_bot.bot_name
            }
        return None

    def get_quantum_bot(self, obj):
        """Get quantum AI bot information."""
        if obj.quantum_bot:
            return {
                'id': str(obj.quantum_bot.id),
                'bot_name': obj.quantum_bot.bot_name
            }
        return None


class TechnicalIndicatorSerializer(serializers.ModelSerializer):
    """Serializer for TechnicalIndicator model."""
    class Meta:
        model = TechnicalIndicator
        fields = [
            'id', 'pair', 'exchange', 'indicator_type', 'timeframe',
            'value', 'timestamp', 'additional_data'
        ]


class BotOverviewSerializer(serializers.Serializer):
    """Serializer for bot overview statistics."""
    total_bots = serializers.IntegerField(read_only=True)
    running_bots = serializers.IntegerField(read_only=True)
    total_users = serializers.IntegerField(read_only=True)
    daily_trades = serializers.IntegerField(read_only=True)
    platform_volume = serializers.DecimalField(max_digits=20, decimal_places=2, read_only=True)
    by_type = serializers.DictField(read_only=True)
    by_exchange = serializers.DictField(read_only=True)