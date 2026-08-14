"""
Serializers for payment models
"""

from decimal import Decimal

from rest_framework import serializers

from .models import (
    BlockchainAddress,
    BotSubscription,
    BotSubscriptionPlan,
    PaymentTransaction,
    QuantumAIDeposit,
    ReferralPayout,
    SubscriptionPlan,
    WithdrawalRequest,
)


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    """
    Serializer for SubscriptionPlan model.
    """

    class Meta:
        model = SubscriptionPlan
        fields = [
            "id",
            "name",
            "slug",
            "price_monthly",
            "price_yearly",
            "max_bots_allowed",
            "max_webhooks_allowed",
            "features",
            "is_active",
            "trial_days",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class QuantumAIDepositSerializer(serializers.ModelSerializer):
    """
    Serializer for QuantumAIDeposit model.
    """

    user_email = serializers.EmailField(source="user.email", read_only=True)
    bot_name = serializers.CharField(source="quantum_bot.bot_name", read_only=True)
    is_expired = serializers.BooleanField(read_only=True)

    class Meta:
        model = QuantumAIDeposit
        fields = [
            "id",
            "user",
            "user_email",
            "quantum_bot",
            "bot_name",
            "amount",
            "currency",
            "blockchain",
            "from_address",
            "transaction_hash",
            "block_number",
            "block_confirmations",
            "required_confirmations",
            "transaction_screenshot",
            "transaction_proof",
            "status",
            "admin_notes",
            "verified_by",
            "verified_at",
            "verification_method",
            "usdt_amount",
            "exchange_rate",
            "risk_score",
            "flagged_for_review",
            "is_expired",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "user",
            "user_email",
            "bot_name",
            "verified_by",
            "verified_at",
            "is_expired",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "quantum_bot": {"write_only": True},
            "admin_notes": {"read_only": True},
            "verification_method": {"read_only": True},
            "risk_score": {"read_only": True},
            "flagged_for_review": {"read_only": True},
        }


class BlockchainAddressSerializer(serializers.ModelSerializer):
    """
    Serializer for BlockchainAddress model.
    """

    class Meta:
        model = BlockchainAddress
        fields = [
            "id",
            "coin_type",
            "blockchain",
            "address",
            "label",
            "is_active",
            "is_hot_wallet",
            "balance",
            "last_used",
            "usage_count",
            "requires_multisig",
            "min_confirmations",
            "max_daily_limit",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "balance", "last_used", "usage_count", "created_at", "updated_at"]


class WithdrawalRequestSerializer(serializers.ModelSerializer):
    """
    Serializer for WithdrawalRequest model.

    SECURITY: ``user``, ``status``, ``network_fee``, ``processing_fee``,
    ``total_amount`` and admin fields are read-only because they are
    server-controlled. Allowing them to be writable let any authenticated
    user submit a withdrawal status='completed', a free zero-fee withdrawal,
    or one impersonating another user.
    """

    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = WithdrawalRequest
        fields = [
            "id",
            "user",
            "user_email",
            "amount",
            "currency",
            "blockchain",
            "to_address",
            "transaction_hash",
            "status",
            "network_fee",
            "processing_fee",
            "total_amount",
            "two_factor_code",
            "email_verification_token",
            "admin_approved_by",
            "admin_notes",
            "risk_score",
            "flagged_for_review",
            "ip_address",
            "user_agent",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "user",
            "user_email",
            "transaction_hash",
            "status",
            "network_fee",
            "processing_fee",
            "total_amount",
            "admin_approved_by",
            "admin_notes",
            "risk_score",
            "flagged_for_review",
            "ip_address",
            "user_agent",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "two_factor_code": {"write_only": True, "required": True},
            "email_verification_token": {"write_only": True, "required": False},
        }

    def validate_amount(self, value):
        """Validate withdrawal amount."""
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than 0")
        # Minimum withdrawal (configurable; default $10)
        from django.conf import settings

        min_w = getattr(settings, "WITHDRAWAL_MIN_AMOUNT", Decimal("10"))
        if Decimal(value) < Decimal(str(min_w)):
            raise serializers.ValidationError(f"Minimum withdrawal is {min_w}")
        return value

    def validate_to_address(self, value):
        """Validate withdrawal address."""
        if not value or len(value) < 10:
            raise serializers.ValidationError("Invalid withdrawal address")
        return value

    def validate_blockchain(self, value):
        """Validate chain matches one of the supported chains."""
        allowed = {
            "BEP20",
            "ERC20",
            "TRC20",
            "SOL",
            "APTOS",
            "POLYGON",
            "ARBITRUM",
            "OPTIMISM",
            "AVALANCHE",
            "FANTOM",
            "Bitcoin",
        }
        if value not in allowed:
            raise serializers.ValidationError(f"Unsupported blockchain: {value}")
        return value

    def validate(self, attrs):
        # Cap concurrent pending withdrawals per user (anti-flood)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            pending = WithdrawalRequest.objects.filter(
                user=request.user,
                status__in=("pending", "processing"),
            ).count()
            if pending >= 3:
                raise serializers.ValidationError(
                    "Too many pending withdrawals (limit: 3). "
                    "Wait for one to complete before requesting another."
                )
        return attrs


class PaymentTransactionSerializer(serializers.ModelSerializer):
    """
    Serializer for PaymentTransaction model.
    """

    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = PaymentTransaction
        fields = [
            "id",
            "user",
            "user_email",
            "transaction_type",
            "amount",
            "currency",
            "reference_id",
            "external_id",
            "gateway",
            "status",
            "description",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "user", "user_email", "reference_id", "created_at", "updated_at"]


class ReferralPayoutSerializer(serializers.ModelSerializer):
    """
    Serializer for ReferralPayout model.
    """

    referrer_email = serializers.EmailField(source="referrer.email", read_only=True)
    referred_user_email = serializers.EmailField(source="referred_user.email", read_only=True)

    class Meta:
        model = ReferralPayout
        fields = [
            "id",
            "referrer",
            "referrer_email",
            "referred_user",
            "referred_user_email",
            "amount",
            "percentage",
            "source_transaction",
            "status",
            "paid_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "referrer_email",
            "referred_user_email",
            "paid_at",
            "created_at",
            "updated_at",
        ]


# ==================== BOT SUBSCRIPTION SERIALIZERS ====================


class BotSubscriptionPlanSerializer(serializers.ModelSerializer):
    """
    Serializer for BotSubscriptionPlan model.
    """

    class Meta:
        model = BotSubscriptionPlan
        fields = [
            "id",
            "bot_type",
            "name",
            "price",
            "duration_days",
            "description",
            "features",
            "is_active",
            "requires_approval",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class BotSubscriptionSerializer(serializers.ModelSerializer):
    """
    Serializer for BotSubscription model with webhook config support.
    """

    plan = BotSubscriptionPlanSerializer(read_only=True)
    webhook_config = serializers.SerializerMethodField()
    is_expired = serializers.BooleanField(read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = BotSubscription
        fields = [
            "id",
            "user",
            "user_email",
            "plan",
            "status",
            "payment_screenshot",
            "payment_transaction_hash",
            "payment_blockchain",
            "exchange_name",
            "webhook_config",
            "approved_by",
            "approved_at",
            "rejected_by",
            "rejected_at",
            "rejection_reason",
            "notes",
            "started_at",
            "expires_at",
            "is_expired",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "user",
            "user_email",
            "plan",
            "webhook_config",
            "is_expired",
            "approved_by",
            "approved_at",
            "rejected_by",
            "rejected_at",
            "started_at",
            "expires_at",
            "created_at",
            "updated_at",
        ]

    def get_webhook_config(self, obj):
        """
        Return webhook configuration for custom bots only.
        """
        if obj.plan.bot_type == "custom" and obj.webhook_secret:
            return obj.get_webhook_json_template()
        return None
