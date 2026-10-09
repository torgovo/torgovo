from decimal import Decimal

import pytest
from django.db import models
from django.utils import timezone

from apps.subscriptions.models import (
    SignalResult,
    SignalStatistics,
    TelegramChannel,
    TelegramSignalPlan,
    TelegramSubscription,
    TelegramSubscriptionChannel,
    TradingSignal,
)


@pytest.mark.django_db
class TestTelegramSignalPlanModel:
    def test_create_plan(self):
        plan = TelegramSignalPlan.objects.create(
            name="Premium Signals",
            slug="premium-signals",
            description="High quality trading signals",
            price_monthly=Decimal("49.99"),
            price_quarterly=Decimal("129.99"),
            price_yearly=Decimal("499.99"),
            features=["real_time", "analysis"],
            signals_per_day=20,
            exchanges_covered=["binance", "bybit"],
            risk_level="moderate",
            max_subscribers=1000,
        )
        assert plan.name == "Premium Signals"
        assert plan.price_monthly == Decimal("49.99")
        assert plan.is_active is True
        assert plan.trial_days == 7
        assert str(plan) == "Premium Signals ($49.99/month)"

    def test_plan_unique_slug(self, db):
        TelegramSignalPlan.objects.create(
            name="Basic",
            slug="basic",
            description="Basic plan",
            price_monthly=9.99,
            price_quarterly=24.99,
            price_yearly=99.99,
        )
        with pytest.raises(Exception):
            TelegramSignalPlan.objects.create(
                name="Basic2",
                slug="basic",
                description="Another basic",
                price_monthly=19.99,
                price_quarterly=49.99,
                price_yearly=199.99,
            )


@pytest.mark.django_db
class TestTelegramChannelModel:
    def test_create_channel(self):
        channel = TelegramChannel.objects.create(
            name="Crypto Signals",
            channel_id="crypto_signals_channel",
            channel_type="signals",
            invite_link="https://t.me/crypto_signals_channel",
            description="Daily trading signals",
            is_private=False,
            is_active=True,
        )
        assert channel.name == "Crypto Signals"
        assert channel.channel_id == "crypto_signals_channel"
        assert channel.channel_type == "signals"
        assert str(channel) == "Crypto Signals (@crypto_signals_channel)"

    def test_channel_unique(self, db):
        TelegramChannel.objects.create(
            name="Channel1",
            channel_id="ch1",
            channel_type="signals",
            invite_link="https://t.me/ch1",
            description="Desc",
        )
        with pytest.raises(Exception):
            TelegramChannel.objects.create(
                name="Channel2",
                channel_id="ch1",
                channel_type="news",
                invite_link="https://t.me/ch2",
                description="Desc",
            )


@pytest.mark.django_db
class TestTelegramSubscriptionModel:
    def test_create_subscription(self, user):
        plan = TelegramSignalPlan.objects.create(
            name="Pro",
            slug="pro",
            description="Pro plan",
            price_monthly=49.99,
            price_quarterly=129.99,
            price_yearly=499.99,
        )
        sub = TelegramSubscription.objects.create(
            user=user,
            plan=plan,
            telegram_handle="testuser_tg",
            amount_paid=Decimal("49.99"),
        )
        assert sub.user == user
        assert sub.plan == plan
        assert sub.status == "pending_payment"
        assert sub.telegram_handle == "testuser_tg"
        assert sub.amount_paid == Decimal("49.99")
        assert sub.billing_cycle == "monthly"
        assert sub.auto_renew is True
        assert str(sub) == f"{user.email} - Pro (pending_payment)"

    def test_is_active_property(self, user):
        plan = TelegramSignalPlan.objects.create(
            name="Basic",
            slug="basic",
            description="Basic",
            price_monthly=9.99,
            price_quarterly=24.99,
            price_yearly=99.99,
        )
        sub = TelegramSubscription.objects.create(
            user=user,
            plan=plan,
            telegram_handle="tg_user",
            amount_paid=Decimal("9.99"),
        )
        assert sub.is_active is False

        sub.status = "active"
        sub.end_date = timezone.now().date() + timezone.timedelta(days=30)
        sub.save()
        sub.refresh_from_db()
        assert sub.is_active is True

    def test_approve_subscription(self, user, admin_user):
        plan = TelegramSignalPlan.objects.create(
            name="Pro",
            slug="pro",
            description="Pro",
            price_monthly=49.99,
            price_quarterly=129.99,
            price_yearly=499.99,
        )
        sub = TelegramSubscription.objects.create(
            user=user,
            plan=plan,
            telegram_handle="tg_pro",
            amount_paid=Decimal("49.99"),
            status="pending_approval",
        )
        sub.approve(admin_user, "Welcome!")
        sub.refresh_from_db()
        assert sub.status == "active"
        assert sub.approved_by == admin_user
        assert sub.approved_at is not None
        assert sub.started_at is not None
        assert sub.end_date is not None

    def test_reject_subscription(self, user, admin_user):
        plan = TelegramSignalPlan.objects.create(
            name="Basic",
            slug="basic",
            description="Basic",
            price_monthly=9.99,
            price_quarterly=24.99,
            price_yearly=99.99,
        )
        sub = TelegramSubscription.objects.create(
            user=user,
            plan=plan,
            telegram_handle="tg_basic",
            amount_paid=Decimal("9.99"),
            status="pending_approval",
        )
        sub.reject(admin_user, "Payment verification failed")
        sub.refresh_from_db()
        assert sub.status == "rejected"
        assert sub.rejected_by == admin_user
        assert sub.rejection_reason == "Payment verification failed"

    def test_extend_subscription(self, user):
        plan = TelegramSignalPlan.objects.create(
            name="Pro",
            slug="pro",
            description="Pro",
            price_monthly=49.99,
            price_quarterly=129.99,
            price_yearly=499.99,
        )
        sub = TelegramSubscription.objects.create(
            user=user,
            plan=plan,
            telegram_handle="tg_extend",
            amount_paid=Decimal("49.99"),
            status="active",
            end_date=timezone.now().date() + timezone.timedelta(days=30),
        )
        sub.extend_subscription(30)
        sub.refresh_from_db()
        assert sub.status == "active"

    def test_soft_delete(self, user):
        plan = TelegramSignalPlan.objects.create(
            name="Basic",
            slug="basic",
            description="Basic",
            price_monthly=9.99,
            price_quarterly=24.99,
            price_yearly=99.99,
        )
        sub = TelegramSubscription.objects.create(
            user=user,
            plan=plan,
            telegram_handle="tg_del",
            amount_paid=Decimal("9.99"),
        )
        sub.delete()
        assert sub.is_deleted is True


@pytest.mark.django_db
class TestTelegramSubscriptionChannelModel:
    def test_create_through(self, user):
        plan = TelegramSignalPlan.objects.create(
            name="Basic",
            slug="basic",
            description="Basic",
            price_monthly=9.99,
            price_quarterly=24.99,
            price_yearly=99.99,
        )
        channel = TelegramChannel.objects.create(
            name="Signals",
            channel_id="signals_ch",
            channel_type="signals",
            invite_link="https://t.me/signals_ch",
            description="Signals",
        )
        sub = TelegramSubscription.objects.create(
            user=user,
            plan=plan,
            telegram_handle="tg_user",
            amount_paid=Decimal("9.99"),
        )
        through = TelegramSubscriptionChannel.objects.create(
            subscription=sub,
            channel=channel,
        )
        assert through.subscription == sub
        assert through.channel == channel
        assert through.is_active is True

    def test_unique_together(self, user):
        plan = TelegramSignalPlan.objects.create(
            name="Basic",
            slug="basic",
            description="Basic",
            price_monthly=9.99,
            price_quarterly=24.99,
            price_yearly=99.99,
        )
        channel = TelegramChannel.objects.create(
            name="Ch",
            channel_id="ch",
            channel_type="signals",
            invite_link="https://t.me/ch",
            description="Ch",
        )
        sub = TelegramSubscription.objects.create(
            user=user,
            plan=plan,
            telegram_handle="tg_u",
            amount_paid=Decimal("9.99"),
        )
        TelegramSubscriptionChannel.objects.create(subscription=sub, channel=channel)
        with pytest.raises(Exception):
            TelegramSubscriptionChannel.objects.create(subscription=sub, channel=channel)


@pytest.mark.django_db
class TestTradingSignalModel:
    def test_create_signal(self):
        plan = TelegramSignalPlan.objects.create(
            name="Pro",
            slug="pro",
            description="Pro",
            price_monthly=49.99,
            price_quarterly=129.99,
            price_yearly=499.99,
        )
        signal = TradingSignal.objects.create(
            plan=plan,
            signal_type="buy",
            trading_pair="BTC/USDT",
            exchange="binance",
            timeframe="1h",
            entry_price=Decimal("50000.00000000"),
            stop_loss=Decimal("49000.00000000"),
            take_profit_1=Decimal("51000.00000000"),
            confidence_level=8,
            analysis="Bullish breakout",
            source="manual",
            ai_generated=False,
            published_at=timezone.now(),
            expires_at=timezone.now() + timezone.timedelta(hours=24),
        )
        assert signal.signal_type == "buy"
        assert signal.trading_pair == "BTC/USDT"
        assert signal.exchange == "binance"
        assert signal.entry_price == Decimal("50000.00000000")
        assert signal.is_active is True
        assert str(signal) == "BUY BTC/USDT - Pro"

    def test_is_expired_property(self):
        plan = TelegramSignalPlan.objects.create(
            name="Pro",
            slug="pro",
            description="Pro",
            price_monthly=49.99,
            price_quarterly=129.99,
            price_yearly=499.99,
        )
        signal = TradingSignal.objects.create(
            plan=plan,
            signal_type="sell",
            trading_pair="ETH/USDT",
            exchange="bybit",
            timeframe="4h",
            entry_price=Decimal("3000"),
            analysis="Test",
            published_at=timezone.now(),
            expires_at=timezone.now() - timezone.timedelta(hours=1),
        )
        assert signal.is_expired is True


@pytest.mark.django_db
class TestSignalResultModel:
    def test_create_result(self):
        plan = TelegramSignalPlan.objects.create(
            name="Pro",
            slug="pro",
            description="Pro",
            price_monthly=49.99,
            price_quarterly=129.99,
            price_yearly=499.99,
        )
        signal = TradingSignal.objects.create(
            plan=plan,
            signal_type="buy",
            trading_pair="BTC/USDT",
            exchange="binance",
            timeframe="1h",
            entry_price=Decimal("50000"),
            analysis="Test",
            published_at=timezone.now(),
            expires_at=timezone.now() + timezone.timedelta(hours=24),
        )
        result = SignalResult.objects.create(
            signal=signal,
            result_type="profit",
            entry_price_actual=Decimal("50000"),
            exit_price=Decimal("51500"),
            profit_loss=Decimal("1500"),
            profit_loss_percent=Decimal("3.00"),
            entry_time=timezone.now(),
            exit_time=timezone.now() + timezone.timedelta(hours=6),
            duration_hours=6,
        )
        assert result.signal == signal
        assert result.result_type == "profit"
        assert result.profit_loss_percent == Decimal("3.00")
        assert result.hit_take_profit is False
        assert str(result) == f"{signal} - profit (3.00%)"


@pytest.mark.django_db
class TestSignalStatisticsModel:
    def test_create_statistics(self):
        plan = TelegramSignalPlan.objects.create(
            name="Pro",
            slug="pro",
            description="Pro",
            price_monthly=49.99,
            price_quarterly=129.99,
            price_yearly=499.99,
        )
        stats = SignalStatistics.objects.create(
            plan=plan,
            date=timezone.now().date(),
            total_signals=10,
            successful_signals=7,
            profit_signals=6,
            loss_signals=1,
            total_profit_loss=Decimal("2500"),
            win_rate=Decimal("70.00"),
        )
        assert stats.plan == plan
        assert stats.total_signals == 10
        assert stats.win_rate == Decimal("70.00")
        assert str(stats) == f"Pro - {timezone.now().date()} (10 signals)"

    def test_unique_together(self):
        plan = TelegramSignalPlan.objects.create(
            name="Pro",
            slug="pro",
            description="Pro",
            price_monthly=49.99,
            price_quarterly=129.99,
            price_yearly=499.99,
        )
        date = timezone.now().date()
        SignalStatistics.objects.create(plan=plan, date=date, total_signals=1)
        with pytest.raises(Exception):
            SignalStatistics.objects.create(plan=plan, date=date, total_signals=2)


# ============================================================================
# A11 — approve() assigns plan-eligible channels server-side
# ============================================================================


@pytest.mark.django_db
class TestApproveChannelAssignment:
    """A11: channels are granted on approval by required_plan_id, never
    via user-supplied API payload."""

    @pytest.fixture(autouse=True)
    def setup(self, db, user, admin_user):
        self.user = user
        self.admin = admin_user
        self.plan = TelegramSignalPlan.objects.create(
            name="Pro",
            slug="pro",
            description="Pro",
            price_monthly=Decimal("49.99"),
            price_quarterly=Decimal("129.99"),
            price_yearly=Decimal("499.99"),
        )
        self.other_plan = TelegramSignalPlan.objects.create(
            name="Basic",
            slug="basic",
            description="Basic",
            price_monthly=Decimal("9.99"),
            price_quarterly=Decimal("24.99"),
            price_yearly=Decimal("99.99"),
        )
        # Eligible: active + matches this plan
        self.plan_channel = TelegramChannel.objects.create(
            name="Pro Signals",
            channel_id="pro_signals",
            channel_type="signals",
            invite_link="https://t.me/pro_signals",
            description="Pro only",
            is_active=True,
            required_plan=self.plan,
        )
        # Eligible: active + unrestricted (no required plan)
        self.free_channel = TelegramChannel.objects.create(
            name="General",
            channel_id="general",
            channel_type="general",
            invite_link="https://t.me/general",
            description="Everyone",
            is_active=True,
            required_plan=None,
        )
        # Not eligible: requires a different plan
        self.other_plan_channel = TelegramChannel.objects.create(
            name="Basic Signals",
            channel_id="basic_signals",
            channel_type="signals",
            invite_link="https://t.me/basic_signals",
            description="Basic only",
            is_active=True,
            required_plan=self.other_plan,
        )
        # Not eligible: inactive even though unrestricted
        self.inactive_channel = TelegramChannel.objects.create(
            name="Archived",
            channel_id="archived",
            channel_type="general",
            invite_link="https://t.me/archived",
            description="Off",
            is_active=False,
            required_plan=None,
        )
        self.sub = TelegramSubscription.objects.create(
            user=self.user,
            plan=self.plan,
            telegram_handle="tg_user",
            amount_paid=Decimal("49.99"),
            status="pending_approval",
        )

    def test_approve_assigns_only_eligible_channels(self):
        self.sub.approve(self.admin)
        self.sub.refresh_from_db()
        assigned = set(self.sub.channels.values_list("id", flat=True))
        assert assigned == {self.plan_channel.id, self.free_channel.id}
        assert self.other_plan_channel.id not in assigned
        assert self.inactive_channel.id not in assigned

    def test_approval_is_idempotent_for_channels(self):
        """Re-running assignment logic must not duplicate through rows."""
        self.sub.approve(self.admin)
        before = TelegramSubscriptionChannel.objects.filter(subscription=self.sub).count()
        eligible = TelegramChannel.objects.filter(is_active=True).filter(
            models.Q(required_plan_id__isnull=True) | models.Q(required_plan_id=self.sub.plan_id)
        )
        self.sub.channels.set(eligible)
        after = TelegramSubscriptionChannel.objects.filter(subscription=self.sub).count()
        assert before == after == 2
