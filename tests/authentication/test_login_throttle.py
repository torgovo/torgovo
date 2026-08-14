"""Tests for the improved login throttle: (email, IP /24, user_agent_hash)."""

import pytest
from django.urls import reverse
from rest_framework import status


@pytest.mark.django_db
class TestLoginThrottleIPPrefix:
    """Lockout uses /24 IP prefix instead of full IP."""

    def test_ip_prefix_method(self):
        from apps.authentication.views import UserLoginView

        view = UserLoginView()
        assert view._ip_prefix("192.168.1.100") == "192.168.1.0"
        assert view._ip_prefix("10.0.0.55") == "10.0.0.0"
        assert view._ip_prefix("invalid") == "invalid"

    def test_ua_hash_method(self):
        from apps.authentication.views import UserLoginView

        view = UserLoginView()
        h1 = view._ua_hash("Mozilla/5.0 Chrome/120")
        h2 = view._ua_hash("Mozilla/5.0 Chrome/120")
        assert h1 == h2
        assert len(h1) == 12

    def test_is_locked_out_method(self, db, user):
        from django.utils import timezone

        from apps.authentication.models import LoginAttempt
        from apps.authentication.views import UserLoginView

        LoginAttempt.objects.create(
            username="test@example.com",
            ip_address="192.168.1.100",
            user_agent="Mozilla/5.0 Chrome/120",
            was_successful=False,
            created_at=timezone.now(),
        )

        view = UserLoginView()
        # 1 attempt < threshold of 5 — should not lock
        locked = view._is_locked_out("test@example.com", "192.168.1.200", "Mozilla/5.0 Chrome/120")
        assert not locked  # same /24, same UA — only 1 attempt

    def test_lockout_triggers_after_threshold(self, db, user):
        from django.utils import timezone

        from apps.authentication.models import LoginAttempt
        from apps.authentication.views import UserLoginView

        for i in range(6):
            LoginAttempt.objects.create(
                username="victim@example.com",
                ip_address=f"192.168.1.{i}",
                user_agent="Mozilla/5.0 Chrome/120",
                was_successful=False,
                created_at=timezone.now(),
            )

        view = UserLoginView()
        locked = view._is_locked_out(
            "victim@example.com", "192.168.1.200", "Mozilla/5.0 Chrome/120"
        )
        assert locked


@pytest.mark.django_db
class TestLoginViewLockoutResponse:
    """Actual login endpoint returns 429 when locked."""

    def test_login_returns_429_on_lockout(self, api_client, db):
        from django.utils import timezone

        from apps.authentication.models import LoginAttempt

        for _ in range(6):
            LoginAttempt.objects.create(
                username="locked@example.com",
                ip_address="127.0.0.1",
                user_agent="Mozilla/5.0",
                was_successful=False,
                created_at=timezone.now(),
            )

        url = reverse("authentication:login")
        resp = api_client.post(
            url,
            {
                "email": "locked@example.com",
                "password": "wrong",
            },
            format="json",
            HTTP_USER_AGENT="Mozilla/5.0",
        )
        assert resp.status_code == status.HTTP_429_TOO_MANY_REQUESTS
