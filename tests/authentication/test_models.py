import pytest
from django.utils import timezone
from datetime import timedelta
from apps.authentication.models import (
    UserProfile, EmailVerification, PhoneVerification,
    PasswordResetToken, LoginAttempt
)


@pytest.mark.django_db
class TestUserProfile:
    def test_create_user_profile_via_signal(self, user):
        profile = UserProfile.objects.get(user=user)
        assert profile.user == user
        assert profile.subscription_plan == 'free'
        assert profile.max_bots_allowed == 3
        assert profile.demo_trading_enabled is True
        assert profile.email_notifications is True
        assert profile.push_notifications is True
        assert profile.sms_notifications is False

    def test_str_representation(self, user):
        profile = UserProfile.objects.get(user=user)
        assert str(profile) == f"{user.email} - {profile.subscription_plan}"

    def test_referral_code_generated_on_save(self, user):
        profile = UserProfile.objects.get(user=user)
        assert len(profile.referral_code) == 8
        assert profile.referral_code.isalnum()

    def test_referral_code_uniqueness(self, user):
        profile1 = UserProfile.objects.get(user=user)
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user2 = User.objects.create_user(
            username='testuser2', email='test2@example.com', password='testpass456'
        )
        profile2 = UserProfile.objects.get(user=user2)
        assert profile1.referral_code != profile2.referral_code

    def test_update_bot_limits(self, user):
        profile = UserProfile.objects.get(user=user)
        assert profile.max_bots_allowed == 3
        profile.subscription_plan = 'premium'
        profile.save()
        profile.refresh_from_db()
        assert profile.max_bots_allowed == 15

    def test_bot_limits_all_plans(self, user):
        profile = UserProfile.objects.get(user=user)
        cases = [('free', 3), ('basic', 5), ('premium', 15), ('enterprise', 50)]
        for plan, expected in cases:
            profile.subscription_plan = plan
            profile.save()
            profile.refresh_from_db()
            assert profile.max_bots_allowed == expected, f"Plan {plan} expected {expected}"

    def test_has_active_subscription_free_plan(self, user):
        profile = UserProfile.objects.get(user=user)
        assert profile.has_active_subscription() is False

    def test_has_active_subscription_inactive(self, user):
        profile = UserProfile.objects.get(user=user)
        profile.subscription_plan = 'premium'
        profile.is_subscription_active = False
        assert profile.has_active_subscription() is False

    def test_has_active_subscription_expired(self, user):
        profile = UserProfile.objects.get(user=user)
        profile.subscription_plan = 'premium'
        profile.is_subscription_active = True
        profile.subscription_end_date = timezone.now() - timedelta(days=1)
        assert profile.has_active_subscription() is False

    def test_has_active_subscription_valid(self, user):
        profile = UserProfile.objects.get(user=user)
        profile.subscription_plan = 'premium'
        profile.is_subscription_active = True
        profile.subscription_end_date = timezone.now() + timedelta(days=30)
        assert profile.has_active_subscription() is True

    def test_has_active_subscription_no_end_date(self, user):
        profile = UserProfile.objects.get(user=user)
        profile.subscription_plan = 'premium'
        profile.is_subscription_active = True
        profile.subscription_end_date = None
        assert profile.has_active_subscription() is True

    def test_profile_defaults(self, user):
        profile = UserProfile.objects.get(user=user)
        assert profile.timezone == 'UTC'
        assert profile.trading_preferences == dict()
        assert profile.total_trades_executed == 0
        assert float(profile.total_volume_traded) == 0
        assert profile.is_subscription_active is False
        assert profile.subscription_start_date is None
        assert profile.subscription_end_date is None
        assert profile.referred_by is None

    def test_referral_code_regeneration_does_not_change(self, user):
        profile = UserProfile.objects.get(user=user)
        original_code = profile.referral_code
        profile.save()
        profile.refresh_from_db()
        assert profile.referral_code == original_code


@pytest.mark.django_db
class TestEmailVerification:
    def test_create_email_verification(self, user):
        expires_at = timezone.now() + timedelta(hours=24)
        ev = EmailVerification.objects.create(
            user=user, token='testtoken123', expires_at=expires_at
        )
        assert ev.user == user
        assert ev.token == 'testtoken123'
        assert ev.is_verified is False
        assert ev.verified_at is None

    def test_str_representation_pending(self, user):
        ev = EmailVerification.objects.create(
            user=user, token='pendingtoken', expires_at=timezone.now() + timedelta(hours=24)
        )
        assert str(ev) == f"{user.email} - Pending"

    def test_str_representation_verified(self, user):
        ev = EmailVerification.objects.create(
            user=user, token='verifiedtoken', expires_at=timezone.now() + timedelta(hours=24),
            is_verified=True, verified_at=timezone.now()
        )
        assert str(ev) == f"{user.email} - Verified"

    def test_is_expired_false(self, user):
        ev = EmailVerification.objects.create(
            user=user, token='nottoken', expires_at=timezone.now() + timedelta(hours=24)
        )
        assert ev.is_expired() is False

    def test_is_expired_true(self, user):
        ev = EmailVerification.objects.create(
            user=user, token='expiredtoken', expires_at=timezone.now() - timedelta(hours=1)
        )
        assert ev.is_expired() is True

    def test_verify(self, user):
        assert user.is_email_verified is False
        ev = EmailVerification.objects.create(
            user=user, token='verifytoken', expires_at=timezone.now() + timedelta(hours=24)
        )
        ev.verify()
        ev.refresh_from_db()
        assert ev.is_verified is True
        assert ev.verified_at is not None
        user.refresh_from_db()
        assert user.is_email_verified is True

    def test_unique_token_constraint(self, user):
        expires_at = timezone.now() + timedelta(hours=24)
        EmailVerification.objects.create(user=user, token='uniquetoken', expires_at=expires_at)
        from django.db import IntegrityError
        with pytest.raises(IntegrityError):
            EmailVerification.objects.create(user=user, token='uniquetoken', expires_at=expires_at)


@pytest.mark.django_db
class TestPhoneVerification:
    def test_create_phone_verification(self, user):
        pv = PhoneVerification.objects.create(
            user=user, code='123456', phone_number='+1234567890',
            expires_at=timezone.now() + timedelta(minutes=10)
        )
        assert pv.user == user
        assert pv.code == '123456'
        assert pv.phone_number == '+1234567890'
        assert pv.is_verified is False
        assert pv.attempts == 0
        assert pv.max_attempts == 3

    def test_str_representation(self, user):
        pv = PhoneVerification.objects.create(
            user=user, code='654321', phone_number='+1234567890',
            expires_at=timezone.now() + timedelta(minutes=10)
        )
        assert str(pv) == f"{user.email} - {pv.phone_number}"

    def test_is_expired_false(self, user):
        pv = PhoneVerification.objects.create(
            user=user, code='000000', phone_number='+1234567890',
            expires_at=timezone.now() + timedelta(minutes=10)
        )
        assert pv.is_expired() is False

    def test_is_expired_true(self, user):
        pv = PhoneVerification.objects.create(
            user=user, code='000000', phone_number='+1234567890',
            expires_at=timezone.now() - timedelta(minutes=1)
        )
        assert pv.is_expired() is True

    def test_has_attempts_left_initial(self, user):
        pv = PhoneVerification.objects.create(
            user=user, code='111111', phone_number='+1234567890',
            expires_at=timezone.now() + timedelta(minutes=10)
        )
        assert pv.has_attempts_left() is True

    def test_has_attempts_left_exhausted(self, user):
        pv = PhoneVerification.objects.create(
            user=user, code='111111', phone_number='+1234567890',
            expires_at=timezone.now() + timedelta(minutes=10),
            attempts=3
        )
        assert pv.has_attempts_left() is False

    def test_increment_attempt(self, user):
        pv = PhoneVerification.objects.create(
            user=user, code='222222', phone_number='+1234567890',
            expires_at=timezone.now() + timedelta(minutes=10)
        )
        pv.increment_attempt()
        assert pv.attempts == 1
        pv.increment_attempt()
        assert pv.attempts == 2

    def test_verify(self, user):
        assert user.is_phone_verified is False
        pv = PhoneVerification.objects.create(
            user=user, code='333333', phone_number='+1234567890',
            expires_at=timezone.now() + timedelta(minutes=10)
        )
        pv.verify()
        pv.refresh_from_db()
        assert pv.is_verified is True
        assert pv.verified_at is not None
        user.refresh_from_db()
        assert user.is_phone_verified is True
        assert user.phone_number == '+1234567890'


@pytest.mark.django_db
class TestPasswordResetToken:
    def test_create_token(self, user):
        prt = PasswordResetToken.objects.create(
            user=user, token='resettoken123', expires_at=timezone.now() + timedelta(hours=2)
        )
        assert prt.user == user
        assert prt.token == 'resettoken123'
        assert prt.is_used is False
        assert prt.used_at is None

    def test_str_representation_pending(self, user):
        prt = PasswordResetToken.objects.create(
            user=user, token='pendingtoken123', expires_at=timezone.now() + timedelta(hours=2)
        )
        assert str(prt) == f"{user.email} - Pending"

    def test_str_representation_used(self, user):
        prt = PasswordResetToken.objects.create(
            user=user, token='usedtoken123', expires_at=timezone.now() + timedelta(hours=2),
            is_used=True, used_at=timezone.now()
        )
        assert str(prt) == f"{user.email} - Used"

    def test_is_expired_false(self, user):
        prt = PasswordResetToken.objects.create(
            user=user, token='freshtoken', expires_at=timezone.now() + timedelta(hours=2)
        )
        assert prt.is_expired() is False

    def test_is_expired_true(self, user):
        prt = PasswordResetToken.objects.create(
            user=user, token='oldtoken', expires_at=timezone.now() - timedelta(hours=1)
        )
        assert prt.is_expired() is True

    def test_use(self, user):
        prt = PasswordResetToken.objects.create(
            user=user, token='usetoken123', expires_at=timezone.now() + timedelta(hours=2)
        )
        assert prt.is_used is False
        prt.use()
        prt.refresh_from_db()
        assert prt.is_used is True
        assert prt.used_at is not None

    def test_unique_token_constraint(self, user):
        expires_at = timezone.now() + timedelta(hours=2)
        PasswordResetToken.objects.create(user=user, token='uniqresettoken', expires_at=expires_at)
        from django.db import IntegrityError
        with pytest.raises(IntegrityError):
            PasswordResetToken.objects.create(user=user, token='uniqresettoken', expires_at=expires_at)


@pytest.mark.django_db
class TestLoginAttempt:
    def test_create_login_attempt_success(self):
        attempt = LoginAttempt.objects.create(
            username='test@example.com', ip_address='192.168.1.1',
            user_agent='Mozilla/5.0', was_successful=True
        )
        assert attempt.username == 'test@example.com'
        assert attempt.ip_address == '192.168.1.1'
        assert attempt.was_successful is True
        assert attempt.failure_reason == ''

    def test_create_login_attempt_failure(self):
        attempt = LoginAttempt.objects.create(
            username='test@example.com', ip_address='10.0.0.1',
            user_agent='', was_successful=False, failure_reason='Invalid password'
        )
        assert attempt.was_successful is False
        assert attempt.failure_reason == 'Invalid password'

    def test_str_representation_success(self):
        attempt = LoginAttempt.objects.create(
            username='test@example.com', ip_address='192.168.1.1', was_successful=True
        )
        assert str(attempt) == 'test@example.com - 192.168.1.1 - Success'

    def test_str_representation_failure(self):
        attempt = LoginAttempt.objects.create(
            username='test@example.com', ip_address='10.0.0.1', was_successful=False
        )
        assert str(attempt) == 'test@example.com - 10.0.0.1 - Failed'

    def test_login_attempt_ordering(self, user):
        a1 = LoginAttempt.objects.create(
            username='test@example.com', ip_address='1.1.1.1', was_successful=True
        )
        a2 = LoginAttempt.objects.create(
            username='test@example.com', ip_address='2.2.2.2', was_successful=False
        )
        assert LoginAttempt.objects.count() == 2
        assert a1.created_at <= a2.created_at

    def test_blank_user_agent(self):
        attempt = LoginAttempt.objects.create(
            username='', ip_address='0.0.0.0', was_successful=False
        )
        assert attempt.user_agent == ''
