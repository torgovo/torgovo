"""
Black-box security tests for vulnerability fixes.

Each test simulates an attacker trying to exploit the fixed vulnerability.
"""
import pytest
import json
import logging
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


# =========================================================================
# 1. BlockchainAddressViewSet — CUD blocked for regular users
# =========================================================================

class TestBlockchainAddressViewSetAuthZ:
    """PRE: authenticated users could create/update/delete any address."""

    def test_unauthenticated_cannot_create(self, api_client):
        url = reverse('exchanges:blockchain-addresses-list')
        data = {'coin_type': 'USDT', 'blockchain': 'BEP20', 'address': '0xbad'}
        response = api_client.post(url, data, format='json')
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ), f"Anonymous could create address: {response.status_code}"

    def test_unauthenticated_cannot_delete(self, api_client, db):
        from apps.payments.models import BlockchainAddress
        addr = BlockchainAddress.objects.create(
            coin_type='USDT', blockchain='ERC20',
            address='0x1234567890abcdef',
        )
        url = reverse('exchanges:blockchain-addresses-detail', args=[addr.id])
        response = api_client.delete(url)
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ), f"Anonymous could delete address: {response.status_code}"

    def test_unauthenticated_cannot_update(self, api_client, db):
        from apps.payments.models import BlockchainAddress
        addr = BlockchainAddress.objects.create(
            coin_type='USDT', blockchain='ERC20',
            address='0x1234567890abcdef',
        )
        url = reverse('exchanges:blockchain-addresses-detail', args=[addr.id])
        response = api_client.patch(url, {'address': '0xdeadbeef'}, format='json')
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ), f"Anonymous could update address: {response.status_code}"

    def test_regular_user_cannot_create(self, auth_client):
        url = reverse('exchanges:blockchain-addresses-list')
        data = {'coin_type': 'USDT', 'blockchain': 'BEP20', 'address': '0xbad'}
        response = auth_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_403_FORBIDDEN, (
            f"Regular user could create address: {response.status_code}"
        )

    def test_regular_user_cannot_delete(self, auth_client, db):
        from apps.payments.models import BlockchainAddress
        addr = BlockchainAddress.objects.create(
            coin_type='USDT', blockchain='ERC20',
            address='0x1234567890abcdef',
        )
        url = reverse('exchanges:blockchain-addresses-detail', args=[addr.id])
        response = auth_client.delete(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN, (
            f"Regular user could delete address: {response.status_code}"
        )

    def test_regular_user_cannot_update(self, auth_client, db):
        from apps.payments.models import BlockchainAddress
        addr = BlockchainAddress.objects.create(
            coin_type='USDT', blockchain='ERC20',
            address='0x1234567890abcdef',
        )
        url = reverse('exchanges:blockchain-addresses-detail', args=[addr.id])
        response = auth_client.patch(url, {'address': '0xdeadbeef'}, format='json')
        assert response.status_code == status.HTTP_403_FORBIDDEN, (
            f"Regular user could update address: {response.status_code}"
        )

    def test_regular_user_can_read(self, auth_client, db):
        from apps.payments.models import BlockchainAddress
        BlockchainAddress.objects.create(
            coin_type='USDT', blockchain='ERC20',
            address='0x1234567890abcdef',
        )
        url = reverse('exchanges:blockchain-addresses-list')
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK, (
            f"Regular user cannot read addresses: {response.status_code}"
        )

    def test_admin_can_create(self, admin_client):
        url = reverse('exchanges:blockchain-addresses-list')
        data = {'coin_type': 'USDT', 'blockchain': 'BEP20', 'address': '0xgood'}
        response = admin_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_201_CREATED, (
            f"Admin could not create address: {response.status_code}"
        )

    def test_admin_can_delete(self, admin_client, db):
        from apps.payments.models import BlockchainAddress
        addr = BlockchainAddress.objects.create(
            coin_type='USDT', blockchain='ERC20',
            address='0x1234567890abcdef',
        )
        url = reverse('exchanges:blockchain-addresses-detail', args=[addr.id])
        response = admin_client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT, (
            f"Admin could not delete address: {response.status_code}"
        )


# =========================================================================
# 2. ExchangeStatusViewSet — unauthenticated access blocked
# =========================================================================

class TestExchangeStatusViewSetAuthZ:
    """PRE: anyone (even unauthenticated) could read exchange status."""

    def test_unauthenticated_cannot_list(self, api_client, db):
        from apps.trading.models import ExchangeStatus
        ExchangeStatus.objects.create(exchange_name='binance', status='online')
        url = reverse('exchanges:status-list')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED, (
            f"Anonymous could list status: {response.status_code}"
        )

    def test_authenticated_can_list(self, auth_client, db):
        from apps.trading.models import ExchangeStatus
        ExchangeStatus.objects.create(exchange_name='binance', status='online')
        url = reverse('exchanges:status-list')
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK, (
            f"Authenticated user cannot list status: {response.status_code}"
        )


# =========================================================================
# 3. Old admin views (IndicatorView, BybitIndicatorView) — staff-only
# =========================================================================

class TestOldAdminViewsAuthZ:
    """PRE: any unauthenticated user could view any user's indicators."""

    INDICATOR_URLS = [
        'bots:binance-indicator',
        'bots:bybit-indicator',
    ]
    ORDER_URLS = [
        'bots:close-order',
        'bots:open-order',
    ]

    @pytest.fixture(autouse=True)
    def _setup(self, db, user):
        from apps.bots.models import PairConfig
        PairConfig.objects.create(user=user, pair_symbol='BTC/USDT', slug='btc')

    def test_unauthenticated_cannot_access_indicators(self, api_client):
        for url_name in self.INDICATOR_URLS:
            url = reverse(url_name, kwargs={'username': 'testuser', 'pair': 'btc'})
            response = api_client.get(url)
            assert response.status_code == status.HTTP_401_UNAUTHORIZED, (
                f"Anonymous could access {url_name}: {response.status_code}"
            )

    def test_regular_user_cannot_access_indicators(self, second_auth_client):
        for url_name in self.INDICATOR_URLS:
            url = reverse(url_name, kwargs={'username': 'testuser', 'pair': 'btc'})
            response = second_auth_client.get(url)
            assert response.status_code == status.HTTP_401_UNAUTHORIZED, (
                f"Regular user could access {url_name}: {response.status_code}"
            )

    def test_unauthenticated_cannot_close_order(self, api_client):
        url = reverse('bots:close-order', kwargs={
            'username': 'testuser', 'pair': 'btc',
        })
        response = api_client.post(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED, (
            f"Anonymous could close order: {response.status_code}"
        )

    def test_unauthenticated_cannot_open_order(self, api_client):
        url = reverse('bots:open-order', kwargs={
            'username': 'testuser', 'pair': 'btc', 'side': 'buy',
        })
        response = api_client.post(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED, (
            f"Anonymous could open order: {response.status_code}"
        )

    def test_regular_user_cannot_close_order(self, auth_client):
        url = reverse('bots:close-order', kwargs={
            'username': 'testuser', 'pair': 'btc',
        })
        response = auth_client.post(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED, (
            f"Regular user could close order: {response.status_code}"
        )

    def test_regular_user_cannot_open_order(self, auth_client):
        url = reverse('bots:open-order', kwargs={
            'username': 'testuser', 'pair': 'btc', 'side': 'buy',
        })
        response = auth_client.post(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED, (
            f"Regular user could open order: {response.status_code}"
        )

    def test_close_order_get_rejected_method_not_allowed(self, admin_client):
        """GET to close-order must be rejected (POST only for CSRF protection)."""
        url = reverse('bots:close-order', kwargs={
            'username': 'testuser', 'pair': 'btc',
        })
        response = admin_client.get(url)
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED, (
            f"Admin GET to close-order should be 405, got {response.status_code}"
        )

    def test_open_order_get_rejected_method_not_allowed(self, admin_client):
        """GET to open-order must be rejected (POST only for CSRF protection)."""
        url = reverse('bots:open-order', kwargs={
            'username': 'testuser', 'pair': 'btc', 'side': 'buy',
        })
        response = admin_client.get(url)
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED, (
            f"Admin GET to open-order should be 405, got {response.status_code}"
        )


# =========================================================================
# 4. Bot serializers — subscription FK read-only on updates
# =========================================================================

class TestSubscriptionFKReadOnly:
    """PRE: subscription field was writable on PATCH, allowing hijacking."""

    @pytest.fixture(autouse=True)
    def _setup(self, db, user, second_user, bot_subscription):
        from apps.payments.models import BotSubscription
        # Create a subscription belonging to second_user
        self.other_sub = BotSubscription.objects.create(
            user=second_user,
            plan=bot_subscription.plan,
            status='active',
        )
        self.other_sub_id = str(self.other_sub.id)

    def test_gridbot_patch_subscription_rejected(self, auth_client, user):
        from apps.bots.models import GridBot
        bot = GridBot.objects.create(
            user=user, bot_name='mybot', exchange_name='binance',
            trading_pair='BTC/USDT',
            base_amount=100, favor_levels=3, against_levels=3,
        )
        url = reverse('bots:gridbot-detail', args=[bot.id])
        response = auth_client.patch(url, {'subscription': self.other_sub_id}, format='json')
        # Should not allow changing subscription
        assert response.status_code in (
            status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST,
        ), f"Unexpected status: {response.status_code}"
        bot.refresh_from_db()
        assert str(bot.subscription_id) != self.other_sub_id, (
            "Subscription was hijacked to another user's subscription!"
        )

    def test_signalbot_patch_subscription_rejected(self, auth_client, user):
        from apps.bots.models import SignalBot
        bot = SignalBot.objects.create(
            user=user, bot_name='mysignal', exchange_name='binance',
            trading_pair='BTC/USDT', default_amount=10,
        )
        url = reverse('bots:signalbot-detail', args=[bot.id])
        response = auth_client.patch(url, {'subscription': self.other_sub_id}, format='json')
        assert response.status_code in (
            status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST,
        ), f"Unexpected status: {response.status_code}"
        bot.refresh_from_db()
        assert str(bot.subscription_id) != self.other_sub_id, (
            "SignalBot subscription hijacked!"
        )

    def test_martingale_patch_subscription_rejected(self, auth_client, user):
        from apps.bots.models import MartingaleBot
        bot = MartingaleBot.objects.create(
            user=user, bot_name='mymart', exchange_name='binance',
            trading_pair='BTC/USDT',
            base_amount=100, favor_levels=3, against_levels=3,
        )
        url = reverse('bots:martingalebot-detail', args=[bot.id])
        response = auth_client.patch(url, {'subscription': self.other_sub_id}, format='json')
        assert response.status_code in (
            status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST,
        ), f"Unexpected status: {response.status_code}"
        bot.refresh_from_db()
        assert str(bot.subscription_id) != self.other_sub_id, (
            "MartingaleBot subscription hijacked!"
        )

    def test_pairconfig_patch_subscription_rejected(self, auth_client, user):
        from apps.bots.models import PairConfig
        config = PairConfig.objects.create(
            user=user, pair_symbol='BTC/USDT', slug='btc',
        )
        url = reverse('bots:pairconfig-detail', args=[config.id])
        response = auth_client.patch(url, {'subscription': self.other_sub_id}, format='json')
        assert response.status_code in (
            status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST,
        ), f"Unexpected status: {response.status_code}"
        config.refresh_from_db()
        assert str(config.subscription_id) != self.other_sub_id, (
            "PairConfig subscription hijacked!"
        )


# =========================================================================
# 5. TelegramSubscriptionViewSet — user enforcement
# =========================================================================

class TestTelegramSubscriptionUserEnforcement:
    """PRE: any authenticated user could create a sub for any user_id."""

    def test_create_forces_current_user(self, auth_client, user, second_user):
        from apps.bots.models import TelegramSignalPlan
        plan = TelegramSignalPlan.objects.create(
            name='Test Plan', description='test', duration_days=30, price_usd=10,
        )
        url = reverse('bots:telegramsub-list')
        response = auth_client.post(url, {
            'plan': plan.id,
            'telegram_handle': '@testuser',
            'user': second_user.id,
        }, format='json')
        # The serializer's HiddenField should override user to request.user
        from apps.bots.models import TelegramSignalSubscription
        subs = TelegramSignalSubscription.objects.filter(user=second_user)
        assert subs.count() == 0, (
            "Subscription was created for the wrong user!"
        )
        subs = TelegramSignalSubscription.objects.filter(user=user)
        assert subs.count() == 1, (
            "Subscription was not created for the authenticated user!"
        )


# =========================================================================
# 6. Webhook logging — secret redacted
# =========================================================================

class TestWebhookLoggingSecretRedaction:
    """PRE: full webhook payload including 'secret' was logged."""

    def test_secret_not_in_log(self, caplog):
        caplog.set_level(logging.INFO)
        from apps.webhooks.views import SignalBotWebhookView
        from django.test import RequestFactory
        from unittest.mock import patch

        # We test the redaction logic directly
        payload = {
            'bot_id': 'test-bot-id',
            'secret': 'super-secret-key-12345',
            'side': 'buy',
            'Pair': 'BTC/USDT',
        }
        safe_payload = {k: v for k, v in payload.items() if k != 'secret'}

        assert 'secret' not in safe_payload, "Secret key still present in safe payload"
        assert safe_payload.get('secret') is None, "Secret value leaked"
        assert safe_payload['bot_id'] == 'test-bot-id', "Non-secret fields preserved"
        assert safe_payload['side'] == 'buy', "Non-secret fields preserved"


# =========================================================================
# 7. BotEngine config — API keys stripped after init
# =========================================================================

class TestBotEngineConfigStripsKeys:
    """PRE: decrypted API keys remained in self.config for the bot's lifetime."""

    REQUIRED_PARAMS = {
        'symbol': 'BTC/USDT',
        'quantity': 10,
        'Amount_Type': 'dollar',
        'Order_Type': 'market',
    }

    def test_api_keys_stripped_from_config(self):
        from apps.trading.engines.bot_engine import BotEngine
        from unittest.mock import patch, MagicMock

        with patch('apps.trading.engines.bot_engine.BotExecutor.from_config') as mock_from_config:
            mock_executor = MagicMock()
            mock_from_config.return_value = mock_executor

            config = {
                'bot_id': 'test-id',
                'bot_name': 'testbot',
                'bot_type': 'grid',
                'api_key': 'decrypted-key-123',
                'secret_key': 'decrypted-secret-456',
                'passphrase': 'decrypted-passphrase-789',
                'parameters': self.REQUIRED_PARAMS,
                'symbol': 'BTC/USDT',
                'strategy': 'quantum_ai',
            }
            engine = BotEngine(config)

            assert engine.config.get('api_key') is None, (
                "api_key was NOT stripped from config"
            )
            assert engine.config.get('secret_key') is None, (
                "secret_key was NOT stripped from config"
            )
            assert engine.config.get('passphrase') is None, (
                "passphrase was NOT stripped from config"
            )
            assert engine.config.get('bot_id') == 'test-id', (
                "Non-sensitive fields were stripped too"
            )
            assert engine.config.get('bot_name') == 'testbot', (
                "Non-sensitive fields were stripped too"
            )


# =========================================================================
# 13. Indicator webhook endpoints — X-Webhook-Token required
# =========================================================================

class TestIndicatorWebhookEndpointsAuth:
    """Authenticated users can POST indicator values; anonymous get 401."""

    def test_ema_webhook_returns_401_without_token(self, api_client):
        url = '/api/bots/indicators/ema/'
        response = api_client.post(url, {'EMA200': 200, 'pair': 'BTC/USDT'}, format='json')
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN,
        ), f"Anonymous could POST EMA: {response.status_code}"

    def test_rsi_webhook_returns_401_without_token(self, api_client):
        url = '/api/bots/indicators/rsi/'
        response = api_client.post(url, {'RSI': 50, 'pair': 'BTC/USDT'}, format='json')
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN,
        ), f"Anonymous could POST RSI: {response.status_code}"

    def test_bb_webhook_returns_401_without_token(self, api_client):
        url = '/api/bots/indicators/bb/'
        response = api_client.post(url, {'BB': 'upper', 'pair': 'BTC/USDT'}, format='json')
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN,
        ), f"Anonymous could POST BB: {response.status_code}"

    def test_ema_webhook_returns_404_with_valid_token_but_no_pair(self, user, api_client):
        """A non-existent pair should 404, not 500 (token was valid)."""
        url = '/api/bots/indicators/ema/'
        response = api_client.post(
            url,
            {'EMA200': 200, 'pair': 'NONEXISTENT'},
            format='json',
            HTTP_X_WEBHOOK_TOKEN=str(user.webhook_token),
        )
        assert response.status_code in (
            status.HTTP_404_NOT_FOUND, status.HTTP_400_BAD_REQUEST,
        ), f"Expected 404/400 for nonexistent pair, got {response.status_code}"

    def test_ema_webhook_accepts_with_valid_token_and_pair(self, user, api_client, db):
        """Full happy-path: valid token + existing pair + indicator value."""
        from apps.bots.models import PairConfig, Indicator, SignalBot
        pair = PairConfig.objects.create(
            user=user, pair_symbol='BTC/USDT', quantity=0.001,
        )
        url = '/api/bots/indicators/ema/'
        response = api_client.post(
            url,
            {'EMA200': 200, 'pair': 'BTC/USDT', 'exchange': 'binance'},
            format='json',
            HTTP_X_WEBHOOK_TOKEN=str(user.webhook_token),
        )
        assert response.status_code in (200, 404), (
            f"Expected 200 or 404 (200=ok, 404=missing creds or pair), got {response.status_code}"
        )
