"""G5 / FR A7 referral rewards — cash commissions, referee discounts, payouts.

Design (BACKEND_PRODUCTION_TASKS.md §1.2):
- Commission: accrued when a referred user's subscription is APPROVED
  (admin verified real money), only when the referrer holds an active
  plan with `grants_referral_commission` (tier ladder — admin-editable,
  seeded creator=True in payments migration 0013).
- Referee discount: percent off the referee's FIRST subscription payment,
  only when the referrer is NOT creator-tier (never both rewards).
- Payouts: referrer requests >= payout_minimum_usd from their pending
  ReferralPayout balance; admin pays externally and enters the actual
  payout amount; approve FIFO-marks accruals paid + books a
  `referral_payout` PaymentTransaction (mirrors QuantumLockService
  withdrawal flow).

ALL business values live in SiteConfig.referral_config (admin-editable);
DEFAULT_REFERRAL_CONFIG below is only the fallback for unset keys.
"""

import logging
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import TYPE_CHECKING

from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.utils import timezone

if TYPE_CHECKING:
    from apps.payments.models import ReferralPayoutRequest

logger = logging.getLogger(__name__)

# Fallback defaults for keys the admin has NOT set in SiteConfig.referral_config.
DEFAULT_REFERRAL_CONFIG = {
    "commission_pct": Decimal("10"),
    "referee_discount_pct": Decimal("15"),
    "payout_minimum_usd": Decimal("50"),
}

_USD = Decimal("0.01")  # cash commissions are whole cents


class ReferralRewardError(Exception):
    """Domain error — views map it to HTTP 400 {"error": str(e)}."""


def _usd(amount: Decimal) -> Decimal:
    return Decimal(amount).quantize(_USD, rounding=ROUND_HALF_UP)


def get_referral_config() -> dict:
    """Admin-editable rewards config with per-key fallback to defaults."""
    from core.models import SiteConfig

    raw = SiteConfig.get().referral_config or {}
    cfg = dict(DEFAULT_REFERRAL_CONFIG)
    for key, default in DEFAULT_REFERRAL_CONFIG.items():
        if key not in raw or raw[key] is None or raw[key] == "":
            continue
        try:
            cfg[key] = Decimal(str(raw[key]))
        except (ValueError, TypeError, InvalidOperation):
            logger.warning(
                "Invalid SiteConfig.referral_config[%r]=%r — using default %r",
                key,
                raw[key],
                default,
            )
    return cfg


def apply_discount(full_price: Decimal, pct: Decimal) -> Decimal:
    """Net price after a percent discount (rounded to cents)."""
    if pct <= 0:
        return _usd(full_price)
    return _usd(full_price * (Decimal("100") - pct) / Decimal("100"))


class ReferralRewardService:
    """Static service — mirrors QuantumLockService's shape."""

    # ------------------------------------------------------------------ tier

    @staticmethod
    def commission_tier_plan(user):
        """Return the user's active commission-earning SubscriptionPlan, or None.

        Tier walk: active, non-expired (or in G4 grace window) BotSubscription
        -> BotSubscriptionPlan -> SubscriptionPlan (G5 bridge FK) whose
        `grants_referral_commission` flag is set.
        """
        from apps.payments.models import BotSubscription

        now = timezone.now()
        sub = (
            BotSubscription.objects.filter(user=user, status="active")
            .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now) | Q(grace_until__gt=now))
            .select_related("plan__subscription_plan")
            .order_by("-created_at")
            .first()
        )
        if sub is None:
            return None
        plan = sub.plan.subscription_plan
        if plan is not None and plan.grants_referral_commission:
            return plan
        return None

    @staticmethod
    def referrer_earns_commission(referrer) -> bool:
        return ReferralRewardService.commission_tier_plan(referrer) is not None

    # -------------------------------------------------------------- discount

    @staticmethod
    def referee_discount_pct(user) -> Decimal:
        """Percent off `user`'s FIRST subscription payment (0 = not eligible).

        Eligible when: they were referred (non-rejected Referral row), their
        referrer is NOT creator-tier (creators get the commission instead),
        and they have no prior paid/pending-approval subscription.
        """
        from apps.payments.models import BotSubscription
        from apps.referrals.models import Referral
        from apps.subscriptions.models import TelegramSubscription

        referral = Referral.objects.filter(referred_user=user).exclude(status="rejected").first()
        if referral is None:
            return Decimal("0")
        if ReferralRewardService.referrer_earns_commission(referral.referrer):
            return Decimal("0")

        # First payment only: any non-draft subscription already exists.
        # (pending_payment = no proof yet, so it does not count as a payment;
        #  pending_approval/active/expired = money was already paid.)
        paid_q = ~Q(status__in=["pending_payment", "cancelled", "rejected"])
        has_prior = BotSubscription.objects.filter(user=user).filter(paid_q).exists()
        if not has_prior:
            has_prior = TelegramSubscription.objects.filter(user=user).filter(paid_q).exists()
        if has_prior:
            return Decimal("0")

        return get_referral_config()["referee_discount_pct"]

    @staticmethod
    def claim_referee_discount(user) -> Decimal:
        """Atomic referee-discount claim — closes the concurrent-first-purchase
        race (two simultaneous subscribe POSTs both seeing has_prior=False and
        both applying the discount).

        Locks the caller's Referral row (if any) with SELECT ... FOR UPDATE,
        then re-runs the eligibility check under the held lock. A second
        concurrent request blocks on the lock until the first commits (having
        created its subscription); after the first commits, the second's
        has_prior check now sees that subscription and returns 0.

        MUST be called inside transaction.atomic() together with the
        subscription create — otherwise select_for_update raises
        TransactionManagementError, or the lock is released before the
        subscription row is visible to the blocked peer.
        """
        from apps.referrals.models import Referral

        # Lock the referral row (if any) to serialize concurrent first-purchases
        # for the same referred user. Unreferred users have nothing to lock.
        locked = (
            Referral.objects.select_for_update()
            .filter(referred_user=user)
            .exclude(status="rejected")
            .first()
        )
        if locked is None:
            return Decimal("0")
        # Eligibility re-checked under the held lock — a concurrent request
        # that committed a subscription between our read and the lock will
        # now see it via has_prior and get 0.
        return ReferralRewardService.referee_discount_pct(user)

    # -------------------------------------------------------------- accrual

    @staticmethod
    @transaction.atomic
    def record_subscription_payment(subscription, *, kind: str):
        """G5 hook — call once per APPROVED subscription payment.

        Books the baseline `subscription` PaymentTransaction (the net amount
        the referee actually paid) and, when their referrer is creator-tier,
        accrues one pending ReferralPayout for commission_pct of that basis.

        `kind`: "telegram" (TelegramSubscription) or "bot" (BotSubscription).
        Returns the PaymentTransaction, or None when there is nothing to book.
        """
        from apps.payments.models import PaymentTransaction, ReferralPayout
        from apps.referrals.models import Referral

        cfg = get_referral_config()
        user = subscription.user

        if kind == "telegram":
            basis = subscription.amount_paid
            ref = f"telegram:{subscription.id}"
            label = "Telegram subscription"
        else:
            basis = (
                subscription.amount_due
                if subscription.amount_due is not None
                else subscription.plan.price
            )
            ref = f"bot:{subscription.id}"
            label = "Bot subscription"

        if basis is None or basis <= 0:
            return None  # zero-priced approval — nothing to book

        tx = PaymentTransaction.objects.create(
            user=user,
            transaction_type="subscription",
            amount=_usd(basis),
            currency="USD",
            reference_id=ref,
            gateway="system",
            status="completed",
            description=f"{label} payment (G5)",
        )

        referral = (
            Referral.objects.filter(referred_user=user)
            .exclude(status="rejected")
            .select_related("referrer")
            .first()
        )
        if referral is None:
            return tx  # not referred — baseline ledger row only

        pct = cfg["commission_pct"]
        if pct <= 0:
            return tx  # admin disabled commissions
        if not ReferralRewardService.referrer_earns_commission(referral.referrer):
            return tx  # referrer not creator-tier (or expired out of tier)

        amount = _usd(basis * pct / Decimal("100"))
        if amount <= 0:
            return tx  # rounds to zero cents — no accrual row

        ReferralPayout.objects.create(
            referrer=referral.referrer,
            referred_user=user,
            amount=amount,
            percentage=pct,
            source_transaction=tx,
            status="pending",
        )
        logger.info(
            "G5 commission accrued: %s USD (pct=%s) referrer=%s ref=%s",
            amount,
            pct,
            referral.referrer.email,
            ref,
        )
        return tx

    # -------------------------------------------------------- payout requests

    @staticmethod
    @transaction.atomic
    def request_payout(*, user, amount) -> "ReferralPayoutRequest":
        """File a payout request against the referrer's pending balance."""
        from apps.payments.models import ReferralPayout, ReferralPayoutRequest

        amount = _usd(Decimal(str(amount)))
        cfg = get_referral_config()
        minimum = _usd(cfg["payout_minimum_usd"])

        if amount <= 0:
            raise ReferralRewardError("Amount must be > 0.")
        if amount < minimum:
            raise ReferralRewardError(f"Minimum payout request is ${minimum}.")

        # Lock accrual rows so the balance check is race-free vs decide.
        balance = ReferralPayout.objects.select_for_update().filter(
            referrer=user, status="pending"
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
        if amount > balance:
            raise ReferralRewardError(
                f"Amount {amount} exceeds pending commission balance {_usd(balance)}."
            )
        if ReferralPayoutRequest.objects.filter(user=user, status="pending").exists():
            raise ReferralRewardError("A pending payout request already exists.")

        try:
            req = ReferralPayoutRequest.objects.create(user=user, amount_requested=amount)
        except IntegrityError:
            # Race lost against the DB-level uniq_pending_payout_request_per_user
            # constraint (migration 0014) — another request slipped in between
            # the exists() check above and this insert.
            raise ReferralRewardError("A pending payout request already exists.")
        logger.info("Payout requested: user=%s amount=%s", user.email, amount)
        return req

    @staticmethod
    @transaction.atomic
    def approve_payout_request(
        *, request_id, admin, payout_amount, notes: str = ""
    ) -> "ReferralPayoutRequest":
        """Admin paid the referrer externally — record it and settle accruals.

        `payout_amount` is what was ACTUALLY paid (may differ from
        `amount_requested` to cover network fees). FIFO-marks pending
        ReferralPayout rows covering `amount_requested` as paid and books one
        `referral_payout` PaymentTransaction for the entered amount.
        No UserBalance movement — payout left the platform.
        """
        from apps.payments.models import PaymentTransaction, ReferralPayout, ReferralPayoutRequest

        payout_amount = _usd(Decimal(str(payout_amount if payout_amount is not None else 0)))
        req = ReferralPayoutRequest.objects.select_for_update().get(id=request_id)
        if req.status != "pending":
            raise ReferralRewardError(f"Request is already {req.status}.")
        if payout_amount <= 0:
            raise ReferralRewardError("Payout amount must be > 0.")
        # Business-rule guard: fees reduce the net payout, never increase it.
        # payout_amount is what was ACTUALLY paid — it must not exceed what the
        # referrer requested. Guards against an admin typo booking a huge
        # ledger row (admin-trusted, but a cheap sanity check).
        if payout_amount > req.amount_requested:
            raise ReferralRewardError(
                f"Payout amount {payout_amount} exceeds the requested "
                f"{req.amount_requested} — fees reduce the net payout, "
                f"they never increase it."
            )

        # Pending accruals may have been cancelled since the request was filed.
        pending_rows = list(
            ReferralPayout.objects.select_for_update()
            .filter(referrer=req.user, status="pending")
            .order_by("created_at")
        )
        balance = sum((p.amount for p in pending_rows), Decimal("0"))
        if req.amount_requested > balance:
            raise ReferralRewardError(
                f"Pending balance {_usd(balance)} no longer covers " f"{req.amount_requested}."
            )

        # FIFO: settle accruals until the requested amount is covered.
        remaining = req.amount_requested
        for payout in pending_rows:
            if remaining <= 0:
                break
            payout.status = "paid"
            payout.paid_at = timezone.now()
            payout.save(update_fields=["status", "paid_at"])
            remaining -= payout.amount

        tx = PaymentTransaction.objects.create(
            user=req.user,
            transaction_type="referral_payout",
            amount=payout_amount,
            currency="USD",
            reference_id=str(req.id),
            gateway="system",
            status="completed",
            description="Referral commission payout (G5)",
        )
        req.status = "approved"
        req.admin_entered_payout = payout_amount
        req.admin_notes = notes
        req.decided_at = timezone.now()
        req.decided_by = admin
        req.payment_transaction = tx
        req.save()
        logger.info(
            "Payout approved: request=%s payout=%s admin=%s",
            req.id,
            payout_amount,
            admin.email,
        )
        return req

    @staticmethod
    @transaction.atomic
    def reject_payout_request(*, request_id, admin, notes: str = "") -> "ReferralPayoutRequest":
        """Reject a pending request — accruals stay pending (claim only)."""
        from apps.payments.models import ReferralPayoutRequest

        req = ReferralPayoutRequest.objects.select_for_update().get(id=request_id)
        if req.status != "pending":
            raise ReferralRewardError(f"Request is already {req.status}.")

        req.status = "rejected"
        req.admin_notes = notes
        req.decided_at = timezone.now()
        req.decided_by = admin
        req.save()
        logger.info("Payout rejected: request=%s admin=%s", req.id, admin.email)
        return req
