"""
Serializers for admin endpoints
"""

from django.contrib.auth import get_user_model
from django.db import models
from rest_framework import serializers

User = get_user_model()


class UserAdminSerializer(serializers.ModelSerializer):
    """Admin user list serializer with additional fields."""

    full_name = serializers.ReadOnlyField()
    total_deposits = serializers.IntegerField(read_only=True)
    active_bots_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "username",
            "first_name",
            "last_name",
            "full_name",
            "phone_number",
            "is_active",
            "is_staff",
            "is_email_verified",
            "is_phone_verified",
            "date_joined",
            "last_login",
            "subscription_plan",
            "is_subscription_active",
            "max_bots_allowed",
            "demo_trading_enabled",
            "total_trades_executed",
            "total_deposits",
            "active_bots_count",
        ]


class UserAdminDetailSerializer(serializers.ModelSerializer):
    """Detailed user information for admin."""

    full_name = serializers.ReadOnlyField()

    # Trading statistics
    total_bots = serializers.SerializerMethodField()
    total_deposits = serializers.SerializerMethodField()
    last_activity = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "username",
            "first_name",
            "last_name",
            "full_name",
            "phone_number",
            "is_active",
            "is_staff",
            "is_email_verified",
            "is_phone_verified",
            "date_joined",
            "last_login",
            "last_activity",
            "subscription_plan",
            "is_subscription_active",
            "max_bots_allowed",
            "demo_trading_enabled",
            "total_trades_executed",
            "total_bots",
            "total_deposits",
        ]
        read_only_fields = ["id", "date_joined", "last_login"]

    def get_total_bots(self, obj):
        """Get total number of bots for this user."""
        from apps.bots.models import GridBot, MartingaleBot, SignalBot

        return (
            SignalBot.objects.filter(user=obj, is_deleted=False).count()
            + GridBot.objects.filter(user=obj, is_deleted=False).count()
            + MartingaleBot.objects.filter(user=obj, is_deleted=False).count()
        )

    def get_total_deposits(self, obj):
        """Get total deposited amount for Quantum AI."""
        from apps.payments.models import InvestorDeposit

        deposit_deposits = (
            InvestorDeposit.objects.filter(user=obj, status="approved").aggregate(
                total=models.Sum("usdt_amount")
            )["total"]
            or 0
        )

        return float(deposit_deposits)

    def get_last_activity(self, obj):
        """Get user's last activity timestamp."""
        from apps.bots.models import BotOrder

        last_order = BotOrder.objects.filter(user=obj).order_by("-created_at").first()
        return last_order.created_at if last_order else obj.last_login
