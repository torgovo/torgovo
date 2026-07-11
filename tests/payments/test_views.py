import pytest
from decimal import Decimal
from django.urls import reverse
from rest_framework import status
from apps.payments.models import (
    SubscriptionPlan, QuantumAIDeposit, BlockchainAddress,
    WithdrawalRequest, PaymentTransaction, BotSubscriptionPlan, BotSubscription,
)


@pytest.mark.django_db
class TestSubscriptionPlanViewSet:
    @pytest.fixture(autouse=True)
    def setup(self, db):
        self.plan = SubscriptionPlan.objects.create(
            name='Premium', slug='premium',
            price_monthly=Decimal('29.99'), price_yearly=Decimal('299.99'),
            max_bots_allowed=10,
        )
        SubscriptionPlan.objects.create(
            name='Inactive Plan', slug='inactive',
            price_monthly=1.00, price_yearly=10.00, max_bots_allowed=1,
            is_active=False,
        )

    def test_list_active_plans(self, auth_client):
        url = reverse('payments:subscriptionplan-list')
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1

    def test_retrieve_plan(self, auth_client):
        url = reverse('payments:subscriptionplan-detail', args=[self.plan.id])
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['name'] == 'Premium'

    def test_unauthenticated(self, api_client):
        url = reverse('payments:subscriptionplan-list')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestBotSubscriptionViews:
    @pytest.fixture(autouse=True)
    def setup(self, db):
        self.plan = BotSubscriptionPlan.objects.create(
            bot_type='custom', name='Custom Bot', price=99.99,
        )

    def test_list_bot_subscriptions(self, auth_client, user):
        BotSubscription.objects.create(user=user, plan=self.plan)
        url = reverse('payments:bot-subscription-list')
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1

    def test_create_bot_subscription(self, auth_client):
        url = reverse('payments:bot-subscription-create')
        data = {
            'plan_id': str(self.plan.id),
            'payment_transaction_hash': '0xtxhash1234567890',
            'payment_blockchain': 'BEP20',
        }
        response = auth_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['success'] is True
        assert response.data['status'] == 'pending_approval'

    def test_create_bot_subscription_requires_plan(self, auth_client):
        url = reverse('payments:bot-subscription-create')
        response = auth_client.post(url, {}, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'plan_id' in str(response.data['error'])

    def test_create_bot_subscription_requires_payment(self, auth_client):
        url = reverse('payments:bot-subscription-create')
        data = {'plan_id': str(self.plan.id)}
        response = auth_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_bot_subscription_invalid_plan(self, auth_client):
        url = reverse('payments:bot-subscription-create')
        data = {
            'plan_id': '00000000-0000-0000-0000-000000000000',
            'payment_transaction_hash': '0xhash',
        }
        response = auth_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_admin_approve_subscription(self, admin_client, user):
        sub = BotSubscription.objects.create(user=user, plan=self.plan, status='pending_approval')
        url = reverse('payments:admin-approve-subscription', args=[sub.id])
        response = admin_client.post(url, {}, format='json')
        assert response.status_code == status.HTTP_200_OK
        assert response.data['success'] is True

    def test_non_admin_cannot_approve(self, auth_client, user):
        sub = BotSubscription.objects.create(user=user, plan=self.plan, status='pending_approval')
        url = reverse('payments:admin-approve-subscription', args=[sub.id])
        response = auth_client.post(url, {}, format='json')
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_reject_subscription_requires_reason(self, admin_client, user):
        sub = BotSubscription.objects.create(user=user, plan=self.plan, status='pending_approval')
        url = reverse('payments:admin-reject-subscription', args=[sub.id])
        response = admin_client.post(url, {}, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_admin_reject_subscription(self, admin_client, user):
        sub = BotSubscription.objects.create(user=user, plan=self.plan, status='pending_approval')
        url = reverse('payments:admin-reject-subscription', args=[sub.id])
        response = admin_client.post(url, {'reason': 'Insufficient funds'}, format='json')
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestQuantumDepositViewSet:
    def test_list_deposits_empty(self, auth_client):
        url = reverse('payments:quantumdeposit-list')
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data == []

    def test_create_deposit(self, auth_client, user):
        url = reverse('payments:quantumdeposit-list')
        data = {
            'amount': '100.00000000',
            'currency': 'USDT',
            'blockchain': 'BEP20',
            'from_address': '0xsender1234567890abc',
            'transaction_hash': '0xtxhash_test_create_deposit',
        }
        response = auth_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['status'] == 'pending'

    def test_retrieve_deposit(self, auth_client, user):
        deposit = QuantumAIDeposit.objects.create(
            user=user, amount=Decimal('500'), currency='USDT',
            blockchain='ERC20', from_address='0xabc',
            transaction_hash='0xtxhash_retrieve',
        )
        url = reverse('payments:quantumdeposit-detail', args=[deposit.id])
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK

    def test_list_own_deposits_only(self, auth_client, user, admin_user):
        QuantumAIDeposit.objects.create(
            user=admin_user, amount=Decimal('999'), currency='USDT',
            blockchain='BEP20', from_address='0xadmin',
            transaction_hash='0xtxhash_admin_deposit',
        )
        url = reverse('payments:quantumdeposit-list')
        response = auth_client.get(url)
        assert len(response.data) == 0

    def test_pending_endpoint_admin(self, admin_client):
        url = reverse('payments:quantumdeposit-pending')
        response = admin_client.get(url)
        assert response.status_code == status.HTTP_200_OK

    def test_pending_endpoint_non_admin(self, auth_client):
        url = reverse('payments:quantumdeposit-pending')
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_unauthenticated(self, api_client):
        url = reverse('payments:quantumdeposit-list')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestDepositAdminViews:
    def test_approve_deposit(self, admin_client, user):
        deposit = QuantumAIDeposit.objects.create(
            user=user, amount=Decimal('100'), currency='USDT',
            blockchain='BEP20', from_address='0xabc',
            transaction_hash='0xtxhash_adm_approve',
        )
        url = reverse('payments:approve_deposit', args=[deposit.id])
        response = admin_client.post(url, {'notes': 'Approved'}, format='json')
        assert response.status_code == status.HTTP_200_OK

    def test_approve_already_approved(self, admin_client, user):
        deposit = QuantumAIDeposit.objects.create(
            user=user, amount=Decimal('100'), currency='USDT',
            blockchain='BEP20', from_address='0xabc',
            transaction_hash='0xtxhash_alr_appr', status='approved',
        )
        url = reverse('payments:approve_deposit', args=[deposit.id])
        response = admin_client.post(url, {}, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_reject_deposit(self, admin_client, user):
        deposit = QuantumAIDeposit.objects.create(
            user=user, amount=Decimal('100'), currency='USDT',
            blockchain='BEP20', from_address='0xabc',
            transaction_hash='0xtxhash_adm_reject',
        )
        url = reverse('payments:reject_deposit', args=[deposit.id])
        response = admin_client.post(url, {'reason': 'Fraud suspicion'}, format='json')
        assert response.status_code == status.HTTP_200_OK

    def test_reject_without_reason(self, admin_client, user):
        deposit = QuantumAIDeposit.objects.create(
            user=user, amount=Decimal('100'), currency='USDT',
            blockchain='BEP20', from_address='0xabc',
            transaction_hash='0xtxhash_no_reason',
        )
        url = reverse('payments:reject_deposit', args=[deposit.id])
        response = admin_client.post(url, {}, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_non_admin_cannot_approve(self, auth_client, user):
        deposit = QuantumAIDeposit.objects.create(
            user=user, amount=Decimal('100'), currency='USDT',
            blockchain='BEP20', from_address='0xabc',
            transaction_hash='0xtxhash_nonadmin',
        )
        url = reverse('payments:approve_deposit', args=[deposit.id])
        response = auth_client.post(url, {}, format='json')
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestWithdrawalRequestViewSet:
    def test_list_withdrawals_empty(self, auth_client):
        url = reverse('payments:withdrawal-list')
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data == []

    def test_create_withdrawal(self, auth_client, user):
        url = reverse('payments:withdrawal-list')
        data = {
            'amount': '50.00000000',
            'currency': 'USDT',
            'blockchain': 'BEP20',
            'to_address': '0xreceiver1234567890abcdef12345678',
            'total_amount': '50.00000000',
        }
        response = auth_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['status'] == 'pending'

    def test_list_own_withdrawals_only(self, auth_client, user, admin_user):
        WithdrawalRequest.objects.create(
            user=admin_user, amount=Decimal('999'), currency='USDT',
            blockchain='ERC20', to_address='0xadmin',
            total_amount=Decimal('999'),
        )
        url = reverse('payments:withdrawal-list')
        response = auth_client.get(url)
        assert len(response.data) == 0

    def test_cancel_withdrawal(self, auth_client, user):
        withdrawal = WithdrawalRequest.objects.create(
            user=user, amount=Decimal('100'), currency='USDT',
            blockchain='BEP20', to_address='0xreceiver',
            total_amount=Decimal('100'),
        )
        url = reverse('payments:withdrawal-cancel', args=[withdrawal.id])
        response = auth_client.post(url, {}, format='json')
        assert response.status_code == status.HTTP_200_OK
        assert response.data['success'] is True

    def test_cancel_already_completed(self, auth_client, user):
        withdrawal = WithdrawalRequest.objects.create(
            user=user, amount=Decimal('100'), currency='USDT',
            blockchain='BEP20', to_address='0xreceiver',
            total_amount=Decimal('100'), status='completed',
        )
        url = reverse('payments:withdrawal-cancel', args=[withdrawal.id])
        response = auth_client.post(url, {}, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_unauthenticated(self, api_client):
        url = reverse('payments:withdrawal-list')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestPaymentTransactionViewSet:
    @pytest.fixture(autouse=True)
    def setup(self, db, user):
        PaymentTransaction.objects.create(
            user=user, transaction_type='deposit',
            amount=Decimal('1000'), currency='USDT', status='completed',
        )
        PaymentTransaction.objects.create(
            user=user, transaction_type='withdrawal',
            amount=Decimal('500'), currency='USDT', status='completed',
        )

    def test_list_transactions(self, auth_client):
        url = reverse('payments:paymenttransaction-list')
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 2

    def test_recent_transactions(self, auth_client):
        url = reverse('payments:paymenttransaction-recent')
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK

    def test_by_type(self, auth_client):
        url = reverse('payments:paymenttransaction-by-type')
        response = auth_client.get(f'{url}?type=deposit')
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1

    def test_by_type_missing_param(self, auth_client):
        url = reverse('payments:paymenttransaction-by-type')
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_unauthenticated(self, api_client):
        url = reverse('payments:paymenttransaction-list')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestBlockchainAddressListView:
    @pytest.fixture(autouse=True)
    def setup(self, db):
        BlockchainAddress.objects.create(
            coin_type='USDT', blockchain='BEP20',
            address='0xactive1', is_active=True,
        )
        BlockchainAddress.objects.create(
            coin_type='BTC', blockchain='Bitcoin',
            address='1inactive', is_active=False,
        )

    def test_list_active_addresses(self, auth_client):
        url = reverse('payments:blockchain_address_list')
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]['coin_type'] == 'USDT'

    def test_unauthenticated(self, api_client):
        url = reverse('payments:blockchain_address_list')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
