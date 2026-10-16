"""
G2 / FR A3 — manual multi-coin payment codes: full coverage.

Covers: coin seed/list, code creation (both order kinds, duplicate/capacity
pre-flight), live quote re-locking (TTL cadence, coin switch, freeze after
submit), payment-window expiry + explicit re-request (no silent re-lock),
combined amount (plan price + per-chain fee buffer), proof fulfillment,
admin-decision mirror signal, quote-service unit behaviour (clamps, peg
fallback, refuse-when-unpriced), and worst-case races.
"""

import base64
import sys
import types
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.payments.models import (
    BotSubscription,
    PaymentCode,
    PaymentCoin,
    PaymentQuote,
    SubscriptionPlan,
)
from apps.payments.services.quote import (
    QuoteUnavailable,
    create_quote,
    get_coin_usd_rate,
    get_or_refresh_quote,
    get_quote_ttl_seconds,
    is_window_open,
    renew_quote,
)
from apps.subscriptions.models import TelegramSignalPlan, TelegramSubscription

_PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="  # noqa: E501
)


# ---------------------------------------------------------------------------
# shared fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def tg_plan(db):
    return TelegramSignalPlan.objects.create(
        name="G2 Signals",
        slug="g2-signals",
        description="test",
        price_monthly=Decimal("15.00"),
        price_quarterly=Decimal("40.00"),
        price_yearly=Decimal("140.00"),
    )


@pytest.fixture
def bot_plan(db):
    return SubscriptionPlan.objects.create(
        name="G2 Bot",
        slug="g2-bot",
        price_monthly=Decimal("49.00"),
        price_yearly=Decimal("470.00"),
        max_bots_allowed=5,
        max_webhooks_allowed=10,
    )


@pytest.fixture
def coin(db):
    return PaymentCoin.objects.create(
        coin="USDT",
        chain="TRC20",
        deposit_address="TXYZ123fakeReceiveAddress",
        sort_order=10,
    )


@pytest.fixture
def rate_one(monkeypatch):
    """Deterministic rate: 1.00 USD per coin."""
    monkeypatch.setattr(
        "apps.payments.services.quote.get_coin_usd_rate",
        lambda symbol: Decimal("1.00000000"),
    )


@pytest.fixture
def rate_two(monkeypatch):
    """Later price: 2.00 USD per coin (used to prove re-locking)."""
    monkeypatch.setattr(
        "apps.payments.services.quote.get_coin_usd_rate",
        lambda symbol: Decimal("2.00000000"),
    )


def make_code(user, kind="telegram_signal", plan=None, cycle="monthly", fiat=None):
    """Build (unbound) a PaymentCode row directly for view/service tests."""
    from apps.payments.services.fulfill import plan_fiat_amount

    if kind == "telegram_signal":
        kwargs = {"telegram_plan": plan, "bot_plan": None}
        amount = fiat if fiat is not None else plan_fiat_amount("telegram_signal", plan, cycle)
    else:
        kwargs = {"telegram_plan": None, "bot_plan": plan}
        amount = fiat if fiat is not None else plan_fiat_amount("bot", plan, cycle)
    code = PaymentCode(
        user=user,
        order_kind=kind,
        billing_cycle=cycle,
        fiat_amount=amount,
        **kwargs,
    )
    code.save()
    return code


def expire_quote(code):
    """Force the latest quote past its TTL (bypasses sleeping)."""
    PaymentQuote.objects.filter(code=code).update(expires_at=timezone.now() - timedelta(seconds=1))


def close_window(code):
    """Force the payment window past its end (bypasses sleeping)."""
    code.quote_window_expires_at = timezone.now() - timedelta(seconds=1)
    code.save(update_fields=["quote_window_expires_at"])


# ---------------------------------------------------------------------------
# quote service unit tests
# ---------------------------------------------------------------------------


class TestQuoteService:
    @override_settings(PAYMENT_QUOTE_TTL_SECONDS=5000)
    def test_ttl_clamped_to_3600s_max(self):
        assert get_quote_ttl_seconds() == 3600

    @override_settings(PAYMENT_QUOTE_TTL_SECONDS=1)
    def test_ttl_clamped_to_60s_min(self):
        assert get_quote_ttl_seconds() == 60

    def test_ttl_default_is_5min(self):
        """FR A3: the FE auto-updates the combined amount every 5 minutes."""
        assert get_quote_ttl_seconds() == 300

    @override_settings(PAYMENT_QUOTE_TTL_SECONDS=150)
    def test_ttl_passthrough_within_envelope(self):
        assert get_quote_ttl_seconds() == 150

    def test_create_quote_math_and_expiry(self, db, tg_plan, coin, rate_one, user):
        code = make_code(user, "telegram_signal", tg_plan)  # fiat 15.00
        quote = create_quote(code, coin)
        assert quote.crypto_amount == Decimal("15.00000000")
        assert quote.rate == Decimal("1.00000000")
        ttl = get_quote_ttl_seconds()
        assert quote.expires_at <= timezone.now() + timedelta(seconds=ttl + 5)
        assert not quote.is_expired

    def test_get_or_refresh_none_without_coin_or_quote(self, db, tg_plan, user):
        code = make_code(user, "telegram_signal", tg_plan)
        assert get_or_refresh_quote(code, None) is None

    def test_get_or_refresh_creates_with_coin(self, db, tg_plan, coin, rate_one, user):
        code = make_code(user, "telegram_signal", tg_plan)
        quote = get_or_refresh_quote(code, coin)
        assert quote is not None and PaymentQuote.objects.filter(code=code).count() == 1

    def test_get_or_refresh_returns_same_while_fresh(self, db, tg_plan, coin, rate_one, user):
        code = make_code(user, "telegram_signal", tg_plan)
        first = get_or_refresh_quote(code, coin)
        second = get_or_refresh_quote(code, coin)
        assert first.id == second.id
        assert PaymentQuote.objects.filter(code=code).count() == 1

    def test_expired_relocks_at_new_rate(self, db, tg_plan, coin, rate_one, user, monkeypatch):
        code = make_code(user, "telegram_signal", tg_plan)
        first = get_or_refresh_quote(code, coin)
        expire_quote(code)
        # price moved between polls
        monkeypatch.setattr(
            "apps.payments.services.quote.get_coin_usd_rate",
            lambda symbol: Decimal("2.00000000"),
        )
        second = get_or_refresh_quote(code, coin)
        assert second.id != first.id
        assert second.crypto_amount == Decimal("7.50000000")
        assert PaymentQuote.objects.filter(code=code).count() == 2

    def test_coin_switch_relocks_even_when_fresh(self, db, tg_plan, coin, rate_one, user):
        other = PaymentCoin.objects.create(
            coin="USDC", chain="ERC20", deposit_address="0xabc", sort_order=20
        )
        code = make_code(user, "telegram_signal", tg_plan)
        first = get_or_refresh_quote(code, coin)
        second = get_or_refresh_quote(code, other)
        assert second.id != first.id
        assert second.coin_id == other.id

    def test_submitted_code_never_relocks(self, db, tg_plan, coin, rate_one, user):
        code = make_code(user, "telegram_signal", tg_plan)
        quote = get_or_refresh_quote(code, coin)
        code.status = "submitted"
        code.save()
        expire_quote(code)
        same = get_or_refresh_quote(code, coin)
        assert same.id == quote.id
        assert PaymentQuote.objects.filter(code=code).count() == 1

    def test_submitted_without_quote_never_hits_feed(self, db, tg_plan, coin, user):
        """Worst case: submitted code with no quote → no price fetch at all."""
        code = make_code(user, "telegram_signal", tg_plan)
        code.status = "submitted"
        code.save()
        assert get_or_refresh_quote(code, coin) is None  # would raise if priced

    def test_stable_peg_fallback_when_feed_down(self, monkeypatch):
        """USDT with a dead feed pegs to 1.0 (logged), never a fake number."""
        monkeypatch.setitem(
            sys.modules,
            "ccxt",
            types.SimpleNamespace(
                bybit=types.SimpleNamespace(
                    fetch_ticker=lambda self=None, pair=None: (_ for _ in ()).throw(
                        RuntimeError("down")
                    ),
                )
            ),
        )
        monkeypatch.delattr("apps.payments.services.quote.get_coin_usd_rate", raising=False)
        with override_settings(PAYMENT_QUOTE_EXCHANGE="bybit"):
            rate = get_coin_usd_rate("USDT")
        assert rate == Decimal("1.00000000")

    def test_non_stable_refuses_when_feed_down(self, monkeypatch):
        """BTC with a dead feed MUST fail — never silently peg."""
        monkeypatch.setitem(
            sys.modules,
            "ccxt",
            types.SimpleNamespace(
                bybit=types.SimpleNamespace(
                    fetch_ticker=lambda self=None, pair=None: (_ for _ in ()).throw(
                        RuntimeError("down")
                    ),
                )
            ),
        )
        with override_settings(PAYMENT_QUOTE_EXCHANGE="bybit"):
            with pytest.raises(QuoteUnavailable):
                get_coin_usd_rate("BTC")

    def test_direct_pair_used_when_available(self, monkeypatch):
        """USDT/USD ticker wins when the exchange lists it."""
        calls = []

        class Ex:
            def __init__(self, *a, **k):
                pass

            def fetch_ticker(self, pair):
                calls.append(pair)
                if pair == "USDT/USD":
                    return {"last": 0.9995}
                raise RuntimeError("no")

        monkeypatch.setitem(sys.modules, "ccxt", types.SimpleNamespace(bybit=Ex))
        with override_settings(PAYMENT_QUOTE_EXCHANGE="bybit"):
            assert get_coin_usd_rate("USDT") == Decimal("0.99950000")
        assert calls[0] == "USDT/USD"

    def test_unknown_exchange_refuses(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "ccxt", types.SimpleNamespace(bybit=object))
        with override_settings(PAYMENT_QUOTE_EXCHANGE="notanexchange"):
            with pytest.raises(QuoteUnavailable):
                get_coin_usd_rate("BTC")


# ---------------------------------------------------------------------------
# FR A3 quote rules: combined amount, payment window, re-request
# ---------------------------------------------------------------------------


class TestQuoteWindowAndCombinedAmount:
    def test_create_quote_combined_amount_includes_chain_fee(
        self, db, tg_plan, coin, rate_one, user
    ):
        """crypto_amount = plan price + network_fee (combined payable)."""
        coin.network_fee = Decimal("0.20000000")
        coin.save()
        code = make_code(user, "telegram_signal", tg_plan)  # fiat 15.00
        quote = create_quote(code, coin)
        assert quote.crypto_amount == Decimal("15.20000000")

    def test_first_quote_starts_payment_window(self, db, tg_plan, coin, rate_one, user):
        code = make_code(user, "telegram_signal", tg_plan)
        assert code.quote_window_expires_at is None
        create_quote(code, coin)
        code.refresh_from_db()
        expected = timezone.now() + timedelta(seconds=coin.quote_window_seconds)
        assert code.quote_window_expires_at is not None
        # default 6h window — allow a few seconds of test drift
        assert abs((code.quote_window_expires_at - expected).total_seconds()) < 5

    def test_window_expiry_truncates_quote_ttl(self, db, tg_plan, coin, rate_one, user):
        """expires_at ≤ window end, so is_expired flips when re-request starts."""
        coin.quote_window_seconds = 120  # shorter than the 300s TTL
        coin.save()
        code = make_code(user, "telegram_signal", tg_plan)
        quote = create_quote(code, coin)
        code.refresh_from_db()
        assert quote.expires_at == code.quote_window_expires_at

    def test_automatic_refresh_does_not_extend_window(self, db, tg_plan, coin, rate_one, user):
        code = make_code(user, "telegram_signal", tg_plan)
        create_quote(code, coin)
        code.refresh_from_db()
        window_before = code.quote_window_expires_at
        expire_quote(code)
        get_or_refresh_quote(code, coin)  # TTL refresh inside the window
        code.refresh_from_db()
        assert code.quote_window_expires_at == window_before

    def test_is_window_open_helper(self, db, tg_plan, coin, rate_one, user):
        code = make_code(user, "telegram_signal", tg_plan)
        assert is_window_open(code) is True  # never-quoted counts as open
        create_quote(code, coin)
        assert is_window_open(code) is True
        close_window(code)
        assert is_window_open(code) is False

    def test_window_closed_never_silently_relocks(
        self, db, tg_plan, coin, rate_one, user, monkeypatch
    ):
        """FR A3: after expiry the quote stays expired until re-request."""
        code = make_code(user, "telegram_signal", tg_plan)
        first = get_or_refresh_quote(code, coin)
        close_window(code)
        expire_quote(code)
        monkeypatch.setattr(
            "apps.payments.services.quote.get_coin_usd_rate",
            lambda symbol: (_ for _ in ()).throw(AssertionError("must not price")),
        )
        same = get_or_refresh_quote(code, coin)
        assert same.id == first.id
        assert same.is_expired
        assert PaymentQuote.objects.filter(code=code).count() == 1

    def test_window_closed_coin_switch_never_relocks(
        self, db, tg_plan, coin, rate_one, user, monkeypatch
    ):
        other = PaymentCoin.objects.create(
            coin="USDC", chain="ERC20", deposit_address="0xabc", sort_order=20
        )
        code = make_code(user, "telegram_signal", tg_plan)
        first = get_or_refresh_quote(code, coin)
        close_window(code)
        monkeypatch.setattr(
            "apps.payments.services.quote.get_coin_usd_rate",
            lambda symbol: (_ for _ in ()).throw(AssertionError("must not price")),
        )
        same = get_or_refresh_quote(code, other)
        assert same.id == first.id
        assert PaymentQuote.objects.filter(code=code).count() == 1

    def test_renew_quote_resets_window_and_relocks(self, db, tg_plan, coin, rate_one, user):
        code = make_code(user, "telegram_signal", tg_plan)
        get_or_refresh_quote(code, coin)
        close_window(code)
        expire_quote(code)
        quote = renew_quote(code)
        code.refresh_from_db()
        assert not quote.is_expired
        assert code.quotes.count() == 2
        # window restarted for a full coin window from now
        assert is_window_open(code) is True
        expected = timezone.now() + timedelta(seconds=coin.quote_window_seconds)
        assert abs((code.quote_window_expires_at - expected).total_seconds()) < 5

    def test_renew_at_new_rate_after_window(self, db, tg_plan, coin, rate_one, user, monkeypatch):
        code = make_code(user, "telegram_signal", tg_plan)
        get_or_refresh_quote(code, coin)
        close_window(code)
        expire_quote(code)
        monkeypatch.setattr(
            "apps.payments.services.quote.get_coin_usd_rate",
            lambda symbol: Decimal("2.00000000"),
        )
        quote = renew_quote(code)
        assert quote.rate == Decimal("2.00000000")
        assert quote.crypto_amount == Decimal("7.50000000")

    def test_renew_rejects_submitted_code(self, db, tg_plan, coin, rate_one, user):
        code = make_code(user, "telegram_signal", tg_plan)
        get_or_refresh_quote(code, coin)
        code.status = "submitted"
        code.save()
        with pytest.raises(ValueError):
            renew_quote(code)

    def test_renew_without_any_coin_refused(self, db, tg_plan, user):
        code = make_code(user, "telegram_signal", tg_plan)
        with pytest.raises(ValueError):
            renew_quote(code)


# ---------------------------------------------------------------------------
# payment coin list + seed
# ---------------------------------------------------------------------------


class TestPaymentCoinsAndSeed:
    def test_public_list_only_configured_active(self, db, api_client):
        PaymentCoin.objects.create(coin="USDT", chain="TRC20", deposit_address="TX1")
        PaymentCoin.objects.create(coin="USDT", chain="ERC20", deposit_address="")  # blank
        PaymentCoin.objects.create(
            coin="BTC", chain="Bitcoin", deposit_address="bc1", is_active=False
        )
        resp = api_client.get(reverse("payments:payment-coin-list"))
        assert resp.status_code == 200
        assert len(resp.data) == 1
        assert resp.data[0]["coin"] == "USDT" and resp.data[0]["chain"] == "TRC20"

    def test_seed_idempotent_and_never_invents_addresses(self, db):
        call_command("seed_payment_coins")
        call_command("seed_payment_coins")
        assert PaymentCoin.objects.count() == 3
        assert set(PaymentCoin.objects.values_list("coin", flat=True)) == {"USDT"}
        chains = set(PaymentCoin.objects.values_list("chain", flat=True))
        assert chains == {"TRC20", "BEP20", "ERC20"}
        # addresses deliberately blank until admin sets real ones
        assert not PaymentCoin.objects.filter(deposit_address__gt="").exists()

    def test_seed_dry_run_writes_nothing(self, db):
        call_command("seed_payment_coins", dry_run=True)
        assert PaymentCoin.objects.count() == 0


# ---------------------------------------------------------------------------
# code creation
# ---------------------------------------------------------------------------


class TestPaymentCodeCreate:
    URL = "payments:payment-code-create"

    def test_telegram_monthly(self, auth_client, tg_plan, coin):
        resp = auth_client.post(
            reverse(self.URL),
            {"order_kind": "telegram_signal", "plan_id": tg_plan.pk, "billing_cycle": "monthly"},
            format="json",
        )
        assert resp.status_code == 201
        assert resp.data["fiat_amount"] == "15.00"
        assert resp.data["status"] == "awaiting_payment"
        assert len(resp.data["code"]) >= 10

    def test_telegram_by_slug_and_quarterly(self, auth_client, tg_plan, coin):
        resp = auth_client.post(
            reverse(self.URL),
            {
                "order_kind": "telegram_signal",
                "plan_id": "g2-signals",
                "billing_cycle": "quarterly",
            },
            format="json",
        )
        assert resp.status_code == 201
        assert resp.data["fiat_amount"] == "40.00"
        assert resp.data["billing_cycle"] == "quarterly"

    def test_bot_plan_forces_monthly_fiat(self, auth_client, bot_plan, coin):
        resp = auth_client.post(
            reverse(self.URL),
            {"order_kind": "bot", "plan_id": bot_plan.slug, "billing_cycle": "yearly"},
            format="json",
        )
        assert resp.status_code == 201
        assert resp.data["fiat_amount"] == "49.00"  # bot = monthly price always
        assert resp.data["billing_cycle"] == "monthly"

    def test_invalid_plan_400(self, auth_client, coin):
        resp = auth_client.post(
            reverse(self.URL),
            {"order_kind": "bot", "plan_id": "nope"},
            format="json",
        )
        assert resp.status_code == 400

    def test_invalid_billing_cycle_400(self, auth_client, tg_plan, coin):
        resp = auth_client.post(
            reverse(self.URL),
            {"order_kind": "telegram_signal", "plan_id": tg_plan.pk, "billing_cycle": "weekly"},
            format="json",
        )
        assert resp.status_code == 400

    def test_invalid_order_kind_400(self, auth_client, tg_plan, coin):
        resp = auth_client.post(
            reverse(self.URL),
            {"order_kind": "gift", "plan_id": tg_plan.pk},
            format="json",
        )
        assert resp.status_code == 400

    def test_no_configured_coin_400(self, auth_client, tg_plan):
        """Worst case: no receive address set anywhere → fail loudly."""
        resp = auth_client.post(
            reverse(self.URL),
            {"order_kind": "telegram_signal", "plan_id": tg_plan.pk},
            format="json",
        )
        assert resp.status_code == 400
        assert "coin" in str(resp.data).lower()
        assert resp.data["error"]["field_errors"]["coin"]  # envelope, keyed
        assert PaymentCode.objects.count() == 0

    def test_duplicate_telegram_409_with_metadata(self, auth_client, user, tg_plan, coin):
        TelegramSubscription.objects.create(
            user=user, plan=tg_plan, status="active", telegram_handle="x"
        )
        resp = auth_client.post(
            reverse(self.URL),
            {"order_kind": "telegram_signal", "plan_id": tg_plan.pk},
            format="json",
        )
        assert resp.status_code == 409
        assert resp.data["error"]["code"] == "CONFLICT"
        assert "already have" in resp.data["error"]["message"]
        assert "subscription_id" in resp.data["error"]["details"]

    def test_capacity_full_409(self, auth_client, coin, db):
        plan = TelegramSignalPlan.objects.create(
            name="Cap",
            slug="cap",
            description="x",
            price_monthly=Decimal("10.00"),
            price_quarterly=Decimal("30.00"),
            price_yearly=Decimal("100.00"),
            max_subscribers=1,
        )
        TelegramSubscription.objects.create(
            plan=plan,
            status="active",
            telegram_handle="taken",
            user=__import__("django.contrib.auth", fromlist=["get_user_model"])
            .get_user_model()
            .objects.create_user(username="occupant", email="o@x.com", password="p"),
        )
        resp = auth_client.post(
            reverse(self.URL),
            {"order_kind": "telegram_signal", "plan_id": plan.pk},
            format="json",
        )
        assert resp.status_code == 409
        assert "maximum subscribers" in str(resp.data)

    def test_unauthenticated_401(self, api_client, tg_plan, coin):
        resp = api_client.post(
            reverse(self.URL),
            {"order_kind": "telegram_signal", "plan_id": tg_plan.pk},
            format="json",
        )
        assert resp.status_code == 401

    def test_codes_unique_per_order(self, auth_client, second_auth_client, tg_plan, coin):
        a = auth_client.post(
            reverse(self.URL),
            {"order_kind": "telegram_signal", "plan_id": tg_plan.pk},
            format="json",
        )
        b = second_auth_client.post(
            reverse(self.URL),
            {"order_kind": "telegram_signal", "plan_id": tg_plan.pk},
            format="json",
        )
        assert a.status_code == 201 and b.status_code == 201
        assert a.data["code"] != b.data["code"]


# ---------------------------------------------------------------------------
# detail → live quote
# ---------------------------------------------------------------------------


class TestPaymentCodeDetailQuote:
    def url(self, code):
        return reverse("payments:payment-code-detail", args=[code.code])

    def test_returns_live_quote(self, auth_client, user, tg_plan, coin, rate_one):
        code = make_code(user, "telegram_signal", tg_plan)
        resp = auth_client.get(self.url(code))
        assert resp.status_code == 200
        quote = resp.data["quote"]
        assert quote["rate"] == "1.00000000"
        assert quote["crypto_amount"] == "15.00000000"
        assert quote["is_expired"] is False
        assert quote["coin"]["chain"] == "TRC20"
        assert resp.data["locked_rate"] is None  # not frozen until proof

    def test_coin_switch_param(self, auth_client, user, tg_plan, coin, rate_one):
        other = PaymentCoin.objects.create(
            coin="USDC", chain="BEP20", deposit_address="bnb1", sort_order=20
        )
        code = make_code(user, "telegram_signal", tg_plan)
        resp = auth_client.get(self.url(code) + f"?coin_id={other.id}")
        assert resp.status_code == 200
        assert resp.data["quote"]["coin"]["chain"] == "BEP20"

    def test_unknown_coin_param_400(self, auth_client, user, tg_plan, coin, rate_one):
        code = make_code(user, "telegram_signal", tg_plan)
        resp = auth_client.get(self.url(code) + "?coin_id=99999")
        assert resp.status_code == 400

    def test_expired_quote_relocks_on_poll(
        self, auth_client, user, tg_plan, coin, rate_one, monkeypatch
    ):
        code = make_code(user, "telegram_signal", tg_plan)
        auth_client.get(self.url(code))  # first lock @ 1.0
        expire_quote(code)
        monkeypatch.setattr(
            "apps.payments.services.quote.get_coin_usd_rate",
            lambda symbol: Decimal("2.00000000"),
        )
        resp = auth_client.get(self.url(code))
        assert resp.status_code == 200
        assert resp.data["quote"]["rate"] == "2.00000000"
        assert resp.data["quote"]["crypto_amount"] == "7.50000000"
        assert PaymentQuote.objects.filter(code=code).count() == 2

    def test_submitted_code_frozen_on_poll(
        self, auth_client, user, tg_plan, coin, rate_one, monkeypatch
    ):
        code = make_code(user, "telegram_signal", tg_plan)
        auth_client.get(self.url(code))
        code.status = "submitted"
        code.save()
        expire_quote(code)
        monkeypatch.setattr(
            "apps.payments.services.quote.get_coin_usd_rate",
            lambda symbol: (_ for _ in ()).throw(AssertionError("must not price")),
        )
        resp = auth_client.get(self.url(code))
        assert resp.status_code == 200
        assert PaymentQuote.objects.filter(code=code).count() == 1

    def test_feed_down_returns_503(self, auth_client, user, tg_plan, coin, monkeypatch):
        monkeypatch.setattr(
            "apps.payments.services.quote.get_coin_usd_rate",
            lambda symbol: (_ for _ in ()).throw(QuoteUnavailable("down")),
        )
        code = make_code(user, "telegram_signal", tg_plan)
        resp = auth_client.get(self.url(code))
        assert resp.status_code == 503
        # standard envelope (A14), not a flat string
        assert resp.data["error"]["code"] == "SERVICE_UNAVAILABLE"

    def test_other_users_code_404(self, auth_client, second_user, tg_plan, coin, rate_one):
        code = make_code(second_user, "telegram_signal", tg_plan)
        resp = auth_client.get(self.url(code))
        assert resp.status_code == 404

    def test_unauthenticated_401(self, api_client, user, tg_plan, coin, rate_one):
        code = make_code(user, "telegram_signal", tg_plan)
        assert api_client.get(self.url(code)).status_code == 401

    def test_quote_payload_exposes_chain_fee_and_combined_amount(
        self, auth_client, user, tg_plan, coin, rate_one
    ):
        """FR A3 breakdown: coin.network_fee + quote.crypto_amount = combined."""
        coin.network_fee = Decimal("0.20000000")
        coin.save()
        code = make_code(user, "telegram_signal", tg_plan)
        resp = auth_client.get(self.url(code))
        quote = resp.data["quote"]
        assert quote["coin"]["network_fee"] == "0.20000000"
        assert quote["crypto_amount"] == "15.20000000"

    def test_window_closed_returns_expired_quote_no_relock(
        self, auth_client, user, tg_plan, coin, rate_one, monkeypatch
    ):
        """Polling after the window must NOT silently re-lock — only renew does."""
        code = make_code(user, "telegram_signal", tg_plan)
        auth_client.get(self.url(code))
        close_window(code)
        expire_quote(code)
        monkeypatch.setattr(
            "apps.payments.services.quote.get_coin_usd_rate",
            lambda symbol: (_ for _ in ()).throw(AssertionError("must not price")),
        )
        resp = auth_client.get(self.url(code))
        assert resp.status_code == 200
        assert resp.data["quote"]["is_expired"] is True
        assert PaymentQuote.objects.filter(code=code).count() == 1


# ---------------------------------------------------------------------------
# re-request quote after window (POST …/quote/)
# ---------------------------------------------------------------------------


class TestPaymentCodeQuoteRerequest:
    def url(self, code):
        return reverse("payments:payment-code-quote", args=[code.code])

    def test_rerequest_after_window_relocks(self, auth_client, user, tg_plan, coin, rate_one):
        code = make_code(user, "telegram_signal", tg_plan)
        auth_client.get(reverse("payments:payment-code-detail", args=[code.code]))
        close_window(code)
        expire_quote(code)
        resp = auth_client.post(self.url(code), {}, format="json")
        assert resp.status_code == 200
        assert resp.data["quote"]["is_expired"] is False
        assert resp.data["quote"]["rate"] == "1.00000000"
        assert PaymentQuote.objects.filter(code=code).count() == 2
        code.refresh_from_db()
        assert is_window_open(code) is True  # window restarted

    def test_rerequest_with_coin_switch(self, auth_client, user, tg_plan, coin, rate_one):
        other = PaymentCoin.objects.create(
            coin="USDC", chain="BEP20", deposit_address="bnb1", sort_order=20
        )
        code = make_code(user, "telegram_signal", tg_plan)
        auth_client.get(reverse("payments:payment-code-detail", args=[code.code]))
        close_window(code)
        resp = auth_client.post(self.url(code), {"coin_id": other.pk}, format="json")
        assert resp.status_code == 200
        assert resp.data["quote"]["coin"]["chain"] == "BEP20"

    def test_rerequest_inside_window_still_relocks(
        self, auth_client, user, tg_plan, coin, rate_one
    ):
        """Explicit request always force-locks fresh + restarts the window."""
        code = make_code(user, "telegram_signal", tg_plan)
        auth_client.get(reverse("payments:payment-code-detail", args=[code.code]))
        code.refresh_from_db()
        window_before = code.quote_window_expires_at
        resp = auth_client.post(self.url(code), {}, format="json")
        assert resp.status_code == 200
        assert resp.data["quote"]["is_expired"] is False
        assert resp.data["quote"]["rate"] == "1.00000000"
        assert PaymentQuote.objects.filter(code=code).count() == 2
        code.refresh_from_db()
        assert code.quote_window_expires_at >= window_before

    def test_rerequest_unknown_coin_400(self, auth_client, user, tg_plan, coin, rate_one):
        code = make_code(user, "telegram_signal", tg_plan)
        resp = auth_client.post(self.url(code), {"coin_id": 99999}, format="json")
        assert resp.status_code == 400

    def test_rerequest_submitted_code_400(self, auth_client, user, tg_plan, coin, rate_one):
        code = make_code(user, "telegram_signal", tg_plan)
        code.status = "submitted"
        code.save()
        resp = auth_client.post(self.url(code), {}, format="json")
        assert resp.status_code == 400

    def test_rerequest_other_users_code_404(
        self, auth_client, second_user, tg_plan, coin, rate_one
    ):
        code = make_code(second_user, "telegram_signal", tg_plan)
        resp = auth_client.post(self.url(code), {}, format="json")
        assert resp.status_code == 404

    def test_rerequest_unauthenticated_401(self, api_client, user, tg_plan, coin, rate_one):
        code = make_code(user, "telegram_signal", tg_plan)
        assert api_client.post(self.url(code), {}, format="json").status_code == 401


# ---------------------------------------------------------------------------
# proof submission → fulfillment
# ---------------------------------------------------------------------------


class TestPaymentCodeProof:
    def url(self, code):
        return reverse("payments:payment-code-proof", args=[code.code])

    def test_telegram_hash_proof(self, auth_client, user, tg_plan, coin, rate_one):
        code = make_code(user, "telegram_signal", tg_plan)
        resp = auth_client.post(
            self.url(code),
            {
                "payment_transaction_hash": "0xdeadbeef",
                "payment_blockchain": "TRC20",
                "telegram_handle": "@g2tester",
            },
            format="json",
        )
        assert resp.status_code == 201
        assert resp.data["status"] == "submitted"
        sub = TelegramSubscription.objects.get(id=resp.data["subscription_id"])
        assert sub.status == "pending_approval"
        assert sub.telegram_handle == "@g2tester"
        assert sub.payment_transaction_hash == "0xdeadbeef"
        assert sub.amount_paid == Decimal("15.00")
        code.refresh_from_db()
        assert code.status == "submitted"
        assert code.locked_rate == Decimal("1.00000000")
        assert code.locked_crypto_amount == Decimal("15.00000000")
        assert code.locked_coin == "USDT"

    def test_telegram_screenshot_proof(self, auth_client, user, tg_plan, coin, rate_one):
        from django.core.files.uploadedfile import SimpleUploadedFile

        code = make_code(user, "telegram_signal", tg_plan)
        resp = auth_client.post(
            self.url(code),
            {
                "payment_screenshot": SimpleUploadedFile("p.png", _PNG_1PX, "image/png"),
                "telegram_handle": "@imguser",
            },
            format="multipart",
        )
        assert resp.status_code == 201
        sub = TelegramSubscription.objects.get(id=resp.data["subscription_id"])
        assert sub.payment_screenshot

    def test_telegram_missing_handle_400(self, auth_client, user, tg_plan, coin, rate_one):
        code = make_code(user, "telegram_signal", tg_plan)
        resp = auth_client.post(self.url(code), {"payment_transaction_hash": "0x1"}, format="json")
        assert resp.status_code == 400

    def test_missing_proof_400(self, auth_client, user, tg_plan, coin, rate_one):
        code = make_code(user, "telegram_signal", tg_plan)
        resp = auth_client.post(self.url(code), {"telegram_handle": "@x"}, format="json")
        assert resp.status_code == 400

    def test_bot_proof_creates_pending_subscription(
        self, auth_client, user, bot_plan, coin, rate_one
    ):
        code = make_code(user, "bot", bot_plan)
        resp = auth_client.post(
            self.url(code),
            {"payment_transaction_hash": "0xbot", "payment_blockchain": "BEP20"},
            format="json",
        )
        assert resp.status_code == 201
        sub = BotSubscription.objects.get(id=resp.data["subscription_id"])
        assert sub.status == "pending_approval"
        assert sub.plan.name == "G2 Bot"
        assert sub.plan.bot_type == "custom"  # shim get_or_create matches legacy
        code.refresh_from_db()
        assert code.subscription_id == str(sub.id)
        assert code.status == "submitted"

    def test_proof_twice_409(self, auth_client, user, tg_plan, coin, rate_one):
        code = make_code(user, "telegram_signal", tg_plan)
        first = auth_client.post(
            self.url(code),
            {"payment_transaction_hash": "0x1", "telegram_handle": "@a"},
            format="json",
        )
        assert first.status_code == 201
        second = auth_client.post(
            self.url(code),
            {"payment_transaction_hash": "0x2", "telegram_handle": "@a"},
            format="json",
        )
        assert second.status_code == 409

    def test_rejects_expired_state_409(self, auth_client, user, tg_plan, coin, rate_one):
        code = make_code(user, "telegram_signal", tg_plan)
        code.status = "cancelled"
        code.save()
        resp = auth_client.post(
            self.url(code),
            {"payment_transaction_hash": "0x1", "telegram_handle": "@a"},
            format="json",
        )
        assert resp.status_code == 409

    def test_other_users_code_404(self, auth_client, second_user, tg_plan, coin, rate_one):
        code = make_code(second_user, "telegram_signal", tg_plan)
        resp = auth_client.post(
            self.url(code),
            {"payment_transaction_hash": "0x1", "telegram_handle": "@a"},
            format="json",
        )
        assert resp.status_code == 404

    def test_duplicate_appearing_after_creation_409(
        self, auth_client, user, tg_plan, coin, rate_one
    ):
        """Race: legacy subscribe succeeds between code creation and proof."""
        code = make_code(user, "telegram_signal", tg_plan)
        TelegramSubscription.objects.create(
            user=user,
            plan=tg_plan,
            status="pending_approval",
            telegram_handle="racer",
        )
        resp = auth_client.post(
            self.url(code),
            {"payment_transaction_hash": "0x1", "telegram_handle": "@a"},
            format="json",
        )
        assert resp.status_code == 409

    def test_frozen_rate_uses_fresh_price_at_submission(
        self, auth_client, user, tg_plan, coin, rate_one, monkeypatch
    ):
        """Quote older than TTL → re-priced at proof time, then frozen."""
        code = make_code(user, "telegram_signal", tg_plan)
        auth_client.get(reverse("payments:payment-code-detail", args=[code.code]))
        expire_quote(code)
        monkeypatch.setattr(
            "apps.payments.services.quote.get_coin_usd_rate",
            lambda symbol: Decimal("2.00000000"),
        )
        resp = auth_client.post(
            self.url(code),
            {"payment_transaction_hash": "0x1", "telegram_handle": "@a"},
            format="json",
        )
        assert resp.status_code == 201
        assert resp.data["locked_rate"] == "2.00000000"
        assert resp.data["locked_crypto_amount"] == "7.50000000"

    def test_proof_after_window_freezes_stale_amount(
        self, auth_client, user, tg_plan, coin, rate_one, monkeypatch
    ):
        """FR A3: window expired at submit → lock the stale quote, no re-price."""
        code = make_code(user, "telegram_signal", tg_plan)
        auth_client.get(reverse("payments:payment-code-detail", args=[code.code]))
        close_window(code)
        expire_quote(code)
        monkeypatch.setattr(
            "apps.payments.services.quote.get_coin_usd_rate",
            lambda symbol: (_ for _ in ()).throw(AssertionError("must not price")),
        )
        resp = auth_client.post(
            self.url(code),
            {"payment_transaction_hash": "0x1", "telegram_handle": "@a"},
            format="json",
        )
        assert resp.status_code == 201
        assert resp.data["locked_rate"] == "1.00000000"
        assert resp.data["locked_crypto_amount"] == "15.00000000"

    def test_direct_proof_without_detail_get_still_locks(
        self, auth_client, user, tg_plan, coin, rate_one
    ):
        """Worst case: proof posted without ever loading the quote."""
        code = make_code(user, "telegram_signal", tg_plan)
        resp = auth_client.post(
            self.url(code),
            {"payment_transaction_hash": "0x1", "telegram_handle": "@a"},
            format="json",
        )
        assert resp.status_code == 201
        assert resp.data["locked_rate"] == "1.00000000"

    def test_unauthenticated_401(self, api_client, user, tg_plan, coin, rate_one):
        code = make_code(user, "telegram_signal", tg_plan)
        resp = api_client.post(self.url(code), {"payment_transaction_hash": "0x1"}, format="json")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# admin-decision mirror (signal)
# ---------------------------------------------------------------------------


class TestCodeStatusMirror:
    @pytest.fixture
    def admin(self, db):
        from django.contrib.auth import get_user_model

        return get_user_model().objects.create_superuser(
            username="g2admin", email="g2@x.com", password="p"
        )

    def test_telegram_approve_marks_code_approved(self, user, admin, tg_plan, coin, rate_one):
        code = make_code(user, "telegram_signal", tg_plan)
        sub = TelegramSubscription.objects.create(
            user=user, plan=tg_plan, status="pending_approval", telegram_handle="x"
        )
        code.status = "submitted"
        code.subscription_id = str(sub.id)
        code.save()
        sub.approve(admin, notes="ok")
        code.refresh_from_db()
        assert code.status == "approved"

    def test_telegram_reject_marks_code_rejected(self, user, admin, tg_plan, coin, rate_one):
        code = make_code(user, "telegram_signal", tg_plan)
        sub = TelegramSubscription.objects.create(
            user=user, plan=tg_plan, status="pending_approval", telegram_handle="x"
        )
        code.status = "submitted"
        code.subscription_id = str(sub.id)
        code.save()
        sub.reject(admin, "bad proof")
        code.refresh_from_db()
        assert code.status == "rejected"

    def test_bot_approve_marks_code_approved(self, user, admin, bot_plan, coin, rate_one):
        from apps.payments.models import BotSubscriptionPlan

        code = make_code(user, "bot", bot_plan)
        shim = BotSubscriptionPlan.objects.create(
            name="G2 Bot", bot_type="custom", price=Decimal("49.00")
        )
        sub = BotSubscription.objects.create(user=user, plan=shim, status="pending_approval")
        code.status = "submitted"
        code.subscription_id = str(sub.id)
        code.save()
        sub.approve(admin)
        code.refresh_from_db()
        assert code.status == "approved"

    def test_legacy_subscription_save_is_noop(self, db, user, tg_plan):
        """Worst case: legacy flow (no code row) must not error in the signal."""
        sub = TelegramSubscription.objects.create(
            user=user, plan=tg_plan, status="pending_approval", telegram_handle="x"
        )
        sub.status = "active"
        sub.save()  # signal runs, finds no code → no-op, no exception
        assert sub.status == "active"


# ---------------------------------------------------------------------------
# end-to-end happy path (create → quote → proof → approve)
# ---------------------------------------------------------------------------


class TestE2EFlow:
    def test_full_telegram_lifecycle(self, auth_client, user, tg_plan, coin, rate_one, db):
        from django.contrib.auth import get_user_model

        admin = get_user_model().objects.create_superuser(
            username="e2eadmin", email="e2e@x.com", password="p"
        )

        # 1. create code
        created = auth_client.post(
            reverse("payments:payment-code-create"),
            {"order_kind": "telegram_signal", "plan_id": tg_plan.pk, "billing_cycle": "monthly"},
            format="json",
        )
        assert created.status_code == 201
        code_str = created.data["code"]

        # 2. poll quote twice (price changes in between)
        q1 = auth_client.get(reverse("payments:payment-code-detail", args=[code_str]))
        assert q1.data["quote"]["rate"] == "1.00000000"
        # price moves: expire the lock, then re-poll at 2.0
        expire_quote(PaymentCode.objects.get(code=code_str))
        from unittest import mock

        with mock.patch(
            "apps.payments.services.quote.get_coin_usd_rate",
            return_value=Decimal("2.00000000"),
        ):
            q2 = auth_client.get(reverse("payments:payment-code-detail", args=[code_str]))
        assert q2.data["quote"]["rate"] == "2.00000000"

        # 3. proof at the then-current rate
        proof = auth_client.post(
            reverse("payments:payment-code-proof", args=[code_str]),
            {"payment_transaction_hash": "0xe2e", "telegram_handle": "@e2e"},
            format="json",
        )
        assert proof.status_code == 201
        assert proof.data["locked_rate"] == "2.00000000"

        # 4. admin approves → code flips
        sub = TelegramSubscription.objects.get(id=proof.data["subscription_id"])
        sub.approve(admin, notes="paid")
        final = auth_client.get(reverse("payments:payment-code-detail", args=[code_str]))
        assert final.data["status"] == "approved"
        assert final.data["quote"]["rate"] == "2.00000000"  # frozen, not re-priced
