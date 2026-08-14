import hashlib
import hmac
import json
import time
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
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
class TestFullWebhookFlow:
    def test_valid_signature_executes_trade_updates_stats(
        self, api_client, signal_bot, exchange_credentials
    ):
        url = reverse("webhooks:signalbot_webhook")
        payload = _build_payload(bot_id=signal_bot.bot_id)
        sig = _sign(payload, signal_bot.secret_key)

        with patch("apps.webhooks.views.SignalBotWebhookView.execute_trade") as mock_execute:
            mock_execute.return_value = {
                "status": "success",
                "order_id": "order-123",
                "timestamp": 1234567890000,
                "amount": 0.001,
                "price": 50000.0,
                "cost": 50.0,
                "exchange": "binance",
            }
            resp = api_client.post(url, payload, format="json", HTTP_X_SIGNATURE=sig)

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["success"] is True
        assert resp.data["trade_details"]["order_id"] == "order-123"

        signal_bot.refresh_from_db()
        assert signal_bot.total_trades == 1
        assert signal_bot.signals_used_this_month == 1

    def test_subscribed_user_bypasses_signal_limit(
        self, api_client, signal_bot, signal_bot_subscription, exchange_credentials
    ):
        signal_bot.subscription = signal_bot_subscription
        signal_bot.signals_used_this_month = 9999
        signal_bot.save()

        url = reverse("webhooks:signalbot_webhook")
        payload = _build_payload(bot_id=signal_bot.bot_id, side="sell")
        sig = _sign(payload, signal_bot.secret_key)

        with patch("apps.webhooks.views.SignalBotWebhookView.execute_trade") as mock_execute:
            mock_execute.return_value = {"status": "success", "order_id": "o-1"}
            resp = api_client.post(url, payload, format="json", HTTP_X_SIGNATURE=sig)

        assert resp.status_code == status.HTTP_200_OK
        signal_bot.refresh_from_db()
        assert signal_bot.total_trades == 1

    def test_sell_side_trade_executes_successfully(
        self, api_client, signal_bot, exchange_credentials
    ):
        url = reverse("webhooks:signalbot_webhook")
        payload = _build_payload(bot_id=signal_bot.bot_id, side="sell")
        sig = _sign(payload, signal_bot.secret_key)

        with patch("apps.webhooks.views.SignalBotWebhookView.execute_trade") as mock_execute:
            mock_execute.return_value = {
                "status": "success",
                "order_id": "sell-456",
                "amount": 0.001,
                "price": 50000.0,
                "cost": 50.0,
                "exchange": "binance",
            }
            resp = api_client.post(url, payload, format="json", HTTP_X_SIGNATURE=sig)

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["trade_details"]["order_id"] == "sell-456"

    def test_consecutive_trades_increment_stats(self, api_client, signal_bot, exchange_credentials):
        url = reverse("webhooks:signalbot_webhook")

        for i in range(3):
            payload = _build_payload(bot_id=signal_bot.bot_id, order_id=f"order-{i}")
            sig = _sign(payload, signal_bot.secret_key)
            with patch("apps.webhooks.views.SignalBotWebhookView.execute_trade") as mock_execute:
                mock_execute.return_value = {"status": "success", "order_id": f"o-{i}"}
                resp = api_client.post(url, payload, format="json", HTTP_X_SIGNATURE=sig)
            assert resp.status_code == status.HTTP_200_OK

        signal_bot.refresh_from_db()
        assert signal_bot.total_trades == 3
        assert signal_bot.signals_used_this_month == 3

    def test_trade_updates_last_triggered(self, api_client, signal_bot, exchange_credentials):
        url = reverse("webhooks:signalbot_webhook")
        payload = _build_payload(bot_id=signal_bot.bot_id)
        sig = _sign(payload, signal_bot.secret_key)

        with patch("apps.webhooks.views.SignalBotWebhookView.execute_trade") as mock_execute:
            mock_execute.return_value = {"status": "success", "order_id": "o-1"}
            api_client.post(url, payload, format="json", HTTP_X_SIGNATURE=sig)

        signal_bot.refresh_from_db()
        assert signal_bot.last_triggered is not None


@pytest.mark.django_db
class TestWebhookErrorFlow:
    def test_invalid_signature_returns_403(self, api_client, signal_bot):
        url = reverse("webhooks:signalbot_webhook")
        payload = _build_payload(bot_id=signal_bot.bot_id)
        resp = api_client.post(url, payload, format="json", HTTP_X_SIGNATURE="deadbeef")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_missing_bot_id_returns_400(self, api_client):
        url = reverse("webhooks:signalbot_webhook")
        resp = api_client.post(url, {"side": "buy"}, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "bot_id" in str(resp.data.get("error", ""))

    def test_missing_side_returns_400(self, api_client, signal_bot):
        url = reverse("webhooks:signalbot_webhook")
        payload = {
            "bot_id": signal_bot.bot_id,
            "Pair": "BTC/USDT",
            "timestamp": str(int(time.time() * 1000)),
        }
        sig = _sign(payload, signal_bot.secret_key)
        resp = api_client.post(url, payload, format="json", HTTP_X_SIGNATURE=sig)
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_missing_pair_returns_400(self, api_client, signal_bot):
        signal_bot.trading_pair = ""
        signal_bot.save()
        url = reverse("webhooks:signalbot_webhook")
        payload = {
            "bot_id": signal_bot.bot_id,
            "side": "buy",
            "timestamp": str(int(time.time() * 1000)),
        }
        sig = _sign(payload, signal_bot.secret_key)
        resp = api_client.post(url, payload, format="json", HTTP_X_SIGNATURE=sig)
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_missing_timestamp_returns_400(self, api_client, signal_bot):
        url = reverse("webhooks:signalbot_webhook")
        payload = {"bot_id": signal_bot.bot_id, "side": "buy", "Pair": "BTC/USDT"}
        sig = _sign(payload, signal_bot.secret_key)
        resp = api_client.post(url, payload, format="json", HTTP_X_SIGNATURE=sig)
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_inactive_bot_returns_403(self, api_client, signal_bot):
        signal_bot.is_active = False
        signal_bot.save()
        url = reverse("webhooks:signalbot_webhook")
        payload = _build_payload(bot_id=signal_bot.bot_id)
        sig = _sign(payload, signal_bot.secret_key)
        resp = api_client.post(url, payload, format="json", HTTP_X_SIGNATURE=sig)
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_invalid_bot_id_returns_403(self, api_client):
        url = reverse("webhooks:signalbot_webhook")
        payload = _build_payload(bot_id="nonexistent-bot")
        sig = _sign(payload, "some-secret")
        resp = api_client.post(url, payload, format="json", HTTP_X_SIGNATURE=sig)
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_expired_timestamp_returns_400(self, api_client, signal_bot):
        url = reverse("webhooks:signalbot_webhook")
        old_ts = str(int((time.time() - 300) * 1000))
        payload = _build_payload(bot_id=signal_bot.bot_id, timestamp=old_ts)
        sig = _sign(payload, signal_bot.secret_key)
        resp = api_client.post(url, payload, format="json", HTTP_X_SIGNATURE=sig)
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_missing_x_signature_returns_401(self, api_client, signal_bot):
        url = reverse("webhooks:signalbot_webhook")
        payload = _build_payload(bot_id=signal_bot.bot_id)
        resp = api_client.post(url, payload, format="json")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestWebhookRateLimiting:
    def test_too_many_failures_returns_429(self, api_client, signal_bot):
        url = reverse("webhooks:signalbot_webhook")
        payload = _build_payload(bot_id=signal_bot.bot_id)
        for _ in range(6):
            resp = api_client.post(url, payload, format="json")

        assert resp.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert "Too many" in str(resp.data.get("error", ""))

    def test_failure_count_resets_after_window(self, api_client, signal_bot):
        url = reverse("webhooks:signalbot_webhook")
        payload = _build_payload(bot_id=signal_bot.bot_id)
        for _ in range(4):
            api_client.post(url, payload, format="json")

        from django.core.cache import cache

        key = f"webhook:fail:{signal_bot.bot_id}"
        current = cache.get(key, 0)
        assert current == 4

    def test_different_bot_not_blocked_by_another_bot_failures(self, api_client, signal_bot):
        url = reverse("webhooks:signalbot_webhook")
        p1 = _build_payload(bot_id=signal_bot.bot_id)
        p2 = _build_payload(bot_id="other-bot")
        for _ in range(5):
            api_client.post(url, p1, format="json")
        resp = api_client.post(url, p2, format="json")
        assert resp.status_code != status.HTTP_429_TOO_MANY_REQUESTS

    def test_valid_trade_does_not_count_as_failure(
        self, api_client, signal_bot, exchange_credentials
    ):
        url = reverse("webhooks:signalbot_webhook")
        payload = _build_payload(bot_id=signal_bot.bot_id)
        sig = _sign(payload, signal_bot.secret_key)

        for _ in range(4):
            with patch("apps.webhooks.views.SignalBotWebhookView.execute_trade") as mock_execute:
                mock_execute.return_value = {"status": "success", "order_id": "o-1"}
                resp = api_client.post(url, payload, format="json", HTTP_X_SIGNATURE=sig)
            assert resp.status_code == status.HTTP_200_OK

        from django.core.cache import cache

        fail_key = f"webhook:fail:{signal_bot.bot_id}"
        assert cache.get(fail_key, 0) == 0

    def test_free_user_blocked_at_signal_limit(self, api_client, signal_bot, exchange_credentials):
        signal_bot.signal_limit = 1
        signal_bot.signals_used_this_month = 1
        signal_bot.subscription = None
        signal_bot.save()

        url = reverse("webhooks:signalbot_webhook")
        payload = _build_payload(bot_id=signal_bot.bot_id)
        sig = _sign(payload, signal_bot.secret_key)

        with patch("apps.webhooks.views.SignalBotWebhookView.execute_trade") as mock_execute:
            mock_execute.return_value = {"status": "success", "order_id": "o-1"}
            resp = api_client.post(url, payload, format="json", HTTP_X_SIGNATURE=sig)

        assert resp.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert "signal limit" in str(resp.data.get("error", "")).lower()
