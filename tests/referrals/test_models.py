from decimal import Decimal

import pytest

from apps.referrals.models import Referral


@pytest.mark.django_db
class TestReferralModel:
    def test_create_referral(self, user, admin_user):
        referral = Referral.objects.create(
            referrer=user,
            referred_user=admin_user,
            code="TOR001010101",
            bonus_amount=Decimal("50.00000000"),
            currency="USDT",
        )
        assert referral.referrer == user
        assert referral.referred_user == admin_user
        assert referral.code == "TOR001010101"
        assert referral.bonus_amount == Decimal("50.00000000")
        assert referral.currency == "USDT"
        assert referral.status == "pending"
        assert str(referral) == f"{user.email} referred {admin_user.email}"

    def test_default_values(self, user, admin_user):
        referral = Referral.objects.create(
            referrer=user,
            referred_user=admin_user,
            code="DEFAULT_TEST",
        )
        assert referral.bonus_amount == Decimal("0")
        assert referral.currency == "USDT"
        assert referral.status == "pending"

    def test_referred_user_unique(self, user, admin_user):
        Referral.objects.create(referrer=user, referred_user=admin_user, code="CODE1")
        with pytest.raises(Exception):
            Referral.objects.create(referrer=user, referred_user=admin_user, code="CODE2")

    def test_status_choices(self, user, admin_user):
        users = [user, admin_user]
        for i, status in enumerate(["pending", "paid", "rejected"]):
            u = (
                users[i]
                if i < len(users)
                else user.__class__.objects.create_user(
                    username=f"user{i}",
                    email=f"user{i}@test.com",
                    password="pass",
                )
            )
            referral = Referral.objects.create(
                referrer=user,
                referred_user=u,
                code=f"STATUS_{status}",
                status=status,
            )
            assert referral.status == status

    def test_valid_statuses(self):
        valid_statuses = {choice[0] for choice in Referral._meta.get_field("status").choices}
        assert valid_statuses == {"pending", "paid", "rejected"}

    def test_multiple_referrals_same_referrer(self, user, admin_user):
        another_user = admin_user.__class__.objects.create_user(
            username="another",
            email="another@test.com",
            password="pass",
        )
        ref1 = Referral.objects.create(referrer=user, referred_user=admin_user, code="CODE_A")
        assert ref1.referrer == user
        ref2 = Referral.objects.create(
            referrer=user,
            referred_user=another_user,
            code="CODE_B",
        )
        assert ref2.referrer == user
        assert (
            Referral.objects.filter(referrer=user).count() == 3
        )  # 1 auto-created via CustomUser.save() + 2 explicit
