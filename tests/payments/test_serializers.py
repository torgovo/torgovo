from decimal import Decimal

import pytest

from apps.payments.models import (
    BlockchainAddress,
    BotSubscription,
    BotSubscriptionPlan,
    InvestorDeposit,
    PaymentTransaction,
    ReferralPayout,
    SubscriptionPlan,
    WithdrawalRequest,
)
from apps.payments.serializers import (
    BlockchainAddressSerializer,
    BotSubscriptionPlanSerializer,
    BotSubscriptionSerializer,
    InvestorDepositSerializer,
    PaymentTransactionSerializer,
    ReferralPayoutSerializer,
    SubscriptionPlanSerializer,
    WithdrawalRequestSerializer,
)


@pytest.mark.django_db
class TestSubscriptionPlanSerializer:
    def test_serialize_plan(self, db):
        plan = SubscriptionPlan.objects.create(
            name="Pro",
            slug="pro",
            price_monthly=Decimal("49.99"),
            price_yearly=Decimal("499.99"),
            max_bots_allowed=10,
            max_webhooks_allowed=50,
            features=["api_access"],
            trial_days=14,
        )
        serializer = SubscriptionPlanSerializer(plan)
        assert serializer.data["name"] == "Pro"
        assert serializer.data["slug"] == "pro"
        assert Decimal(serializer.data["price_monthly"]) == Decimal("49.99")
        assert serializer.data["is_active"] is True
        assert serializer.data["trial_days"] == 14

    def test_read_only_fields(self, db):
        plan = SubscriptionPlan.objects.create(
            name="Basic",
            slug="basic",
            price_monthly=9.99,
            price_yearly=99.99,
            max_bots_allowed=1,
        )
        serializer = SubscriptionPlanSerializer(plan)
        assert "id" in serializer.data
        assert "created_at" in serializer.data
        assert "updated_at" in serializer.data


@pytest.mark.django_db
class TestInvestorDepositSerializer:
    def test_serialize_deposit(self, user):
        deposit = InvestorDeposit.objects.create(
            user=user,
            amount=Decimal("500.00000000"),
            currency="USDT",
            blockchain="BEP20",
            from_address="0xabc",
            transaction_hash="0xtxhash123",
        )
        serializer = InvestorDepositSerializer(deposit)
        assert serializer.data["user_email"] == user.email
        assert Decimal(serializer.data["amount"]) == Decimal("500.00000000")
        assert serializer.data["currency"] == "USDT"
        assert serializer.data["status"] == "pending"
        assert "is_expired" in serializer.data

    def test_read_only_fields(self, user):
        deposit = InvestorDeposit.objects.create(
            user=user,
            amount=Decimal("100"),
            currency="BTC",
            blockchain="Bitcoin",
            from_address="1abc",
            transaction_hash="0xtxhash456",
        )
        serializer = InvestorDepositSerializer(deposit)
        assert "user_email" in serializer.data
        assert "verified_by" in serializer.data
        assert "verified_at" in serializer.data


@pytest.mark.django_db
class TestBlockchainAddressSerializer:
    def test_serialize_address(self, db):
        addr = BlockchainAddress.objects.create(
            coin_type="USDT",
            blockchain="ERC20",
            address="0x1234567890abcdef1234567890abcdef12345678",
            label="Main Wallet",
        )
        serializer = BlockchainAddressSerializer(addr)
        assert serializer.data["coin_type"] == "USDT"
        assert serializer.data["blockchain"] == "ERC20"
        assert serializer.data["address"] == "0x1234567890abcdef1234567890abcdef12345678"
        assert serializer.data["is_active"] is True


@pytest.mark.django_db
class TestWithdrawalRequestSerializer:
    def test_serialize_withdrawal(self, user):
        withdrawal = WithdrawalRequest.objects.create(
            user=user,
            amount=Decimal("50.00000000"),
            currency="USDT",
            blockchain="BEP20",
            to_address="0xreceiver1234567890abc",
            total_amount=Decimal("50.00000000"),
        )
        serializer = WithdrawalRequestSerializer(withdrawal)
        assert serializer.data["user_email"] == user.email
        assert Decimal(serializer.data["amount"]) == Decimal("50.00000000")
        assert serializer.data["status"] == "pending"

    def test_validate_amount_zero(self):
        serializer = WithdrawalRequestSerializer(
            data={
                "amount": 0,
                "currency": "USDT",
                "blockchain": "BEP20",
                "to_address": "0x1234567890abcdef",
                "total_amount": 0,
            }
        )
        assert serializer.is_valid() is False
        assert "amount" in serializer.errors

    def test_validate_to_address_short(self):
        serializer = WithdrawalRequestSerializer(
            data={
                "amount": 100,
                "currency": "USDT",
                "blockchain": "BEP20",
                "to_address": "0xshort",
                "total_amount": 100,
            }
        )
        assert serializer.is_valid() is False
        assert "to_address" in serializer.errors

    def test_valid_withdrawal(self):
        serializer = WithdrawalRequestSerializer(
            data={
                "amount": 100.50,
                "currency": "USDT",
                "blockchain": "BEP20",
                "to_address": "0x1234567890abcdef1234567890abcdef12345678",
                "total_amount": 100.50,
                "two_factor_code": "123456",
            }
        )
        assert serializer.is_valid() is True


@pytest.mark.django_db
class TestPaymentTransactionSerializer:
    def test_serialize_transaction(self, user):
        tx = PaymentTransaction.objects.create(
            user=user,
            transaction_type="deposit",
            amount=Decimal("1000"),
            currency="USDT",
        )
        serializer = PaymentTransactionSerializer(tx)
        assert serializer.data["user_email"] == user.email
        assert serializer.data["transaction_type"] == "deposit"
        assert Decimal(serializer.data["amount"]) == Decimal("1000")

    def test_serialize_all_types(self, user):
        for tx_type in ["deposit", "withdrawal", "subscription", "refund", "fee"]:
            tx = PaymentTransaction.objects.create(
                user=user,
                transaction_type=tx_type,
                amount=Decimal("100"),
                currency="USDT",
                description=f"Test {tx_type}",
            )
            serializer = PaymentTransactionSerializer(tx)
            assert serializer.data["transaction_type"] == tx_type


@pytest.mark.django_db
class TestReferralPayoutSerializer:
    def test_serialize_payout(self, user, admin_user):
        payout = ReferralPayout.objects.create(
            referrer=user,
            referred_user=admin_user,
            amount=Decimal("25.00000000"),
            percentage=Decimal("10.00"),
        )
        serializer = ReferralPayoutSerializer(payout)
        assert serializer.data["referrer_email"] == user.email
        assert serializer.data["referred_user_email"] == admin_user.email
        assert Decimal(serializer.data["amount"]) == Decimal("25.00000000")


@pytest.mark.django_db
class TestBotSubscriptionPlanSerializer:
    def test_serialize_plan(self, db):
        plan = BotSubscriptionPlan.objects.create(
            bot_type="custom",
            name="Custom Bot",
            price=Decimal("99.99"),
            duration_days=30,
            description="Desc",
            features=["webhook"],
        )
        serializer = BotSubscriptionPlanSerializer(plan)
        assert serializer.data["bot_type"] == "custom"
        assert serializer.data["name"] == "Custom Bot"
        assert Decimal(serializer.data["price"]) == Decimal("99.99")
        assert serializer.data["is_active"] is True

    def test_read_only_fields(self, db):
        plan = BotSubscriptionPlan.objects.create(
            bot_type="grid",
            name="Grid Plan",
            price=49.99,
        )
        serializer = BotSubscriptionPlanSerializer(plan)
        assert "id" in serializer.data
        assert "created_at" in serializer.data


@pytest.mark.django_db
class TestBotSubscriptionSerializer:
    def test_serialize_subscription(self, user):
        plan = BotSubscriptionPlan.objects.create(
            bot_type="custom",
            name="Custom Plan",
            price=99.99,
        )
        sub = BotSubscription.objects.create(user=user, plan=plan)
        serializer = BotSubscriptionSerializer(sub)
        assert serializer.data["user_email"] == user.email
        assert serializer.data["status"] == "pending_payment"
        assert "plan" in serializer.data
        assert serializer.data["plan"]["bot_type"] == "custom"

    def test_webhook_config_for_custom_bot(self, user):
        plan = BotSubscriptionPlan.objects.create(
            bot_type="custom",
            name="Custom Plan",
            price=99.99,
        )
        sub = BotSubscription.objects.create(
            user=user,
            plan=plan,
            webhook_secret="sec-12345",
        )
        serializer = BotSubscriptionSerializer(sub)
        assert serializer.data["webhook_config"] is not None

    def test_webhook_config_null_for_non_custom(self, user):
        plan = BotSubscriptionPlan.objects.create(
            bot_type="grid",
            name="Grid Plan",
            price=49.99,
        )
        sub = BotSubscription.objects.create(user=user, plan=plan)
        serializer = BotSubscriptionSerializer(sub)
        assert serializer.data["webhook_config"] is None

    def test_is_expired_field(self, user):
        plan = BotSubscriptionPlan.objects.create(
            bot_type="martingale",
            name="M Plan",
            price=149.99,
        )
        sub = BotSubscription.objects.create(user=user, plan=plan)
        serializer = BotSubscriptionSerializer(sub)
        assert serializer.data["is_expired"] is False
