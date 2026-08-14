"""
Investment App Serializers for Torgovo Crypto Trading Platform
Comprehensive serializer implementation matching DOCUMENTATION.md
"""

import logging

from django.contrib.auth import get_user_model
from django.db import models
from rest_framework import serializers

from apps.exchanges.models import Exchange, TradingPair

from .models import InvestmentBalance, Order, Position, TechnicalIndicator

logger = logging.getLogger(__name__)
User = get_user_model()


# ========== BASE & UTILITY SERIALIZERS ==========


class ExchangeNestedSerializer(serializers.ModelSerializer):
    """Lightweight exchange info for nested representations"""

    class Meta:
        model = Exchange
        fields = ["id", "name", "display_name"]


class TradingPairNestedSerializer(serializers.ModelSerializer):
    """Lightweight trading pair info for nested representations"""

    exchange_name = serializers.CharField(read_only=True)

    class Meta:
        model = TradingPair
        fields = ["id", "symbol", "base_asset", "quote_asset", "exchange_name"]


class UserNestedSerializer(serializers.ModelSerializer):
    """Lightweight user info for nested representations"""

    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name"]


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

    # Display fields
    exchange_name = serializers.CharField(source="exchange.name", read_only=True)
    pair = serializers.CharField(source="trading_pair.symbol", read_only=True)

    # Timestamp formatting (API docs use capital 'Time')
    Time = serializers.DateTimeField(source="created_at", read_only=True)

    # Price formatting
    Price = serializers.DecimalField(
        source="price", max_digits=20, decimal_places=8, read_only=True
    )
    Take_Profit = serializers.DecimalField(
        source="take_profit", max_digits=20, decimal_places=8, read_only=True, allow_null=True
    )
    Stop_Loss = serializers.DecimalField(
        source="stop_loss", max_digits=20, decimal_places=8, read_only=True, allow_null=True
    )

    # Capitalised aliases for API docs compatibility
    Side = serializers.SerializerMethodField()
    Description = serializers.SerializerMethodField()

    # P&L field
    profit_loss = serializers.DecimalField(max_digits=20, decimal_places=8, read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "user",
            "exchange",
            "exchange_id",
            "exchange_name",
            "trading_pair",
            "trading_pair_id",
            "pair",
            "order_type",
            "Side",
            "quantity",
            "Price",
            "filled_quantity",
            "average_price",
            "Take_Profit",
            "Stop_Loss",
            "status",
            "profit_loss",
            "Description",
            "executed_at",
            "Time",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "user",
            "filled_quantity",
            "average_price",
            "profit_loss",
            "executed_at",
            "created_at",
        ]
        extra_kwargs = {
            "order_type": {"required": True},
            "quantity": {"required": True},
            "price": {"required": True},
        }

    def get_Side(self, obj):
        """Capitalize side for API docs compatibility"""
        return obj.side.capitalize() if obj.side else None

    def get_Description(self, obj):
        """Capitalize description field for API docs"""
        return obj.description or ""

    def validate_quantity(self, value):
        """Ensure positive quantity"""
        if value <= 0:
            raise serializers.ValidationError("Quantity must be positive")
        return value

    def validate_price(self, value):
        """Ensure non-negative price"""
        if value < 0:
            raise serializers.ValidationError("Price cannot be negative")
        return value

    def create(self, validated_data):
        """Auto-assign user"""
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)


# ========== POSITION SERIALIZER ==========


class PositionSerializer(serializers.ModelSerializer):
    """Open positions serializer"""

    user = UserNestedSerializer(read_only=True)
    exchange = ExchangeNestedSerializer(read_only=True)
    trading_pair = TradingPairNestedSerializer(read_only=True)

    exchange_id = serializers.UUIDField(write_only=True)
    trading_pair_id = serializers.UUIDField(write_only=True)

    exchange_name = serializers.CharField(source="exchange.name", read_only=True)
    pair = serializers.CharField(source="trading_pair.symbol", read_only=True)

    # P&L calculations
    unrealized_pnl_display = serializers.DecimalField(
        source="unrealized_pnl", max_digits=20, decimal_places=8, read_only=True
    )
    unrealized_pnl_percent_display = serializers.DecimalField(
        source="unrealized_pnl_percent", max_digits=10, decimal_places=4, read_only=True
    )

    class Meta:
        model = Position
        fields = [
            "id",
            "user",
            "exchange",
            "trading_pair",
            "exchange_id",
            "trading_pair_id",
            "exchange_name",
            "pair",
            "side",
            "quantity",
            "entry_price",
            "current_price",
            "leverage",
            "liquidation_price",
            "unrealized_pnl",
            "unrealized_pnl_percent",
            "unrealized_pnl_display",
            "unrealized_pnl_percent_display",
            "opened_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "user", "created_at", "updated_at"]

    def validate_leverage(self, value):
        """Leverage bounds check"""
        if not (1 <= value <= 125):
            raise serializers.ValidationError("Leverage must be between 1x and 125x")
        return value

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)


# ========== TECHNICAL INDICATOR SERIALIZER ==========


class TechnicalIndicatorSerializer(serializers.ModelSerializer):
    """Technical indicator webhook data"""

    exchange = ExchangeNestedSerializer(read_only=True)
    trading_pair = TradingPairNestedSerializer(read_only=True)

    exchange_name = serializers.CharField(source="exchange.name", read_only=True)
    pair = serializers.CharField(source="trading_pair.symbol", read_only=True)

    class Meta:
        model = TechnicalIndicator
        fields = [
            "id",
            "indicator_type",
            "trading_pair",
            "exchange",
            "exchange_name",
            "pair",
            "values",
            "color",
            "prev_color",
            "triggered_at",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


# ========== BALANCE SERIALIZER ==========


class UserBalanceSerializer(serializers.ModelSerializer):
    """User balance across exchanges"""

    user = UserNestedSerializer(read_only=True)
    exchange = ExchangeNestedSerializer(read_only=True)

    exchange_name = serializers.CharField(source="exchange.name", read_only=True)
    currency_display = serializers.CharField(source="currency", read_only=True)

    class Meta:
        model = InvestmentBalance
        fields = [
            "id",
            "user",
            "exchange",
            "exchange_name",
            "currency",
            "currency_display",
            "available",
            "locked",
            "total",
        ]
        read_only_fields = ["id", "total"]

    def validate(self, data):
        """Ensure total = available + locked"""
        if "available" in data and "locked" in data:
            data["total"] = data["available"] + data["locked"]
        elif "available" in data and "total" not in data:
            data["total"] = data["available"]
        return data

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
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
        request = self.context["request"]
        user = request.user

        total_trades = Order.objects.filter(user=user).count()
        total_volume = (
            Order.objects.filter(user=user).aggregate(total=models.Sum("quantity"))["total"] or 0
        )

        return {
            "id": str(user.id),
            "user_email": user.email,
            "user_full_name": user.get_full_name(),
            "subscription_plan": getattr(user, "subscription_plan", "basic"),
            "max_bots_allowed": getattr(user, "max_bots_allowed", 10),
            "timezone": getattr(user, "timezone", "UTC"),
            "demo_trading_enabled": getattr(user, "demo_trading_enabled", True),
            "email_notifications": getattr(user, "email_notifications", True),
            "is_subscription_active": getattr(user, "is_subscription_active", True),
            "total_trades_executed": total_trades,
            "total_volume_traded": str(total_volume),
        }

    def get_balances(self, obj):
        """Get all user balances"""
        request = self.context["request"]
        balances = InvestmentBalance.objects.filter(user=request.user)
        total_usdt = sum(balance.total for balance in balances if balance.currency == "USDT")

        return {
            "total_usdt_value": str(total_usdt),
            "balances": UserBalanceSerializer(balances, many=True).data,
        }

    def get_open_positions(self, obj):
        """Get open positions with P&L"""
        request = self.context["request"]
        positions = Position.objects.filter(user=request.user)
        return PositionSerializer(positions, many=True).data

    def get_active_bots(self, obj):
        """Get active trading bots from apps.bots"""
        request = self.context["request"]
        from apps.bots.models import SignalBot

        bots = SignalBot.objects.filter(user=request.user, is_active=True)
        from apps.bots.serializers import SignalBotSerializer

        return SignalBotSerializer(bots, many=True, context=self.context).data

    def get_recent_orders(self, obj):
        """Get recent 20 orders"""
        request = self.context["request"]
        orders = Order.objects.filter(user=request.user).order_by("-created_at")[:20]
        return OrderSerializer(orders, many=True).data

    class Meta:
        fields = ["user_profile", "balances", "open_positions", "active_bots", "recent_orders"]
        read_only_fields = fields
