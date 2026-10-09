"""
Tests for Referral endpoints
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

User = get_user_model()


class ReferralTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        # Endpoints are JWT-protected (IsAuthenticated) — session login()
        # returns 401; force_authenticate bypasses JWT for unit testing
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_my_referral_stats(self):
        """Test referral stats endpoint returns 200"""
        response = self.client.get("/api/referrals/my-stats/")
        self.assertEqual(response.status_code, 200)

    def test_apply_referral(self):
        """Test applying referral code returns 400 (invalid code)"""
        data = {"referral_code": "INVALID"}
        response = self.client.post("/api/referrals/apply/", data, format="json")
        self.assertEqual(response.status_code, 400)

    def test_apply_valid_code_creates_row(self):
        """A2: applying a valid code creates a new Referral row"""
        referrer = User.objects.create_user(
            username="refuser", email="ref@example.com", password="testpass123"
        )
        response = self.client.post(
            "/api/referrals/apply/",
            {"referral_code": referrer.referral_code},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        from apps.referrals.models import Referral

        self.assertTrue(
            Referral.objects.filter(referrer=referrer, referred_user=self.user).exists()
        )

    def test_stats_counter_not_always_zero(self):
        """A3: total_referrals counts referred users (old paid-filter = 0)"""
        from decimal import Decimal

        from apps.referrals.models import Referral

        referrer = self.user
        other = User.objects.create_user(
            username="referred1", email="r1@example.com", password="testpass123"
        )
        Referral.objects.create(
            referrer=referrer,
            referred_user=other,
            code=referrer.referral_code,
            status="pending",
            bonus_amount=Decimal("10"),
        )
        response = self.client.get("/api/referrals/my-stats/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_referrals"], 1)
