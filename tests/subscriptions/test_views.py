import pytest
from decimal import Decimal
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from apps.subscriptions.models import (
    TelegramSignalPlan, TelegramChannel, TelegramSubscription,
    TradingSignal, SignalResult, SignalStatistics,
)


@pytest.mark.django_db
class TestTelegramSignalPlanViewSet:
    @pytest.fixture(autouse=True)
    def setup(self, db):
        self.plan = TelegramSignalPlan.objects.create(
            name='Premium', slug='premium', description='Premium signals',
            price_monthly=49.99, price_quarterly=129.99, price_yearly=499.99,
        )
        TelegramSignalPlan.objects.create(
            name='Inactive', slug='inactive', description='Inactive',
            price_monthly=0, price_quarterly=0, price_yearly=0,
            is_active=False,
        )

    def test_list_active_plans(self, auth_client):
        url = reverse('subscriptions:plans-list')
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 1

    def test_retrieve_plan(self, auth_client):
        url = reverse('subscriptions:plans-detail', args=[self.plan.id])
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['name'] == 'Premium'

    def test_unauthenticated(self, api_client):
        url = reverse('subscriptions:plans-list')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestTelegramSubscriptionViewSet:
    @pytest.fixture(autouse=True)
    def setup(self, db, user):
        self.plan = TelegramSignalPlan.objects.create(
            name='Pro', slug='pro', description='Pro signals',
            price_monthly=49.99, price_quarterly=129.99, price_yearly=499.99,
        )
        self.sub = TelegramSubscription.objects.create(
            user=user, plan=self.plan, telegram_handle='tg_user',
            amount_paid=Decimal('49.99'),
        )

    def test_list_subscriptions(self, auth_client):
        url = reverse('subscriptions:subscriptions-list')
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 1

    def test_retrieve_subscription(self, auth_client):
        url = reverse('subscriptions:subscriptions-detail', args=[self.sub.id])
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK

    def test_other_user_subscriptions_not_visible(self, auth_client, user, admin_user):
        TelegramSubscription.objects.create(
            user=admin_user, plan=self.plan, telegram_handle='tg_admin',
            amount_paid=Decimal('49.99'),
        )
        url = reverse('subscriptions:subscriptions-list')
        response = auth_client.get(url)
        assert len(response.data['results']) == 1

    def test_unauthenticated(self, api_client):
        url = reverse('subscriptions:subscriptions-list')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestTelegramChannelViewSet:
    @pytest.fixture(autouse=True)
    def setup(self, db):
        TelegramChannel.objects.create(
            name='Signals', channel_id='signals_ch', channel_type='signals',
            invite_link='https://t.me/signals_ch', description='Signals', is_active=True,
        )
        TelegramChannel.objects.create(
            name='Hidden', channel_id='hidden_ch', channel_type='analysis',
            invite_link='https://t.me/hidden_ch', description='Hidden', is_active=False,
        )

    def test_list_active_channels(self, auth_client):
        url = reverse('subscriptions:channels-list')
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 1

    def test_unauthenticated(self, api_client):
        url = reverse('subscriptions:channels-list')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestTradingSignalViewSet:
    @pytest.fixture(autouse=True)
    def setup(self, db):
        plan = TelegramSignalPlan.objects.create(
            name='Pro', slug='pro', description='Pro',
            price_monthly=49.99, price_quarterly=129.99, price_yearly=499.99,
        )
        TradingSignal.objects.create(
            plan=plan, signal_type='buy', trading_pair='BTC/USDT',
            exchange='binance', timeframe='1h', entry_price=Decimal('50000'),
            analysis='Test', published_at=timezone.now(),
            expires_at=timezone.now() + timezone.timedelta(hours=24),
        )

    def test_list_active_signals(self, auth_client):
        url = reverse('subscriptions:signals-list')
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 1

    def test_unauthenticated(self, api_client):
        url = reverse('subscriptions:signals-list')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestSignalResultViewSet:
    @pytest.fixture(autouse=True)
    def setup(self, db):
        plan = TelegramSignalPlan.objects.create(
            name='Pro', slug='pro', description='Pro',
            price_monthly=49.99, price_quarterly=129.99, price_yearly=499.99,
        )
        signal = TradingSignal.objects.create(
            plan=plan, signal_type='buy', trading_pair='BTC/USDT',
            exchange='binance', timeframe='1h', entry_price=Decimal('50000'),
            analysis='Test', published_at=timezone.now(),
            expires_at=timezone.now() + timezone.timedelta(hours=24),
        )
        SignalResult.objects.create(
            signal=signal, result_type='profit',
            entry_price_actual=Decimal('50000'), profit_loss=Decimal('1000'),
            profit_loss_percent=Decimal('2.00'), entry_time=timezone.now(),
        )

    def test_list_results(self, auth_client):
        url = reverse('subscriptions:signal-results-list')
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 1

    def test_unauthenticated(self, api_client):
        url = reverse('subscriptions:signal-results-list')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestPublicPlanListView:
    @pytest.fixture(autouse=True)
    def setup(self, db):
        TelegramSignalPlan.objects.create(
            name='Public Plan', slug='public', description='Public',
            price_monthly=19.99, price_quarterly=49.99, price_yearly=199.99,
        )

    def test_public_list(self, api_client):
        url = reverse('subscriptions:public_plans')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 1


@pytest.mark.django_db
class TestMySubscriptionView:
    @pytest.fixture(autouse=True)
    def setup(self, db, user):
        self.plan = TelegramSignalPlan.objects.create(
            name='Active Plan', slug='active-plan', description='Active',
            price_monthly=29.99, price_quarterly=79.99, price_yearly=299.99,
        )

    def test_no_active_subscription(self, auth_client):
        url = reverse('subscriptions:my_subscription')
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_with_active_subscription(self, auth_client, user):
        TelegramSubscription.objects.create(
            user=user, plan=self.plan, telegram_handle='tg_active',
            amount_paid=Decimal('29.99'), status='active',
            end_date=timezone.now().date() + timezone.timedelta(days=30),
        )
        url = reverse('subscriptions:my_subscription')
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == 'active'

    def test_unauthenticated(self, api_client):
        url = reverse('subscriptions:my_subscription')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestAdminChannelViews:
    @pytest.fixture(autouse=True)
    def setup(self, db):
        TelegramChannel.objects.create(
            name='Channel 1', channel_id='ch1', channel_type='signals',
            invite_link='https://t.me/ch1', description='Ch1',
        )

    def test_admin_list_channels(self, admin_client):
        url = reverse('subscriptions:admin_channel_list')
        response = admin_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 1

    def test_admin_create_channel(self, admin_client):
        url = reverse('subscriptions:admin_create_channel')
        data = {
            'name': 'New Channel', 'channel_id': 'new_ch',
            'channel_type': 'analysis', 'invite_link': 'https://t.me/new_ch',
            'description': 'New analysis channel',
        }
        response = admin_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_201_CREATED

    def test_non_admin_cannot_list_channels(self, auth_client):
        url = reverse('subscriptions:admin_channel_list')
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_non_admin_cannot_create_channel(self, auth_client):
        url = reverse('subscriptions:admin_create_channel')
        data = {
            'name': 'Test', 'channel_id': 'test_ch',
            'channel_type': 'signals', 'invite_link': 'https://t.me/test',
            'description': 'Test',
        }
        response = auth_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestTelegramPlanListView:
    @pytest.fixture(autouse=True)
    def setup(self, db):
        TelegramSignalPlan.objects.create(
            name='Telegram Pro', slug='tg-pro', description='TG Pro',
            price_monthly=49.99, price_quarterly=129.99, price_yearly=499.99,
        )

    def test_public_telegram_plans(self, api_client):
        url = reverse('subscriptions:telegram-plan-list')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert 'plans' in response.data

    def test_cached_response(self, api_client):
        url = reverse('subscriptions:telegram-plan-list')
        response1 = api_client.get(url)
        response2 = api_client.get(url)
        assert response1.status_code == status.HTTP_200_OK
        assert response2.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestMyTelegramUsageView:
    def test_no_active_subscription(self, auth_client):
        url = reverse('subscriptions:telegram-my-usage')
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['is_active'] is False

    def test_with_active_subscription(self, auth_client, user):
        plan = TelegramSignalPlan.objects.create(
            name='Usage Plan', slug='usage-plan', description='Usage',
            price_monthly=29.99, price_quarterly=79.99, price_yearly=299.99,
            signals_per_day=15, exchanges_covered=['binance'],
        )
        TelegramSubscription.objects.create(
            user=user, plan=plan, telegram_handle='tg_usage',
            amount_paid=Decimal('29.99'), status='active',
            end_date=timezone.now().date() + timezone.timedelta(days=30),
        )
        url = reverse('subscriptions:telegram-my-usage')
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['is_active'] is True
        assert response.data['plan'] == 'Usage Plan'

    def test_unauthenticated(self, api_client):
        url = reverse('subscriptions:telegram-my-usage')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestTelegramSubscribeView:
    @pytest.fixture(autouse=True)
    def setup(self, db):
        self.plan = TelegramSignalPlan.objects.create(
            name='Subscribe Plan', slug='sub-plan', description='Subscribe',
            price_monthly=49.99, price_quarterly=129.99, price_yearly=499.99,
        )

    def test_subscribe_success(self, auth_client):
        url = reverse('subscriptions:telegram-subscribe')
        data = {
            'plan_id': str(self.plan.id),
            'telegram_handle': 'new_user_tg',
            'payment_transaction_hash': '0xtx_subscribe_success',
            'payment_blockchain': 'BEP20',
        }
        response = auth_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['status'] == 'pending_approval'

    def test_subscribe_missing_fields(self, auth_client):
        url = reverse('subscriptions:telegram-subscribe')
        response = auth_client.post(url, {}, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_subscribe_missing_handle(self, auth_client):
        url = reverse('subscriptions:telegram-subscribe')
        data = {'plan_id': str(self.plan.id)}
        response = auth_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_subscribe_invalid_plan(self, auth_client):
        url = reverse('subscriptions:telegram-subscribe')
        data = {
            'plan_id': '00000000-0000-0000-0000-000000000000',
            'telegram_handle': 'tg_user',
            'payment_transaction_hash': '0xhash',
        }
        response = auth_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_subscribe_unauthenticated(self, api_client):
        url = reverse('subscriptions:telegram-subscribe')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_subscribe_not_implemented(self, auth_client):
        url = reverse('subscriptions:create_subscription')
        response = auth_client.post(url, {}, format='json')
        assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED


@pytest.mark.django_db
class TestExtendCancelSubscriptionViews:
    def test_extend_not_implemented(self, auth_client):
        url = reverse('subscriptions:extend_subscription')
        response = auth_client.post(url, {}, format='json')
        assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED

    def test_cancel_not_implemented(self, auth_client):
        url = reverse('subscriptions:cancel_subscription')
        response = auth_client.post(url, {}, format='json')
        assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED

    def test_statistics_not_implemented(self, api_client):
        url = reverse('subscriptions:signal_statistics')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED
