from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework import status

from apps.referrals.models import Referral
from apps.referrals.views import ReferralRegistrationMixin


@pytest.mark.django_db
class TestMyReferralStatsView:
    def test_stats_no_referrals(self, auth_client, user):
        url = reverse("referrals:my-referral-stats")
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert "referral_code" in response.data
        assert response.data["total_referrals"] == 0
        from decimal import Decimal

        assert response.data["total_bonus_usdt"] == Decimal("0")
        assert "referral_link" in response.data

    def test_stats_with_referrals(self, auth_client, user, admin_user):
        Referral.objects.create(
            referrer=user,
            referred_user=admin_user,
            code="TOR000001",
            bonus_amount=Decimal("50"),
            status="paid",
        )
        url = reverse("referrals:my-referral-stats")
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["total_referrals"] == 1
        assert Decimal(response.data["total_bonus_usdt"]) == Decimal("50")

    def test_stats_counts_pending_not_only_paid(self, auth_client, user, second_user, admin_user):
        """A3: old filter was status="paid" (never set at runtime) → always 0.
        Counter must count ALL referred users regardless of status."""
        Referral.objects.create(
            referrer=user,
            referred_user=second_user,
            code=user.referral_code,
            status="pending",
        )
        Referral.objects.create(
            referrer=user,
            referred_user=admin_user,
            code=user.referral_code,
            status="paid",
        )
        url = reverse("referrals:my-referral-stats")
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["total_referrals"] == 2

    def test_stats_excludes_rejected_and_placeholders(self, auth_client, user, admin_user):
        """Rejected rows (fraud) and placeholder rows (referred_user NULL)
        must not inflate the counter."""
        Referral.objects.create(
            referrer=user,
            referred_user=admin_user,
            code=user.referral_code,
            status="rejected",
        )
        url = reverse("referrals:my-referral-stats")
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["total_referrals"] == 0

    def test_stats_code_persists(self, auth_client, user):
        url = reverse("referrals:my-referral-stats")
        response1 = auth_client.get(url)
        code1 = response1.data["referral_code"]

        response2 = auth_client.get(url)
        assert response2.data["referral_code"] == code1

    def test_unauthenticated(self, api_client):
        url = reverse("referrals:my-referral-stats")
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestApplyReferralCodeView:
    def test_apply_valid_code(self, auth_client, user, admin_user):
        # A2: source of truth is CustomUser.referral_code — no Referral row
        # is required for the referrer anymore
        admin_user.referral_code = "TORADMIN1"
        admin_user.save()
        url = reverse("referrals:apply-referral-code")
        response = auth_client.post(url, {"referral_code": "TORADMIN1"}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["message"] == "Referral code applied successfully"

        # A2: one NEW row per applicant — existing rows are never overwritten
        assert Referral.objects.filter(
            referrer=admin_user, referred_user=user, code="TORADMIN1"
        ).exists()
        user.refresh_from_db()
        assert user.referred_by == admin_user

    def test_apply_own_code_fails(self, auth_client, user):
        user.referral_code = "TORSELF"
        user.save()
        url = reverse("referrals:apply-referral-code")
        response = auth_client.post(url, {"referral_code": "TORSELF"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        # A14: flat body → uniform envelope, message carries the reason
        assert "own referral code" in response.data["error"]["message"]

    def test_apply_twice_fails(self, auth_client, user, admin_user):
        admin_user.referral_code = "TORADMIN2"
        admin_user.save()
        # User already referred (row from a previous apply/registration)
        Referral.objects.create(referrer=admin_user, referred_user=user, code="TORADMIN2")
        user.referred_by = admin_user
        user.save(update_fields=["referred_by"])

        url = reverse("referrals:apply-referral-code")
        response = auth_client.post(url, {"referral_code": "TORADMIN2"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        # A14: flat body → uniform envelope, message carries the reason
        assert "already applied" in response.data["error"]["message"]

    def test_unlimited_second_applicant(self, auth_client, second_auth_client, admin_user):
        """A2: unlimited applicants — the 2nd user applying the SAME code must
        succeed (old code claimed one shared row and dropped applicant 2+)."""
        admin_user.referral_code = "TORMULTI1"
        admin_user.save()
        url = reverse("referrals:apply-referral-code")

        first = auth_client.post(url, {"referral_code": "TORMULTI1"}, format="json")
        assert first.status_code == status.HTTP_200_OK

        second = second_auth_client.post(url, {"referral_code": "TORMULTI1"}, format="json")
        assert second.status_code == status.HTTP_200_OK

        assert (
            Referral.objects.filter(referrer=admin_user, referred_user__isnull=False).count() == 2
        )

    def test_apply_works_without_referrer_rows(self, auth_client, user, admin_user):
        """A2: referrer who never opened my-stats has zero Referral rows —
        code must still validate via user-level referral_code."""
        admin_user.referral_code = "TORFRESH1"
        admin_user.save()
        Referral.objects.filter(referrer=admin_user).delete()

        response = auth_client.post(
            reverse("referrals:apply-referral-code"),
            {"referral_code": "TORFRESH1"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert Referral.objects.filter(referrer=admin_user, referred_user=user).exists()

    def test_apply_code_case_insensitive(self, auth_client, user, admin_user):
        admin_user.referral_code = "TORLOWER"
        admin_user.save()
        response = auth_client.post(
            reverse("referrals:apply-referral-code"),
            {"referral_code": "torlower"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert Referral.objects.filter(referrer=admin_user, referred_user=user).exists()

    def test_invalid_code(self, auth_client):
        url = reverse("referrals:apply-referral-code")
        response = auth_client.post(url, {"referral_code": "INVALID_CODE"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        # A14: flat body → uniform envelope, message carries the reason
        assert "Invalid" in response.data["error"]["message"]

    def test_invalid_code_full_envelope_shape(self, auth_client):
        # A14: the WHOLE envelope contract, not just the message
        url = reverse("referrals:apply-referral-code")
        response = auth_client.post(url, {"referral_code": "INVALID_CODE"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        err = response.data["error"]
        assert err["code"] == "VALIDATION_ERROR"
        assert "Invalid" in err["message"]
        assert "timestamp" in response.data

    def test_missing_code(self, auth_client):
        url = reverse("referrals:apply-referral-code")
        response = auth_client.post(url, {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_unauthenticated(self, api_client):
        url = reverse("referrals:apply-referral-code")
        response = api_client.post(url, {"referral_code": "TEST"}, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestReferralRegistrationMixin:
    def test_apply_referral_after_registration_success(self, user, admin_user):
        admin_user.referral_code = "REGCODE1"
        admin_user.save()
        mixin = ReferralRegistrationMixin()
        result = mixin.apply_referral_after_registration(user, "REGCODE1")
        assert result is not None
        assert result["referral_applied"] is True
        # A2: one NEW row per referred user — nothing overwritten
        assert Referral.objects.filter(
            referrer=admin_user, referred_user=user, code="REGCODE1"
        ).exists()
        user.refresh_from_db()
        assert user.referred_by == admin_user

    def test_apply_referral_no_code(self, user):
        mixin = ReferralRegistrationMixin()
        result = mixin.apply_referral_after_registration(user, None)
        assert result is None

    def test_apply_referral_empty_code(self, user):
        mixin = ReferralRegistrationMixin()
        result = mixin.apply_referral_after_registration(user, "")
        assert result is None

    def test_apply_referral_self_referral_skipped(self, user, admin_user):
        admin_user.referral_code = "SELFREF"
        admin_user.save()
        mixin = ReferralRegistrationMixin()
        result = mixin.apply_referral_after_registration(admin_user, "SELFREF")
        assert result is None
        admin_user.refresh_from_db()
        assert admin_user.referred_by_id is None
        assert not Referral.objects.filter(referrer=admin_user, referred_user=admin_user).exists()

    def test_apply_referral_invalid_code(self, user):
        mixin = ReferralRegistrationMixin()
        result = mixin.apply_referral_after_registration(user, "NONEXISTENT")
        assert result is None
