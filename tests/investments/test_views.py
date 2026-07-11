import pytest
from decimal import Decimal
from django.urls import reverse
from rest_framework import status
from apps.investments.models import (
    Exchange, TradingPair, ExchangeCredential, BotBase,
    WebhookAlertBot, GridBot, MartingaleBot, QuantumAIBot,
    Order, Position, TechnicalIndicator, UserBalance,
)


@pytest.mark.django_db
class TestExchangeViewSet:
    @pytest.fixture(autouse=True)
    def setup(self, db):
        self.active = Exchange.objects.create(name='binance', display_name='Binance', status='active')
        Exchange.objects.create(name='offline', display_name='Offline', status='inactive')

    def test_list_exchanges(self, api_client):
        url = reverse('investments:exchange-list')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 1

    def test_supported_action(self, api_client):
        url = reverse('investments:exchange-supported')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert 'exchanges' in response.data

    def test_retrieve_exchange(self, api_client):
        url = reverse('investments:exchange-detail', args=[self.active.id])
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['name'] == 'binance'


@pytest.mark.django_db
class TestExchangeCredentialViewSet:
    @pytest.fixture(autouse=True)
    def setup(self, db, user):
        self.exchange = Exchange.objects.create(name='binance', display_name='Binance')
        ExchangeCredential.objects.create(
            user=user, exchange=self.exchange, api_key='key', secret_key='secret',
        )

    def test_list_credentials(self, auth_client):
        url = reverse('investments:credential-list')
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 1

    def test_create_credential(self, auth_client):
        exchange = Exchange.objects.create(name='bybit', display_name='Bybit')
        url = reverse('investments:credential-list')
        data = {
            'exchange_id': exchange.id,
            'api_key': 'my-api-key-12345',
            'secret_key': 'my-secret-key-67890',
        }
        response = auth_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_201_CREATED

    def test_test_connection_action(self, auth_client):
        cred = ExchangeCredential.objects.filter(api_key='key').first()
        url = reverse('investments:credential-test-connection', args=[cred.id])
        response = auth_client.post(url, {}, format='json')
        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == 'connected'

    def test_unauthenticated(self, api_client):
        url = reverse('investments:credential-list')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestTradingPairViewSet:
    @pytest.fixture(autouse=True)
    def setup(self, db):
        self.exchange = Exchange.objects.create(name='binance', display_name='Binance')
        TradingPair.objects.create(
            exchange=self.exchange, symbol='BTC/USDT', base_asset='BTC', quote_asset='USDT', is_active=True,
        )
        TradingPair.objects.create(
            exchange=self.exchange, symbol='ETH/USDT', base_asset='ETH', quote_asset='USDT', is_active=False,
        )

    def test_list_active_pairs(self, api_client):
        url = reverse('investments:trading-pair-list')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 1

    def test_top_gainers(self, api_client):
        url = reverse('investments:trading-pair-top-gainers')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK

    def test_top_losers(self, api_client):
        url = reverse('investments:trading-pair-top-losers')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK

    def test_most_active(self, api_client):
        url = reverse('investments:trading-pair-most-active')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestWebhookAlertBotViewSet:
    @pytest.fixture(autouse=True)
    def setup(self, db, user):
        self.exchange = Exchange.objects.create(name='binance', display_name='Binance')
        self.pair = TradingPair.objects.create(
            exchange=self.exchange, symbol='BTC/USDT', base_asset='BTC', quote_asset='USDT',
        )

    def test_create_webhook_bot(self, auth_client):
        url = reverse('investments:webhook-bot-list')
        data = {
            'bot_name': 'My Webhook Bot',
            'exchange_id': self.exchange.id,
            'trading_pair_id': self.pair.id,
            'default_amount': '50.00000000',
        }
        response = auth_client.post(url, data, format='json')
        if response.status_code != 201:
            print(f'\nCREATE ERROR: {response.data}')
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['bot_name'] == 'My Webhook Bot'
        assert response.data['category'] == 'webhook'

    def test_list_webhook_bots(self, auth_client, user):
        WebhookAlertBot.objects.create(
            user=user, bot_name='Bot1', category='webhook',
            exchange=self.exchange, trading_pair=self.pair,
        )
        url = reverse('investments:webhook-bot-list')
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 1

    def test_regenerate_secret(self, auth_client, user):
        bot = WebhookAlertBot.objects.create(
            user=user, bot_name='Bot', category='webhook',
            exchange=self.exchange, trading_pair=self.pair,
            secret_key='old-secret',
        )
        url = reverse('investments:webhook-bot-regenerate-secret', args=[bot.id])
        response = auth_client.post(url, {}, format='json')
        assert response.status_code == status.HTTP_200_OK
        assert response.data['secret_key'] != 'old-secret'


@pytest.mark.django_db
class TestGridBotViewSet:
    @pytest.fixture(autouse=True)
    def setup(self, db, user):
        self.exchange = Exchange.objects.create(name='binance', display_name='Binance')
        self.pair = TradingPair.objects.create(
            exchange=self.exchange, symbol='BTC/USDT', base_asset='BTC', quote_asset='USDT',
        )

    def test_create_grid_bot(self, auth_client):
        url = reverse('investments:grid-bot-list')
        data = {
            'bot_name': 'Grid Bot 1',
            'exchange_id': self.exchange.id,
            'trading_pair_id': self.pair.id,
            'base_amount': '100.00000000',
            'favor_levels': 5,
            'against_levels': 5,
        }
        response = auth_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['category'] == 'grid'

    def test_list_grid_bots(self, auth_client, user):
        GridBot.objects.create(
            user=user, bot_name='Grid1', category='grid',
            exchange=self.exchange, trading_pair=self.pair,
        )
        url = reverse('investments:grid-bot-list')
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestMartingaleBotViewSet:
    @pytest.fixture(autouse=True)
    def setup(self, db, user):
        self.exchange = Exchange.objects.create(name='binance', display_name='Binance')
        self.pair = TradingPair.objects.create(
            exchange=self.exchange, symbol='BTC/USDT', base_asset='BTC', quote_asset='USDT',
        )

    def test_create_martingale_bot(self, auth_client):
        url = reverse('investments:martingale-bot-list')
        data = {
            'bot_name': 'Martingale Bot 1',
            'exchange_id': self.exchange.id,
            'trading_pair_id': self.pair.id,
            'base_amount': '50.00000000',
            'favor_levels': 3,
            'against_levels': 3,
            'multiplier_factor': '2.0',
        }
        response = auth_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['category'] == 'martingale'


@pytest.mark.django_db
class TestQuantumAIBotViewSet:
    @pytest.fixture(autouse=True)
    def setup(self, db, user):
        self.exchange = Exchange.objects.create(name='binance', display_name='Binance')
        self.pair = TradingPair.objects.create(
            exchange=self.exchange, symbol='BTC/USDT', base_asset='BTC', quote_asset='USDT',
        )

    def test_create_quantum_bot(self, auth_client):
        url = reverse('investments:quantum-ai-bot-list')
        data = {
            'bot_name': 'Quantum Bot',
            'exchange_id': self.exchange.id,
            'trading_pair_id': self.pair.id,
            'risk_level': 'medium',
            'auto_compound': True,
        }
        response = auth_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_201_CREATED

    def test_generate_addresses(self, auth_client, user):
        bot = QuantumAIBot.objects.create(
            user=user, bot_name='QB', category='quantum_ai',
            exchange=self.exchange, trading_pair=self.pair,
        )
        url = reverse('investments:quantum-ai-bot-generate-addresses', args=[bot.id])
        response = auth_client.post(url, {}, format='json')
        assert response.status_code == status.HTTP_200_OK
        assert 'addresses' in response.data


@pytest.mark.django_db
class TestOrderViewSet:
    @pytest.fixture(autouse=True)
    def setup(self, db, user):
        self.exchange = Exchange.objects.create(name='binance', display_name='Binance')
        self.pair = TradingPair.objects.create(
            exchange=self.exchange, symbol='BTC/USDT', base_asset='BTC', quote_asset='USDT',
        )

    def test_create_order(self, auth_client):
        url = reverse('investments:order-list')
        data = {
            'exchange_id': self.exchange.id,
            'trading_pair_id': self.pair.id,
            'order_type': 'market',
            'Side': 'buy',
            'quantity': '0.00100000',
            'Price': '50000.00000000',
        }
        response = auth_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_201_CREATED

    def test_cancel_order(self, auth_client, user):
        order = Order.objects.create(
            user=user, exchange=self.exchange, trading_pair=self.pair,
            order_type='limit', side='buy',
            quantity=Decimal('0.1'), price=Decimal('40000'),
        )
        url = reverse('investments:order-cancel', args=[order.id])
        response = auth_client.post(url, {}, format='json')
        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == 'cancelled'

    def test_cancel_filled_order_fails(self, auth_client, user):
        order = Order.objects.create(
            user=user, exchange=self.exchange, trading_pair=self.pair,
            order_type='market', side='buy',
            quantity=Decimal('0.1'), price=Decimal('50000'),
            status='filled',
        )
        url = reverse('investments:order-cancel', args=[order.id])
        response = auth_client.post(url, {}, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestPositionViewSet:
    @pytest.fixture(autouse=True)
    def setup(self, db, user):
        self.exchange = Exchange.objects.create(name='binance', display_name='Binance')
        self.pair = TradingPair.objects.create(
            exchange=self.exchange, symbol='BTC/USDT', base_asset='BTC', quote_asset='USDT',
        )

    def test_create_position(self, auth_client):
        url = reverse('investments:position-list')
        data = {
            'exchange_id': self.exchange.id,
            'trading_pair_id': self.pair.id,
            'side': 'long',
            'entry_price': '50000.00000000',
            'quantity': '0.10000000',
        }
        response = auth_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_201_CREATED

    def test_close_position(self, auth_client, user):
        position = Position.objects.create(
            user=user, exchange=self.exchange, trading_pair=self.pair,
            side='long', entry_price=Decimal('50000'), quantity=Decimal('0.1'),
        )
        url = reverse('investments:position-close', args=[position.id])
        response = auth_client.post(url, {}, format='json')
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestTechnicalIndicatorViewSet:
    @pytest.fixture(autouse=True)
    def setup(self, db):
        self.exchange = Exchange.objects.create(name='binance', display_name='Binance')
        self.pair = TradingPair.objects.create(
            exchange=self.exchange, symbol='BTC/USDT', base_asset='BTC', quote_asset='USDT',
        )
        TechnicalIndicator.objects.create(
            indicator_type='EMA', trading_pair=self.pair, exchange=self.exchange,
            values={'EMA200': 45000}, triggered_at=None,
        )

    def test_list_indicators(self, api_client):
        url = reverse('investments:indicator-list')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 1


@pytest.mark.django_db
class TestUserBalanceViewSet:
    @pytest.fixture(autouse=True)
    def setup(self, db, user):
        self.exchange = Exchange.objects.create(name='binance', display_name='Binance')
        UserBalance.objects.create(
            user=user, exchange=self.exchange, currency='USDT',
            available=Decimal('1000'), total=Decimal('1000'),
        )

    def test_list_balances(self, auth_client):
        url = reverse('investments:balance-list')
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 1

    def test_summary(self, auth_client):
        url = reverse('investments:balance-summary')
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert 'total_usdt_value' in response.data

    def test_unauthenticated(self, api_client):
        url = reverse('investments:balance-list')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestExchangeListView:
    @pytest.fixture(autouse=True)
    def setup(self, db):
        Exchange.objects.create(name='binance', display_name='Binance', status='active')

    def test_list_exchanges(self, api_client):
        url = reverse('investments:exchange-list-view')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestExchangeSymbolsView:
    @pytest.fixture(autouse=True)
    def setup(self, db):
        self.exchange = Exchange.objects.create(name='binance', display_name='Binance')
        TradingPair.objects.create(
            exchange=self.exchange, symbol='BTC/USDT', base_asset='BTC', quote_asset='USDT', is_active=True,
        )

    def test_get_symbols(self, auth_client):
        url = reverse('investments:exchange-symbols', args=['binance'])
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert 'symbols' in response.data
        assert 'BTC/USDT' in response.data['symbols']

    def test_exchange_not_found(self, auth_client):
        url = reverse('investments:exchange-symbols', args=['nonexistent'])
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestUserOrdersView:
    def test_my_orders(self, auth_client, user):
        exchange = Exchange.objects.create(name='binance', display_name='Binance')
        pair = TradingPair.objects.create(
            exchange=exchange, symbol='BTC/USDT', base_asset='BTC', quote_asset='USDT',
        )
        Order.objects.create(
            user=user, exchange=exchange, trading_pair=pair,
            order_type='market', side='buy',
            quantity=Decimal('0.01'), price=Decimal('50000'),
        )
        url = reverse('investments:user-orders')
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestUserProfileView:
    def test_user_profile(self, auth_client):
        url = reverse('investments:user-profile')
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert 'user_email' in response.data
        assert 'total_trades_executed' in response.data


@pytest.mark.django_db
class TestBlockchainAddressesView:
    def test_blockchain_addresses(self, auth_client):
        url = reverse('investments:blockchain-addresses')
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert 'USDT' in response.data
        assert 'BTC' in response.data


@pytest.mark.django_db
class TestBotActionViews:
    @pytest.fixture(autouse=True)
    def setup(self, db, user):
        self.exchange = Exchange.objects.create(name='binance', display_name='Binance')
        self.pair = TradingPair.objects.create(
            exchange=self.exchange, symbol='BTC/USDT', base_asset='BTC', quote_asset='USDT',
        )
        self.bot = BotBase.objects.create(
            user=user, bot_name='Test Bot', category='webhook',
            exchange=self.exchange, trading_pair=self.pair,
        )

    def test_start_bot(self, auth_client):
        url = reverse('investments:bot-start', args=[self.bot.id])
        response = auth_client.post(url, {}, format='json')
        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == 'running'

    def test_start_already_running_fails(self, auth_client):
        self.bot.status = 'running'
        self.bot.save()
        url = reverse('investments:bot-start', args=[self.bot.id])
        response = auth_client.post(url, {}, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_stop_bot(self, auth_client):
        self.bot.status = 'running'
        self.bot.save()
        url = reverse('investments:bot-stop', args=[self.bot.id])
        response = auth_client.post(url, {}, format='json')
        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == 'stopped'

    def test_stop_not_running_fails(self, auth_client):
        url = reverse('investments:bot-stop', args=[self.bot.id])
        response = auth_client.post(url, {}, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_pause_bot(self, auth_client):
        self.bot.status = 'running'
        self.bot.save()
        url = reverse('investments:bot-pause', args=[self.bot.id])
        response = auth_client.post(url, {}, format='json')
        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == 'paused'

    def test_pause_not_running_fails(self, auth_client):
        url = reverse('investments:bot-pause', args=[self.bot.id])
        response = auth_client.post(url, {}, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_bot_not_found(self, auth_client):
        url = reverse('investments:bot-start', args=['00000000-0000-0000-0000-000000000000'])
        response = auth_client.post(url, {}, format='json')
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestTradingViewWebhookView:
    @pytest.fixture(autouse=True)
    def setup(self, db, user):
        self.exchange = Exchange.objects.create(name='binance', display_name='Binance')
        self.pair = TradingPair.objects.create(
            exchange=self.exchange, symbol='BTC/USDT', base_asset='BTC', quote_asset='USDT',
        )

    def test_webhook_bot_not_found(self, api_client):
        url = reverse('investments:tradingview-webhook', args=['00000000-0000-0000-0000-000000000000'])
        response = api_client.post(url, {'secret': 'test'}, format='json')
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_webhook_invalid_secret(self, api_client, user):
        bot = WebhookAlertBot.objects.create(
            user=user, bot_name='Webhook Bot', category='webhook',
            exchange=self.exchange, trading_pair=self.pair,
            secret_key='correct-secret',
        )
        url = reverse('investments:tradingview-webhook', args=[bot.webhook_id])
        response = api_client.post(url, {'secret': 'wrong-secret'}, format='json')
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_webhook_invalid_action(self, api_client, user):
        bot = WebhookAlertBot.objects.create(
            user=user, bot_name='Webhook Bot', category='webhook',
            exchange=self.exchange, trading_pair=self.pair,
            secret_key='my-secret',
        )
        url = reverse('investments:tradingview-webhook', args=[bot.webhook_id])
        response = api_client.post(url, {'secret': 'my-secret', 'action': 'hold'}, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_webhook_buy_success(self, api_client, user):
        self.pair.current_price = Decimal('50000')
        self.pair.save()
        bot = WebhookAlertBot.objects.create(
            user=user, bot_name='Webhook Bot', category='webhook',
            exchange=self.exchange, trading_pair=self.pair,
            secret_key='my-secret', default_amount=Decimal('10'),
        )
        url = reverse('investments:tradingview-webhook', args=[bot.webhook_id])
        response = api_client.post(url, {
            'secret': 'my-secret',
            'action': 'buy',
            'order': {'amount': '0.001'},
        }, format='json')
        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == 'success'


@pytest.mark.django_db
class TestEMAWebhookView:
    @pytest.fixture(autouse=True)
    def setup(self, db, user):
        user.username = 'testuser_ema'
        user.save()
        self.exchange = Exchange.objects.create(name='binance', display_name='Binance')
        self.pair = TradingPair.objects.create(
            exchange=self.exchange, symbol='BTC/USDT', base_asset='BTC', quote_asset='USDT',
        )

    def test_ema_webhook_success(self, api_client, user):
        url = reverse('investments:ema-webhook')
        data = {
            'username': 'testuser_ema',
            'pair': 'BTC/USDT',
            'exchange': 'binance',
            'EMA200': 45000,
        }
        response = api_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == 'success'

    def test_ema_webhook_invalid_user(self, api_client):
        url = reverse('investments:ema-webhook')
        data = {
            'username': 'nonexistent',
            'pair': 'BTC/USDT',
            'exchange': 'binance',
            'EMA200': 45000,
        }
        response = api_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestRSIWebhookView:
    @pytest.fixture(autouse=True)
    def setup(self, db, user):
        user.username = 'testuser_rsi'
        user.save()
        self.exchange = Exchange.objects.create(name='binance', display_name='Binance')
        self.pair = TradingPair.objects.create(
            exchange=self.exchange, symbol='BTC/USDT', base_asset='BTC', quote_asset='USDT',
        )

    def test_rsi_webhook_success(self, api_client, user):
        url = reverse('investments:rsi-webhook')
        data = {
            'username': 'testuser_rsi',
            'pair': 'BTC/USDT',
            'exchange': 'binance',
            'RSI': 72.5,
            'color': 'red',
            'prev_color': 'green',
        }
        response = api_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == 'success'


@pytest.mark.django_db
class TestQuantumAIDepositView:
    @pytest.fixture(autouse=True)
    def setup(self, db, user):
        self.exchange = Exchange.objects.create(name='binance', display_name='Binance')
        self.pair = TradingPair.objects.create(
            exchange=self.exchange, symbol='BTC/USDT', base_asset='BTC', quote_asset='USDT',
        )

    def test_deposit_success(self, auth_client, user):
        bot = QuantumAIBot.objects.create(
            user=user, bot_name='QB', category='quantum_ai',
            exchange=self.exchange, trading_pair=self.pair,
        )
        url = reverse('investments:quantum-deposit', args=[bot.id])
        data = {
            'amount': '100.00',
            'coin_type': 'USDT',
            'blockchain': 'BEP20',
            'transaction_hash': '0xtxhash_deposit_test',
        }
        response = auth_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_200_OK

    def test_deposit_missing_fields(self, auth_client, user):
        bot = QuantumAIBot.objects.create(
            user=user, bot_name='QB', category='quantum_ai',
            exchange=self.exchange, trading_pair=self.pair,
        )
        url = reverse('investments:quantum-deposit', args=[bot.id])
        response = auth_client.post(url, {}, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_deposit_bot_not_found(self, auth_client):
        url = reverse('investments:quantum-deposit', args=['00000000-0000-0000-0000-000000000000'])
        data = {'amount': '100', 'coin_type': 'USDT', 'blockchain': 'BEP20', 'transaction_hash': '0xhash'}
        response = auth_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestIndicatorManualViews:
    def test_ema_manual(self, api_client):
        url = reverse('investments:ema-indicator')
        response = api_client.post(url, {}, format='json')
        assert response.status_code == status.HTTP_200_OK

    def test_rsi_manual(self, api_client):
        url = reverse('investments:rsi-indicator')
        response = api_client.post(url, {}, format='json')
        assert response.status_code == status.HTTP_200_OK
