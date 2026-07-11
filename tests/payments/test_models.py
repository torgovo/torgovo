import pytest
from decimal import Decimal
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.payments.models import (
    SubscriptionPlan, QuantumAIDeposit, BlockchainAddress,
    WithdrawalRequest, PaymentTransaction, ReferralPayout,
    BotSubscriptionPlan, BotSubscription
)


@pytest.mark.django_db
class TestSubscriptionPlanModel:
    def test_create_plan(self):
        plan = SubscriptionPlan.objects.create(
            name='Premium',
            slug='premium',
            price_monthly=Decimal('29.99'),
            price_yearly=Decimal('299.99'),
            max_bots_allowed=10,
            max_webhooks_allowed=50,
            features=['advanced_analytics', 'priority_support'],
            trial_days=7,
        )
        assert plan.name == 'Premium'
        assert plan.price_monthly == Decimal('29.99')
        assert plan.is_active is True
        assert str(plan) == 'Premium ($29.99/month)'

    def test_plan_slug_unique(self):
        SubscriptionPlan.objects.create(
            name='Basic', slug='basic',
            price_monthly=9.99, price_yearly=99.99, max_bots_allowed=1,
        )
        with pytest.raises(Exception):
            SubscriptionPlan.objects.create(
                name='Basic2', slug='basic',
                price_monthly=19.99, price_yearly=199.99, max_bots_allowed=5,
            )

    def test_feature_dict_default(self):
        plan = SubscriptionPlan.objects.create(
            name='Basic', slug='basic',
            price_monthly=9.99, price_yearly=99.99, max_bots_allowed=2,
        )
        fd = plan.feature_dict
        assert fd['max_bots'] == 2
        assert fd['include_quantum_ai'] is False

    def test_feature_dict_from_dict(self):
        plan = SubscriptionPlan.objects.create(
            name='Pro', slug='pro',
            price_monthly=49.99, price_yearly=499.99, max_bots_allowed=20,
            features={'max_bots': 20, 'include_quantum_ai': True},
        )
        fd = plan.feature_dict
        assert fd['max_bots'] == 20
        assert fd['include_quantum_ai'] is True


@pytest.mark.django_db
class TestQuantumAIDepositModel:
    def test_create_deposit(self, user):
        deposit = QuantumAIDeposit.objects.create(
            user=user,
            amount=Decimal('100.00000000'),
            currency='USDT',
            blockchain='BEP20',
            from_address='0xabc123',
            transaction_hash='0xtxhash1234567890abcdef',
        )
        assert deposit.user == user
        assert deposit.amount == Decimal('100.00000000')
        assert deposit.status == 'pending'
        assert deposit.required_confirmations == 6
        assert deposit.risk_score == 0
        assert deposit.flagged_for_review is False
        assert str(deposit) == f'100.00000000 USDT - {user.email} (pending)'

    def test_deposit_unique_transaction_hash(self, user):
        QuantumAIDeposit.objects.create(
            user=user, amount=Decimal('50'), currency='USDT',
            blockchain='ERC20', from_address='0xabc',
            transaction_hash='0xuniquehash1',
        )
        with pytest.raises(Exception):
            QuantumAIDeposit.objects.create(
                user=user, amount=Decimal('50'), currency='USDT',
                blockchain='ERC20', from_address='0xabc',
                transaction_hash='0xuniquehash1',
            )

    def test_is_expired_property(self, user):
        deposit = QuantumAIDeposit.objects.create(
            user=user, amount=Decimal('10'), currency='USDT',
            blockchain='BEP20', from_address='0xabc',
            transaction_hash='0xexp1',
        )
        assert deposit.is_expired is False

    def test_approve_deposit(self, user, admin_user):
        deposit = QuantumAIDeposit.objects.create(
            user=user, amount=Decimal('500'), currency='USDT',
            blockchain='BEP20', from_address='0xabc',
            transaction_hash='0xapprove1',
        )
        deposit.approve(admin_user, 'Approved via test')
        deposit.refresh_from_db()
        assert deposit.status == 'approved'
        assert deposit.verified_by == admin_user
        assert deposit.verified_at is not None

    def test_reject_deposit(self, user, admin_user):
        deposit = QuantumAIDeposit.objects.create(
            user=user, amount=Decimal('500'), currency='USDT',
            blockchain='BEP20', from_address='0xabc',
            transaction_hash='0xreject1',
        )
        deposit.reject(admin_user, 'Suspicious activity')
        deposit.refresh_from_db()
        assert deposit.status == 'rejected'
        assert deposit.verified_by == admin_user
        assert deposit.admin_notes == 'Suspicious activity'

    def test_soft_delete(self, user):
        deposit = QuantumAIDeposit.objects.create(
            user=user, amount=Decimal('100'), currency='USDT',
            blockchain='ERC20', from_address='0xabc',
            transaction_hash='0xsoftdel1',
        )
        deposit.delete()
        assert deposit.is_deleted is True


@pytest.mark.django_db
class TestBlockchainAddressModel:
    def test_create_address(self):
        addr = BlockchainAddress.objects.create(
            coin_type='USDT',
            blockchain='BEP20',
            address='0x1234567890abcdef1234567890abcdef12345678',
            label='Receiving Wallet',
        )
        assert addr.coin_type == 'USDT'
        assert addr.blockchain == 'BEP20'
        assert addr.is_active is True
        assert addr.is_hot_wallet is False
        assert addr.min_confirmations == 6
        assert str(addr) == 'USDT on BEP20: 0x12345678...'

    def test_address_unique(self):
        BlockchainAddress.objects.create(
            coin_type='USDT', blockchain='BEP20',
            address='0xunique1',
        )
        with pytest.raises(Exception):
            BlockchainAddress.objects.create(
                coin_type='USDT', blockchain='BEP20',
                address='0xunique1',
            )


@pytest.mark.django_db
class TestWithdrawalRequestModel:
    def test_create_withdrawal(self, user):
        withdrawal = WithdrawalRequest.objects.create(
            user=user,
            amount=Decimal('50.00000000'),
            currency='USDT',
            blockchain='BEP20',
            to_address='0xreceiveraddress1234567890',
            total_amount=Decimal('50.00000000'),
        )
        assert withdrawal.user == user
        assert withdrawal.amount == Decimal('50.00000000')
        assert withdrawal.status == 'pending'
        assert withdrawal.network_fee == 0
        assert withdrawal.risk_score == 0
        assert withdrawal.flagged_for_review is False
        assert str(withdrawal) == f'Withdrawal: 50.00000000 USDT - {user.email}'

    def test_withdrawal_defaults(self, user):
        withdrawal = WithdrawalRequest.objects.create(
            user=user, amount=Decimal('100'), currency='USDT',
            blockchain='ERC20', to_address='0xreceiver1234567890abc',
            total_amount=Decimal('100'),
        )
        assert withdrawal.status == 'pending'
        assert withdrawal.network_fee == 0
        assert withdrawal.processing_fee == 0

    def test_soft_delete(self, user):
        withdrawal = WithdrawalRequest.objects.create(
            user=user, amount=Decimal('10'), currency='USDT',
            blockchain='BEP20', to_address='0xreceiver',
            total_amount=Decimal('10'),
        )
        withdrawal.delete()
        assert withdrawal.is_deleted is True


@pytest.mark.django_db
class TestPaymentTransactionModel:
    def test_create_transaction(self, user):
        tx = PaymentTransaction.objects.create(
            user=user,
            transaction_type='deposit',
            amount=Decimal('1000.00000000'),
            currency='USDT',
            gateway='system',
            status='completed',
        )
        assert tx.user == user
        assert tx.transaction_type == 'deposit'
        assert tx.amount == Decimal('1000.00000000')
        assert tx.gateway == 'system'
        assert tx.metadata == {}
        assert str(tx) == f'deposit: 1000.00000000 USDT - {user.email}'

    def test_transaction_types(self, user):
        for tx_type in ['deposit', 'withdrawal', 'subscription', 'refund', 'fee']:
            tx = PaymentTransaction.objects.create(
                user=user, transaction_type=tx_type,
                amount=Decimal('100'), currency='USDT',
            )
            assert tx.transaction_type == tx_type


@pytest.mark.django_db
class TestReferralPayoutModel:
    def test_create_payout(self, user, admin_user):
        payout = ReferralPayout.objects.create(
            referrer=user,
            referred_user=admin_user,
            amount=Decimal('50.00000000'),
            percentage=Decimal('10.00'),
        )
        assert payout.referrer == user
        assert payout.referred_user == admin_user
        assert payout.status == 'pending'
        assert str(payout) == f'Referral: 50.00000000 - {user.email}'

    def test_soft_delete(self, user, admin_user):
        payout = ReferralPayout.objects.create(
            referrer=user, referred_user=admin_user,
            amount=Decimal('25'), percentage=Decimal('5.00'),
        )
        payout.delete()
        assert payout.is_deleted is True


@pytest.mark.django_db
class TestBotSubscriptionPlanModel:
    def test_create_plan(self):
        plan = BotSubscriptionPlan.objects.create(
            bot_type='custom',
            name='Custom Bot Plan',
            price=Decimal('99.99'),
            duration_days=30,
            description='Build your own bot',
            features=['webhook_alerts', 'custom_strategies'],
        )
        assert plan.bot_type == 'custom'
        assert plan.price == Decimal('99.99')
        assert plan.is_active is True
        assert plan.requires_approval is True
        assert str(plan) == 'Custom Bot Plan - $99.99'

    def test_bot_type_unique(self):
        BotSubscriptionPlan.objects.create(
            bot_type='grid', name='Grid Plan', price=49.99,
        )
        with pytest.raises(Exception):
            BotSubscriptionPlan.objects.create(
                bot_type='grid', name='Grid Plan 2', price=59.99,
            )

    def test_duration_choices(self):
        plan = BotSubscriptionPlan.objects.create(
            bot_type='martingale', name='Martingale Plan', price=149.99, duration_days=90,
        )
        assert plan.duration_days == 90


@pytest.mark.django_db
class TestBotSubscriptionModel:
    def test_create_subscription(self, user):
        plan = BotSubscriptionPlan.objects.create(
            bot_type='custom', name='Custom Plan', price=99.99,
        )
        sub = BotSubscription.objects.create(
            user=user,
            plan=plan,
            exchange_name='binance',
        )
        assert sub.user == user
        assert sub.plan == plan
        assert sub.status == 'pending_payment'
        assert sub.exchange_name == 'binance'
        assert str(sub) == f'{user.email} - Custom Plan (pending_payment)'

    def test_subscription_unique_per_user_plan(self, user):
        plan = BotSubscriptionPlan.objects.create(
            bot_type='grid', name='Grid Plan', price=49.99,
        )
        BotSubscription.objects.create(user=user, plan=plan)
        with pytest.raises(Exception):
            BotSubscription.objects.create(user=user, plan=plan)

    def test_is_expired_property(self, user):
        plan = BotSubscriptionPlan.objects.create(
            bot_type='quantum_ai', name='Quantum Plan', price=199.99,
        )
        sub = BotSubscription.objects.create(user=user, plan=plan)
        assert sub.is_expired is False

    def test_soft_delete(self, user):
        plan = BotSubscriptionPlan.objects.create(
            bot_type='custom', name='Custom', price=99.99,
        )
        sub = BotSubscription.objects.create(user=user, plan=plan)
        sub.delete()
        assert sub.is_deleted is True
