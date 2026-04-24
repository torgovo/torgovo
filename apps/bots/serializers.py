"""
Serializers for trading bots - Updated for subscription system
"""
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import (
    SignalBot, GridBot, MartingaleBot, Order,
    Indicator, PairConfig, QuantumAIFund, QuantumAIInvestment,
    TelegramSignalSubscription, TelegramSignalPlan,
    QuantumDepositWallet, QuantumDeposit, QuantumWeeklyProfit
)

User = get_user_model()


# ==================== SIGNAL BOT (TradingView Webhook) ====================

class SignalBotSerializer(serializers.ModelSerializer):
    """Serializer for SignalBot model."""
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    success_rate = serializers.ReadOnlyField()

    class Meta:
        model = SignalBot
        fields = [
            'id', 'user', 'bot_name', 'webhook_url', 'secret_key', 'exchange_name',
            'market_type', 'trading_pair', 'default_amount', 'take_profit_percent',
            'stop_loss_percent', 'is_active', 'signals_used_this_month', 'signal_limit',
            'last_triggered', 'total_trades', 'successful_trades', 'total_profit_loss',
            'created_at', 'updated_at', 'success_rate', 'last_error', 'subscription'
        ]
        read_only_fields = [
            'id', 'user', 'webhook_url', 'secret_key', 'created_at', 'updated_at',
            'last_triggered', 'total_trades', 'successful_trades', 'total_profit_loss',
            'success_rate', 'last_error'
        ]


class SignalBotCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating SignalBot."""
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = SignalBot
        fields = [
            'bot_name', 'exchange_name', 'market_type', 'trading_pair',
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


# ==================== GRID BOT ====================

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
            'initial_amount', 'base_amount', 'favor_levels', 'against_levels',
            'level_spacing_percent', 'favor_level_qty', 'against_level_qty',
            'favor_level_difference', 'against_level_difference', 'amount_type',
            'take_profit_percent', 'stop_loss_percent', 'is_running', 'started_at',
            'stopped_at', 'current_profit_loss', 'total_invested', 'total_trades_executed',
            'created_at', 'updated_at', 'subscription'
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
            'bot_name', 'exchange_name', 'trading_pair', 'initial_amount',
            'base_amount', 'favor_levels', 'against_levels', 'favor_level_qty',
            'against_level_qty', 'favor_level_difference', 'against_level_difference',
            'amount_type', 'take_profit_percent', 'stop_loss_percent'
        ]


# ==================== MARTINGALE BOT ====================

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
            'initial_amount', 'base_amount', 'favor_levels', 'against_levels',
            'level_spacing_percent', 'favor_level_qty', 'against_level_qty',
            'favor_level_difference', 'against_level_difference', 'amount_type',
            'multiplier_factor', 'take_profit_percent', 'stop_loss_percent',
            'is_running', 'started_at', 'stopped_at', 'current_level', 'max_level_reached',
            'last_execution_price', 'current_profit_loss', 'total_invested', 'total_trades_executed',
            'created_at', 'updated_at', 'subscription'
        ]
        read_only_fields = [
            'id', 'user', 'is_running', 'started_at', 'stopped_at', 'current_level',
            'max_level_reached', 'last_execution_price', 'current_profit_loss',
            'total_invested', 'total_trades_executed', 'created_at', 'updated_at'
        ]


class MartingaleBotCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating MartingaleBot."""
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = MartingaleBot
        fields = [
            'bot_name', 'exchange_name', 'trading_pair', 'initial_amount',
            'base_amount', 'favor_levels', 'against_levels', 'favor_level_qty',
            'against_level_qty', 'favor_level_difference', 'against_level_difference',
            'amount_type', 'multiplier_factor', 'take_profit_percent', 'stop_loss_percent'
        ]


# ==================== QUANTUM AI (Fund & Investment) ====================

class QuantumAIFundSerializer(serializers.ModelSerializer):
    """Serializer for QuantumAIFund (Admin only)"""

    class Meta:
        model = QuantumAIFund
        fields = [
            'id', 'name', 'trading_strategy', 'risk_parameters',
            'master_api_key', 'master_secret_key', 'master_passphrase',
            'total_fund_value', 'total_profit', 'total_deposits', 'last_trade_at',
            'is_active', 'admin_notes', 'created_at', 'updated_at'
        ]
        read_only_fields = ['total_profit', 'created_at', 'updated_at']


class QuantumAIInvestmentSerializer(serializers.ModelSerializer):
    """Serializer for user's Quantum AI investment"""
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    user_share_amount = serializers.ReadOnlyField(source='calculate_profit_share')
    share_percentage = serializers.ReadOnlyField()

    class Meta:
        model = QuantumAIInvestment
        fields = [
            'id', 'user', 'fund', 'subscription', 'amount', 'share_percentage',
            'deposited_at', 'status', 'accrued_profit', 'total_payouts',
            'user_share_amount'
        ]
        read_only_fields = [
            'id', 'user', 'share_percentage', 'accrued_profit', 'total_payouts',
            'user_share_amount', 'created_at', 'updated_at'
        ]


# ==================== PAIR CONFIG ====================

class PairConfigSerializer(serializers.ModelSerializer):
    """Serializer for PairConfig model."""
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = PairConfig
        fields = [
            'id', 'user', 'pair_symbol', 'slug', 'subscription', 'bot_type',
            'quantity', 'favor_levels', 'against_levels', 'favor_level_qty',
            'against_level_qty', 'favor_level_difference', 'against_level_difference',
            'Order_Type', 'Amount_Type', 'SLTP_Type', 'Stop_Loss', 'Take_Profit',
            'RSI_Lower', 'RSI_Upper', 'RSI_Entry', 'BB_Entry', 'EMA_RSI_Entry',
            'EMA_BB_Entry', 'BB_RSI_Entry', 'EMA_BB_RSI_Entry', 'BB_Exit',
            'RSI_Exit', 'EMA_RSI_Exit', 'EMA_BB_Exit', 'BB_RSI_Exit', 'EMA_BB_RSI_Exit', 'SL_Exit'
        ]
        read_only_fields = ['slug']


# ==================== ORDER ====================

class OrderSerializer(serializers.ModelSerializer):
    """Serializer for Order model."""
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    user_info = serializers.SerializerMethodField()
    signal_bot_info = serializers.SerializerMethodField()
    grid_bot_info = serializers.SerializerMethodField()
    martingale_bot_info = serializers.SerializerMethodField()
    quantum_ai_info = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            'id', 'Time', 'user', 'user_info', 'Pair', 'PairConfig', 'Indicators',
            'Side', 'Category', 'Order_type', 'Quantity', 'Price', 'Exchange',
            'Take_Profit', 'Stop_Loss', 'Description', 'Details',
            'signal_bot', 'grid_bot', 'martingale_bot', 'quantum_ai_investment',
            'signal_bot_info', 'grid_bot_info', 'martingale_bot_info', 'quantum_ai_info'
        ]

    def get_user_info(self, obj):
        if obj.user:
            return {'id': str(obj.user.id), 'email': obj.user.email}
        return None

    def get_signal_bot_info(self, obj):
        if obj.signal_bot:
            return {'id': str(obj.signal_bot.id), 'bot_name': obj.signal_bot.bot_name}
        return None

    def get_grid_bot_info(self, obj):
        if obj.grid_bot:
            return {'id': str(obj.grid_bot.id), 'bot_name': obj.grid_bot.bot_name}
        return None

    def get_martingale_bot_info(self, obj):
        if obj.martingale_bot:
            return {'id': str(obj.martingale_bot.id), 'bot_name': obj.martingale_bot.bot_name}
        return None

    def get_quantum_ai_info(self, obj):
        if obj.quantum_ai_investment:
            return {
                'id': str(obj.quantum_ai_investment.id),
                'amount': obj.quantum_ai_investment.amount
            }
        return None


# ==================== INDICATOR ====================

class IndicatorSerializer(serializers.ModelSerializer):
    """Serializer for Indicator model."""
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = Indicator
        fields = [
            'id', 'user', 'Pair', 'EMA', 'RSI', 'Prev_RSI',
            'Color', 'Prev_Color', 'BB', 'TSI', 'ADX'
        ]


# ==================== TELEGRAM SIGNALS ====================

class TelegramSignalPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = TelegramSignalPlan
        fields = '__all__'


class TelegramSignalSubscriptionSerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    is_active = serializers.ReadOnlyField()

    class Meta:
        model = TelegramSignalSubscription
        fields = [
            'id', 'user', 'plan', 'telegram_handle', 'invitation_link',
            'joined_channel', 'joined_at', 'status', 'subscribed_at',
            'approved_at', 'expires_at', 'is_active'
        ]
        read_only_fields = [
            'invitation_link', 'joined_at', 'subscribed_at', 'approved_at',
            'expires_at', 'is_active'
        ]


# ==================== QUANTUM DEPOSITS ====================

class QuantumDepositWalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuantumDepositWallet
        fields = ['id', 'coin', 'blockchain', 'address', 'is_active']


class QuantumDepositSerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    is_expired = serializers.ReadOnlyField()

    class Meta:
        model = QuantumDeposit
        fields = [
            'id', 'user', 'wallet', 'amount', 'transaction_hash', 'screenshot',
            'status', 'review_notes', 'reviewed_by', 'reviewed_at', 'is_expired'
        ]
        read_only_fields = ['status', 'reviewed_by', 'reviewed_at', 'is_expired']


# ==================== BOT OVERVIEW ====================

class BotOverviewSerializer(serializers.Serializer):
    """Serializer for bot overview statistics."""
    total_bots = serializers.IntegerField(read_only=True)
    running_bots = serializers.IntegerField(read_only=True)
    total_users = serializers.IntegerField(read_only=True)
    daily_trades = serializers.IntegerField(read_only=True)
    platform_volume = serializers.DecimalField(max_digits=20, decimal_places=2, read_only=True)
    by_type = serializers.DictField(read_only=True)
    by_exchange = serializers.DictField(read_only=True)