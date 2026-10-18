"""FR A2 Model C plan-limit gates — full scenario matrix.

Covers (one class per surface):
- get_plan_limit: Model C SubscriptionPlan row is authoritative per slug
  (SiteConfig.get_plan_limit consults the row BEFORE the legacy
  SiteConfig.plan_limits JSON; not filtered on is_active).
- Creation gates: type 403 / seat 429 via enforce_bot_creation, plus the
  legacy/none no-op parity (G4 keeps owning per-bot subscriptions — gate
  never fires twice) and quantum_ai type-exemption with seat still applied.
- Webhook quota: plan-level signals/month summed across the user's live
  signal bots, enforced BEFORE the legacy per-bot block, counter increments.
- MyUsageView additive keys: row-authoritative limits, UNLIMITED sentinel
  for legacy/none, plan_slug/bot_types None outside Model C.
- approve(): Model C syncs the profile (slug + seat recompute); legacy
  approvals never touch the profile.
- expiry: hard-stopped Model C row drops profile to free ONLY when it
  governs it and no other usable Model C row remains; legacy never touched.
- effective_limits: source resolution (model_c > legacy > none, custom shim
  preferred, hard-stopped rows unusable).

Scenario-matrix convention: every gate has a matching "not gated" test so
legacy/none behaviour is pinned byte-stable, not just assumed.
"""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

# Reuse the webhook signing/payload helpers so quota tests exercise the exact
# auth path production TradingView alerts use (tests package is importable).
from tests.webhooks.test_views import _build_payload, _sign

SIGNAL_URL = "/api/bots/signal-bots/"
GRID_URL = "/api/bots/grid-bots/"
MARTINGALE_URL = "/api/bots/martingale-bots/"
QUANTUM_INVESTMENT_URL = "/api/bots/quantum-investments/"
UNLIMITED = 2_147_483_647  # matches MyUsageView's sentinel


# ==================== HELPERS ====================


def _mk_plan(slug, *, max_bots, bot_types, signals=100, name=None, is_active=True):
    """Create a Model C SubscriptionPlan row (the admin-editable SoT)."""
    from apps.payments.models import SubscriptionPlan

    return SubscriptionPlan.objects.create(
        name=name or slug.title(),
        slug=slug,
        price_monthly=Decimal("19.99"),
        price_yearly=Decimal("199.99"),
        max_bots_allowed=max_bots,
        max_webhooks_allowed=10,
        bot_types=bot_types,
        max_signals_per_month=signals,
        is_active=is_active,
    )


def _mk_model_c_sub(
    user,
    plan,
    *,
    days=30,
    status_="active",
    hard_stopped=False,
    shim_features=None,
    bot_type="custom",
):
    """Mirror the SubscribeView shim: BotSubscriptionPlan linked to the row.

    ``shim_features`` defaults to deliberately STALE values (999) so every
    consumer test proves the linked SubscriptionPlan row wins over the shim's
    own features dict. ``hard_stopped`` keeps status="active" but stamps both
    expires_at and grace_until in the past (live-date hard stop).
    """
    from apps.payments.models import BotSubscription, BotSubscriptionPlan

    if shim_features is None:
        shim_features = {"max_bots": 999, "max_webhooks": 999}
    shim = BotSubscriptionPlan.objects.create(
        bot_type=bot_type,
        name=f"{plan.name} Shim",
        price=plan.price_monthly,
        duration_days=30,
        features=shim_features,
        subscription_plan=plan,
    )
    now = timezone.now()
    if hard_stopped:
        expires_at = now - timedelta(days=1)
        grace_until = now - timedelta(days=1)
    else:
        expires_at = now + timedelta(days=days)
        grace_until = expires_at + timedelta(days=2)
    return BotSubscription.objects.create(
        user=user,
        plan=shim,
        status=status_,
        expires_at=expires_at,
        grace_until=grace_until,
    )


def _signal_data(bot_name="Gate Bot"):
    """Valid SignalBotCreateSerializer payload (mirrors existing green test)."""
    return {
        "bot_name": bot_name,
        "exchange_name": "binance",
        "market_type": "spot",
        "trading_pair": "BTC/USDT",
        "default_amount": "0.01",
    }


def _grid_data(bot_name="Gate Grid"):
    """Valid GridBotCreateSerializer payload (mirrors existing green test)."""
    return {
        "bot_name": bot_name,
        "exchange_name": "binance",
        "trading_pair": "BTC/USDT",
        "base_amount": "0.001",
        "favor_levels": 5,
        "against_levels": 5,
    }


def _martingale_data(bot_name="Gate Martingale"):
    """Valid MartingaleBotCreateSerializer payload (mirrors existing green test)."""
    return {
        "bot_name": bot_name,
        "exchange_name": "binance",
        "trading_pair": "BTC/USDT",
        "base_amount": "0.01",
        "favor_levels": 3,
        "against_levels": 3,
    }


def _mk_signal_bot_row(user, bot_name="Pre-created", *, is_deleted=False, used=0):
    """ORM seat-count row (no subscription → never trips unique_together)."""
    from apps.bots.models import SignalBot

    return SignalBot.objects.create(
        user=user,
        bot_name=bot_name,
        exchange_name="binance",
        trading_pair="BTC/USDT",
        default_amount=Decimal("10"),
        is_active=True,
        is_deleted=is_deleted,
        signals_used_this_month=used,
    )


@pytest.fixture
def mock_execute_trade():
    with patch("apps.webhooks.views.SignalBotWebhookView.execute_trade") as mock:
        mock.return_value = {
            "status": "success",
            "order_id": "mock-order-123",
            "timestamp": 1234567890000,
            "amount": 0.001,
            "price": 50000.0,
            "cost": 50.0,
            "exchange": "binance",
        }
        yield mock


# ==================== 1. get_plan_limit ====================


@pytest.mark.django_db
class TestGetPlanLimitModelC:
    def test_row_wins_over_json_defaults(self, user):
        # JSON fallback would give default=3 for an unknown slug; the row says 7.
        _mk_plan("standard", max_bots=7, bot_types=["signal"])
        user.subscription_plan = "standard"
        user.save()
        assert user.max_bots_allowed == 7

    def test_missing_row_falls_back_to_json(self, user):
        # No row for this slug → SiteConfig.plan_limits JSON path stays
        # reachable (the fallback JSON lives on SiteConfig, not on User).
        from core.models import SiteConfig

        cfg = SiteConfig.get()
        cfg.plan_limits = {"gold": 42}
        cfg.save()
        user.subscription_plan = "gold"
        user.save()
        assert user.max_bots_allowed == 42

    def test_row_used_even_when_deactivated(self, user):
        # Deactivation gates sales, it must not loosen limits for holders.
        _mk_plan("premium", max_bots=9, bot_types=["signal"], is_active=False)
        user.subscription_plan = "premium"
        user.save()
        assert user.max_bots_allowed == 9

    def test_siteconfig_reads_row(self, user):
        from core.models import SiteConfig

        _mk_plan("enterprise", max_bots=50, bot_types=["signal"])
        assert SiteConfig.get().get_plan_limit("enterprise") == 50

    def test_defaults_untouched_without_any_row(self, user):
        # Row absence → built-in defaults (free=3) stay byte-stable.
        user.subscription_plan = "free"
        user.save()
        assert user.max_bots_allowed == 3


# ==================== 2. Creation gates ====================


@pytest.mark.django_db
class TestBotCreationGates:
    def test_type_gate_blocks_disallowed(self, auth_client, user):
        # Plan sells grid+martingale only → signal create must 403.
        plan = _mk_plan("standard", max_bots=5, bot_types=["grid", "martingale"])
        _mk_model_c_sub(user, plan)
        resp = auth_client.post(SIGNAL_URL, _signal_data(), format="json")
        assert resp.status_code == status.HTTP_403_FORBIDDEN
        assert resp.data["error"]["code"] == "PERMISSION_DENIED"

    def test_type_gate_allows_listed_and_attaches_shared_sub(self, auth_client, user):
        plan = _mk_plan("standard", max_bots=5, bot_types=["signal", "grid"])
        sub = _mk_model_c_sub(user, plan)
        resp = auth_client.post(SIGNAL_URL, _signal_data(), format="json")
        assert resp.status_code == status.HTTP_201_CREATED, resp.data
        # Model C: the shared Model C subscription row IS the bot's sub.
        from apps.bots.models import SignalBot

        bot = SignalBot.objects.get(bot_name="Gate Bot")
        assert bot.subscription_id == sub.id

    def test_seat_gate_429_at_plan_limit(self, auth_client, user):
        plan = _mk_plan("standard", max_bots=1, bot_types=["signal", "grid"])
        _mk_model_c_sub(user, plan)
        _mk_signal_bot_row(user)  # seat 1/1 used
        resp = auth_client.post(SIGNAL_URL, _signal_data(), format="json")
        assert resp.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert resp.data["error"]["code"] == "BOT_LIMIT_EXCEEDED"

    def test_soft_deleted_bots_do_not_consume_seats(self, auth_client, user):
        plan = _mk_plan("standard", max_bots=1, bot_types=["signal"])
        _mk_model_c_sub(user, plan)
        _mk_signal_bot_row(user, is_deleted=True)
        resp = auth_client.post(SIGNAL_URL, _signal_data(), format="json")
        assert resp.status_code == status.HTTP_201_CREATED, resp.data

    def test_grid_seat_gate_counts_other_bot_types(self, auth_client, user):
        # Seats are cross-type: a signal bot fills the only grid seat too.
        plan = _mk_plan("standard", max_bots=1, bot_types=["signal", "grid"])
        _mk_model_c_sub(user, plan)
        _mk_signal_bot_row(user)
        resp = auth_client.post(GRID_URL, _grid_data(), format="json")
        assert resp.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert resp.data["error"]["code"] == "BOT_LIMIT_EXCEEDED"

    def test_second_grid_allowed_under_model_c(self, auth_client, user):
        # Shared-sub contract (2026-10-18): the one Model C subscription
        # holds MANY grids — seat count is the only cap (1-per-sub 400 and
        # DB unique_together removed for model_c source only; legacy pin
        # lives in tests/bots/test_views.py::test_create_duplicate_grid_bot_fails).
        plan = _mk_plan("standard", max_bots=3, bot_types=["grid"])
        sub = _mk_model_c_sub(user, plan)
        r1 = auth_client.post(GRID_URL, _grid_data("Grid One"), format="json")
        assert r1.status_code == status.HTTP_201_CREATED, r1.data
        r2 = auth_client.post(GRID_URL, _grid_data("Grid Two"), format="json")
        assert r2.status_code == status.HTTP_201_CREATED, r2.data
        from apps.bots.models import GridBot

        assert GridBot.objects.filter(subscription=sub, is_deleted=False).count() == 2

    def test_second_martingale_allowed_under_model_c(self, auth_client, user):
        # Same shared-sub contract as the grid test above; legacy 1-per-sub
        # pin: tests/bots/test_views.py::test_create_duplicate_martingale_fails.
        plan = _mk_plan("standard", max_bots=3, bot_types=["martingale"])
        sub = _mk_model_c_sub(user, plan)
        r1 = auth_client.post(MARTINGALE_URL, _martingale_data("Mart One"), format="json")
        assert r1.status_code == status.HTTP_201_CREATED, r1.data
        r2 = auth_client.post(MARTINGALE_URL, _martingale_data("Mart Two"), format="json")
        assert r2.status_code == status.HTTP_201_CREATED, r2.data
        from apps.bots.models import MartingaleBot

        assert MartingaleBot.objects.filter(subscription=sub, is_deleted=False).count() == 2

    def test_legacy_not_count_gated(self, auth_client, user, signal_bot_subscription):
        # Parity pin: legacy G4 access is seat-blind (enforce is a no-op).
        # Profile default max is 3 — 4 pre-created bots would trip a Model C
        # seat gate, so a 201 here proves legacy never enters the count gate.
        for i in range(4):
            _mk_signal_bot_row(user, bot_name=f"Legacy {i}")
        resp = auth_client.post(SIGNAL_URL, _signal_data(), format="json")
        assert resp.status_code == status.HTTP_201_CREATED, resp.data

    def test_no_subscription_source_never_count_gated(self, auth_client, user):
        # source="none" → G4 (not enforce) rejects; no 429 can leak out.
        resp = auth_client.post(SIGNAL_URL, _signal_data(), format="json")
        assert resp.status_code == status.HTTP_403_FORBIDDEN
        assert resp.data["error"]["code"] == "PERMISSION_DENIED"

    def test_quantum_type_exempt_but_seat_gated(
        self, auth_client, user, quantum_fund, quantum_ai_subscription
    ):
        # Q2: quantum_ai is not a Model C bot type (empty list → type gate
        # skipped) but the shared seat count still applies → 429, not 403.
        plan = _mk_plan("standard", max_bots=1, bot_types=[])
        _mk_model_c_sub(user, plan)
        _mk_signal_bot_row(user)
        resp = auth_client.post(
            QUANTUM_INVESTMENT_URL,
            {
                "fund": str(quantum_fund.id),
                "amount": "1000",
                "subscription": str(quantum_ai_subscription.id),
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert resp.data["error"]["code"] == "BOT_LIMIT_EXCEEDED"

    def test_quantum_without_model_c_never_seat_gated(
        self, auth_client, user, quantum_fund, quantum_ai_subscription
    ):
        # Legacy-only quantum: G4 passes, enforce no-ops → 201 (parity).
        resp = auth_client.post(
            QUANTUM_INVESTMENT_URL,
            {
                "fund": str(quantum_fund.id),
                "amount": "1000",
                "subscription": str(quantum_ai_subscription.id),
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED, resp.data


# ==================== 3. Webhook Model C quota ====================


@pytest.mark.django_db
class TestWebhookModelCQuota:
    def _post(self, api_client, bot, **overrides):
        payload = _build_payload(bot_id=bot.bot_id, **overrides)
        sig = _sign(payload, bot.secret_key)
        return api_client.post(
            reverse("webhooks:signalbot_webhook"),
            payload,
            format="json",
            HTTP_X_SIGNATURE=sig,
        )

    def test_blocks_at_plan_limit_across_bots(self, api_client, signal_bot, user):
        # Plan limit 2; ANOTHER of the user's bots already used 2 → block
        # even though this bot is at 0 (plan-level, not per-bot).
        plan = _mk_plan("standard", max_bots=5, bot_types=["signal"], signals=2)
        sub = _mk_model_c_sub(user, plan)
        signal_bot.subscription = sub
        signal_bot.save()
        _mk_signal_bot_row(user, bot_name="Other", used=2)
        resp = self._post(api_client, signal_bot)
        assert resp.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert "Monthly signal limit reached" in str(resp.data)

    def test_blocks_on_cross_bot_sum_not_just_own_counter(self, api_client, signal_bot, user):
        # limit 1, other bot used 1, this bot 0 → still blocked (sum).
        plan = _mk_plan("standard", max_bots=5, bot_types=["signal"], signals=1)
        sub = _mk_model_c_sub(user, plan)
        signal_bot.subscription = sub
        signal_bot.save()
        _mk_signal_bot_row(user, bot_name="Other", used=1)
        resp = self._post(api_client, signal_bot)
        assert resp.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    def test_allows_below_limit_and_increments_counter(
        self,
        api_client,
        signal_bot,
        user,
        exchange_credentials,
        mock_execute_trade,
    ):
        plan = _mk_plan("standard", max_bots=5, bot_types=["signal"], signals=10)
        sub = _mk_model_c_sub(user, plan)
        signal_bot.subscription = sub
        signal_bot.save()
        _mk_signal_bot_row(user, bot_name="Other", used=1)
        resp = self._post(api_client, signal_bot)
        assert resp.status_code == status.HTTP_200_OK, resp.data
        signal_bot.refresh_from_db()
        assert signal_bot.signals_used_this_month == 1  # 0 → +1 after trade

    def test_soft_deleted_bots_excluded_from_sum(
        self, api_client, signal_bot, user, exchange_credentials, mock_execute_trade
    ):
        # A deleted bot holding 9999 must not push a live user over the edge.
        plan = _mk_plan("standard", max_bots=5, bot_types=["signal"], signals=2)
        sub = _mk_model_c_sub(user, plan)
        signal_bot.subscription = sub
        signal_bot.save()
        _mk_signal_bot_row(user, bot_name="Deleted", is_deleted=True, used=9999)
        resp = self._post(api_client, signal_bot)
        assert resp.status_code == status.HTTP_200_OK, resp.data

    def test_legacy_subscribed_bypass_stays_open(
        self,
        api_client,
        signal_bot,
        signal_bot_subscription,
        exchange_credentials,
        mock_execute_trade,
    ):
        # Parity pin: legacy sub → plan.subscription_plan is NULL → branch
        # skipped entirely (the G4-era per-bot bypass must stay byte-stable).
        signal_bot.signals_used_this_month = 9999
        signal_bot.subscription = signal_bot_subscription
        signal_bot.save()
        resp = self._post(api_client, signal_bot)
        assert resp.status_code == status.HTTP_200_OK, resp.data


# ==================== 4. MyUsageView additive keys ====================


@pytest.mark.django_db
class TestMyUsageAdditiveKeys:
    def test_model_c_row_authoritative_over_stale_shim(self, auth_client, user):
        # Shim features say 999; the linked row (5/77) must win everywhere.
        plan = _mk_plan("standard", max_bots=5, bot_types=["signal", "grid"], signals=77)
        _mk_model_c_sub(user, plan, shim_features={"max_bots": 999, "max_webhooks": 999})
        _mk_signal_bot_row(user, bot_name="A", used=3)
        _mk_signal_bot_row(user, bot_name="B", used=4)
        resp = auth_client.get(reverse("subscriptions:my-usage"))
        assert resp.status_code == status.HTTP_200_OK
        limits = resp.data["limits"]
        assert limits["max_bots"] == 5
        assert limits["max_webhooks"] == 10
        assert limits["max_signals_per_month"] == 77
        assert limits["plan_slug"] == "standard"
        assert limits["bot_types"] == ["signal", "grid"]
        assert resp.data["usage"]["signals_used_this_month"] == 7  # 3 + 4

    def test_legacy_gets_unlimited_sentinel_and_none_keys(
        self, auth_client, user, signal_bot_subscription
    ):
        resp = auth_client.get(reverse("subscriptions:my-usage"))
        assert resp.status_code == status.HTTP_200_OK
        limits = resp.data["limits"]
        assert limits["max_signals_per_month"] == UNLIMITED
        assert limits["plan_slug"] is None
        assert limits["bot_types"] is None
        # Legacy shim without features → view's documented fallback of 1.
        assert limits["max_bots"] == 1
        assert resp.data["plan"]["name"] == "Signal Bot Plan"  # legacy intact

    def test_no_sub_limits_shape(self, auth_client, user):
        resp = auth_client.get(reverse("subscriptions:my-usage"))
        assert resp.status_code == status.HTTP_200_OK
        limits = resp.data["limits"]
        assert resp.data["plan"] is None
        assert limits["max_bots"] == 0
        assert limits["max_signals_per_month"] == UNLIMITED
        assert limits["plan_slug"] is None
        assert limits["bot_types"] is None
        assert resp.data["usage"] == {
            "bots_created": 0,
            "signals_used_this_month": 0,
        }


# ==================== 5. approve() profile sync ====================


@pytest.mark.django_db
class TestProfileSyncOnApprove:
    def test_model_c_approval_syncs_profile_and_seats(self, user, admin_user):
        # Start on free (seat 3); approving standard must land slug + row seats.
        plan = _mk_plan("standard", max_bots=5, bot_types=["signal"])
        sub = _mk_model_c_sub(user, plan, status_="pending_payment")
        assert user.subscription_plan == "free"
        sub.approve(admin_user)
        user.refresh_from_db()
        assert user.subscription_plan == "standard"
        assert user.max_bots_allowed == 5  # row-driven recompute, not JSON

    def test_legacy_approval_never_touches_profile(self, user, admin_user):
        # Enterprise profile pinned; legacy shim has no FK → no sync.
        user.subscription_plan = "enterprise"
        user.save()
        assert user.max_bots_allowed == 100  # JSON default for enterprise
        from apps.payments.models import BotSubscription, BotSubscriptionPlan

        shim = BotSubscriptionPlan.objects.create(
            bot_type="custom",
            name="Legacy Plan",
            price=Decimal("29.99"),
            duration_days=30,
        )
        sub = BotSubscription.objects.create(user=user, plan=shim, status="pending_payment")
        sub.approve(admin_user)
        user.refresh_from_db()
        assert user.subscription_plan == "enterprise"
        assert user.max_bots_allowed == 100

    def test_model_c_approval_stamps_clock(self, user, admin_user):
        # G4/A6 combo: approve starts the paid clock + grace window.
        plan = _mk_plan("standard", max_bots=5, bot_types=["signal"])
        sub = _mk_model_c_sub(user, plan, status_="pending_payment")
        sub.approve(admin_user)
        now = timezone.now()
        assert sub.status == "active"
        assert sub.started_at is not None
        assert sub.expires_at > now
        assert sub.grace_until > sub.expires_at


# ==================== 6. expiry → free downgrade ====================


@pytest.mark.django_db
class TestExpiryProfileFallback:
    def _expire_profile(self, user, slug, max_bots):
        user.subscription_plan = slug
        user.save()
        assert user.max_bots_allowed == max_bots  # pre-condition: row-driven

    def test_downgrade_to_free_when_governing_and_no_other(self, user, admin_user):
        from apps.payments.services.expiry import transition_expired_subscriptions

        _mk_plan("free", max_bots=1, bot_types=[])
        standard = _mk_plan("standard", max_bots=5, bot_types=["signal"])
        sub = _mk_model_c_sub(user, standard, hard_stopped=True)
        self._expire_profile(user, "standard", 5)

        assert transition_expired_subscriptions() == 1
        sub.refresh_from_db()
        user.refresh_from_db()
        assert sub.status == "expired"
        assert user.subscription_plan == "free"
        assert user.max_bots_allowed == 1  # free row, not stale 5

    def test_no_downgrade_while_other_usable_model_c_exists(self, user):
        from apps.payments.services.expiry import transition_expired_subscriptions

        standard = _mk_plan("standard", max_bots=5, bot_types=["signal"])
        premium = _mk_plan("premium", max_bots=25, bot_types=["signal"])
        dead = _mk_model_c_sub(user, standard, hard_stopped=True)
        _mk_model_c_sub(user, premium)  # still usable
        self._expire_profile(user, "standard", 5)

        transition_expired_subscriptions()
        dead.refresh_from_db()
        user.refresh_from_db()
        assert dead.status == "expired"
        # Usable tier remains → profile must NOT be reset to free.
        assert user.subscription_plan == "standard"

    def test_profile_mismatch_untouched(self, user):
        from apps.payments.services.expiry import transition_expired_subscriptions

        standard = _mk_plan("standard", max_bots=5, bot_types=["signal"])
        _mk_model_c_sub(user, standard, hard_stopped=True)
        # Profile (premium) does not match the expiring tier → guard skips.
        user.subscription_plan = "premium"
        user.save()

        transition_expired_subscriptions()
        user.refresh_from_db()
        assert user.subscription_plan == "premium"

    def test_legacy_expiry_never_touches_profile(self, user, signal_bot_subscription):
        from apps.payments.services.expiry import transition_expired_subscriptions

        # Hard-stop the legacy row (no Model C FK → never collected).
        signal_bot_subscription.expires_at = timezone.now() - timedelta(days=1)
        signal_bot_subscription.grace_until = timezone.now() - timedelta(days=1)
        signal_bot_subscription.save()
        user.subscription_plan = "enterprise"
        user.save()

        assert transition_expired_subscriptions() == 1
        signal_bot_subscription.refresh_from_db()
        user.refresh_from_db()
        assert signal_bot_subscription.status == "expired"
        assert user.subscription_plan == "enterprise"  # profile untouched

    def test_grace_row_not_transitioned_not_downgraded(self, user):
        from apps.payments.services.expiry import transition_expired_subscriptions

        standard = _mk_plan("standard", max_bots=5, bot_types=["signal"])
        # expires_at past but grace_until still future → full access (A6).
        sub = _mk_model_c_sub(user, standard, days=-1)
        sub.grace_until = timezone.now() + timedelta(days=1)
        sub.save()
        self._expire_profile(user, "standard", 5)

        assert transition_expired_subscriptions() == 0
        sub.refresh_from_db()
        user.refresh_from_db()
        assert sub.status == "active"
        assert user.subscription_plan == "standard"


# ==================== 7. effective_limits resolution ====================


@pytest.mark.django_db
class TestEffectiveLimitsResolution:
    def test_model_c_preferred_over_legacy(self, user, signal_bot_subscription):
        from services.plan_limits import effective_limits

        plan = _mk_plan("standard", max_bots=5, bot_types=["signal"])
        model_c = _mk_model_c_sub(user, plan)
        limits = effective_limits(user)
        assert limits.source == "model_c"
        assert limits.slug == "standard"
        assert limits.max_bots == 5
        assert limits.subscription.id == model_c.id  # not the legacy row

    def test_legacy_source_shape(self, user, signal_bot_subscription):
        from services.plan_limits import effective_limits

        limits = effective_limits(user)
        assert limits.source == "legacy"
        assert limits.slug is None
        assert limits.bot_types is None
        assert limits.max_signals_per_month is None
        assert limits.subscription.id == signal_bot_subscription.id

    def test_none_source(self, user):
        from services.plan_limits import effective_limits

        limits = effective_limits(user)
        assert limits.source == "none"
        assert limits.subscription is None
        assert limits.max_bots == user.max_bots_allowed

    def test_hard_stopped_model_c_is_not_usable(self, user):
        from services.plan_limits import effective_limits

        plan = _mk_plan("standard", max_bots=5, bot_types=["signal"])
        _mk_model_c_sub(user, plan, hard_stopped=True)
        # Hard stop → not usable → falls through to "none" (G4 owns access).
        assert effective_limits(user).source == "none"

    def test_grace_period_model_c_still_usable(self, user):
        from services.plan_limits import effective_limits

        plan = _mk_plan("standard", max_bots=5, bot_types=["signal"])
        sub = _mk_model_c_sub(user, plan, days=-1)
        sub.grace_until = timezone.now() + timedelta(days=1)
        sub.save()
        limits = effective_limits(user)
        assert limits.source == "model_c"  # A6: full access in grace

    def test_custom_shim_preferred_between_model_c_rows(self, user):
        from services.plan_limits import effective_limits

        plan = _mk_plan("standard", max_bots=5, bot_types=["signal"])
        grid_tier = _mk_model_c_sub(user, plan, bot_type="grid")
        custom = _mk_model_c_sub(user, plan, bot_type="custom")
        limits = effective_limits(user)
        assert limits.subscription.id == custom.id
        assert grid_tier.id != custom.id  # both exist; custom won

    def test_enforce_noop_for_legacy_even_over_seats(self, user, signal_bot_subscription):
        from services.plan_limits import enforce_bot_creation

        for i in range(5):  # exceeds profile default seat of 3
            _mk_signal_bot_row(user, bot_name=f"Legacy {i}")
        limits = enforce_bot_creation(user, "signal")  # must not raise
        assert limits.source == "legacy"

    def test_enforce_noop_for_none_source(self, user):
        from services.plan_limits import enforce_bot_creation

        limits = enforce_bot_creation(user, "signal")  # must not raise
        assert limits.source == "none"
