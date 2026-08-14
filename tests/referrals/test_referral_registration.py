import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.referrals.models import Referral

User = get_user_model()


@pytest.mark.django_db
class TestReferralRegistration:

    def test_happy_path_valid_referral_code(self, api_client):
        """User signs up with valid referral code -> referred_by set, Referral claimed."""
        referrer = User.objects.create_user(username="referrer", password="testpass123")

        response = api_client.post(
            reverse("auth:register"),
            {
                "username": "newuser",
                "email": "new@example.com",
                "password": "testpass123",
                "password_confirm": "testpass123",
                "referral_code": referrer.referral_code,
            },
        )

        assert response.status_code == 201
        new_user = User.objects.get(username="newuser")
        assert new_user.referred_by == referrer

        referral = Referral.objects.get(code=referrer.referral_code)
        assert referral.referred_user == new_user

    def test_invalid_referral_code_returns_400(self, api_client):
        """Invalid code blocks registration with validation error."""
        response = api_client.post(
            reverse("auth:register"),
            {
                "username": "newuser",
                "email": "new@example.com",
                "password": "testpass123",
                "password_confirm": "testpass123",
                "referral_code": "FAKECODE",
            },
        )

        assert response.status_code == 400
        assert "referral_code" in response.data["error"]["details"]
        assert User.objects.filter(username="newuser").exists() is False

    def test_self_referral_blocked_silently(self, api_client):
        """User's own code used during signup -> ignored, no referred_by set."""
        referrer = User.objects.create_user(username="selfref", password="testpass123")

        response = api_client.post(
            reverse("auth:register"),
            {
                "username": "newuser",
                "email": "new@example.com",
                "password": "testpass123",
                "password_confirm": "testpass123",
                "referral_code": referrer.referral_code,
            },
        )
        assert response.status_code == 201  # valid referral, user referred by 'selfref'
        new_user = User.objects.get(username="newuser")
        assert new_user.referred_by == referrer

    def test_double_referral_only_first_applied(self):
        """Only the first referral code takes effect; second is ignored."""
        referrer1 = User.objects.create_user(
            username="ref1", email="ref1@test.com", password="testpass123"
        )
        referrer2 = User.objects.create_user(
            username="ref2", email="ref2@test.com", password="testpass123"
        )

        new_user = User.objects.create_user(
            username="newuser", email="new@example.com", password="testpass123"
        )

        from apps.referrals.views import ReferralRegistrationMixin

        mixin = ReferralRegistrationMixin()
        mixin.apply_referral_after_registration(new_user, referrer1.referral_code)
        assert new_user.referred_by == referrer1

        mixin.apply_referral_after_registration(new_user, referrer2.referral_code)
        new_user.refresh_from_db()
        assert new_user.referred_by == referrer1

    def test_referral_record_auto_created_on_signup(self, api_client):
        """Every new user gets a Referral record on signup."""
        response = api_client.post(
            reverse("auth:register"),
            {
                "username": "newuser",
                "email": "new@example.com",
                "password": "testpass123",
                "password_confirm": "testpass123",
            },
        )
        assert response.status_code == 201
        user = User.objects.get(username="newuser")

        assert Referral.objects.filter(referrer=user).exists()
        assert Referral.objects.get(referrer=user).code == user.referral_code

    def test_legacy_ref_query_param(self, api_client):
        """?ref= query param is processed when no POST body referral_code."""
        referrer = User.objects.create_user(username="referrer", password="testpass123")

        response = api_client.post(
            f"{reverse('auth:register')}?ref={referrer.referral_code}",
            {
                "username": "newuser",
                "email": "new@example.com",
                "password": "testpass123",
                "password_confirm": "testpass123",
            },
        )
        assert response.status_code == 201
        new_user = User.objects.get(username="newuser")
        assert new_user.referred_by == referrer

    def test_idempotent_same_code_called_twice(self):
        """Calling apply_referral_after_registration twice with same code is a no-op."""
        referrer = User.objects.create_user(username="referrer", password="testpass123")
        new_user = User.objects.create_user(
            username="newuser", email="new@example.com", password="testpass123"
        )

        from apps.referrals.views import ReferralRegistrationMixin

        mixin = ReferralRegistrationMixin()
        result1 = mixin.apply_referral_after_registration(new_user, referrer.referral_code)
        result2 = mixin.apply_referral_after_registration(new_user, referrer.referral_code)

        assert result1 is not None
        assert result1["referral_applied"] is True
        assert result2 is None  # idempotent guard

    def test_code_normalization_case_insensitive(self, api_client):
        """Referral codes are case-insensitive (normalized to uppercase)."""
        referrer = User.objects.create_user(username="referrer", password="testpass123")
        code_lower = referrer.referral_code.lower()

        response = api_client.post(
            reverse("auth:register"),
            {
                "username": "newuser",
                "email": "new@example.com",
                "password": "testpass123",
                "password_confirm": "testpass123",
                "referral_code": code_lower,
            },
        )

        assert response.status_code == 201
        new_user = User.objects.get(username="newuser")
        assert new_user.referred_by == referrer
