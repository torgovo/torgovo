"""
Serializers for subscription models.
"""

from rest_framework import serializers

from .models import (
    SignalResult,
    SignalStatistics,
    TelegramChannel,
    TelegramSignalPlan,
    TelegramSubscription,
    TelegramSubscriptionChannel,
    TradingSignal,
)


class TelegramPlanSerializer(serializers.ModelSerializer):
    channels = serializers.SerializerMethodField()

    class Meta:
        model = TelegramSignalPlan
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "price_monthly",
            "price_quarterly",
            "price_yearly",
            "signals_per_day",
            "exchanges_covered",
            "risk_level",
            "success_rate",
            "max_subscribers",
            "features",
            "is_active",
            "trial_days",
            "channels",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_channels(self, obj):
        return [
            {
                "id": tc.id,
                "channel_id": tc.channel_id,
                "channel_name": tc.name,
            }
            for tc in TelegramChannel.objects.filter(required_plan_id__in=[obj.id])
        ]


class TelegramChannelSerializer(serializers.ModelSerializer):
    class Meta:
        model = TelegramChannel
        fields = "__all__"


class TelegramSubscriptionSerializer(serializers.ModelSerializer):
    plan_details = TelegramPlanSerializer(source="plan", read_only=True)

    class Meta:
        model = TelegramSubscription
        fields = [
            "id",
            "user",
            "plan",
            "plan_details",
            "status",
            "started_at",
            "end_date",
            "auto_renew",
            "telegram_user_id",
            "telegram_handle",
            "signals_received",
            "payment_screenshot",
            "billing_cycle",
            "amount_paid",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "user",
            "signals_received",
            "created_at",
            "updated_at",
        ]


class TelegramSubscriptionChannelSerializer(serializers.ModelSerializer):
    class Meta:
        model = TelegramSubscriptionChannel
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]


class TradingSignalSerializer(serializers.ModelSerializer):
    class Meta:
        model = TradingSignal
        fields = "__all__"
        read_only_fields = ["id", "created_at"]


class SignalResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = SignalResult
        fields = "__all__"
        read_only_fields = ["id", "created_at"]


class SignalStatisticsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SignalStatistics
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]


class SubscriptionPlanSerializer(serializers.Serializer):
    """Legacy compatibility serializer — maps Telegram plans to generic format."""

    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    interval = serializers.ChoiceField(choices=["monthly", "quarterly", "yearly"])
    max_signals = serializers.IntegerField()
    is_active = serializers.BooleanField()


class SubscribeSerializer(serializers.Serializer):
    plan_id = serializers.UUIDField()
    interval = serializers.ChoiceField(choices=["monthly", "quarterly", "yearly"])
    payment_screenshot = serializers.ImageField(required=False)
