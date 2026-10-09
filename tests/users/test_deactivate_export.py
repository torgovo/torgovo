"""
Tests for user-facing GDPR account endpoints:
- POST /api/users/deactivate/  (right to erasure -> account deactivation)
- GET  /api/users/export-data/ (right to data access/portability)
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from apps.bots.models import GridBot, SignalBot
from apps.exchanges.models import ExchangeCredentials
from apps.users.models import UserBalance
from core.models import AuditLog, UserActivityLog

User = get_user_model()

DEACTIVATE_URL = "/api/users/deactivate/"
EXPORT_URL = "/api/users/export-data/"


def make_refresh_token(user):
    """Create a real OutstandingToken/refresh for the user (later blacklisted)."""
    return RefreshToken.for_user(user)


# ---------------------------------------------------------------------------
# Deactivate account
# ---------------------------------------------------------------------------


class TestDeactivateAccount:
    def test_deactivate_with_correct_password(self, auth_client, user):
        response = auth_client.post(DEACTIVATE_URL, {"password": "testpass123"})
        assert response.status_code == status.HTTP_200_OK
        assert response.data["detail"]
        user.refresh_from_db()
        assert user.is_active is False

    def test_deactivate_revokes_outstanding_refresh_tokens(self, auth_client, user):
        # Mint two real refresh tokens so they are registered in the blacklist app.
        token1 = make_refresh_token(user)
        token2 = make_refresh_token(user)

        response = auth_client.post(DEACTIVATE_URL, {"password": "testpass123"})
        assert response.status_code == status.HTTP_200_OK
        assert response.data["sessions_revoked"] == 2

        # Both previously-valid refresh tokens must now be blacklisted.
        from rest_framework_simplejwt.token_blacklist.models import (
            BlacklistedToken,
            OutstandingToken,
        )

        outstanding = list(OutstandingToken.objects.filter(user=user))
        assert len(outstanding) == 2
        assert all(BlacklistedToken.objects.filter(token=ot).exists() for ot in outstanding)
        assert {ot.jti for ot in outstanding} == {token1["jti"], token2["jti"]}

    def test_deactivate_blocks_reuse_of_old_refresh(self, auth_client, user):
        token = make_refresh_token(user)
        auth_client.post(DEACTIVATE_URL, {"password": "testpass123"})

        # The old refresh token must now be rejected (blacklisted).
        from rest_framework_simplejwt.exceptions import TokenError

        refresh = RefreshToken(str(token), verify=False)
        with pytest.raises(TokenError):
            refresh.check_blacklist()

    def test_deactivate_wrong_password_rejected(self, auth_client, user):
        response = auth_client.post(DEACTIVATE_URL, {"password": "wrongpassword"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        user.refresh_from_db()
        assert user.is_active is True

    def test_deactivate_missing_password_rejected(self, auth_client, user):
        response = auth_client.post(DEACTIVATE_URL, {})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        user.refresh_from_db()
        assert user.is_active is True

    def test_deactivate_already_inactive_rejected(self, user):
        user.is_active = False
        user.save()

        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=user)
        response = client.post(DEACTIVATE_URL, {"password": "testpass123"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_deactivate_requires_authentication(self, api_client):
        response = api_client.post(DEACTIVATE_URL, {"password": "testpass123"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_deactivate_writes_audit_and_activity_logs(self, auth_client, user):
        auth_client.post(DEACTIVATE_URL, {"password": "testpass123"})
        assert AuditLog.objects.filter(user=user, resource_type="user_account").exists()
        assert UserActivityLog.objects.filter(user=user, action="account_deactivated").exists()

    def test_deactivated_user_cannot_login(self, api_client, user):
        api_client.login(username=user.username, password="testpass123")

        from rest_framework.test import APIClient

        authenticated = APIClient()
        authenticated.force_authenticate(user=user)
        authenticated.post(DEACTIVATE_URL, {"password": "testpass123"})

        api_client2 = APIClient()
        ok = api_client2.login(username=user.username, password="testpass123")
        assert ok is False


# ---------------------------------------------------------------------------
# Data export
# ---------------------------------------------------------------------------


def seed_export_data(user):
    """Create one row of every major data type the export should include."""
    SignalBot.objects.create(
        user=user,
        bot_name="My Signal",
        exchange_name="binance",
        trading_pair="BTC/USDT",
        default_amount=10,
    )
    GridBot.objects.create(
        user=user,
        bot_name="My Grid",
        exchange_name="binance",
        trading_pair="BTC/USDT",
        initial_amount=100,
        base_amount=1,
        favor_levels=10,
        against_levels=5,
    )
    UserBalance.objects.create(user=user, available=1000, hold=0, currency="USDT")
    ExchangeCredentials.objects.create(
        user=user,
        exchange_name="binance",
        api_key="supersecretapikey1234567890",
        secret_key="supersecretsecretkey1234567890",
    )


class TestUserDataExport:
    def test_export_returns_profile(self, auth_client, user):
        response = auth_client.get(EXPORT_URL)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["profile"]["email"] == "test@example.com"
        assert response.data["profile"]["username"] == "testuser"

    def test_export_includes_all_sections(self, auth_client, user):
        seed_export_data(user)
        response = auth_client.get(EXPORT_URL)
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        # Top-level sections all present.
        for section in [
            "profile",
            "balances",
            "exchange_credentials",
            "bots",
            "quantum_ai",
            "orders",
            "payments",
            "subscriptions",
            "referrals",
            "activity_logs",
        ]:
            assert section in data
        # Seeded rows appear.
        assert len(data["bots"]["signal_bots"]) == 1
        assert len(data["bots"]["grid_bots"]) == 1
        assert len(data["balances"]) == 1
        assert len(data["exchange_credentials"]) == 1

    def test_export_masks_exchange_credentials(self, auth_client, user):
        seed_export_data(user)
        response = auth_client.get(EXPORT_URL)
        cred = response.data["exchange_credentials"][0]
        # Raw secrets never appear; masked form keeps only identification fragments.
        assert "supersecretapikey1234567890" not in cred["api_key"]
        assert "supersecretsecretkey1234567890" not in cred["secret_key"]
        assert cred["api_key"] == "supe...7890"
        assert cred["secret_key"] == "supe...7890"

    def test_export_excludes_soft_deleted_rows(self, auth_client, user):
        bot = SignalBot.objects.create(
            user=user,
            bot_name="Gone",
            exchange_name="binance",
            trading_pair="ETH/USDT",
            default_amount=5,
        )
        bot.is_deleted = True
        bot.deleted_at = None
        bot.save()
        response = auth_client.get(EXPORT_URL)
        assert response.data["bots"]["signal_bots"] == []

    def test_export_scoped_to_requester_only(self, auth_client, user, second_user):
        # second_user's data must never leak into this user's export.
        SignalBot.objects.create(
            user=second_user,
            bot_name="Other User Bot",
            exchange_name="binance",
            trading_pair="BTC/USDT",
            default_amount=1,
        )
        response = auth_client.get(EXPORT_URL)
        assert response.data["bots"]["signal_bots"] == []
        assert response.data["profile"]["email"] == "test@example.com"

    def test_export_requires_authentication(self, api_client):
        response = api_client.get(EXPORT_URL)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_export_empty_user_returns_empty_sections(self, auth_client, user):
        response = auth_client.get(EXPORT_URL)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["balances"] == []
        assert response.data["bots"]["signal_bots"] == []
        assert response.data["payments"]["payment_transactions"] == []
