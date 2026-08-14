import pytest

from apps.webhooks.models import WebhookLog


@pytest.mark.django_db
class TestWebhookLogModel:
    def test_create_webhook_log(self, user):
        log = WebhookLog.objects.create(
            user=user,
            webhook_id="wh_test_001",
            ip_address="192.168.1.1",
            user_agent="TradingView/1.0",
            payload={"action": "buy", "Pair": "BTC/USDT"},
            response_status=200,
            response_body='{"success": true}',
            processing_time_ms=150,
            is_successful=True,
        )
        assert log.user == user
        assert log.webhook_id == "wh_test_001"
        assert log.ip_address == "192.168.1.1"
        assert log.payload == {"action": "buy", "Pair": "BTC/USDT"}
        assert log.response_status == 200
        assert log.is_successful is True
        assert log.processing_time_ms == 150

    def test_create_log_without_user(self, db):
        log = WebhookLog.objects.create(
            ip_address="10.0.0.1",
            payload={"test": True},
            is_successful=False,
            error_message="Connection timeout",
        )
        assert log.user is None
        assert log.is_successful is False
        assert log.error_message == "Connection timeout"
        assert log.response_status is None

    def test_default_values(self, db):
        log = WebhookLog.objects.create(
            ip_address="127.0.0.1",
            payload={},
        )
        assert log.is_successful is False
        assert log.processing_time_ms is None
        assert log.webhook_id == ""
        assert log.user_agent == ""
        assert log.response_body == ""
        assert log.error_message == ""

    def test_failed_webhook_log(self, user):
        log = WebhookLog.objects.create(
            user=user,
            webhook_id="wh_failed_001",
            ip_address="192.168.1.100",
            payload={"action": "sell", "Pair": "ETH/USDT"},
            response_status=500,
            response_body="Internal server error",
            processing_time_ms=2500,
            is_successful=False,
            error_message="ccxt exchange error: Invalid API key",
        )
        assert log.is_successful is False
        assert log.error_message == "ccxt exchange error: Invalid API key"

    def test_payload_json_field(self, db):
        complex_payload = {
            "action": "buy",
            "Pair": "BTC/USDT",
            "order": {
                "amount": 0.001,
                "type": "market",
            },
            "strategy": {
                "name": "EMA Cross",
                "params": {"fast": 9, "slow": 21},
            },
        }
        log = WebhookLog.objects.create(
            ip_address="10.0.0.50",
            payload=complex_payload,
            is_successful=True,
        )
        assert log.payload["action"] == "buy"
        assert log.payload["strategy"]["name"] == "EMA Cross"
