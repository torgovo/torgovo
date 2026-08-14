"""
Tests for Referral endpoints
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()


class ReferralTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.client.login(username="testuser", password="testpass123")

    def test_my_referral_stats(self):
        """Test referral stats endpoint returns 200"""
        response = self.client.get("/api/referrals/my-stats/")
        self.assertEqual(response.status_code, 200)

    def test_apply_referral(self):
        """Test applying referral code returns 400 (invalid code)"""
        data = {"referral_code": "INVALID"}
        response = self.client.post("/api/referrals/apply/", data, format="json")
        self.assertEqual(response.status_code, 400)
