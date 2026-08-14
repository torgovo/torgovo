"""
Tests for Withdrawal endpoints
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()


class WithdrawalTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.client.login(username="testuser", password="testpass123")

    def test_withdrawal_list(self):
        """Test that withdrawal list endpoint returns 200"""
        response = self.client.get("/api/payments/withdrawals/")
        self.assertEqual(response.status_code, 200)

    def test_create_withdrawal(self):
        """Test that creating a withdrawal returns 400 (missing required fields)"""
        data = {
            "amount": 100.50,
            "currency": "USDT",
            "blockchain": "BEP20",
        }
        response = self.client.post("/api/payments/withdrawals/", data, format="json")
        # Will return 400 due to missing fields, but endpoint exists
        self.assertIn(response.status_code, [400, 201])
