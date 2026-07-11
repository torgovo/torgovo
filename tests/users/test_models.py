import pytest
from django.contrib.auth import get_user_model
from apps.users.models import UserBalance

User = get_user_model()


@pytest.mark.django_db
class TestCustomUser:
    def test_create_user(self):
        user = User.objects.create_user(
            username='newuser',
            email='newuser@example.com',
            password='testpass123',
        )
        assert user.username == 'newuser'
        assert user.email == 'newuser@example.com'
        assert user.check_password('testpass123')
        assert user.is_active is True
        assert user.is_staff is False
        assert user.is_superuser is False

    def test_create_superuser(self):
        admin = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='adminpass123',
        )
        assert admin.is_staff is True
        assert admin.is_superuser is True

    def test_str_representation(self, user):
        assert str(user) == f"{user.username} ({user.email})"

    def test_default_values(self, user):
        assert user.subscription_plan == 'free'
        assert user.max_bots_allowed == 3
        assert user.demo_trading_enabled is True
        assert user.risk_tolerance == 'moderate'
        assert user.email_notifications is True
        assert user.push_notifications is True
        assert user.sms_notifications is False
        assert user.timezone == 'UTC'
        assert user.is_verified is False
        assert user.two_factor_enabled is False
        assert user.total_trades_executed == 0
        assert float(user.total_volume_traded) == 0.0
        assert float(user.total_profit_loss) == 0.0

    def test_save_updates_max_bots_allowed(self, user):
        assert user.max_bots_allowed == 3
        user.subscription_plan = 'basic'
        user.save()
        user.refresh_from_db()
        assert user.max_bots_allowed == 10

    def test_save_updates_max_bots_premium(self, user):
        user.subscription_plan = 'premium'
        user.save()
        user.refresh_from_db()
        assert user.max_bots_allowed == 999999

    def test_save_updates_max_bots_enterprise(self, user):
        user.subscription_plan = 'enterprise'
        user.save()
        user.refresh_from_db()
        assert user.max_bots_allowed == 999999

    def test_get_full_trading_profile(self, user):
        profile = user.get_full_trading_profile()
        assert profile['plan'] == 'free'
        assert profile['max_bots'] == 3
        assert profile['demo_mode'] is True
        assert profile['risk_level'] == 'moderate'
        assert profile['total_trades'] == 0
        assert profile['default_exchange'] is None

    def test_email_verified_default_false(self, user):
        assert user.is_email_verified is False

    def test_phone_verified_default_false(self, user):
        assert user.is_phone_verified is False

    def test_two_factor_disabled_default(self, user):
        assert user.two_factor_enabled is False

    def test_auto_compound_defaults(self, user):
        assert user.auto_compound_profits is False
        assert user.compound_frequency == 'weekly'


@pytest.mark.django_db
class TestUserBalance:
    def test_create_balance(self, user):
        balance = UserBalance.objects.create(
            user=user, currency='USDT', available=1000.0
        )
        assert balance.user == user
        assert balance.currency == 'USDT'
        assert float(balance.available) == 1000.0
        assert float(balance.hold) == 0.0

    def test_str_representation(self, user):
        balance = UserBalance.objects.create(
            user=user, currency='USDT', available=500.0
        )
        assert str(balance) == f"{user.email} - 500.00000000 USDT"

    def test_balance_with_hold(self, user):
        balance = UserBalance.objects.create(
            user=user, currency='BTC', available=0.5, hold=0.1
        )
        assert float(balance.available) == 0.5
        assert float(balance.hold) == 0.1

    def test_unique_together_constraint(self, user):
        UserBalance.objects.create(user=user, currency='USDT', available=100.0)
        from django.db import IntegrityError
        with pytest.raises(IntegrityError):
            UserBalance.objects.create(user=user, currency='USDT', available=200.0)

    def test_multiple_currencies_allowed(self, user):
        UserBalance.objects.create(user=user, currency='USDT', available=1000.0)
        UserBalance.objects.create(user=user, currency='BTC', available=2.5)
        UserBalance.objects.create(user=user, currency='ETH', available=10.0)
        assert UserBalance.objects.filter(user=user).count() == 3

    def test_balance_defaults(self, user):
        balance = UserBalance.objects.create(user=user, currency='USDT')
        assert float(balance.available) == 0.0
        assert float(balance.hold) == 0.0
