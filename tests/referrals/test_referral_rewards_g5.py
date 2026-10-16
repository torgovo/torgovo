"""G5 / FR A7 — referral rewards (commissions, discounts, payout requests).

Covers services/referral_rewards.py end-to-end:
- get_referral_config fallbacks + admin overrides
- apply_discount rounding
- commission_tier_plan / referrer_earns_commission tier walk
- referee_discount_pct eligibility (referee side)
- record_subscription_payment accrual (bot + telegram)
- request_payout / approve_payout_request / reject_payout_request
- API: PayoutRequestsView, admin decide endpoints, my-stats hybrid fields
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.payments.models import (
    BotSubscription,
    BotSubscriptionPlan,
    ReferralPayout,
    SubscriptionPlan,
)
from apps.referrals.models import Referral
from services.referral_rewards import (
    ReferralRewardError,
    ReferralRewardService,
    apply_discount,
    get_referral_config,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_siteconfig_cache():
    """SiteConfig.get is @lru_cache'd — the cache survives across tests
    (it's a class-level cache, not per-test). Clear before AND after each
    test so a config mutation in one test doesn't leak into the next."""
    from core.models import SiteConfig

    SiteConfig.get.cache_clear()
    yield
    SiteConfig.get.cache_clear()


# ---------------------------------------------------------------- fixtures


def make_creator_subscription(user, *, plan_name="Creator", price=Decimal("99.99")):
    """Active BotSubscription whose BotSubscriptionPlan bridges to a
    SubscriptionPlan with grants_referral_commission=True."""
    sp, _ = SubscriptionPlan.objects.get_or_create(
        name=plan_name,
        defaults={
            "slug": plan_name.lower().replace(" ", "-"),
            "price_monthly": price,
            "price_yearly": price * 12,
            "max_bots_allowed": 10,
            "grants_referral_commission": True,
        },
    )
    # ensure flag is set even if row already existed
    if not sp.grants_referral_commission:
        sp.grants_referral_commission = True
        sp.save(update_fields=["grants_referral_commission"])
    bsp = BotSubscriptionPlan.objects.create(
        bot_type="custom",
        name=f"{plan_name}-shim-{user.id}",
        price=price,
        duration_days=30,
        subscription_plan=sp,
    )
    return BotSubscription.objects.create(
        user=user,
        plan=bsp,
        status="active",
        expires_at=timezone.now() + timedelta(days=30),
    )


def make_free_plan_bot_subscription(user, *, bot_type="grid"):
    """Active BotSubscription whose plan has NO subscription_plan bridge
    (pure per-bot plan → referrer is NOT creator-tier)."""
    bsp = BotSubscriptionPlan.objects.create(
        bot_type=bot_type,
        name=f"{bot_type}-plan-{user.id}",
        price=Decimal("49.99"),
        duration_days=30,
    )
    return BotSubscription.objects.create(
        user=user,
        plan=bsp,
        status="active",
        expires_at=timezone.now() + timedelta(days=30),
    )


def make_referral(referrer, referred):
    return Referral.objects.create(
        referrer=referrer,
        referred_user=referred,
        code=referrer.referral_code or f"REF{user_id_suffix(referrer)}",
        status="pending",
    )


def user_id_suffix(u):
    return str(u.pk)[:8]


def accrue(referrer, referred, amount=Decimal("60.00")):
    """Create a pending ReferralPayout accrual row directly (bypasses hook)."""
    return ReferralPayout.objects.create(
        referrer=referrer,
        referred_user=referred,
        amount=amount,
        percentage=Decimal("10"),
        status="pending",
    )


# ======================================================== config & discount


class TestReferralConfig:
    def test_defaults_when_unset(self, db):
        cfg = get_referral_config()
        assert cfg["commission_pct"] == Decimal("10")
        assert cfg["referee_discount_pct"] == Decimal("15")
        assert cfg["payout_minimum_usd"] == Decimal("50")

    def test_admin_override(self, db):
        from core.models import SiteConfig

        sc = SiteConfig.get()
        sc.referral_config = {
            "commission_pct": 20,
            "referee_discount_pct": 25,
            "payout_minimum_usd": 100,
        }
        sc.save()
        # bust the lru_cache on SiteConfig.get
        SiteConfig.get.cache_clear()
        cfg = get_referral_config()
        assert cfg["commission_pct"] == Decimal("20")
        assert cfg["referee_discount_pct"] == Decimal("25")
        assert cfg["payout_minimum_usd"] == Decimal("100")

    def test_invalid_value_falls_back(self, db):
        from core.models import SiteConfig

        sc = SiteConfig.get()
        sc.referral_config = {"commission_pct": "not-a-number"}
        sc.save()
        SiteConfig.get.cache_clear()
        cfg = get_referral_config()
        assert cfg["commission_pct"] == Decimal("10")  # fallback


class TestApplyDiscount:
    def test_basic_15_pct(self):
        assert apply_discount(Decimal("100"), Decimal("15")) == Decimal("85.00")

    def test_zero_pct_returns_full(self):
        assert apply_discount(Decimal("49.99"), Decimal("0")) == Decimal("49.99")

    def test_rounding_half_up(self):
        # 49.99 * 0.85 = 42.4915 → 42.49
        assert apply_discount(Decimal("49.99"), Decimal("15")) == Decimal("42.49")

    def test_negative_pct_returns_full(self):
        assert apply_discount(Decimal("100"), Decimal("-5")) == Decimal("100.00")


# ============================================================ tier walk


class TestCommissionTier:
    def test_active_creator_sub_earns(self, user):
        make_creator_subscription(user)
        assert ReferralRewardService.referrer_earns_commission(user) is True

    def test_no_sub_does_not_earn(self, user):
        assert ReferralRewardService.referrer_earns_commission(user) is False

    def test_expired_sub_does_not_earn(self, user):
        make_creator_subscription(user)
        BotSubscription.objects.filter(user=user).update(
            status="active",
            expires_at=timezone.now() - timedelta(days=1),
            grace_until=None,
        )
        assert ReferralRewardService.referrer_earns_commission(user) is False

    def test_grace_window_still_earns(self, user):
        make_creator_subscription(user)
        BotSubscription.objects.filter(user=user).update(
            status="active",
            expires_at=timezone.now() - timedelta(hours=1),
            grace_until=timezone.now() + timedelta(days=1),
        )
        assert ReferralRewardService.referrer_earns_commission(user) is True

    def test_non_creator_plan_does_not_earn(self, user):
        make_free_plan_bot_subscription(user, bot_type="grid")
        assert ReferralRewardService.referrer_earns_commission(user) is False

    def test_null_bridge_plan_does_not_earn(self, user):
        """BotSubscriptionPlan.subscription_plan is NULL (pure per-bot plan
        like grid/martingale) — tier walk must not crash, returns None."""
        bsp = BotSubscriptionPlan.objects.create(
            bot_type="grid",
            name="null-bridge",
            price=Decimal("49.99"),
            duration_days=30,
        )
        # explicitly NULL bridge (default is already None, but be explicit)
        assert bsp.subscription_plan is None
        BotSubscription.objects.create(
            user=user,
            plan=bsp,
            status="active",
            expires_at=timezone.now() + timedelta(days=30),
        )
        assert ReferralRewardService.referrer_earns_commission(user) is False

    def test_pending_sub_does_not_earn(self, user):
        make_creator_subscription(user)
        BotSubscription.objects.filter(user=user).update(status="pending_approval")
        assert ReferralRewardService.referrer_earns_commission(user) is False


# ====================================================== referee discount


class TestRefereeDiscount:
    def test_referred_by_non_creator_gets_discount(self, user, second_user):
        make_free_plan_bot_subscription(second_user)  # referrer NOT creator
        make_referral(second_user, user)
        assert ReferralRewardService.referee_discount_pct(user) == Decimal("15")

    def test_referred_by_creator_gets_no_discount(self, user, second_user):
        make_creator_subscription(second_user)
        make_referral(second_user, user)
        assert ReferralRewardService.referee_discount_pct(user) == Decimal("0")

    def test_unreferred_gets_no_discount(self, user):
        assert ReferralRewardService.referee_discount_pct(user) == Decimal("0")

    def test_rejected_referral_gets_no_discount(self, user, second_user):
        make_free_plan_bot_subscription(second_user)
        ref = make_referral(second_user, user)
        ref.status = "rejected"
        ref.save(update_fields=["status"])
        assert ReferralRewardService.referee_discount_pct(user) == Decimal("0")

    def test_prior_active_sub_gets_no_discount(self, user, second_user):
        make_free_plan_bot_subscription(second_user)
        make_referral(second_user, user)
        # referee already has an active sub → no longer "first payment"
        make_free_plan_bot_subscription(user)
        assert ReferralRewardService.referee_discount_pct(user) == Decimal("0")

    def test_pending_payment_sub_still_eligible(self, user, second_user):
        """pending_payment = no proof yet, does not count as a prior payment."""
        make_free_plan_bot_subscription(second_user)
        make_referral(second_user, user)
        bsp = BotSubscriptionPlan.objects.create(
            bot_type="grid", name="pending-grid", price=Decimal("49.99"), duration_days=30
        )
        BotSubscription.objects.create(user=user, plan=bsp, status="pending_payment")
        assert ReferralRewardService.referee_discount_pct(user) == Decimal("15")

    def test_prior_telegram_sub_blocks_discount(self, user, second_user):
        """An ACTIVE TelegramSubscription (not bot) also counts as a prior
        paid subscription — the discount is first-payment-only across BOTH
        subscription tables."""
        from apps.subscriptions.models import TelegramSignalPlan, TelegramSubscription

        make_free_plan_bot_subscription(second_user)
        make_referral(second_user, user)
        tsp = TelegramSignalPlan.objects.create(
            name="Signals",
            slug="signals-2",
            description="t",
            price_monthly=Decimal("50"),
            price_quarterly=Decimal("135"),
            price_yearly=Decimal("480"),
        )
        TelegramSubscription.objects.create(
            user=user,
            plan=tsp,
            telegram_handle="tester",
            status="active",
            amount_paid=Decimal("50"),
        )
        assert ReferralRewardService.referee_discount_pct(user) == Decimal("0")


# ==================================================== discount claim (race)


class TestClaimRefereeDiscount:
    """claim_referee_discount = the atomic (select_for_update) variant used by
    the subscribe views. SQLite ignores FOR UPDATE (lock is a no-op) so the
    true race is Postgres-only; these tests verify the eligibility + atomic
    integration, the race itself is covered by the regression doc."""

    def test_eligible_first_time_gets_pct(self, user, second_user):
        from django.db import transaction

        make_free_plan_bot_subscription(second_user)
        make_referral(second_user, user)
        with transaction.atomic():
            assert ReferralRewardService.claim_referee_discount(user) == Decimal("15")

    def test_zero_after_subscription_exists(self, user, second_user):
        """Second request after the first committed: has_prior is now True."""
        from django.db import transaction

        make_free_plan_bot_subscription(second_user)
        make_referral(second_user, user)
        make_free_plan_bot_subscription(user)  # first purchase already done
        with transaction.atomic():
            assert ReferralRewardService.claim_referee_discount(user) == Decimal("0")

    def test_unreferred_gets_zero(self, user):
        from django.db import transaction

        with transaction.atomic():
            assert ReferralRewardService.claim_referee_discount(user) == Decimal("0")

    def test_creator_referrer_gets_zero(self, user, second_user):
        """Referrer is creator-tier → commission model, no referee discount."""
        from django.db import transaction

        make_creator_subscription(second_user)
        make_referral(second_user, user)
        with transaction.atomic():
            assert ReferralRewardService.claim_referee_discount(user) == Decimal("0")

    def test_matches_referee_discount_pct(self, user, second_user):
        """For a single-threaded eligible user, claim == referee_discount_pct."""
        from django.db import transaction

        make_free_plan_bot_subscription(second_user)
        make_referral(second_user, user)
        with transaction.atomic():
            claimed = ReferralRewardService.claim_referee_discount(user)
        read = ReferralRewardService.referee_discount_pct(user)
        assert claimed == read == Decimal("15")


# ========================================================== accrual hook


class TestRecordSubscriptionPayment:
    def test_bot_accrual_for_creator_referrer(self, user, second_user):
        make_creator_subscription(second_user)  # second_user is creator referrer
        make_referral(second_user, user)
        bsp = BotSubscriptionPlan.objects.create(
            bot_type="grid", name="g", price=Decimal("100"), duration_days=30
        )
        sub = BotSubscription.objects.create(
            user=user, plan=bsp, status="pending_approval", amount_due=Decimal("100")
        )
        tx = ReferralRewardService.record_subscription_payment(sub, kind="bot")
        assert tx is not None
        assert tx.transaction_type == "subscription"
        assert tx.amount == Decimal("100.00")
        payout = ReferralPayout.objects.get(referrer=second_user)
        assert payout.amount == Decimal("10.00")  # 10% of 100
        assert payout.status == "pending"
        assert payout.source_transaction == tx

    def test_bot_no_accrual_non_creator_referrer(self, user, second_user):
        make_free_plan_bot_subscription(second_user)
        make_referral(second_user, user)
        bsp = BotSubscriptionPlan.objects.create(
            bot_type="grid", name="g", price=Decimal("100"), duration_days=30
        )
        sub = BotSubscription.objects.create(
            user=user, plan=bsp, status="pending_approval", amount_due=Decimal("100")
        )
        tx = ReferralRewardService.record_subscription_payment(sub, kind="bot")
        assert tx is not None
        assert ReferralPayout.objects.count() == 0

    def test_bot_no_accrual_unreferred(self, user):
        bsp = BotSubscriptionPlan.objects.create(
            bot_type="grid", name="g", price=Decimal("100"), duration_days=30
        )
        sub = BotSubscription.objects.create(
            user=user, plan=bsp, status="pending_approval", amount_due=Decimal("100")
        )
        tx = ReferralRewardService.record_subscription_payment(sub, kind="bot")
        assert tx is not None
        assert ReferralPayout.objects.count() == 0

    def test_zero_basis_returns_none(self, user, second_user):
        make_creator_subscription(second_user)
        make_referral(second_user, user)
        bsp = BotSubscriptionPlan.objects.create(
            bot_type="grid", name="g", price=Decimal("0"), duration_days=30
        )
        sub = BotSubscription.objects.create(
            user=user, plan=bsp, status="pending_approval", amount_due=Decimal("0")
        )
        assert ReferralRewardService.record_subscription_payment(sub, kind="bot") is None
        assert ReferralPayout.objects.count() == 0

    def test_telegram_accrual(self, user, second_user):
        from apps.subscriptions.models import TelegramSignalPlan, TelegramSubscription

        make_creator_subscription(second_user)
        make_referral(second_user, user)
        tsp = TelegramSignalPlan.objects.create(
            name="Signals",
            slug="signals",
            description="Test signals",
            price_monthly=Decimal("50"),
            price_quarterly=Decimal("135"),
            price_yearly=Decimal("480"),
        )
        sub = TelegramSubscription.objects.create(
            user=user,
            plan=tsp,
            telegram_handle="tester",
            status="pending_approval",
            amount_paid=Decimal("50.00"),
        )
        tx = ReferralRewardService.record_subscription_payment(sub, kind="telegram")
        assert tx is not None
        payout = ReferralPayout.objects.get(referrer=second_user)
        assert payout.amount == Decimal("5.00")  # 10% of 50

    def test_bot_accrual_amount_due_none_falls_back_to_price(self, user, second_user):
        """amount_due=None → commission basis falls back to plan.price."""
        make_creator_subscription(second_user)
        make_referral(second_user, user)
        bsp = BotSubscriptionPlan.objects.create(
            bot_type="grid",
            name="fallback-grid",
            price=Decimal("49.99"),
            duration_days=30,
        )
        sub = BotSubscription.objects.create(
            user=user,
            plan=bsp,
            status="pending_approval",
            amount_due=None,  # no discount applied
        )
        tx = ReferralRewardService.record_subscription_payment(sub, kind="bot")
        assert tx is not None
        assert tx.amount == Decimal("49.99")  # plan.price fallback
        payout = ReferralPayout.objects.get(referrer=second_user)
        assert payout.amount == Decimal("5.00")  # 10% of 49.99 → 4.999 → 5.00

    def test_disabled_commission_pct(self, user, second_user):
        from core.models import SiteConfig

        sc = SiteConfig.get()
        sc.referral_config = {"commission_pct": 0}
        sc.save()
        SiteConfig.get.cache_clear()
        make_creator_subscription(second_user)
        make_referral(second_user, user)
        bsp = BotSubscriptionPlan.objects.create(
            bot_type="grid", name="g", price=Decimal("100"), duration_days=30
        )
        sub = BotSubscription.objects.create(
            user=user, plan=bsp, status="pending_approval", amount_due=Decimal("100")
        )
        tx = ReferralRewardService.record_subscription_payment(sub, kind="bot")
        assert tx is not None
        assert ReferralPayout.objects.count() == 0


# ======================================================== payout requests


class TestRequestPayout:
    def test_success(self, user, second_user):
        accrue(user, second_user, Decimal("60"))
        req = ReferralRewardService.request_payout(user=user, amount=Decimal("50"))
        assert req.status == "pending"
        assert req.amount_requested == Decimal("50.00")

    def test_below_minimum(self, user, second_user):
        accrue(user, second_user, Decimal("60"))
        with pytest.raises(ReferralRewardError, match="Minimum payout"):
            ReferralRewardService.request_payout(user=user, amount=Decimal("30"))

    def test_exceeds_balance(self, user, second_user):
        accrue(user, second_user, Decimal("10"))
        with pytest.raises(ReferralRewardError, match="exceeds pending"):
            ReferralRewardService.request_payout(user=user, amount=Decimal("50"))

    def test_duplicate_pending_rejected(self, user, second_user):
        accrue(user, second_user, Decimal("100"))
        ReferralRewardService.request_payout(user=user, amount=Decimal("50"))
        with pytest.raises(ReferralRewardError, match="pending payout request"):
            ReferralRewardService.request_payout(user=user, amount=Decimal("60"))

    def test_zero_amount_rejected(self, user):
        with pytest.raises(ReferralRewardError, match="> 0"):
            ReferralRewardService.request_payout(user=user, amount=Decimal("0"))


class TestApprovePayout:
    def test_fifo_settlement(self, user, second_user, admin_user):
        accrue(user, second_user, Decimal("30"))
        accrue(user, second_user, Decimal("30"))
        req = ReferralRewardService.request_payout(user=user, amount=Decimal("50"))
        decided = ReferralRewardService.approve_payout_request(
            request_id=req.id, admin=admin_user, payout_amount=Decimal("50")
        )
        assert decided.status == "approved"
        assert decided.admin_entered_payout == Decimal("50.00")
        assert decided.decided_by == admin_user
        assert decided.payment_transaction is not None
        assert decided.payment_transaction.transaction_type == "referral_payout"
        # FIFO: first accrual fully paid, second partially paid
        p1, p2 = ReferralPayout.objects.filter(referrer=user).order_by("created_at")
        assert p1.status == "paid"
        assert p2.status == "paid"  # 30+30=60 >= 50 → both paid

    def test_partial_fifo(self, user, second_user, admin_user):
        """When the first accrual alone covers amount_requested, the second
        accrual stays pending (FIFO slice, not full drain). payout_amount=48
        = realistic fee-reduced net (requested 50, 2 in network fees)."""
        accrue(user, second_user, Decimal("60"))
        accrue(user, second_user, Decimal("30"))
        req = ReferralRewardService.request_payout(user=user, amount=Decimal("50"))
        decided = ReferralRewardService.approve_payout_request(
            request_id=req.id, admin=admin_user, payout_amount=Decimal("48")
        )
        assert decided.status == "approved"
        assert decided.admin_entered_payout == Decimal("48")
        p1, p2 = ReferralPayout.objects.filter(referrer=user).order_by("created_at")
        assert p1.status == "paid"  # 60 >= 50 → fully covers
        assert p2.status == "pending"  # untouched

    def test_already_decided(self, user, second_user, admin_user):
        accrue(user, second_user, Decimal("60"))
        req = ReferralRewardService.request_payout(user=user, amount=Decimal("50"))
        ReferralRewardService.approve_payout_request(
            request_id=req.id, admin=admin_user, payout_amount=Decimal("50")
        )
        with pytest.raises(ReferralRewardError, match="already approved"):
            ReferralRewardService.approve_payout_request(
                request_id=req.id, admin=admin_user, payout_amount=Decimal("50")
            )

    def test_nonpositive_amount(self, user, second_user, admin_user):
        accrue(user, second_user, Decimal("60"))
        req = ReferralRewardService.request_payout(user=user, amount=Decimal("50"))
        with pytest.raises(ReferralRewardError, match="> 0"):
            ReferralRewardService.approve_payout_request(
                request_id=req.id, admin=admin_user, payout_amount=Decimal("0")
            )

    def test_payout_above_requested_rejected(self, user, second_user, admin_user):
        """Business-rule guard: fees reduce the net payout, never increase it.
        payout_amount must not exceed amount_requested (admin typo guard)."""
        accrue(user, second_user, Decimal("60"))
        req = ReferralRewardService.request_payout(user=user, amount=Decimal("50"))
        with pytest.raises(ReferralRewardError, match="exceeds the requested"):
            ReferralRewardService.approve_payout_request(
                request_id=req.id, admin=admin_user, payout_amount=Decimal("75")
            )

    def test_payout_equal_to_requested_ok(self, user, second_user, admin_user):
        """payout_amount == amount_requested is the normal full-payout path."""
        accrue(user, second_user, Decimal("60"))
        req = ReferralRewardService.request_payout(user=user, amount=Decimal("50"))
        decided = ReferralRewardService.approve_payout_request(
            request_id=req.id, admin=admin_user, payout_amount=Decimal("50")
        )
        assert decided.status == "approved"

    def test_balance_shrank(self, user, second_user, admin_user):
        accrue(user, second_user, Decimal("60"))
        req = ReferralRewardService.request_payout(user=user, amount=Decimal("50"))
        # cancel accrual
        ReferralPayout.objects.filter(referrer=user).update(status="cancelled")
        with pytest.raises(ReferralRewardError, match="no longer covers"):
            ReferralRewardService.approve_payout_request(
                request_id=req.id, admin=admin_user, payout_amount=Decimal("50")
            )


class TestRejectPayout:
    def test_reject_keeps_accruals(self, user, second_user, admin_user):
        accrue(user, second_user, Decimal("60"))
        req = ReferralRewardService.request_payout(user=user, amount=Decimal("50"))
        decided = ReferralRewardService.reject_payout_request(
            request_id=req.id, admin=admin_user, notes="insufficient docs"
        )
        assert decided.status == "rejected"
        assert decided.admin_notes == "insufficient docs"
        assert decided.decided_by == admin_user
        # accruals stay pending
        assert ReferralPayout.objects.get(referrer=user).status == "pending"

    def test_reject_already_decided(self, user, second_user, admin_user):
        accrue(user, second_user, Decimal("60"))
        req = ReferralRewardService.request_payout(user=user, amount=Decimal("50"))
        ReferralRewardService.reject_payout_request(request_id=req.id, admin=admin_user)
        with pytest.raises(ReferralRewardError, match="already rejected"):
            ReferralRewardService.reject_payout_request(request_id=req.id, admin=admin_user)


# ============================================================ API views


class TestPayoutRequestsAPI:
    def test_get_own_requests(self, user, second_user, auth_client):
        accrue(user, second_user, Decimal("60"))
        ReferralRewardService.request_payout(user=user, amount=Decimal("50"))
        url = reverse("referrals:payout-requests")
        resp = auth_client.get(url)
        assert resp.status_code == status.HTTP_200_OK
        rows = resp.data["payout_requests"]
        assert len(rows) == 1
        assert Decimal(str(rows[0]["amount_requested"])) == Decimal("50.00")

    def test_post_success(self, user, second_user, auth_client):
        accrue(user, second_user, Decimal("60"))
        url = reverse("referrals:payout-requests")
        resp = auth_client.post(url, {"amount": "50"}, format="json")
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data["status"] == "pending"

    def test_post_below_minimum(self, user, second_user, auth_client):
        accrue(user, second_user, Decimal("60"))
        url = reverse("referrals:payout-requests")
        resp = auth_client.post(url, {"amount": "30"}, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_post_exceeds_balance(self, user, second_user, auth_client):
        accrue(user, second_user, Decimal("10"))
        url = reverse("referrals:payout-requests")
        resp = auth_client.post(url, {"amount": "50"}, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_unauthenticated(self, api_client):
        url = reverse("referrals:payout-requests")
        resp = api_client.get(url)
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


class TestAdminPayoutDecideAPI:
    def test_approve_endpoint(self, user, second_user, admin_user, admin_client):
        accrue(user, second_user, Decimal("60"))
        req = ReferralRewardService.request_payout(user=user, amount=Decimal("50"))
        url = reverse("payments:admin-payout-request-approve", args=[req.id])
        resp = admin_client.post(
            url, {"payout_amount": "50", "notes": "paid via USDT"}, format="json"
        )
        assert resp.status_code == status.HTTP_200_OK
        req.refresh_from_db()
        assert req.status == "approved"

    def test_reject_endpoint(self, user, second_user, admin_user, admin_client):
        accrue(user, second_user, Decimal("60"))
        req = ReferralRewardService.request_payout(user=user, amount=Decimal("50"))
        url = reverse("payments:admin-payout-request-reject", args=[req.id])
        resp = admin_client.post(url, {"notes": "docs missing"}, format="json")
        assert resp.status_code == status.HTTP_200_OK
        req.refresh_from_db()
        assert req.status == "rejected"

    def test_non_admin_forbidden(self, user, second_user, auth_client):
        accrue(user, second_user, Decimal("60"))
        req = ReferralRewardService.request_payout(user=user, amount=Decimal("50"))
        url = reverse("payments:admin-payout-request-approve", args=[req.id])
        resp = auth_client.post(url, {"payout_amount": "50"}, format="json")
        assert resp.status_code == status.HTTP_403_FORBIDDEN


class TestMyStatsHybridFields:
    def test_commission_referrer(self, user, second_user, auth_client):
        """user = creator referrer → reward_model=commission, balances shown."""
        make_creator_subscription(user)
        accrue(user, second_user, Decimal("60"))
        accrue(user, second_user, Decimal("40"))
        ReferralPayout.objects.filter(referrer=user, amount=Decimal("40")).update(status="paid")
        url = reverse("referrals:my-referral-stats")
        resp = auth_client.get(url)
        assert resp.status_code == status.HTTP_200_OK
        d = resp.data
        assert d["reward_model"] == "commission"
        assert Decimal(d["commission_pct"]) == Decimal("10")
        assert Decimal(d["commission_pending_usd"]) == Decimal("60.00")
        assert Decimal(d["commission_paid_usd"]) == Decimal("40.00")
        assert Decimal(d["payout_minimum_usd"]) == Decimal("50")
        assert d["referee_discount_pct"] is None

    def test_discount_referrer(self, user, second_user, auth_client):
        """user = non-creator referrer → reward_model=referee_discount."""
        make_free_plan_bot_subscription(user)
        url = reverse("referrals:my-referral-stats")
        resp = auth_client.get(url)
        assert resp.status_code == status.HTTP_200_OK
        d = resp.data
        assert d["reward_model"] == "referee_discount"
        assert Decimal(d["referee_discount_pct"]) == Decimal("15")
        assert d["commission_pct"] is None
        assert d["has_pending_payout_request"] is False

    def test_has_pending_payout_request_flag(self, user, second_user, auth_client):
        accrue(user, second_user, Decimal("60"))
        ReferralRewardService.request_payout(user=user, amount=Decimal("50"))
        url = reverse("referrals:my-referral-stats")
        resp = auth_client.get(url)
        assert resp.data["has_pending_payout_request"] is True
