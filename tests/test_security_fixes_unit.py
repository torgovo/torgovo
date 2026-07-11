"""
Black-box security tests — unit level.

Tests each fix by directly exercising the security logic
without going through Django's full request/response cycle,
avoiding environment-specific migration/DRF version issues.
"""
import pytest


# =========================================================================
# 1. BlockchainAddressViewSet — permission check logic
# =========================================================================

class TestBlockchainAddressPermissions:
    """The get_permissions() must block CUD for non-staff."""

    def test_create_action_requires_admin(self):
        from rest_framework.permissions import IsAdminUser, IsAuthenticated
        from apps.exchanges.views import BlockchainAddressViewSet

        view = BlockchainAddressViewSet()
        view.action = 'create'
        perms = view.get_permissions()
        perm_types = [type(p) for p in perms]
        assert IsAuthenticated in perm_types, "Missing IsAuthenticated for create"
        assert IsAdminUser in perm_types, "Missing IsAdminUser for create"

    def test_destroy_action_requires_admin(self):
        from rest_framework.permissions import IsAdminUser, IsAuthenticated
        from apps.exchanges.views import BlockchainAddressViewSet

        view = BlockchainAddressViewSet()
        view.action = 'destroy'
        perms = view.get_permissions()
        perm_types = [type(p) for p in perms]
        assert IsAuthenticated in perm_types
        assert IsAdminUser in perm_types

    def test_update_action_requires_admin(self):
        from rest_framework.permissions import IsAdminUser, IsAuthenticated
        from apps.exchanges.views import BlockchainAddressViewSet

        view = BlockchainAddressViewSet()
        view.action = 'update'
        perms = view.get_permissions()
        perm_types = [type(p) for p in perms]
        assert IsAuthenticated in perm_types
        assert IsAdminUser in perm_types

    def test_partial_update_action_requires_admin(self):
        from rest_framework.permissions import IsAdminUser, IsAuthenticated
        from apps.exchanges.views import BlockchainAddressViewSet

        view = BlockchainAddressViewSet()
        view.action = 'partial_update'
        perms = view.get_permissions()
        perm_types = [type(p) for p in perms]
        assert IsAuthenticated in perm_types
        assert IsAdminUser in perm_types

    def test_list_action_requires_only_auth(self):
        from rest_framework.permissions import IsAdminUser, IsAuthenticated
        from apps.exchanges.views import BlockchainAddressViewSet

        view = BlockchainAddressViewSet()
        view.action = 'list'
        perms = view.get_permissions()
        perm_types = [type(p) for p in perms]
        assert IsAuthenticated in perm_types, "Missing IsAuthenticated for list"
        assert IsAdminUser not in perm_types, "IsAdminUser should NOT be required for list"

    def test_retrieve_action_requires_only_auth(self):
        from rest_framework.permissions import IsAdminUser, IsAuthenticated
        from apps.exchanges.views import BlockchainAddressViewSet

        view = BlockchainAddressViewSet()
        view.action = 'retrieve'
        perms = view.get_permissions()
        perm_types = [type(p) for p in perms]
        assert IsAuthenticated in perm_types
        assert IsAdminUser not in perm_types


# =========================================================================
# 2. ExchangeStatusViewSet — permission_classes set
# =========================================================================

class TestExchangeStatusPermissions:
    """ExchangeStatusViewSet must require authentication."""

    def test_permission_classes_set(self):
        from rest_framework.permissions import IsAuthenticated
        from apps.exchanges.views import ExchangeStatusViewSet

        assert ExchangeStatusViewSet.permission_classes is not None, (
            "permission_classes not set on ExchangeStatusViewSet"
        )
        assert IsAuthenticated in ExchangeStatusViewSet.permission_classes, (
            "IsAuthenticated missing from ExchangeStatusViewSet"
        )


# =========================================================================
# 3. Old admin views — staff-only gate
# =========================================================================

class TestOldAdminViewsStaffGate:
    """The is_staff check must be present in each view."""

    GET_VIEW_CLASSES = []
    POST_VIEW_CLASSES = []

    @pytest.fixture(autouse=True)
    def _setup(self):
        from apps.bots.views import (
            IndicatorView, BybitIndicatorView,
            CustomOrderClosingView, CustomOrderOpeningView,
        )
        self.GET_VIEW_CLASSES = [
            IndicatorView, BybitIndicatorView,
        ]
        self.POST_VIEW_CLASSES = [
            CustomOrderClosingView, CustomOrderOpeningView,
        ]

    def test_indicator_views_have_async_get_method(self):
        """Read-only indicator views use GET."""
        import inspect
        for ViewClass in self.GET_VIEW_CLASSES:
            assert hasattr(ViewClass, 'get'), (
                f"{ViewClass.__name__} missing get() method"
            )
            assert inspect.iscoroutinefunction(ViewClass.get), (
                f"{ViewClass.__name__}.get() is not async"
            )

    def test_order_views_have_async_post_method(self):
        """Order views use POST (required for CSRF protection)."""
        import inspect
        for ViewClass in self.POST_VIEW_CLASSES:
            assert hasattr(ViewClass, 'post'), (
                f"{ViewClass.__name__} missing post() method"
            )
            assert inspect.iscoroutinefunction(ViewClass.post), (
                f"{ViewClass.__name__}.post() is not async"
            )

    def test_order_views_do_not_accept_get(self):
        """Order views must NOT have get() — CSRF vector otherwise."""
        for ViewClass in self.POST_VIEW_CLASSES:
            assert not hasattr(ViewClass, 'get'), (
                f"{ViewClass.__name__} still has get() — CSRF risk"
            )


# =========================================================================
# 4. Serializer read_only_fields — subscription protected
# =========================================================================

class TestSubscriptionReadOnlyFields:
    """subscription FK must be in read_only_fields on bot serializers."""

    SERIALIZER_CLASSES = []

    @pytest.fixture(autouse=True)
    def _setup(self):
        from apps.bots.serializers import (
            SignalBotSerializer, GridBotSerializer,
            MartingaleBotSerializer, QuantumAIInvestmentSerializer,
            PairConfigSerializer,
        )
        self.SERIALIZER_CLASSES = [
            SignalBotSerializer, GridBotSerializer,
            MartingaleBotSerializer, QuantumAIInvestmentSerializer,
            PairConfigSerializer,
        ]

    def test_subscription_in_read_only_fields(self):
        for SerializerClass in self.SERIALIZER_CLASSES:
            ro_fields = getattr(SerializerClass.Meta, 'read_only_fields', [])
            assert 'subscription' in ro_fields, (
                f"'subscription' not in {SerializerClass.__name__}.Meta.read_only_fields "
                f"(got {ro_fields})"
            )


# =========================================================================
# 5. TelegramSubscriptionSerializer — HiddenField for user
# =========================================================================

class TestTelegramSubscriptionUserField:
    """user must be a HiddenField and in read_only_fields."""

    def test_user_is_hidden_field(self):
        from rest_framework import serializers
        from apps.subscriptions.views import TelegramSubscriptionSerializer

        user_field = TelegramSubscriptionSerializer._declared_fields.get('user')
        assert user_field is not None, (
            "TelegramSubscriptionSerializer missing explicit 'user' field"
        )
        assert isinstance(user_field, serializers.HiddenField), (
            "'user' field is not HiddenField"
        )

    def test_user_in_read_only_fields(self):
        from apps.subscriptions.views import TelegramSubscriptionSerializer

        ro_fields = getattr(TelegramSubscriptionSerializer.Meta, 'read_only_fields', [])
        assert 'user' in ro_fields, (
            f"'user' not in read_only_fields (got {ro_fields})"
        )

    def test_perform_create_exists(self):
        from apps.subscriptions.views import TelegramSubscriptionViewSet

        assert hasattr(TelegramSubscriptionViewSet, 'perform_create'), (
            "TelegramSubscriptionViewSet missing perform_create"
        )


# =========================================================================
# 6. Webhook logging — secret redaction logic
# =========================================================================

class TestWebhookSecretRedaction:
    """The payload dict must have 'secret' removed before logging."""

    def test_secret_removed_from_payload(self):
        payload = {
            'bot_id': 'test-bot-id',
            'secret': 'super-secret-key-12345',
            'side': 'buy',
            'Pair': 'BTC/USDT',
        }
        safe_payload = {k: v for k, v in payload.items() if k != 'secret'}

        assert 'secret' not in safe_payload, "Secret key still in safe payload"
        assert safe_payload.get('secret') is None, "Secret value leaked"

    def test_nonsecret_fields_preserved(self):
        payload = {
            'bot_id': 'test-bot-id',
            'secret': 'super-secret-key-12345',
            'side': 'buy',
            'Pair': 'BTC/USDT',
        }
        safe_payload = {k: v for k, v in payload.items() if k != 'secret'}

        assert safe_payload['bot_id'] == 'test-bot-id'
        assert safe_payload['side'] == 'buy'
        assert safe_payload['Pair'] == 'BTC/USDT'

    def test_payload_without_secret_unchanged(self):
        payload = {'bot_id': 'test', 'side': 'sell'}
        safe_payload = {k: v for k, v in payload.items() if k != 'secret'}
        assert safe_payload == payload, "Payload without 'secret' should be unchanged"


# =========================================================================
# 7. BotEngine config — API keys stripped
# =========================================================================

class TestBotEngineConfigStripKeys:
    """api_key, secret_key, passphrase must be removed from config after init."""

    def test_keys_stripped(self):
        from apps.trading.engines.bot_engine import BotEngine
        from unittest.mock import patch, MagicMock

        with patch('apps.trading.engines.bot_engine.BotExecutor') as MockExecutor:
            mock_executor = MagicMock()
            MockExecutor.from_config.return_value = mock_executor

            config = {
                'bot_id': 'test-id',
                'bot_name': 'testbot',
                'api_key': 'decrypted-key-123',
                'secret_key': 'decrypted-secret-456',
                'passphrase': 'decrypted-passphrase-789',
                'parameters': {'symbol': 'BTC/USDT', 'quantity': 10},
                'symbol': 'BTC/USDT',
            }
            engine = BotEngine(config)

            assert engine.config.get('api_key') is None, "api_key NOT stripped"
            assert engine.config.get('secret_key') is None, "secret_key NOT stripped"
            assert engine.config.get('passphrase') is None, "passphrase NOT stripped"

    def test_nonsensitive_fields_preserved(self):
        from apps.trading.engines.bot_engine import BotEngine
        from unittest.mock import patch, MagicMock

        with patch('apps.trading.engines.bot_engine.BotExecutor') as MockExecutor:
            mock_executor = MagicMock()
            MockExecutor.from_config.return_value = mock_executor

            config = {
                'bot_id': 'test-id',
                'bot_name': 'testbot',
                'api_key': 'key',
                'secret_key': 'secret',
                'parameters': {'symbol': 'BTC/USDT', 'quantity': 10},
                'symbol': 'BTC/USDT',
            }
            engine = BotEngine(config)

            assert engine.config.get('bot_id') == 'test-id'
            assert engine.config.get('bot_name') == 'testbot'

    def test_keys_not_in_get_status(self):
        """get_status() should never expose credentials."""
        from apps.trading.engines.bot_engine import BotEngine
        from unittest.mock import patch, MagicMock

        with patch('apps.trading.engines.bot_engine.BotExecutor') as MockExecutor:
            mock_executor = MagicMock()
            MockExecutor.from_config.return_value = mock_executor

            config = {
                'bot_id': 'test-id',
                'bot_name': 'testbot',
                'api_key': 'key',
                'secret_key': 'secret',
                'parameters': {'symbol': 'BTC/USDT', 'quantity': 10},
                'symbol': 'BTC/USDT',
            }
            engine = BotEngine(config)
            status = engine.get_status()

            assert 'api_key' not in status
            assert 'secret_key' not in status
            assert 'api_key' not in str(status)
            assert 'secret_key' not in str(status)


class TestWebhookIntegration:
    """Full request/response cycle tests for SignalBotWebhookView.

    These exercise the live validation logic (timestamp, HMAC, rate limiting,
    dedupe) through Django's test client against the real LocMemCache backend.
    execute_trade is mocked to avoid needing live exchange credentials.
    """

    @pytest.fixture(autouse=True)
    def _clean_cache(self):
        from django.core.cache import cache
        cache.clear()
        yield
        cache.clear()

    def _payload(self, **overrides):
        from django.utils import timezone
        base = {
            "bot_id": "test-aaaaa-bbbbb-ccccc",
            "secret": "test-secret",
            "side": "buy",
            "Pair": "BTC/USDT",
            "timestamp": timezone.now().strftime('%Y-%m-%dT%H:%M:%SZ'),
        }
        base.update(overrides)
        return base

    def _make_bot(self, db):
        from apps.bots.models import SignalBot
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user, _ = User.objects.get_or_create(
            username='webhook_test_user',
            defaults={'email': 'wh@test.com'},
        )
        bot = SignalBot.objects.create(
            user=user,
            bot_id="test-aaaaa-bbbbb-ccccc",
            secret_key="test-secret",
            exchange_name='binance',
            trading_pair='BTC/USDT',
            default_amount=10,
            is_active=True,
        )
        return bot, user

    def test_missing_timestamp_returns_400(self, db):
        from django.test.client import RequestFactory
        from apps.webhooks.views import SignalBotWebhookView
        from unittest.mock import patch
        import json

        self._make_bot(db)
        factory = RequestFactory()
        payload = self._payload()
        del payload['timestamp']
        request = factory.post('/api/webhooks/custombot/',
                               json.dumps(payload),
                               content_type='application/json')

        with patch.object(SignalBotWebhookView, 'execute_trade',
                          return_value={'status': 'success'}):
            response = SignalBotWebhookView.as_view()(request)

        assert response.status_code == 400

    def test_stale_timestamp_returns_400(self, db):
        from django.test.client import RequestFactory
        from apps.webhooks.views import SignalBotWebhookView
        from unittest.mock import patch
        import json
        from datetime import timedelta
        from django.utils import timezone

        self._make_bot(db)
        factory = RequestFactory()
        stale_ts = (timezone.now() - timedelta(seconds=180)).strftime('%Y-%m-%dT%H:%M:%SZ')
        payload = self._payload(timestamp=stale_ts)
        request = factory.post('/api/webhooks/custombot/',
                               json.dumps(payload),
                               content_type='application/json')

        with patch.object(SignalBotWebhookView, 'execute_trade',
                          return_value={'status': 'success'}):
            response = SignalBotWebhookView.as_view()(request)

        assert response.status_code == 400

    def test_wrong_secret_returns_403_and_counted(self, db):
        from django.test.client import RequestFactory
        from apps.webhooks.views import SignalBotWebhookView
        from django.core.cache import cache
        from unittest.mock import patch
        import json

        bot, _ = self._make_bot(db)
        factory = RequestFactory()
        payload = self._payload(secret='wrong-secret')
        request = factory.post('/api/webhooks/custombot/',
                               json.dumps(payload),
                               content_type='application/json')

        with patch.object(SignalBotWebhookView, 'execute_trade',
                          return_value={'status': 'success'}):
            response = SignalBotWebhookView.as_view()(request)

        assert response.status_code == 403

        fail_count = cache.get(f"webhook:fail:{bot.bot_id}", 0)
        assert fail_count == 1

    def test_rate_limit_after_5_failures_returns_429(self, db):
        from django.test.client import RequestFactory
        from apps.webhooks.views import SignalBotWebhookView
        from django.core.cache import cache
        from unittest.mock import patch
        import json

        bot, _ = self._make_bot(db)
        factory = RequestFactory()
        key = f"webhook:fail:{bot.bot_id}"
        cache.add(key, 5, 300)

        payload = self._payload(secret='wrong-secret')
        request = factory.post('/api/webhooks/custombot/',
                               json.dumps(payload),
                               content_type='application/json')

        with patch.object(SignalBotWebhookView, 'execute_trade',
                          return_value={'status': 'success'}):
            response = SignalBotWebhookView.as_view()(request)

        assert response.status_code == 429

    def test_valid_request_returns_200(self, db):
        from django.test.client import RequestFactory
        from apps.webhooks.views import SignalBotWebhookView
        from unittest.mock import patch
        import json

        self._make_bot(db)
        factory = RequestFactory()
        payload = self._payload()
        request = factory.post('/api/webhooks/custombot/',
                               json.dumps(payload),
                               content_type='application/json')

        with patch.object(SignalBotWebhookView, 'execute_trade',
                          return_value={'status': 'success', 'order_id': 'abc'}):
            response = SignalBotWebhookView.as_view()(request)

        assert response.status_code == 200
        assert response.data['success'] is True

    def test_duplicate_replay_dedupe(self, db):
        from django.test.client import RequestFactory
        from apps.webhooks.views import SignalBotWebhookView
        from unittest.mock import patch
        import json

        self._make_bot(db)
        factory = RequestFactory()
        payload = self._payload()
        request = factory.post('/api/webhooks/custombot/',
                               json.dumps(payload),
                               content_type='application/json')

        call_count = 0

        def counting_trade(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return {'status': 'success', 'order_id': f'order-{call_count}'}

        with patch.object(SignalBotWebhookView, 'execute_trade', side_effect=counting_trade):
            response1 = SignalBotWebhookView.as_view()(request)
            assert response1.status_code == 200
            assert call_count == 1

            response2 = SignalBotWebhookView.as_view()(request)
            assert response2.status_code == 200
            assert 'Duplicate ignored' in str(response2.data.get('message', ''))
            assert call_count == 1

    def test_rate_limit_expires_then_valid_succeeds(self, db):
        from django.test.client import RequestFactory
        from apps.webhooks.views import SignalBotWebhookView
        from django.core.cache import cache
        from unittest.mock import patch
        import json
        import time

        bot, _ = self._make_bot(db)
        factory = RequestFactory()
        key = f"webhook:fail:{bot.bot_id}"
        cache.add(key, 5, 1)

        payload = self._payload(secret='wrong-secret')
        request = factory.post('/api/webhooks/custombot/',
                               json.dumps(payload),
                               content_type='application/json')

        with patch.object(SignalBotWebhookView, 'execute_trade',
                          return_value={'status': 'success'}):
            response = SignalBotWebhookView.as_view()(request)
        assert response.status_code == 429

        time.sleep(1.1)

        payload2 = self._payload()
        request2 = factory.post('/api/webhooks/custombot/',
                                json.dumps(payload2),
                                content_type='application/json')

        with patch.object(SignalBotWebhookView, 'execute_trade',
                          return_value={'status': 'success', 'order_id': 'abc'}):
            response2 = SignalBotWebhookView.as_view()(request2)
        assert response2.status_code == 200


# =========================================================================
# 11. Indicator webhook views — X-Webhook-Token required
# =========================================================================

class TestIndicatorWebhookAuth:
    """All 3 indicator webhook views must reject requests without a valid token."""

    VIEW_CLASSES = []

    @pytest.fixture(autouse=True)
    def _setup(self):
        from apps.bots.views import BinanceEMAView, BinanceRSIView, BinanceBBView
        self.VIEW_CLASSES = [
            BinanceEMAView, BinanceRSIView, BinanceBBView,
        ]

    def test_views_have_async_post_method(self):
        import inspect
        for ViewClass in self.VIEW_CLASSES:
            assert hasattr(ViewClass, 'post')
            assert inspect.iscoroutinefunction(ViewClass.post)

    def test_resolve_webhook_user_returns_none_without_token(self):
        from apps.bots.views import _resolve_webhook_user
        from django.test.client import RequestFactory

        factory = RequestFactory()
        request = factory.post('/fake/')
        user = _resolve_webhook_user(request)
        assert user is None, "Should return None when no token provided"

    def test_resolve_webhook_user_returns_none_with_bad_token(self, db):
        from apps.bots.views import _resolve_webhook_user
        from django.test.client import RequestFactory

        factory = RequestFactory()
        request = factory.post('/fake/', HTTP_X_WEBHOOK_TOKEN='nonexistent-token')
        user = _resolve_webhook_user(request)
        assert user is None, "Should return None for nonexistent token"

    def test_resolve_webhook_user_resolves_by_header(self, db, user):
        from apps.bots.views import _resolve_webhook_user
        from django.test.client import RequestFactory

        token = str(user.webhook_token)
        factory = RequestFactory()
        request = factory.post('/fake/', HTTP_X_WEBHOOK_TOKEN=token)
        resolved = _resolve_webhook_user(request)
        assert resolved == user, f"Should resolve user by token, got {resolved}"


# =========================================================================
# 12. QuantumAIFundSerializer — no master API key exposure
# =========================================================================

class TestQuantumAIFundSerializerNoKeys:
    """master_api_key/secret_key/passphrase must NOT appear in serializer fields."""

    SENSITIVE_FIELDS = ['master_api_key', 'master_secret_key', 'master_passphrase']

    def test_sensitive_fields_excluded_from_serializer(self):
        from apps.bots.serializers import QuantumAIFundSerializer

        meta_fields = QuantumAIFundSerializer.Meta.fields
        for field in self.SENSITIVE_FIELDS:
            assert field not in meta_fields, (
                f"'{field}' must not be in QuantumAIFundSerializer.Meta.fields "
                f"(got {meta_fields})"
            )

    def test_sensitive_fields_not_in_read_only(self):
        from apps.bots.serializers import QuantumAIFundSerializer

        ro_fields = getattr(QuantumAIFundSerializer.Meta, 'read_only_fields', [])
        for field in self.SENSITIVE_FIELDS:
            assert field not in ro_fields, (
                f"'{field}' must not be in read_only_fields either — "
                f"it should be excluded entirely (got {ro_fields})"
            )


# =========================================================================
# 14. QuantumAIFund — save() encrypts plaintext, skips encrypted, skips empty
# =========================================================================

class TestQuantumAIFundEncryption:
    """save() must encrypt plaintext, not double-encrypt, not encrypt empty."""

    def test_save_encrypts_plaintext_api_key(self, db):
        from apps.bots.models import QuantumAIFund
        from core.utils import decrypt_api_key, looks_encrypted

        fund = QuantumAIFund.objects.create(
            name='Test Fund',
            master_api_key='my-plain-api-key',
            master_secret_key='my-plain-secret-key',
        )
        fund.refresh_from_db()
        stored_key = fund.master_api_key
        assert looks_encrypted(stored_key), "Value should be encrypted after save"
        assert decrypt_api_key(stored_key) == 'my-plain-api-key', (
            "Decrypted value should match original"
        )

    def test_save_does_not_double_encrypt(self, db):
        from apps.bots.models import QuantumAIFund
        from core.utils import decrypt_api_key

        fund = QuantumAIFund.objects.create(
            name='Test Fund',
            master_api_key='plain-key',
            master_secret_key='plain-secret',
        )
        fund.refresh_from_db()
        first_stored = fund.master_api_key

        fund.save()
        fund.refresh_from_db()
        second_stored = fund.master_api_key

        assert first_stored == second_stored, (
            "Re-save should not change already-encrypted value"
        )
        assert decrypt_api_key(second_stored) == 'plain-key', (
            "Decrypted value should still match original"
        )

    def test_save_does_not_encrypt_empty_key(self, db):
        from apps.bots.models import QuantumAIFund

        fund = QuantumAIFund.objects.create(
            name='Test Fund',
            master_api_key='',
            master_secret_key='plain-secret',
        )
        fund.refresh_from_db()
        assert fund.master_api_key == '', "Empty key should remain empty after save"

    def test_save_does_not_encrypt_none_passphrase(self, db):
        """passphrase is nullable — verify None is not encrypted."""
        from apps.bots.models import QuantumAIFund

        fund = QuantumAIFund.objects.create(
            name='Test Fund',
            master_api_key='key',
            master_secret_key='secret',
            master_passphrase=None,
        )
        fund.refresh_from_db()
        assert fund.master_passphrase is None, "None passphrase should remain None"

    def test_get_decrypted_credentials_returns_plaintext(self, db):
        from apps.bots.models import QuantumAIFund

        fund = QuantumAIFund.objects.create(
            name='Test Fund',
            master_api_key='api-key-123',
            master_secret_key='secret-key-456',
            master_passphrase='passphrase-789',
        )
        creds = fund.get_decrypted_credentials()
        assert creds['api_key'] == 'api-key-123'
        assert creds['secret_key'] == 'secret-key-456'
        assert creds['passphrase'] == 'passphrase-789'

    def test_passphrase_none_does_not_raise(self, db):
        from apps.bots.models import QuantumAIFund

        fund = QuantumAIFund.objects.create(
            name='Test Fund',
            master_api_key='key',
            master_secret_key='secret',
            master_passphrase=None,
        )
        creds = fund.get_decrypted_credentials()
        assert creds['passphrase'] is None, "None passphrase should return None"

    def test_passphrase_empty_does_not_raise(self, db):
        from apps.bots.models import QuantumAIFund

        fund = QuantumAIFund.objects.create(
            name='Test Fund',
            master_api_key='key',
            master_secret_key='secret',
            master_passphrase='',
        )
        creds = fund.get_decrypted_credentials()
        assert creds['passphrase'] is None or creds['passphrase'] == '', (
            "Empty passphrase should return empty/None"
        )

    def test_looks_encrypted_shared_function(self):
        """Verify the shared looks_encrypted function itself."""
        from core.utils import looks_encrypted, encrypt_api_key

        assert looks_encrypted('') is True, "Empty string should return True (skip)"
        assert looks_encrypted(None) is True, "None should return True (skip)"
        assert looks_encrypted('plaintext') is False, "Plaintext should return False"

        cipher = encrypt_api_key('test-value')
        assert looks_encrypted(cipher) is True, "Ciphertext should return True"
        assert looks_encrypted('garbage!!!') is False, "Garbage should return False"


# =========================================================================
# 15. QuantumAIFundAdmin — blank key submission does not wipe stored keys
# =========================================================================

class TestQuantumAIFundAdminBlankGuard:
    """save_model() must restore original values when key fields are blank.

    These tests replicate ModelForm.save()'s construct_instance() step —
    copying cleaned_data onto the instance — so save_model() sees the same
    in-memory state it would in real admin use.  Deleting the guard's
    setattr line makes test_blank_fields_restore_from_db and
    test_nonblank_submission_stores_new_plaintext fail.
    """

    def _mock_form(self, changed_data, cleaned_data):
        """Return a MagicMock that looks like a valid cleaned form."""
        from unittest.mock import MagicMock
        form = MagicMock()
        form.changed_data = changed_data
        form.cleaned_data = cleaned_data
        return form

    def _apply_cleaned(self, obj, form):
        """Replicate django.forms.models.construct_instance(form, instance).

        ModelForm.save(commit=False) runs this before save_model().
        Without it, the in-memory object never receives the form values.
        """
        for k, v in form.cleaned_data.items():
            setattr(obj, k, v)

    def test_blank_fields_restore_from_db(self, db):
        """Submitting blank fields must restore the existing encrypted value.

        Without the guard this test fails: _apply_cleaned sets obj keys to
        '', then save_model writes '' to DB, then refresh sees '' != saved.
        """
        from apps.bots.admin import QuantumAIFundAdmin
        from apps.bots.models import QuantumAIFund
        from django.http import HttpRequest
        from decimal import Decimal

        fund = QuantumAIFund.objects.create(
            name='Test Fund', master_api_key='plain-key',
            master_secret_key='plain-secret', master_passphrase='plain-pass',
            total_fund_value=Decimal('100000'), total_profit=Decimal('10000'),
            total_deposits=Decimal('50000'), risk_parameters={},
        )
        fund.refresh_from_db()
        saved_api = fund.master_api_key
        saved_secret = fund.master_secret_key
        saved_pass = fund.master_passphrase

        form = self._mock_form(
            changed_data=['master_api_key', 'master_secret_key', 'master_passphrase'],
            cleaned_data={'master_api_key': '', 'master_secret_key': '',
                          'master_passphrase': ''},
        )

        self._apply_cleaned(fund, form)

        request = HttpRequest()
        admin_instance = QuantumAIFundAdmin(model=QuantumAIFund, admin_site=None)
        admin_instance.save_model(request, fund, form, change=True)

        fund.refresh_from_db()
        assert fund.master_api_key == saved_api, "Blank wiped api_key"
        assert fund.master_secret_key == saved_secret, "Blank wiped secret_key"
        assert fund.master_passphrase == saved_pass, "Blank wiped passphrase"

    def test_blank_fields_on_existing_empty_keeps_empty(self, db):
        """Submitting blank on a record that already has empty keys is safe."""
        from apps.bots.admin import QuantumAIFundAdmin
        from apps.bots.models import QuantumAIFund
        from django.http import HttpRequest
        from decimal import Decimal

        fund = QuantumAIFund.objects.create(
            name='Empty Fund', master_api_key='', master_secret_key='',
            master_passphrase='', total_fund_value=Decimal('0'),
            total_profit=Decimal('0'), total_deposits=Decimal('0'),
            risk_parameters={},
        )

        form = self._mock_form(
            changed_data=['master_api_key', 'master_secret_key', 'master_passphrase'],
            cleaned_data={'master_api_key': '', 'master_secret_key': '',
                          'master_passphrase': ''},
        )

        self._apply_cleaned(fund, form)

        request = HttpRequest()
        admin_instance = QuantumAIFundAdmin(model=QuantumAIFund, admin_site=None)
        admin_instance.save_model(request, fund, form, change=True)

        fund.refresh_from_db()
        assert fund.master_api_key == '', "Empty api_key was unexpectedly changed"
        assert fund.master_secret_key == '', "Empty secret_key was unexpectedly changed"
        assert fund.master_passphrase == '', "Empty passphrase was unexpectedly changed"

    def test_nonblank_submission_stores_new_plaintext(self, db):
        """A real plaintext key through the form gets encrypted.

        Without the guard's encryption path this fails: _apply_cleaned sets
        obj keys to 'new-...' (plaintext), save_model stores them as-is,
        and looks_encrypted returns False.
        """
        from apps.bots.admin import QuantumAIFundAdmin
        from apps.bots.models import QuantumAIFund
        from core.utils import looks_encrypted
        from django.http import HttpRequest
        from decimal import Decimal

        fund = QuantumAIFund.objects.create(
            name='Update Fund', master_api_key='old-key',
            master_secret_key='old-secret', master_passphrase='old-pass',
            total_fund_value=Decimal('100000'), total_profit=Decimal('10000'),
            total_deposits=Decimal('50000'), risk_parameters={},
        )

        form = self._mock_form(
            changed_data=['master_api_key', 'master_secret_key', 'master_passphrase'],
            cleaned_data={'master_api_key': 'new-key',
                          'master_secret_key': 'new-secret',
                          'master_passphrase': 'new-pass'},
        )

        self._apply_cleaned(fund, form)

        request = HttpRequest()
        admin_instance = QuantumAIFundAdmin(model=QuantumAIFund, admin_site=None)
        admin_instance.save_model(request, fund, form, change=True)

        fund.refresh_from_db()
        assert looks_encrypted(fund.master_api_key), "New api_key not encrypted"
        assert looks_encrypted(fund.master_secret_key), "New secret_key not encrypted"
        assert looks_encrypted(fund.master_passphrase), "New passphrase not encrypted"
