"""
Quantum AI A5 locks — per-investor term locks, admin maturity credit,
post-lock withdrawal approval (FUNCTIONAL_REQUIREMENTS.md §A5, gap G3).

Supersedes the biweekly reserve/smoothing distribution
(services/quantum_ai_fund.py). That module stays importable for legacy tests
but its beat entries were removed from config/celery.py (A5 "replaces current
behavior").

Accounting invariant — InvestorLock.amount is the single balance-of-record
(capital + rolled credit, reduced by approved payouts):
  * credit:   amount x= (1 + pct/100), exactly once per term, then
              matures_at := now + lock_days (compounding carry-over; a late
              credit restarts the window from the credit moment so a second
              credit cannot fire instantly).
  * payout:   amount -= admin-entered payout (incl. chain fees, grill Q12);
              audit counters updated; no UserBalance movement (external
              crypto payout, same model as referral payout A7/Q19).

Hard rule (A5): nothing is ever withdrawable before matures_at.

Concurrency (G4 pattern): every mutation runs in transaction.atomic() with
select_for_update() on the touched rows; QuantumProfitCredit additionally has
the DB unique constraint (lock, term_number) as a double-credit backstop.
"""

import logging
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from apps.bots.models import (
    QUANTUM_LOCK_DAYS_CHOICES,
    InvestorLock,
    QuantumProfitCredit,
    QuantumWithdrawalRequest,
)
from apps.payments.models import PaymentTransaction

logger = logging.getLogger(__name__)

# Amounts are persisted at decimal_places=8 — round every derived figure here
# so in-memory Decimal math and DB values never drift.
_Q = Decimal("0.00000001")

VALID_LOCK_DAYS = {choice[0] for choice in QUANTUM_LOCK_DAYS_CHOICES}


class QuantumLockError(ValueError):
    """Domain error for A5 lock operations; views map it to a 4xx response."""


def _round(value: Decimal) -> Decimal:
    return value.quantize(_Q, rounding=ROUND_HALF_UP)


class QuantumLockService:

    # ------------------------------------------------------------------ #
    # Creation                                                            #
    # ------------------------------------------------------------------ #

    @staticmethod
    @transaction.atomic
    def create_lock(
        *,
        user,
        fund,
        amount: Decimal,
        lock_days: int,
        subscription=None,
        deposit=None,
    ) -> InvestorLock:
        """Open a new investor lock. Called from subscription/deposit approval."""
        amount = _round(amount)
        if amount <= 0:
            raise QuantumLockError("Lock amount must be > 0.")
        if lock_days not in VALID_LOCK_DAYS:
            raise QuantumLockError(
                f"Invalid lock term {lock_days}d — allowed: " f"{sorted(VALID_LOCK_DAYS)}"
            )
        if fund is None or not fund.is_active:
            raise QuantumLockError("No active Quantum AI fund.")

        now = timezone.now()
        lock = InvestorLock.objects.create(
            user=user,
            fund=fund,
            subscription=subscription,
            deposit=deposit,
            amount=amount,
            lock_days=lock_days,
            starts_at=now,
            matures_at=now + timedelta(days=lock_days),
            status="active",
        )
        logger.info(
            "Opened Quantum AI lock %s: user=%s amount=%s term=%sd",
            lock.id,
            user.email,
            amount,
            lock_days,
        )
        return lock

    # ------------------------------------------------------------------ #
    # Maturity credit (admin-triggered, one per term)                     #
    # ------------------------------------------------------------------ #

    @staticmethod
    @transaction.atomic
    def credit_maturity(*, lock_id, pct: Decimal, admin) -> QuantumProfitCredit:
        """
        Apply `capital x (1 + pct/100)` to a matured lock (A5 mechanism).

        Guards: lock active, window elapsed (crediting early credits nothing
        and unlocks nothing), current term not yet credited. The unique
        (lock, term_number) constraint backstops concurrent double-credits.
        """
        pct = Decimal(str(pct))
        if pct < 0:
            raise QuantumLockError("Profit % cannot be negative (credit only, A5).")

        lock = InvestorLock.objects.select_for_update().get(id=lock_id)

        if lock.status != "active":
            raise QuantumLockError(f"Lock is {lock.status}; credit requires an active lock.")
        if not lock.is_matured:
            raise QuantumLockError(
                f"Lock matures at {lock.matures_at.isoformat()}; early credit is not allowed."
            )
        if lock.credited_term >= lock.term_number:
            raise QuantumLockError(f"Term {lock.term_number} already credited (idempotency guard).")

        capital_before = lock.amount
        profit = _round(capital_before * pct / Decimal("100"))
        capital_after = capital_before + profit

        # One credit per term — DB unique constraint is the race backstop.
        credit = QuantumProfitCredit.objects.create(
            lock=lock,
            term_number=lock.term_number,
            pct_entered=pct,
            profit_amount=profit,
            capital_before=capital_before,
            capital_after=capital_after,
            credited_by=admin,
        )

        # Compounding: credited profit becomes capital; roll the window from
        # the credit moment (late credit ⇒ fresh full term, no instant re-fire).
        lock.amount = capital_after
        lock.profit_credited_total = lock.profit_credited_total + profit
        lock.credited_term = lock.term_number
        lock.term_number = lock.term_number + 1
        lock.matures_at = timezone.now() + timedelta(days=lock.lock_days)
        lock.save()

        logger.info(
            "Credited lock %s term %d: +%.2f%% (%s USDT) -> capital %s",
            lock.id,
            credit.term_number,
            pct,
            profit,
            capital_after,
        )
        return credit

    # ------------------------------------------------------------------ #
    # Withdrawals (post-lock only)                                        #
    # ------------------------------------------------------------------ #

    @staticmethod
    @transaction.atomic
    def request_withdrawal(*, user, lock_id, amount: Decimal) -> QuantumWithdrawalRequest:
        """
        File a post-lock withdrawal request (any partial amount <= capital).

        A5 hard rule: rejected while the lock window is running — no
        exceptions, no early-withdrawal path exists.
        """
        amount = _round(amount)

        # Lock the lock row first: serializes concurrent requests so the
        # "one pending per lock" check is race-free.
        lock = InvestorLock.objects.select_for_update().get(id=lock_id)

        if lock.user_id != user.id:
            raise InvestorLock.DoesNotExist  # view maps to 404 (no existence leak)
        if lock.status != "active":
            raise QuantumLockError(f"Lock is {lock.status}; no withdrawal possible.")
        if not lock.is_matured:
            # A5 hard rule — during lock nothing is ever withdrawable.
            raise QuantumLockError("Withdrawals are not available while the lock is running.")
        if amount <= 0:
            raise QuantumLockError("Withdrawal amount must be > 0.")
        if amount > lock.amount:
            raise QuantumLockError(f"Amount {amount} exceeds withdrawable capital {lock.amount}.")
        if QuantumWithdrawalRequest.objects.filter(lock=lock, status="pending").exists():
            raise QuantumLockError("A pending withdrawal request already exists for this lock.")

        request = QuantumWithdrawalRequest.objects.create(
            user=user,
            lock=lock,
            amount_requested=amount,
            status="pending",
        )
        logger.info(
            "Withdrawal requested: lock=%s user=%s amount=%s",
            lock.id,
            user.email,
            amount,
        )
        return request

    @staticmethod
    @transaction.atomic
    def approve_withdrawal(
        *,
        request_id,
        admin,
        payout_amount: Decimal,
        notes: str = "",
    ) -> QuantumWithdrawalRequest:
        """
        Approve a pending request: admin enters the payout amount including
        chain fees (grill Q12); the system debits the lock ledger by exactly
        that figure and records a PaymentTransaction audit row. No
        UserBalance movement — payout is made externally in crypto.
        """
        payout_amount = _round(Decimal(str(payout_amount)))

        req = QuantumWithdrawalRequest.objects.select_for_update().get(id=request_id)
        lock = InvestorLock.objects.select_for_update().get(id=req.lock_id)

        if req.status != "pending":
            raise QuantumLockError(f"Request is already {req.status}.")
        if payout_amount < 0:
            raise QuantumLockError("Payout amount cannot be negative.")
        if payout_amount > lock.amount:
            raise QuantumLockError(f"Payout {payout_amount} exceeds lock capital {lock.amount}.")

        # Debit the ledger (lock capital) by the admin-entered payout.
        lock.amount = lock.amount - payout_amount
        lock.withdrawn_total = lock.withdrawn_total + payout_amount
        if lock.amount <= 0:
            lock.amount = Decimal("0")
            lock.status = "closed"
        lock.save()

        tx = PaymentTransaction.objects.create(
            user=req.user,
            transaction_type="quantum_withdrawal",  # <= 20 chars (CharField)
            amount=payout_amount,
            currency="USDT",
            reference_id=str(lock.id),
            description=(
                f"Quantum AI withdrawal approved — {lock.lock_days}d lock "
                f"(requested {req.amount_requested}, payout incl. fees)"
            ),
            status="completed",
        )

        req.status = "approved"
        req.admin_entered_payout = payout_amount
        req.admin_notes = notes
        req.decided_at = timezone.now()
        req.decided_by = admin
        req.payment_transaction = tx
        req.save()

        logger.info(
            "Withdrawal approved: request=%s lock=%s payout=%s by %s",
            req.id,
            lock.id,
            payout_amount,
            getattr(admin, "email", admin),
        )
        return req

    @staticmethod
    @transaction.atomic
    def reject_withdrawal(*, request_id, admin, notes: str = "") -> QuantumWithdrawalRequest:
        """Reject a pending request. Capital untouched (request was a claim only)."""
        req = QuantumWithdrawalRequest.objects.select_for_update().get(id=request_id)

        if req.status != "pending":
            raise QuantumLockError(f"Request is already {req.status}.")

        req.status = "rejected"
        req.admin_notes = notes
        req.decided_at = timezone.now()
        req.decided_by = admin
        req.save()

        logger.info("Withdrawal rejected: request=%s by %s", req.id, getattr(admin, "email", admin))
        return req
