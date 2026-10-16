"""
G4 / FR A6 — BotSubscription expiry lifecycle (Telegram untouched).

Covers: approve() clock stamping (expires_at from plan.duration_days,
grace window, reminder-ledger reset), the live state machine at every
boundary (active / grace / hard_stopped / inactive / legacy rows), the
bot-creation gate end-to-end (creation allowed in active AND grace,
403 after hard stop), persistence sweep transition_expired_subscriptions,
the daily reminder task (D-N send + idempotency + retry-on-failure),
re-subscribe restore (approve from "expired" retains the row and its
bot FKs; the subscribe endpoint reuses the unique user+plan row), and
core.email.send_email() delivery order (SMTP primary, Resend fallback,
never raises).
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from django.core import mail
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.payments.models import BotSubscription, BotSubscriptionPlan
from apps.payments.services.expiry import (
    get_usable_subscription,
    is_hard_stopped,
    subscription_state,
    transition_expired_subscriptions,
)
from apps.payments.tasks import check_subscription_expiry
from core.email import send_email

# ---------------------------------------------------------------------------
# fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def plan(db):
    """Custom (signal) bot plan, 30-day term."""
    return BotSubscriptionPlan.objects.create(
        bot_type="custom", name="G4 Signal", price=Decimal("49.00"), duration_days=30
    )


def make_sub(user, plan, *, expires_at, grace_until, status="active", reminders=None):
    """Subscription with an explicit absolute window (boundary-exact)."""
    now = timezone.now()
    return BotSubscription.objects.create(
        user=user,
        plan=plan,
        status=status,
        started_at=now - timedelta(days=10),
        expires_at=expires_at,
        grace_until=grace_until,
        expiry_reminders_sent=reminders or {},
    )


def active_sub(user, plan, *, expires_in_days=10, grace_days=2, **kw):
    """Convenience: expires_at/grace_until positioned relative to NOW."""
    now = timezone.now()
    expires_at = now + timedelta(days=expires_in_days)
    return make_sub(
        user,
        plan,
        expires_at=expires_at,
        grace_until=expires_at + timedelta(days=grace_days),
        **kw,
    )


SIGNAL_PAYLOAD = {
    "bot_name": "G4 Gate Bot",
    "exchange_name": "binance",
    "trading_pair": "BTC/USDT",
    "default_amount": "100",
}


# ---------------------------------------------------------------------------
# approve() stamps the clock (A6 term window)
# ---------------------------------------------------------------------------


class TestApproveClock:
    def test_approve_starts_term_and_grace_window(self, db, user, plan, admin_user):
        sub = active_sub(user, plan, expires_in_days=-5, status="expired")
        before = timezone.now()
        sub.approve(admin_user, notes="renew")
        after = timezone.now()

        assert sub.status == "active"
        assert before <= sub.started_at <= after
        # expires_at = now + plan.duration_days (30)
        assert before + timedelta(days=30) <= sub.expires_at <= after + timedelta(days=30)
        # grace_until = expires_at + SUBSCRIPTION_GRACE_PERIOD_DAYS (default 2)
        assert sub.grace_until == sub.expires_at + timedelta(days=2)
        assert sub.notes == "renew"

    def test_approve_resets_reminder_ledger(self, db, user, plan, admin_user):
        """A new paid term must re-arm D-7/5/3/1 emails."""
        sub = active_sub(
            user, plan, expires_in_days=-5, status="expired", reminders={"D-7": "stale"}
        )
        sub.approve(admin_user)
        assert sub.expiry_reminders_sent == {}

    def test_grace_days_follow_settings(self, db, user, plan, admin_user):
        with override_settings(SUBSCRIPTION_GRACE_PERIOD_DAYS=5):
            sub = active_sub(user, plan, expires_in_days=-5, status="expired")
            sub.approve(admin_user)
            assert sub.grace_until == sub.expires_at + timedelta(days=5)


# ---------------------------------------------------------------------------
# state machine boundaries (live date math — never trusted status)
# ---------------------------------------------------------------------------


class TestStateMachine:
    @pytest.fixture
    def window(self, db, user, plan):
        """Fixed window: expires_at = 2030-01-10, grace ends 2030-01-12."""
        return make_sub(
            user,
            plan,
            expires_at=datetime(2030, 1, 10, 12, 0, tzinfo=UTC),
            grace_until=datetime(2030, 1, 12, 12, 0, tzinfo=UTC),
        )

    def test_active_before_expiry(self, window):
        now = datetime(2030, 1, 10, 11, 59, tzinfo=UTC)
        assert subscription_state(window, now) == "active"
        assert not is_hard_stopped(window, now)

    def test_exactly_at_expiry_still_active(self, window):
        now = datetime(2030, 1, 10, 12, 0, tzinfo=UTC)
        assert subscription_state(window, now) == "active"

    def test_grace_after_expiry(self, window):
        now = datetime(2030, 1, 11, 0, 0, tzinfo=UTC)
        assert subscription_state(window, now) == "grace"
        assert not is_hard_stopped(window, now)  # grace = FULL access

    def test_exactly_at_grace_end_still_grace(self, window):
        now = datetime(2030, 1, 12, 12, 0, tzinfo=UTC)
        assert subscription_state(window, now) == "grace"

    def test_hard_stopped_after_grace(self, window):
        now = datetime(2030, 1, 12, 12, 0, 1, tzinfo=UTC)
        assert subscription_state(window, now) == "hard_stopped"
        assert is_hard_stopped(window, now)

    def test_inactive_when_status_not_active(self, db, user, plan):
        """A pending row is never usable regardless of its dates."""
        sub = active_sub(user, plan, expires_in_days=10, status="pending_approval")
        assert subscription_state(sub) == "inactive"

    def test_legacy_row_without_grace_hard_stops_at_expiry(self, db, user, plan):
        """Rows approved before G4 have grace_until=None → no invented grace."""
        now = timezone.now()
        sub = make_sub(user, plan, expires_at=now - timedelta(minutes=1), grace_until=None)
        assert subscription_state(sub) == "hard_stopped"

    def test_row_without_expiry_treated_active(self, db, user, plan):
        """Legacy row with no clock: no basis to stop anything."""
        sub = BotSubscription.objects.create(user=user, plan=plan, status="active")
        assert subscription_state(sub) == "active"


# ---------------------------------------------------------------------------
# get_usable_subscription (the gate's single source of truth)
# ---------------------------------------------------------------------------


class TestUsableSubscription:
    def test_active_returned(self, db, user, plan):
        sub = active_sub(user, plan, expires_in_days=10)
        assert get_usable_subscription(user, "custom") == sub

    def test_grace_returned_full_access(self, db, user, plan):
        sub = active_sub(user, plan, expires_in_days=-1)  # in 2-day grace
        assert subscription_state(sub) == "grace"
        assert get_usable_subscription(user, "custom") == sub

    def test_hard_stopped_returns_none(self, db, user, plan):
        active_sub(user, plan, expires_in_days=-5)  # past grace
        assert get_usable_subscription(user, "custom") is None

    def test_no_row_returns_none(self, db, user):
        assert get_usable_subscription(user, "custom") is None

    def test_other_bot_type_not_returned(self, db, user, plan):
        """Gate is scoped per bot_type — a custom plan unlocks nothing else."""
        active_sub(user, plan, expires_in_days=10)
        assert get_usable_subscription(user, "grid") is None


# ---------------------------------------------------------------------------
# end-to-end creation gate (API)
# ---------------------------------------------------------------------------


class TestBotCreateGate:
    url = "bots:signalbot-list"

    def test_creation_allowed_while_active(self, auth_client, user, plan):
        active_sub(user, plan, expires_in_days=10)
        resp = auth_client.post(reverse(self.url), SIGNAL_PAYLOAD, format="json")
        assert resp.status_code == 201, resp.data

    def test_creation_allowed_during_grace(self, auth_client, user, plan):
        """A6: full access retained during the grace window."""
        active_sub(user, plan, expires_in_days=-1)
        resp = auth_client.post(reverse(self.url), SIGNAL_PAYLOAD, format="json")
        assert resp.status_code == 201, resp.data

    def test_creation_blocked_after_hard_stop(self, auth_client, user, plan):
        """A6: hard stop = no NEW bot entries (403 PERMISSION_DENIED)."""
        active_sub(user, plan, expires_in_days=-5)
        resp = auth_client.post(reverse(self.url), SIGNAL_PAYLOAD, format="json")
        assert resp.status_code == 403
        assert resp.data["error"]["code"] == "PERMISSION_DENIED"

    def test_creation_blocked_without_subscription(self, auth_client):
        resp = auth_client.post(reverse(self.url), SIGNAL_PAYLOAD, format="json")
        assert resp.status_code == 403
        assert resp.data["error"]["code"] == "PERMISSION_DENIED"


# ---------------------------------------------------------------------------
# daily sweep persistence
# ---------------------------------------------------------------------------


class TestTransitionSweep:
    def test_flips_past_grace_rows_only(self, db, user, second_user, plan):
        # One row per (user, plan) — three rows need three users.
        from django.contrib.auth import get_user_model

        third = get_user_model().objects.create_user(
            username="g4third", email="g4third@example.com", password="x"
        )
        hard = active_sub(user, plan, expires_in_days=-5)
        in_grace = active_sub(second_user, plan, expires_in_days=-1)
        fresh = active_sub(third, plan, expires_in_days=10)

        count = transition_expired_subscriptions()

        hard.refresh_from_db()
        in_grace.refresh_from_db()
        fresh.refresh_from_db()
        assert count == 1
        assert hard.status == "expired"
        assert in_grace.status == "active"  # grace untouched
        assert fresh.status == "active"

    def test_ignores_already_inactive_rows(self, db, user, plan):
        pending = active_sub(user, plan, expires_in_days=-5, status="pending_approval")
        count = transition_expired_subscriptions()
        pending.refresh_from_db()
        assert count == 0
        assert pending.status == "pending_approval"

    def test_never_clobbers_concurrent_approve(self, db, user, plan, monkeypatch):
        """Adversarial review 2026-10-15 (CRITICAL): the sweep write is a
        compare-and-swap — an approve() landing between the sweep's read
        and its UPDATE must win, never be clobbered back to "expired"."""
        hard = active_sub(user, plan, expires_in_days=-5)
        fresh_expiry = timezone.now() + timedelta(days=30)

        def racing(s, now=None):
            # Simulate the admin approve committing AFTER the sweep read the
            # row (stale verdict: hard-stopped) but BEFORE its UPDATE.
            BotSubscription.objects.filter(pk=s.pk).update(
                status="active",
                expires_at=fresh_expiry,
                grace_until=fresh_expiry + timedelta(days=2),
            )
            return True  # verdict computed from the PRE-approve row

        monkeypatch.setattr("apps.payments.services.expiry.is_hard_stopped", racing)

        count = transition_expired_subscriptions()

        hard.refresh_from_db()
        assert count == 0  # CAS: expires_at changed → 0 rows updated
        assert hard.status == "active"  # freshly approved term preserved
        assert hard.expires_at == fresh_expiry


# ---------------------------------------------------------------------------
# reminder task (D-N emails, idempotent, retry on failure)
# ---------------------------------------------------------------------------


class TestReminderTask:
    @pytest.fixture
    def expiring_7d(self, db, user, plan):
        return active_sub(user, plan, expires_in_days=7)

    @override_settings(SUBSCRIPTION_REMINDER_OFFSET_DAYS=[7, 5, 3, 1])
    def test_d7_sent_once_then_idempotent(self, expiring_7d):
        result = check_subscription_expiry()
        assert result["reminders_sent"] == 1
        assert len(mail.outbox) == 1
        assert "expires in 7 day" in mail.outbox[0].subject

        expiring_7d.refresh_from_db()
        assert "D-7" in expiring_7d.expiry_reminders_sent

        # Second daily run: ledger blocks a duplicate send.
        result2 = check_subscription_expiry()
        assert result2["reminders_sent"] == 0
        assert len(mail.outbox) == 1

    @override_settings(SUBSCRIPTION_REMINDER_OFFSET_DAYS=[7])
    def test_no_send_outside_offset(self, db, user, plan):
        active_sub(user, plan, expires_in_days=3)  # D-3 not configured here
        result = check_subscription_expiry()
        assert result["reminders_sent"] == 0
        assert len(mail.outbox) == 0

    @override_settings(SUBSCRIPTION_REMINDER_OFFSET_DAYS=[7])
    def test_hard_stopped_rows_never_emailed(self, db, user, plan):
        active_sub(user, plan, expires_in_days=-5)  # past grace → skipped
        result = check_subscription_expiry()
        assert result["reminders_sent"] == 0
        assert len(mail.outbox) == 0

    @override_settings(SUBSCRIPTION_REMINDER_OFFSET_DAYS=[7])
    def test_failed_send_retries_next_run(self, expiring_7d, monkeypatch):
        """Transient delivery failure must NOT stamp the ledger."""
        monkeypatch.setattr("apps.payments.tasks.send_email", lambda *a, **k: False)

        result = check_subscription_expiry()
        # Adversarial review 2026-10-15: failed deliveries are NOT counted.
        assert result["reminders_sent"] == 0
        expiring_7d.refresh_from_db()
        assert expiring_7d.expiry_reminders_sent == {}  # not stamped → retryable

    @override_settings(SUBSCRIPTION_REMINDER_OFFSET_DAYS=[7])
    def test_sweep_and_reminders_compose(self, db, user, second_user, plan):
        """One run: flips the hard-stopped row AND emails the D-7 row."""
        active_sub(user, plan, expires_in_days=-5)  # past grace → expired
        active_sub(second_user, plan, expires_in_days=7)  # D-7 mail
        # (second_user: unique_together [user, plan] allows only one row per pair)

        result = check_subscription_expiry()
        assert result["expired"] == 1
        assert result["reminders_sent"] == 1
        assert len(mail.outbox) == 1


# ---------------------------------------------------------------------------
# re-subscribe restore (retained data, fresh clock)
# ---------------------------------------------------------------------------


class TestReSubscribe:
    def test_approve_expired_row_restores_and_keeps_row(self, db, user, plan, admin_user):
        """Restore on re-subscribe: same PK (bot FKs survive), fresh window."""
        sub = active_sub(user, plan, expires_in_days=-5, status="expired", reminders={"D-7": "old"})
        old_pk = sub.id

        from services.subscription_service import SubscriptionService

        SubscriptionService.approve_subscription(str(sub.id), admin_user)

        sub.refresh_from_db()
        assert sub.id == old_pk  # data retained
        assert sub.status == "active"
        assert sub.expires_at > timezone.now()
        assert sub.expiry_reminders_sent == {}  # new term re-arms reminders

    def test_approve_still_rejects_unknown_status(self, db, user, plan, admin_user):
        sub = active_sub(user, plan, status="rejected")
        from services.subscription_service import SubscriptionService

        with pytest.raises(ValueError, match="rejected"):
            SubscriptionService.approve_subscription(str(sub.id), admin_user)

    def test_create_endpoint_reuses_existing_row(self, auth_client, user, plan):
        """unique_together [user, plan]: re-subscribe reuses, never IntegrityError."""
        expired = active_sub(user, plan, expires_in_days=-5, status="expired")
        url = reverse("payments:bot-subscription-create")
        resp = auth_client.post(
            url,
            {"plan_id": str(plan.id), "payment_transaction_hash": "0xabc"},
            format="json",
        )
        assert resp.status_code == 201, resp.data
        assert resp.data["subscription_id"] == str(expired.id)

        expired.refresh_from_db()
        assert expired.status == "pending_approval"  # awaiting admin re-approval
        assert expired.expires_at is not None  # old clock retained until approve()

    def test_create_endpoint_first_time_creates(self, auth_client, plan):
        url = reverse("payments:bot-subscription-create")
        resp = auth_client.post(
            url,
            {"plan_id": str(plan.id), "payment_transaction_hash": "0xabc"},
            format="json",
        )
        assert resp.status_code == 201, resp.data
        assert BotSubscription.objects.filter(user__username="testuser").count() == 1


# ---------------------------------------------------------------------------
# core.email.send_email — SMTP primary, Resend fallback, never raises
# ---------------------------------------------------------------------------


class _Resp:
    def raise_for_status(self):
        return None


class TestEmailHelper:
    def test_smtp_success_returns_true(self):
        assert send_email("S", "body", ["a@b.com"]) is True
        assert len(mail.outbox) == 1
        assert mail.outbox[0].subject == "S"

    @override_settings(RESEND_API_KEY="re_test_key")
    def test_smtp_failure_falls_back_to_resend(self, monkeypatch):
        calls = {}

        def boom(*a, **k):
            raise OSError("smtp down")

        def fake_post(url, **kwargs):
            calls["url"] = url
            calls["json"] = kwargs["json"]
            return _Resp()

        monkeypatch.setattr("core.email.send_mail", boom)
        monkeypatch.setattr("core.email.requests.post", fake_post)

        assert send_email("Fallback", "body", ["a@b.com"]) is True
        assert calls["url"] == "https://api.resend.com/emails"
        assert calls["json"]["subject"] == "Fallback"
        assert calls["json"]["to"] == ["a@b.com"]

    @override_settings(RESEND_API_KEY="")
    def test_smtp_failure_without_key_returns_false_no_raise(self, monkeypatch):
        def boom(*a, **k):
            raise OSError("smtp down")

        monkeypatch.setattr("core.email.send_mail", boom)
        assert send_email("Lost", "body", ["a@b.com"]) is False

    def test_resend_failure_returns_false_no_raise(self, monkeypatch):
        def boom(*a, **k):
            raise OSError("smtp down")

        def bad_post(*a, **k):
            raise RuntimeError("resend 500")

        monkeypatch.setattr("core.email.send_mail", boom)
        monkeypatch.setattr("core.email.requests.post", bad_post)
        with override_settings(RESEND_API_KEY="re_x"):
            assert send_email("BothFail", "body", ["a@b.com"]) is False

    def test_empty_recipients_dropped(self):
        assert send_email("S", "body", []) is False
        assert len(mail.outbox) == 0
