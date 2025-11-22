"""
Serializers for subscription management models
"""
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal

from .models import (
    SubscriptionPlan, UserSubscription, SubscriptionDiscount,
    SubscriptionUsage, SubscriptionFeature
)

User = get_user_model()


class SubscriptionFeatureSerializer(serializers.ModelSerializer):
    """
    Serializer for SubscriptionFeature model.
    """
    feature_display = serializers.CharField(source='get_feature_type_display', read_only=True)

    class Meta:
        model = SubscriptionFeature
        fields = [
            'id', 'subscription_plan', 'feature_type', 'feature_display',
            'description', 'usage_limit', 'is_active', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    """
    Serializer for SubscriptionPlan model.
    """
    features = SubscriptionFeatureSerializer(many=True, read_only=True)
    currency_display = serializers.CharField(source='get_currency_display', read_only=True)
    billing_cycle_display = serializers.CharField(source='get_billing_cycle_display', read_only=True)

    class Meta:
        model = SubscriptionPlan
        fields = [
            'id', 'name', 'description', 'price_per_month', 'price_per_year',
            'currency', 'currency_display', 'billing_cycle', 'billing_cycle_display',
            'trial_days', 'max_users', 'features', 'is_popular',
            'is_active', 'sort_order', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at'
        ]

    def validate(self, data):
        """Validate subscription plan data."""
        billing_cycle = data.get('billing_cycle')
        price_per_month = data.get('price_per_month')
        price_per_year = data.get('price_per_year')

        if billing_cycle == 'monthly' and not price_per_month:
            raise serializers.ValidationError("Monthly price is required for monthly billing")

        if billing_cycle == 'yearly' and not price_per_year:
            raise serializers.ValidationError("Yearly price is required for yearly billing")

        return data


class SubscriptionDiscountSerializer(serializers.ModelSerializer):
    """
    Serializer for SubscriptionDiscount model.
    """
    discount_type_display = serializers.CharField(source='get_discount_type_display', read_only=True)
    is_expired = serializers.SerializerMethodField()

    class Meta:
        model = SubscriptionDiscount
        fields = [
            'id', 'code', 'description', 'discount_type', 'discount_type_display',
            'discount_value', 'start_date', 'end_date', 'usage_limit',
            'usage_limit_per_user', 'times_used', 'is_active', 'is_expired',
            'applicable_plans', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'times_used', 'created_at', 'updated_at'
        ]

    def get_is_expired(self, obj):
        """Check if discount is expired."""
        if obj.end_date and obj.end_date < timezone.now():
            return True
        if obj.start_date and obj.start_date > timezone.now():
            return True
        return False

    def validate_code(self, value):
        """Validate discount code uniqueness."""
        value = value.upper().strip()
        if SubscriptionDiscount.objects.filter(code__iexact=value).exists():
            if self.instance and self.instance.code.upper() != value:
                raise serializers.ValidationError("Discount code already exists")
        return value

    def validate(self, data):
        """Validate discount data."""
        start_date = data.get('start_date')
        end_date = data.get('end_date')

        if start_date and end_date and start_date > end_date:
            raise serializers.ValidationError("End date must be after start date")

        discount_value = data.get('discount_value')
        discount_type = data.get('discount_type')

        if discount_type == 'percentage' and (discount_value <= 0 or discount_value > 100):
            raise serializers.ValidationError("Percentage discount must be between 0 and 100")

        if discount_type == 'fixed' and discount_value <= 0:
            raise serializers.ValidationError("Fixed discount must be greater than 0")

        return data


class UserSubscriptionSerializer(serializers.ModelSerializer):
    """
    Serializer for UserSubscription model.
    """
    plan_name = serializers.CharField(source='plan.name', read_only=True)
    plan_description = serializers.CharField(source='plan.description', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    auto_renew_display = serializers.CharField(source='get_auto_renew_display', read_only=True)
    days_remaining = serializers.SerializerMethodField()
    is_trial = serializers.SerializerMethodField()
    next_billing_date = serializers.SerializerMethodField()

    class Meta:
        model = UserSubscription
        fields = [
            'id', 'user', 'plan', 'plan_name', 'plan_description',
            'status', 'status_display', 'start_date', 'end_date',
            'auto_renew', 'auto_renew_display', 'cancel_at_period_end',
            'cancelled_at', 'trial_end_date', 'billing_cycle',
            'discount', 'amount_paid', 'currency',
            'days_remaining', 'is_trial', 'next_billing_date',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'user', 'start_date', 'amount_paid',
            'cancelled_at', 'created_at', 'updated_at'
        ]

    def get_days_remaining(self, obj):
        """Calculate days remaining in subscription."""
        if obj.end_date:
            remaining = obj.end_date - timezone.now().date()
            return max(0, remaining.days)
        return 0

    def get_is_trial(self, obj):
        """Check if subscription is in trial period."""
        if obj.trial_end_date:
            return timezone.now().date() <= obj.trial_end_date
        return False

    def get_next_billing_date(self, obj):
        """Get next billing date."""
        if obj.auto_renew and not obj.cancel_at_period_end and obj.end_date:
            return obj.end_date
        return None

    def validate_plan(self, value):
        """Validate subscription plan is active."""
        if not value.is_active:
            raise serializers.ValidationError("This subscription plan is not available")
        return value

    def create(self, validated_data):
        """Create user subscription with proper date calculations."""
        user = self.context['request'].user
        plan = validated_data['plan']
        billing_cycle = validated_data.get('billing_cycle', plan.billing_cycle)

        # Check for existing active subscription
        existing_active = UserSubscription.objects.filter(
            user=user,
            status='active'
        ).first()

        if existing_active:
            raise serializers.ValidationError(
                "You already have an active subscription. Please cancel it first."
            )

        # Calculate dates
        start_date = timezone.now().date()
        trial_end_date = None

        if plan.trial_days > 0:
            trial_end_date = start_date + timezone.timedelta(days=plan.trial_days)

        # Calculate end date based on billing cycle
        if billing_cycle == 'monthly':
            end_date = start_date + timezone.timedelta(days=30)
        else:  # yearly
            end_date = start_date + timezone.timedelta(days=365)

        # Calculate amount
        if billing_cycle == 'monthly':
            amount = plan.price_per_month
        else:
            amount = plan.price_per_year

        # Apply discount if provided
        discount = validated_data.get('discount')
        if discount:
            if discount.discount_type == 'percentage':
                discount_amount = (amount * discount.discount_value) / Decimal('100')
            else:
                discount_amount = min(discount.discount_value, amount)
            amount -= discount_amount

        return UserSubscription.objects.create(
            user=user,
            start_date=start_date,
            end_date=end_date,
            trial_end_date=trial_end_date,
            amount_paid=amount,
            **validated_data
        )


class SubscriptionUsageSerializer(serializers.ModelSerializer):
    """
    Serializer for SubscriptionUsage model.
    """
    feature_name = serializers.CharField(source='feature.name', read_only=True)
    feature_description = serializers.CharField(source='feature.description', read_only=True)
    usage_limit = serializers.IntegerField(source='feature.usage_limit', read_only=True)
    usage_percentage = serializers.SerializerMethodField()

    class Meta:
        model = SubscriptionUsage
        fields = [
            'id', 'user', 'feature', 'feature_name', 'feature_description',
            'date', 'usage_count', 'usage_limit', 'usage_percentage',
            'metadata', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'user', 'created_at', 'updated_at'
        ]

    def get_usage_percentage(self, obj):
        """Calculate usage percentage against limit."""
        if obj.feature.usage_limit and obj.feature.usage_limit > 0:
            return min(100, (obj.usage_count / obj.feature.usage_limit) * 100)
        return 0

    def validate(self, data):
        """Validate usage data."""
        feature = data.get('feature')
        usage_count = data.get('usage_count', 0)

        if usage_count < 0:
            raise serializers.ValidationError("Usage count cannot be negative")

        if feature and feature.usage_limit and usage_count > feature.usage_limit:
            raise serializers.ValidationError(
                f"Usage count ({usage_count}) exceeds limit ({feature.usage_limit})"
            )

        return data


class SubscriptionUpgradeSerializer(serializers.Serializer):
    """
    Serializer for subscription upgrade requests.
    """
    plan_id = serializers.UUIDField(required=True)

    def validate_plan_id(self, value):
        """Validate upgrade plan exists and is more expensive."""
        try:
            plan = SubscriptionPlan.objects.get(id=value, is_active=True)
            return plan
        except SubscriptionPlan.DoesNotExist:
            raise serializers.ValidationError("Invalid subscription plan")


class SubscriptionCancellationSerializer(serializers.Serializer):
    """
    Serializer for subscription cancellation requests.
    """
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)
    feedback = serializers.CharField(required=False, allow_blank=True, max_length=1000)


class SubscriptionLimitsSerializer(serializers.Serializer):
    """
    Serializer for subscription limits response.
    """
    feature = serializers.CharField()
    description = serializers.CharField()
    current_usage = serializers.IntegerField()
    limit = serializers.IntegerField()
    usage_percentage = serializers.DecimalField(max_digits=5, decimal_places=2)
    reset_date = serializers.DateField()


class SubscriptionUsageSummarySerializer(serializers.Serializer):
    """
    Serializer for usage summary response.
    """
    feature = serializers.CharField()
    usage_count = serializers.IntegerField()
    usage_limit = serializers.IntegerField()
    reset_date = serializers.DateField()