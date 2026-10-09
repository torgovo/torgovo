"""
Tests for the TOTP 2FA service (services/two_factor.py) and the
authentication 2FA endpoints (setup/confirm/disable).

Covers S-3: the withdrawal gate now verifies a REAL TOTP code against the
user's stored secret instead of only checking code presence/length.
"""

import pytest
from django.urls import reverse
from rest_framework import status

from services.two_factor import (
    build_otpauth_uri,
    decrypt_totp_secret,
    encrypt_totp_secret,
    generate_totp_secret,
    verify_totp_code,
)

TEST_SECRET = "JBSWY3DPEHPK3PXP"  # fixed base32 secret for deterministic tests
TEST_SECRET2 = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"


@pytest.mark.django_db
class TestTwoFactorService:
    def test_generate_totp_secret_is_cspmrg_base32(self):
        """Secret is CSPRNG-generated, valid base32, and unique per call."""
        a = generate_totp_secret()
        b = generate_totp_secret()
        assert a != b
        assert len(a) == 32  # 20 bytes -> 32 base32 chars
        import base64

        base64.b32decode(a + "=" * ((8 - len(a) % 8) % 8))  # must not raise

    def test_verify_totp_code_valid_and_invalid(self):
        """A generated code verifies; garbage and empty codes do not."""
        code = _totp_code(TEST_SECRET)
        assert verify_totp_code(TEST_SECRET, code) is True
        assert verify_totp_code(TEST_SECRET, "000000") is False
        assert verify_totp_code(TEST_SECRET, "") is False
        assert verify_totp_code(TEST_SECRET, None) is False

    def test_verify_totp_code_window_accepts_drift(self):
        """A code one step in the past still verifies within the window."""
        now = 1_700_000_000
        code_minus_1 = _totp_code_at(TEST_SECRET, now - 30)
        assert verify_totp_code(TEST_SECRET, code_minus_1, window=1, now=now) is True
        far_past = _totp_code_at(TEST_SECRET, now - 120)
        assert verify_totp_code(TEST_SECRET, far_past, window=1, now=now) is False

    def test_encrypt_decrypt_roundtrip(self):
        """Fernet round-trip returns the original secret through the service."""
        encrypted = encrypt_totp_secret(TEST_SECRET)
        assert encrypted != TEST_SECRET
        assert decrypt_totp_secret(encrypted) == TEST_SECRET
        assert decrypt_totp_secret("") is None
        assert decrypt_totp_secret("garbage:not.fernet") is None

    @pytest.mark.parametrize(
        "secret,code,expected",
        [
            (TEST_SECRET, "000000", False),
            (TEST_SECRET, "abcdef", False),  # non-numeric
            (TEST_SECRET2, "000000", False),  # different secret never matches
        ],
    )
    def test_wrong_inputs_rejected(self, secret, code, expected):
        assert verify_totp_code(secret, code) is expected

    def test_build_otpauth_uri_contains_issuer_and_secret(self):
        uri = build_otpauth_uri(TEST_SECRET, "testuser")
        assert uri.startswith("otpauth://totp/")
        assert "issuer=Torgovo2" in uri
        assert TEST_SECRET in uri
        assert "testuser" in uri


def _totp_code(secret_b32, now=None):
    """Current-step TOTP code for a secret (mirrors service internals)."""
    import time

    from services.two_factor import _totp_code as impl

    return impl(secret_b32, int(now if now is not None else time.time()) // 30)


def _totp_code_at(secret_b32, epoch_now):
    from services.two_factor import _totp_code as impl

    return impl(secret_b32, epoch_now // 30)


@pytest.mark.django_db
class TestTwoFactorEndpoints:
    def test_setup_requires_password(self, auth_client):
        url = reverse("auth:two-fa-setup")
        resp = auth_client.post(url, {}, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_setup_wrong_password(self, auth_client):
        url = reverse("auth:two-fa-setup")
        resp = auth_client.post(url, {"password": "wrongpass"}, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_setup_returns_secret_and_uri(self, auth_client, user):
        url = reverse("auth:two-fa-setup")
        resp = auth_client.post(url, {"password": "testpass123"}, format="json")
        assert resp.status_code == status.HTTP_200_OK
        secret = resp.data["secret"]
        assert len(secret) == 32
        assert resp.data["otpauth_uri"].startswith("otpauth://totp/")
        # server stored the ENCRYPTED secret, never the plaintext
        user.refresh_from_db()
        assert user.totp_secret != ""
        assert user.totp_secret != secret
        assert decrypt_totp_secret(user.totp_secret) == secret
        # still disabled until confirmed
        assert user.two_factor_enabled is False

    def test_confirm_enables_2fa_with_valid_code(self, auth_client, user):
        # provision first
        resp = auth_client.post(
            reverse("auth:two-fa-setup"), {"password": "testpass123"}, format="json"
        )
        secret = resp.data["secret"]
        code = _totp_code(secret)
        resp = auth_client.post(reverse("auth:two-fa-confirm"), {"code": code}, format="json")
        assert resp.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        assert user.two_factor_enabled is True

    def test_confirm_rejects_bad_code(self, auth_client, user):
        auth_client.post(reverse("auth:two-fa-setup"), {"password": "testpass123"}, format="json")
        resp = auth_client.post(reverse("auth:two-fa-confirm"), {"code": "000000"}, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        user.refresh_from_db()
        assert user.two_factor_enabled is False

    def test_confirm_without_setup_rejected(self, auth_client, user):
        resp = auth_client.post(reverse("auth:two-fa-confirm"), {"code": "123456"}, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_disable_requires_password_and_code(self, auth_client, user):
        # enable via direct store (fast-path) then disable with wrong password
        user.two_factor_enabled = True
        user.totp_secret = encrypt_totp_secret(TEST_SECRET)
        user.save()
        resp = auth_client.post(
            reverse("auth:two-fa-disable"),
            {"password": "wrong", "code": "000000"},
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        user.refresh_from_db()
        assert user.two_factor_enabled is True  # still enabled

    def test_disable_with_valid_credentials(self, auth_client, user):
        user.two_factor_enabled = True
        user.totp_secret = encrypt_totp_secret(TEST_SECRET)
        user.save()
        resp = auth_client.post(
            reverse("auth:two-fa-disable"),
            {"password": "testpass123", "code": _totp_code(TEST_SECRET)},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        assert user.two_factor_enabled is False
        assert user.totp_secret == ""

    def test_endpoints_require_auth(self, api_client):
        auth_urls = (
            reverse("auth:two-fa-setup"),
            reverse("auth:two-fa-confirm"),
            reverse("auth:two-fa-disable"),
        )
        for url in auth_urls:
            resp = api_client.post(url, {}, format="json")
            assert resp.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
