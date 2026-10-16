"""
Investment App Serializers for Torgovo Crypto Trading Platform
Comprehensive serializer implementation matching DOCUMENTATION.md
"""

import logging

from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.bots.models import InvestorLock, QuantumWithdrawalRequest
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


# ========== A5 QUANTUM AI LOCKS (G3 — FUNCTIONAL_REQUIREMENTS.md §A5) ==========


class QuantumLockSerializer(serializers.ModelSerializer):
    """InvestorLock with A5 derived state exposed read-only."""

    user = UserNestedSerializer(read_only=True)
    fund = serializers.PrimaryKeyRelatedField(read_only=True)
    # Derived A5 properties (computed, never client-writable)
    available_balance = serializers.ReadOnlyField()
    is_matured = serializers.ReadOnlyField()
    is_withdrawable = serializers.ReadOnlyField()
    credit_available = serializers.ReadOnlyField()
    terms_credited = serializers.ReadOnlyField()

    class Meta:
        model = InvestorLock
        fields = [
            "id",
            "user",
            "fund",
            "subscription",
            "deposit",
            "amount",
            "lock_days",
            "status",
            "term_number",
            "credited_term",
            "terms_credited",
            "profit_credited_total",
            "withdrawn_total",
            "available_balance",
            "starts_at",
            "matures_at",
            "is_matured",
            "is_withdrawable",
            "credit_available",
            "cancelled_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class QuantumWithdrawalRequestSerializer(serializers.ModelSerializer):
    """Withdrawal request incl. admin decision fields + pending age (7-day SLA)."""

    user = UserNestedSerializer(read_only=True)
    lock = serializers.PrimaryKeyRelatedField(read_only=True)
    decided_by = UserNestedSerializer(read_only=True)
    days_pending = serializers.SerializerMethodField()

    class Meta:
        model = QuantumWithdrawalRequest
        fields = [
            "id",
            "user",
            "lock",
            "amount_requested",
            "status",
            "admin_entered_payout",
            "admin_notes",
            "requested_at",
            "decided_at",
            "decided_by",
            "payment_transaction",
            "days_pending",
        ]
        read_only_fields = fields

    def get_days_pending(self, obj) -> int | None:
        """Age of a pending request in whole days — surfaces the 7-day SLA."""
        if obj.status != "pending":
            return None
        from django.utils import timezone as _tz

        return (_tz.now() - obj.requested_at).days
