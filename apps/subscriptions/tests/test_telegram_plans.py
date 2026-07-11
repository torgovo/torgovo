"""
Tests for Telegram Subscription endpoints
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from apps.subscriptions.models import TelegramSignalPlan

User = get_user_model()


class TelegramPlanTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', email='test@example.com', password='testpass123')
        self.client.login(username='testuser', password='testpass123')
        self.plan = TelegramSignalPlan.objects.create(
            name='Basic',
            slug='basic',
            price_monthly=9.99,
            description='Test plan'
        )

    def test_telegram_plans_list(self):
        """Test that telegram plans list endpoint returns 200"""
        response = self.client.get('/api/subscriptions/public/plans/')
        self.assertEqual(response.status_code, 200)

    def test_telegram_plans_by_url(self):
        """Test the telegram-specific plans endpoint returns 200"""
        response = self.client.get('/api/subscriptions/telegram/plans/')
        self.assertEqual(response.status_code, 200)

    def test_my_telegram_usage(self):
        """Test my-usage endpoint returns 200"""
        response = self.client.get('/api/subscriptions/telegram/my-usage/')
        self.assertEqual(response.status_code, 200)
