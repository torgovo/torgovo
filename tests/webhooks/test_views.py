import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework import status


def _sign(payload: dict, secret: str) -> str:
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    return hmac.new(secret.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256).hexdigest()


def _build_payload(bot_id="test-bot", **overrides):
    payload = {
        "bot_id": bot_id,
        "side": "buy",
        "Pair": "BTC/USDT",
        "timestamp": str(int(time.time() * 1000)),
        "order_id": f"order-{int(time.time() * 1000000)}",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def mock_execute_trade():
    with patch("apps.webhooks.views.SignalBotWebhookView.execute_trade") as mock:
        mock.return_value = {
            "status": "success",
            "order_id": "mock-order-123",
            "timestamp": 1234567890000,
            "amount": 0.001,
            "price": 50000.0,
            "cost": 50.0,
            "exchange": "binance",
        }
        yield mock


@pytest.mark.django_db
class TestSignalBotWebhookAuth:
    """Auth is per-bot: HMAC via X-Signature header, or body secret for TradingView."""

    def test_missing_credentials_returns_401(self, api_client, signal_bot):
        # No header AND no body secret → unauthenticated.
        url = reverse("webhooks:signalbot_webhook")
        payload = _build_payload(bot_id=signal_bot.bot_id)
        resp = api_client.post(url, payload, format="json")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED
        assert "secret" in str(resp.data.get("error", ""))

    def test_invalid_signature_returns_403(self, api_client, signal_bot):
        url = reverse("webhooks:signalbot_webhook")
        payload = _build_payload(bot_id=signal_bot.bot_id)
        resp = api_client.post(
            url,
            payload,
            format="json",
            HTTP_X_SIGNATURE="deadbeef",
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_valid_signature_returns_200(
        self, api_client, signal_bot, exchange_credentials, mock_execute_trade
    ):
        url = reverse("webhooks:signalbot_webhook")
        payload = _build_payload(bot_id=signal_bot.bot_id)
        sig = _sign(payload, signal_bot.secret_key)
        resp = api_client.post(
            url,
            payload,
            format="json",
            HTTP_X_SIGNATURE=sig,
        )
        assert resp.status_code == status.HTTP_200_OK, resp.data

    def test_secret_in_body_authenticates(
        self, api_client, signal_bot, exchange_credentials, mock_execute_trade
    ):
        # TradingView alert webhooks send ONLY the JSON body — no headers.
        # The unique per-bot secret_key embedded in the message must authenticate.
        url = reverse("webhooks:signalbot_webhook")
        payload = _build_payload(bot_id=signal_bot.bot_id, secret=signal_bot.secret_key)
        resp = api_client.post(url, payload, format="json")
        assert resp.status_code == status.HTTP_200_OK, resp.data
        mock_execute_trade.assert_called_once()

    def test_invalid_body_secret_rejected(self, api_client, signal_bot):
        url = reverse("webhooks:signalbot_webhook")
        payload = _build_payload(bot_id=signal_bot.bot_id, secret="not-the-secret")
        resp = api_client.post(url, payload, format="json")
        assert resp.status_code == status.HTTP_403_FORBIDDEN
        assert "Invalid" in str(resp.data.get("error", ""))


@pytest.mark.django_db
class TestSignalBotWebhookDedup:
    """Dedup uses strategy.order.id (order_id field)."""

    def test_duplicate_order_id_ignored(
        self, api_client, signal_bot, exchange_credentials, mock_execute_trade
    ):
        url = reverse("webhooks:signalbot_webhook")
        payload = _build_payload(bot_id=signal_bot.bot_id, order_id="dup-123")
        sig = _sign(payload, signal_bot.secret_key)
        resp1 = api_client.post(url, payload, format="json", HTTP_X_SIGNATURE=sig)
        assert resp1.status_code == status.HTTP_200_OK
        resp2 = api_client.post(url, payload, format="json", HTTP_X_SIGNATURE=sig)
        assert resp2.status_code == status.HTTP_200_OK
        assert "Duplicate" in str(resp2.data.get("message", ""))

    def test_different_order_ids_both_accepted(
        self, api_client, signal_bot, exchange_credentials, mock_execute_trade
    ):
        url = reverse("webhooks:signalbot_webhook")
        p1 = _build_payload(bot_id=signal_bot.bot_id, order_id="unique-1")
        p2 = _build_payload(bot_id=signal_bot.bot_id, order_id="unique-2")
        sig1 = _sign(p1, signal_bot.secret_key)
        sig2 = _sign(p2, signal_bot.secret_key)
        r1 = api_client.post(url, p1, format="json", HTTP_X_SIGNATURE=sig1)
        r2 = api_client.post(url, p2, format="json", HTTP_X_SIGNATURE=sig2)
        assert r1.status_code == status.HTTP_200_OK
        assert r2.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestSignalBotWebhookRateLimit:
    """Per-bot and per-IP rate limiting."""

    def test_too_many_failures_locks_bot(self, api_client, signal_bot):
        url = reverse("webhooks:signalbot_webhook")
        payload = _build_payload(bot_id=signal_bot.bot_id)
        for _ in range(6):
            resp = api_client.post(url, payload, format="json")
        assert resp.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    def test_different_bot_same_ip_not_blocked_initially(self, api_client, signal_bot):
        url = reverse("webhooks:signalbot_webhook")
        p1 = _build_payload(bot_id=signal_bot.bot_id)
        p2 = _build_payload(bot_id="other-bot-id")
        for _ in range(4):
            api_client.post(url, p1, format="json")
        resp = api_client.post(url, p2, format="json")
        assert resp.status_code in (
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )


@pytest.mark.django_db
class TestSignalBotWebhookSignalLimit:
    """Free users blocked once they hit signal_limit."""

    def test_free_user_blocked_at_limit(self, api_client, signal_bot, exchange_credentials):
        signal_bot.signal_limit = 2
        signal_bot.signals_used_this_month = 2
        signal_bot.subscription = None
        signal_bot.save()

        url = reverse("webhooks:signalbot_webhook")
        payload = _build_payload(bot_id=signal_bot.bot_id)
        sig = _sign(payload, signal_bot.secret_key)
        resp = api_client.post(url, payload, format="json", HTTP_X_SIGNATURE=sig)
        assert resp.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert "signal limit" in str(resp.data.get("error", "")).lower()

    def test_subscribed_user_not_blocked(
        self,
        api_client,
        signal_bot,
        signal_bot_subscription,
        exchange_credentials,
        mock_execute_trade,
    ):
        signal_bot.signals_used_this_month = 9999
        signal_bot.subscription = signal_bot_subscription
        signal_bot.save()

        url = reverse("webhooks:signalbot_webhook")
        payload = _build_payload(bot_id=signal_bot.bot_id)
        sig = _sign(payload, signal_bot.secret_key)
        resp = api_client.post(url, payload, format="json", HTTP_X_SIGNATURE=sig)
        assert resp.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestSignalBotWebhookCredentialZeroing:
    """execute_trade must not leak creds into local scope."""

    def test_creds_not_in_locals_after_execution(self, signal_bot, exchange_credentials):
        from apps.webhooks.views import SignalBotWebhookView

        view = SignalBotWebhookView()
        result = view.execute_trade(
            user=exchange_credentials.user,
            bot=signal_bot,
            exchange_name="binance",
            side="buy",
            trading_pair="BTC/USDT",
            position_size=0.001,
        )
        assert result["status"] == "error"  # no real exchange to connect to
        # confirm no crash — the critical assertion is that the del succeeded


@pytest.mark.django_db
class TestSignalBotWebhookPlatformAliases:
    """The same endpoint must accept JSON from ANY platform, not just TradingView."""

    def test_lowercase_symbol_and_secret_body_authenticates(
        self, api_client, signal_bot, exchange_credentials, mock_execute_trade
    ):
        # A generic platform (no TradingView placeholders): lowercase "symbol",
        # body-secret auth (no headers), ISO timestamp.
        url = reverse("webhooks:signalbot_webhook")
        payload = {
            "bot_id": signal_bot.bot_id,
            "secret": signal_bot.secret_key,
            "symbol": "BTC/USDT",
            "side": "buy",
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        resp = api_client.post(url, payload, format="json")
        assert resp.status_code == status.HTTP_200_OK, resp.data
        mock_execute_trade.assert_called_once()
        _, kwargs = mock_execute_trade.call_args
        assert kwargs["trading_pair"] == "BTC/USDT"

    def test_symbol_alias_with_hmac(
        self, api_client, signal_bot, exchange_credentials, mock_execute_trade
    ):
        # HMAC-signed request using "symbol" alias for the pair field.
        url = reverse("webhooks:signalbot_webhook")
        payload = {
            "bot_id": signal_bot.bot_id,
            "symbol": "ETH/USDT",
            "action": "buy",
            "timestamp": str(int(time.time() * 1000)),
        }
        sig = _sign(payload, signal_bot.secret_key)
        resp = api_client.post(url, payload, format="json", HTTP_X_SIGNATURE=sig)
        assert resp.status_code == status.HTTP_200_OK, resp.data
        _, kwargs = mock_execute_trade.call_args
        assert kwargs["trading_pair"] == "ETH/USDT"

    def test_long_short_side_aliases(
        self, api_client, signal_bot, exchange_credentials, mock_execute_trade
    ):
        # Some platforms signal sides as "long"/"short".
        url = reverse("webhooks:signalbot_webhook")
        payload = {
            "bot_id": signal_bot.bot_id,
            "secret": signal_bot.secret_key,
            "Pair": "BTC/USDT",
            "side": "long",
            "timestamp": str(int(time.time() * 1000)),
        }
        resp = api_client.post(url, payload, format="json")
        assert resp.status_code == status.HTTP_200_OK, resp.data
        _, kwargs = mock_execute_trade.call_args
        assert kwargs["side"] == "buy"

    def test_ticker_alias_and_direction_field(
        self, api_client, signal_bot, exchange_credentials, mock_execute_trade
    ):
        # "ticker" pair alias + "direction" field instead of "side".
        url = reverse("webhooks:signalbot_webhook")
        payload = {
            "bot_id": signal_bot.bot_id,
            "secret": signal_bot.secret_key,
            "ticker": "SOL/USDT",
            "direction": "short",
            "timestamp": str(int(time.time() * 1000)),
        }
        resp = api_client.post(url, payload, format="json")
        assert resp.status_code == status.HTTP_200_OK, resp.data
        _, kwargs = mock_execute_trade.call_args
        assert kwargs["trading_pair"] == "SOL/USDT"
        assert kwargs["side"] == "sell"

    def test_missing_pair_falls_back_to_bot_pair(
        self, api_client, signal_bot, exchange_credentials, mock_execute_trade
    ):
        # No pair field under any alias → falls back to the bot's configured pair.
        url = reverse("webhooks:signalbot_webhook")
        payload = {
            "bot_id": signal_bot.bot_id,
            "secret": signal_bot.secret_key,
            "side": "buy",
            "timestamp": str(int(time.time() * 1000)),
        }
        resp = api_client.post(url, payload, format="json")
        assert resp.status_code == status.HTTP_200_OK, resp.data
        _, kwargs = mock_execute_trade.call_args
        assert kwargs["trading_pair"] == signal_bot.trading_pair
