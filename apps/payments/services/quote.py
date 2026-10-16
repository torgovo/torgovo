"""
G2 / FR A3 — quote service: exchange-style live-price lock for plan payments.

Product rules (FR A3, user decisions 2026-10-12 / 2026-10-14):
- Quote refresh cadence: 5 minutes (settings default 300s, clamped 60..3600)
  while the payment window is open — the FE auto-updates the combined amount.
- Combined payable amount: plan price + per-chain fee buffer
  (PaymentCoin.network_fee, coin units) — the user sends crypto_amount.
- Payment window: per-coin admin-configurable (default 6h). Started at the
  first quote, reset only by an explicit re-request. After it ends the quote
  stays expired — NO silent re-lock at the then-current price.
- Price source: CCXT public ticker on the configured exchange, using the
  PAIR OF THE COIN BEING PAID (USDT → USDT-priced pair, USDC → USDC-priced).
- Auto on-chain TX verification is intentionally NOT built yet (manual
  admin verify at launch; hook point = PaymentCode.locked_* audit fields).
"""

import logging
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.utils import timezone

from apps.payments.models import PaymentCode, PaymentCoin, PaymentQuote

logger = logging.getLogger(__name__)

# 8 dp is the precision floor for USDT-family amounts on-chain.
CRYPTO_QUANT = Decimal("0.00000001")


class QuoteUnavailable(Exception):
    """No reliable live rate for the coin — refuse to quote (never fake price)."""


def get_quote_ttl_seconds() -> int:
    """Configured refresh TTL clamped to the 60..3600s envelope (default 300s)."""
    raw = getattr(settings, "PAYMENT_QUOTE_TTL_SECONDS", 300)
    # NOTE: no `or 300` — a configured 0 must clamp to 60, not fall back.
    ttl = 300 if raw is None else int(raw)
    return max(60, min(3600, ttl))


def is_window_open(code: PaymentCode) -> bool:
    """
    True while the code's payment window is open.

    A never-quoted code has no window yet (the first quote starts it) and
    counts as open — get_or_refresh_quote's other guards still apply.
    """
    if code.quote_window_expires_at is None:
        return True
    return timezone.now() < code.quote_window_expires_at


def get_coin_usd_rate(coin_symbol: str) -> Decimal:
    """
    Live USD rate for a payment coin via CCXT public ticker.

    Fallback chain (first hit wins):
      1. ``{COIN}/USD`` direct pair on the configured exchange
      2. inverse of ``USD/{COIN}``
      3. peg 1.000 — ONLY for settings.PAYMENT_STABLE_COINS (logged)
      4. otherwise QuoteUnavailable (quote fails loudly, never silently pegs)
    """
    coin = coin_symbol.upper()
    exchange_id = getattr(settings, "PAYMENT_QUOTE_EXCHANGE", "bybit")
    pairs = [f"{coin}/USD", f"USD/{coin}"]
    try:
        import ccxt

        exchange_class = getattr(ccxt, exchange_id, None)
        if exchange_class is None:
            raise QuoteUnavailable(f"Unknown CCXT exchange '{exchange_id}'")
        exchange = exchange_class({"enableRateLimit": True})
        for pair in pairs:
            try:
                ticker = exchange.fetch_ticker(pair)
            except Exception:  # noqa: BLE001 — network/ticker errors → next pair
                continue
            last = ticker.get("last") if ticker else None
            if not last or Decimal(str(last)) <= 0:
                continue
            rate = Decimal(str(last))
            if pair.startswith("USD/"):
                rate = Decimal(1) / rate
            return rate.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
    except QuoteUnavailable:
        raise
    except Exception as exc:  # ccxt import/network hard-failure
        logger.warning("quote rate lookup failed for %s: %s", coin, exc)

    # Peg fallback — stables only, and always logged for audit.
    if coin in getattr(settings, "PAYMENT_STABLE_COINS", []):
        logger.info("quote rate peg fallback 1.0 for stable coin %s", coin)
        return Decimal("1.00000000")
    raise QuoteUnavailable(f"No USD rate available for {coin}")


def create_quote(code: PaymentCode, coin: PaymentCoin) -> PaymentQuote:
    """
    Lock a fresh quote: live rate → combined amount → TTL/window expiry.

    crypto_amount = (fiat_amount / rate) + coin.network_fee — the combined
    payable amount (plan price + chain fee buffer, FR A3).

    Starts the payment window on the first quote (never reset by automatic
    refreshes). expires_at is truncated at the window end so `is_expired`
    flips exactly when re-request becomes required.
    """
    rate = get_coin_usd_rate(coin.coin)
    if rate <= 0:
        raise QuoteUnavailable(f"Non-positive rate for {coin.coin}")
    plan_crypto = (code.fiat_amount / rate).quantize(CRYPTO_QUANT, rounding=ROUND_HALF_UP)
    crypto_amount = (plan_crypto + coin.network_fee).quantize(CRYPTO_QUANT)
    now = timezone.now()
    if code.quote_window_expires_at is None:
        code.quote_window_expires_at = now + timedelta(seconds=coin.quote_window_seconds)
        code.save(update_fields=["quote_window_expires_at"])
    window_end = code.quote_window_expires_at
    expires_at = min(now + timedelta(seconds=get_quote_ttl_seconds()), window_end)
    return PaymentQuote.objects.create(
        code=code,
        coin=coin,
        fiat_amount=code.fiat_amount,
        rate=rate,
        crypto_amount=crypto_amount,
        locked_at=now,
        expires_at=expires_at,
    )


def get_or_refresh_quote(code: PaymentCode, coin: PaymentCoin | None = None) -> PaymentQuote | None:
    """
    Return the current live quote, re-locking only while the window is open.

    Re-locks (appends a new row at the then-current price) when the code is
    still `awaiting_payment`, the payment window is open, and either the
    latest quote is expired (TTL cadence) or the caller switched coins.

    Once the payment window ends, the latest quote stays returned/expired —
    the user must re-request via renew_quote() (FR A3: no silent re-lock).
    Once proof is submitted (or rejected/cancelled) the last quote stays
    frozen even if stale — that is the amount the admin verifies against.
    """
    latest = code.current_quote
    if latest is None:
        # No price-lock yet: only awaiting-payment codes ever get one
        # (a submitted code with no prior quote must never hit the feed).
        if coin is None or code.status != "awaiting_payment":
            return None
        return create_quote(code, coin)

    if code.status != "awaiting_payment":
        return latest
    if not is_window_open(code):
        # Window ended: explicit re-request required (never re-lock silently).
        return latest
    switched = coin is not None and latest.coin_id != coin.id
    if switched or latest.is_expired:
        return create_quote(code, coin or latest.coin)
    return latest


def renew_quote(code: PaymentCode, coin: PaymentCoin | None = None) -> PaymentQuote:
    """
    Explicit re-request after payment-window expiry (FR A3).

    Resets the window (now + the coin's quote_window_seconds) and re-locks
    at the then-current price. Only awaiting-payment codes can renew; the
    caller (view) resolves `coin` — falls back to the latest quote's coin.
    """
    if code.status != "awaiting_payment":
        raise ValueError("Cannot re-request a quote for a non-awaiting code")
    if coin is None and code.current_quote is not None:
        coin = code.current_quote.coin
    if coin is None:
        raise ValueError("Cannot re-request a quote without a coin")
    code.quote_window_expires_at = timezone.now() + timedelta(seconds=coin.quote_window_seconds)
    code.save(update_fields=["quote_window_expires_at"])
    return create_quote(code, coin)
