import pytest
from django.urls import reverse
from rest_framework import status


@pytest.mark.django_db
class TestSignalBotWebhookView:
    def test_missing_bot_id(self, api_client):
        url = reverse('webhooks:signalbot_webhook')
        response = api_client.post(url, {'secret': 'test'}, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'bot_id' in str(response.data['error'])

    def test_missing_secret(self, api_client):
        url = reverse('webhooks:signalbot_webhook')
        response = api_client.post(url, {'bot_id': 'test-bot'}, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'secret' in str(response.data['error'])

    def test_invalid_bot_id_and_secret(self, api_client):
        url = reverse('webhooks:signalbot_webhook')
        response = api_client.post(url, {
            'bot_id': 'nonexistent-bot',
            'secret': 'wrong-secret',
            'side': 'buy',
            'Pair': 'BTC/USDT',
        }, format='json')
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert 'Invalid' in str(response.data['error'])

    def test_invalid_side(self, api_client):
        url = reverse('webhooks:signalbot_webhook')
        response = api_client.post(url, {
            'bot_id': 'test-bot',
            'secret': 'test-secret',
            'side': 'invalid_side',
            'Pair': 'BTC/USDT',
        }, format='json')
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_missing_pair(self, api_client):
        url = reverse('webhooks:signalbot_webhook')
        response = api_client.post(url, {
            'bot_id': 'test-bot',
            'secret': 'test-secret',
            'side': 'buy',
        }, format='json')
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestTradingViewWebhookView:
    def test_webhook_no_auth_required(self, api_client):
        url = reverse('webhooks:signalbot_webhook')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


@pytest.mark.django_db
class TestEMAIndicatorView:
    def test_ema_indicator_get(self, api_client):
        url = reverse('webhooks:ema_indicator')
        response = api_client.get(url, {'symbol': 'BTC/USDT', 'period': 20, 'timeframe': '1h'})
        assert response.status_code == status.HTTP_200_OK
        assert response.data['indicator'] == 'EMA'
        assert response.data['symbol'] == 'BTC/USDT'
        assert response.data['period'] == 20

    def test_ema_indicator_defaults(self, api_client):
        url = reverse('webhooks:ema_indicator')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['period'] == 20

    def test_ema_indicator_no_auth_required(self, api_client):
        url = reverse('webhooks:ema_indicator')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestRSIIndicatorView:
    def test_rsi_indicator_get(self, api_client):
        url = reverse('webhooks:rsi_indicator')
        response = api_client.get(url, {'symbol': 'BTC/USDT', 'period': 14, 'timeframe': '1h'})
        assert response.status_code == status.HTTP_200_OK
        assert response.data['indicator'] == 'RSI'
        assert response.data['symbol'] == 'BTC/USDT'
        assert response.data['period'] == 14

    def test_rsi_indicator_defaults(self, api_client):
        url = reverse('webhooks:rsi_indicator')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['period'] == 14

    def test_rsi_indicator_no_auth_required(self, api_client):
        url = reverse('webhooks:rsi_indicator')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
