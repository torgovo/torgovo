"""
A5 Quantum AI lock tests (FUNCTIONAL_REQUIREMENTS.md §A5, gap G3).

Full lifecycle + abuse coverage:
  * creation guards (term, amount, fund state)
  * maturity credit: one per term, compounding roll, DB unique backstop
  * withdrawal hard rule: NOTHING is withdrawable during the lock window
  * admin approve/reject accounting (single balance-of-record invariant)
  * endpoint permission + error mapping
  * superseded biweekly/hourly beat entries removed from the schedule
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.bots.models import InvestorLock, QuantumProfitCredit, QuantumWithdrawalRequest
from services.quantum_locks import QuantumLockError, QuantumLockService

pytestmark = pytest.mark.django_db

D = Decimal


def _make_lock(user, fund, amount=D("1000"), lock_days=30, **kwargs):
    # matures_at has no model default (the service derives it) — mirror service
    kwargs.setdefault("matures_at", timezone.now() + timedelta(days=lock_days))
    return InvestorLock.objects.create(
        user=user, fund=fund, amount=amount, lock_days=lock_days, **kwargs
    )


def _force_mature(lock):
    """Backdate matures_at so is_matured evaluates True (time-travel helper)."""
    InvestorLock.objects.filter(pk=lock.pk).update(matures_at=timezone.now() - timedelta(days=1))
    lock.refresh_from_db()
    return lock


# ==================== CREATION ====================


class TestCreateLock:
    def test_creates_active_lock(self, user, quantum_fund):
        lock = QuantumLockService.create_lock(
            user=user, fund=quantum_fund, amount=D("500"), lock_days=30
        )
        assert lock.status == "active"
        assert lock.amount == D("500")
        assert lock.term_number == 1
        assert lock.credited_term == 0
        # Window opens now and matures in exactly lock_days
        assert lock.matures_at is not None
        delta = lock.matures_at - lock.starts_at
        assert delta == timedelta(days=30)

    def test_rejects_invalid_term(self, user, quantum_fund):
        with pytest.raises(QuantumLockError, match="Invalid lock term"):
            QuantumLockService.create_lock(
                user=user, fund=quantum_fund, amount=D("500"), lock_days=45
            )

    def test_rejects_nonpositive_amount(self, user, quantum_fund):
        with pytest.raises(QuantumLockError, match="must be > 0"):
            QuantumLockService.create_lock(
                user=user, fund=quantum_fund, amount=D("0"), lock_days=30
            )

    def test_rejects_missing_fund(self, user):
        with pytest.raises(QuantumLockError, match="No active Quantum AI fund"):
            QuantumLockService.create_lock(user=user, fund=None, amount=D("500"), lock_days=30)

    def test_rejects_inactive_fund(self, user, quantum_fund):
        quantum_fund.is_active = False
        quantum_fund.save()
        with pytest.raises(QuantumLockError, match="No active Quantum AI fund"):
            QuantumLockService.create_lock(
                user=user, fund=quantum_fund, amount=D("500"), lock_days=30
            )

    def test_subscription_and_deposit_links_persist(self, user, quantum_fund):
        lock = QuantumLockService.create_lock(
            user=user, fund=quantum_fund, amount=D("500"), lock_days=90
        )
        assert lock.subscription_id is None
        assert lock.deposit_id is None
        assert lock.lock_days == 90


# ==================== MATURITY CREDIT ====================


class TestCreditMaturity:
    def test_credit_happy_path(self, user, admin_user, quantum_fund):
        lock = _force_mature(_make_lock(user, quantum_fund))

        credit = QuantumLockService.credit_maturity(lock_id=lock.id, pct=D("10"), admin=admin_user)

        lock.refresh_from_db()
        # capital x 1.10 -> 1100, ledger + credit audit row
        assert lock.amount == D("1100")
        assert credit.capital_before == D("1000")
        assert credit.capital_after == D("1100")
        assert credit.profit_amount == D("100")
        assert credit.credited_by == admin_user
        assert lock.profit_credited_total == D("100")
        # Term advanced once, exactly one credit row for term 1
        assert lock.term_number == 2
        assert lock.credited_term == 1
        assert QuantumProfitCredit.objects.filter(lock=lock, term_number=1).count() == 1

    def test_late_credit_rolls_window_from_credit_moment(self, user, admin_user, quantum_fund):
        """Window restarts at credit time so no instant re-fire (G3)."""
        lock = _force_mature(_make_lock(user, quantum_fund, lock_days=30))
        before = timezone.now()
        QuantumLockService.credit_maturity(lock_id=lock.id, pct=D("5"), admin=admin_user)
        lock.refresh_from_db()

        assert lock.matures_at >= before + timedelta(days=30) - timedelta(seconds=5)
        # Now inside the new window -> not matured -> cannot credit again
        assert not lock.is_matured
        with pytest.raises(QuantumLockError, match="matures at"):
            QuantumLockService.credit_maturity(lock_id=lock.id, pct=D("5"), admin=admin_user)

    def test_credit_before_maturity_rejected(self, user, admin_user, quantum_fund):
        lock = _make_lock(user, quantum_fund)  # matures in 30d — still running
        with pytest.raises(QuantumLockError, match="matures at"):
            QuantumLockService.credit_maturity(lock_id=lock.id, pct=D("5"), admin=admin_user)
        lock.refresh_from_db()
        assert lock.amount == D("1000")
        assert QuantumProfitCredit.objects.count() == 0

    def test_credit_twice_same_maturity_leaves_capital_untouched(
        self, user, admin_user, quantum_fund
    ):
        lock = _force_mature(_make_lock(user, quantum_fund))
        QuantumLockService.credit_maturity(lock_id=lock.id, pct=D("10"), admin=admin_user)
        with pytest.raises(QuantumLockError, match="matures at"):
            QuantumLockService.credit_maturity(lock_id=lock.id, pct=D("10"), admin=admin_user)

        lock.refresh_from_db()
        assert lock.amount == D("1100")  # credited exactly once
        assert QuantumProfitCredit.objects.filter(lock=lock).count() == 1

    def test_credited_term_guard_blocks_same_term(self, user, admin_user, quantum_fund):
        """Belt-and-braces: direct state where the term is already credited."""
        lock = _force_mature(_make_lock(user, quantum_fund))
        # Simulate a credit that landed but left maturity forced true
        InvestorLock.objects.filter(pk=lock.pk).update(
            credited_term=1, term_number=1, matures_at=timezone.now() - timedelta(days=1)
        )
        lock.refresh_from_db()
        with pytest.raises(QuantumLockError, match="already credited"):
            QuantumLockService.credit_maturity(lock_id=lock.id, pct=D("5"), admin=admin_user)
        assert QuantumProfitCredit.objects.count() == 0

    def test_db_unique_backstop_rejects_duplicate_term_rows(self, user, admin_user, quantum_fund):
        from django.db import IntegrityError, transaction

        lock = _force_mature(_make_lock(user, quantum_fund))
        QuantumLockService.credit_maturity(lock_id=lock.id, pct=D("5"), admin=admin_user)
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                QuantumProfitCredit.objects.create(
                    lock=lock,
                    term_number=1,
                    pct_entered=D("5"),
                    profit_amount=D("50"),
                    capital_before=D("1000"),
                    capital_after=D("1050"),
                )

    def test_negative_pct_rejected(self, user, admin_user, quantum_fund):
        """A5 = credit only; loss entries do not exist in this model."""
        lock = _force_mature(_make_lock(user, quantum_fund))
        with pytest.raises(QuantumLockError, match="negative"):
            QuantumLockService.credit_maturity(lock_id=lock.id, pct=D("-3"), admin=admin_user)
        lock.refresh_from_db()
        assert lock.amount == D("1000")

    def test_zero_pct_allowed_free_form_entry(self, user, admin_user, quantum_fund):
        """Admins may enter 0% (flat term) — not clamped to the 2-5% guidance."""
        lock = _force_mature(_make_lock(user, quantum_fund))
        credit = QuantumLockService.credit_maturity(lock_id=lock.id, pct=D("0"), admin=admin_user)
        lock.refresh_from_db()
        assert lock.amount == D("1000")
        assert credit.profit_amount == D("0")
        assert lock.term_number == 2  # term still advances

    def test_credit_on_closed_lock_rejected(self, user, admin_user, quantum_fund):
        lock = _force_mature(_make_lock(user, quantum_fund, amount=D("0")))
        lock.status = "closed"
        lock.save()
        with pytest.raises(QuantumLockError, match="closed"):
            QuantumLockService.credit_maturity(lock_id=lock.id, pct=D("5"), admin=admin_user)

    def test_compounding_across_terms(self, user, admin_user, quantum_fund):
        """Rolled capital earns the next credit (credit x credit, G3)."""
        lock = _force_mature(_make_lock(user, quantum_fund))
        QuantumLockService.credit_maturity(lock_id=lock.id, pct=D("10"), admin=admin_user)
        _force_mature(lock)  # admin backdates / real time passes
        credit2 = QuantumLockService.credit_maturity(lock_id=lock.id, pct=D("10"), admin=admin_user)

        lock.refresh_from_db()
        assert credit2.capital_before == D("1100")
        assert credit2.capital_after == D("1210")
        assert lock.amount == D("1210")
        assert lock.profit_credited_total == D("210")
        assert lock.term_number == 3
        assert lock.credited_term == 2


# ==================== WITHDRAWAL REQUESTS ====================


class TestRequestWithdrawal:
    def test_hard_rule_nothing_withdrawable_during_lock(self, user, quantum_fund):
        """A5 hard rule: during the lock window, withdrawal is impossible."""
        lock = _make_lock(user, quantum_fund)  # matures in 30d
        with pytest.raises(QuantumLockError, match="not available while the lock is running"):
            QuantumLockService.request_withdrawal(user=user, lock_id=lock.id, amount=D("100"))
        assert QuantumWithdrawalRequest.objects.count() == 0

    def test_request_after_maturity_ok(self, user, quantum_fund):
        lock = _force_mature(_make_lock(user, quantum_fund))
        req = QuantumLockService.request_withdrawal(user=user, lock_id=lock.id, amount=D("400"))
        assert req.status == "pending"
        assert req.amount_requested == D("400")
        # Requesting does NOT move capital — only admin approval does
        lock.refresh_from_db()
        assert lock.amount == D("1000")

    def test_amount_over_capital_rejected(self, user, quantum_fund):
        lock = _force_mature(_make_lock(user, quantum_fund))
        with pytest.raises(QuantumLockError, match="exceeds withdrawable capital"):
            QuantumLockService.request_withdrawal(
                user=user, lock_id=lock.id, amount=D("1000.00000001")
            )

    def test_full_capital_allowed(self, user, quantum_fund):
        lock = _force_mature(_make_lock(user, quantum_fund))
        req = QuantumLockService.request_withdrawal(user=user, lock_id=lock.id, amount=D("1000"))
        assert req.amount_requested == D("1000")

    def test_nonpositive_amount_rejected(self, user, quantum_fund):
        lock = _force_mature(_make_lock(user, quantum_fund))
        with pytest.raises(QuantumLockError, match="must be > 0"):
            QuantumLockService.request_withdrawal(user=user, lock_id=lock.id, amount=D("0"))

    def test_second_pending_blocked(self, user, quantum_fund):
        lock = _force_mature(_make_lock(user, quantum_fund))
        QuantumLockService.request_withdrawal(user=user, lock_id=lock.id, amount=D("100"))
        with pytest.raises(QuantumLockError, match="pending withdrawal request already exists"):
            QuantumLockService.request_withdrawal(user=user, lock_id=lock.id, amount=D("200"))

    def test_after_reject_new_request_allowed(self, user, admin_user, quantum_fund):
        lock = _force_mature(_make_lock(user, quantum_fund))
        req = QuantumLockService.request_withdrawal(user=user, lock_id=lock.id, amount=D("100"))
        QuantumLockService.reject_withdrawal(request_id=req.id, admin=admin_user, notes="no")
        again = QuantumLockService.request_withdrawal(user=user, lock_id=lock.id, amount=D("100"))
        assert again.status == "pending"

    def test_non_owner_gets_404_semantics(self, user, second_user, quantum_fund):
        """Service re-fetches the lock scoped to the caller -> DoesNotExist (404)."""
        lock = _force_mature(_make_lock(second_user, quantum_fund))
        with pytest.raises(InvestorLock.DoesNotExist):
            QuantumLockService.request_withdrawal(user=user, lock_id=lock.id, amount=D("100"))

    def test_request_on_closed_lock_rejected(self, user, quantum_fund):
        lock = _make_lock(user, quantum_fund, amount=D("0"))
        lock.status = "closed"
        lock.save()
        with pytest.raises(QuantumLockError, match="closed"):
            QuantumLockService.request_withdrawal(user=user, lock_id=lock.id, amount=D("1"))


# ==================== ADMIN DECISIONS ====================


class TestApproveWithdrawal:
    def _pending_request(self, user, quantum_fund, amount=D("1000")):
        lock = _force_mature(_make_lock(user, quantum_fund, amount=amount))
        req = QuantumLockService.request_withdrawal(user=user, lock_id=lock.id, amount=amount)
        return lock, req

    def test_partial_approve_debits_ledger(self, user, admin_user, quantum_fund):
        lock, req = self._pending_request(user, quantum_fund)

        updated = QuantumLockService.approve_withdrawal(
            request_id=req.id, admin=admin_user, payout_amount=D("450"), notes="paid out"
        )

        lock.refresh_from_db()
        assert lock.amount == D("550")  # 1000 - 450 (payout incl. fees, Q12)
        assert lock.withdrawn_total == D("450")
        assert lock.status == "active"  # capital remains for future terms
        assert updated.status == "approved"
        assert updated.admin_entered_payout == D("450")
        assert updated.decided_by == admin_user
        assert updated.payment_transaction is not None
        assert updated.payment_transaction.transaction_type == "quantum_withdrawal"
        assert updated.payment_transaction.amount == D("450")

    def test_full_drain_closes_lock(self, user, admin_user, quantum_fund):
        lock, req = self._pending_request(user, quantum_fund, amount=D("300"))
        QuantumLockService.approve_withdrawal(
            request_id=req.id, admin=admin_user, payout_amount=D("300")
        )
        lock.refresh_from_db()
        assert lock.amount == D("0")
        assert lock.status == "closed"
        assert lock.withdrawn_total == D("300")

    def test_payout_above_capital_rejected(self, user, admin_user, quantum_fund):
        lock, req = self._pending_request(user, quantum_fund)
        with pytest.raises(QuantumLockError, match="exceeds lock capital"):
            QuantumLockService.approve_withdrawal(
                request_id=req.id, admin=admin_user, payout_amount=D("1000.00000001")
            )
        lock.refresh_from_db()
        assert lock.amount == D("1000")  # untouched on rejection

    def test_double_approve_rejected(self, user, admin_user, quantum_fund):
        _, req = self._pending_request(user, quantum_fund)
        QuantumLockService.approve_withdrawal(
            request_id=req.id, admin=admin_user, payout_amount=D("100")
        )
        with pytest.raises(QuantumLockError, match="already approved"):
            QuantumLockService.approve_withdrawal(
                request_id=req.id, admin=admin_user, payout_amount=D("100")
            )

    def test_negative_payout_rejected(self, user, admin_user, quantum_fund):
        _, req = self._pending_request(user, quantum_fund)
        with pytest.raises(QuantumLockError, match="cannot be negative"):
            QuantumLockService.approve_withdrawal(
                request_id=req.id, admin=admin_user, payout_amount=D("-50")
            )

    def test_no_user_balance_movement(self, user, admin_user, quantum_fund):
        """External crypto payout — UserBalance must not be touched (A7/Q19)."""
        from apps.users.models import UserBalance

        before = list(
            UserBalance.objects.filter(user=user).values("id", "currency", "available", "hold")
        )
        _, req = self._pending_request(user, quantum_fund, amount=D("100"))
        QuantumLockService.approve_withdrawal(
            request_id=req.id, admin=admin_user, payout_amount=D("100")
        )
        after = list(
            UserBalance.objects.filter(user=user).values("id", "currency", "available", "hold")
        )
        assert after == before


class TestRejectWithdrawal:
    def test_reject_keeps_capital_and_closes_request(self, user, admin_user, quantum_fund):
        lock = _force_mature(_make_lock(user, quantum_fund))
        req = QuantumLockService.request_withdrawal(user=user, lock_id=lock.id, amount=D("500"))
        updated = QuantumLockService.reject_withdrawal(
            request_id=req.id, admin=admin_user, notes="suspicious"
        )
        lock.refresh_from_db()
        assert lock.amount == D("1000")  # claim was never a debit
        assert updated.status == "rejected"
        assert updated.admin_notes == "suspicious"
        assert updated.payment_transaction is None

    def test_reject_non_pending_rejected(self, user, admin_user, quantum_fund):
        lock = _force_mature(_make_lock(user, quantum_fund))
        req = QuantumLockService.request_withdrawal(user=user, lock_id=lock.id, amount=D("1"))
        QuantumLockService.reject_withdrawal(request_id=req.id, admin=admin_user)
        with pytest.raises(QuantumLockError, match="already rejected"):
            QuantumLockService.reject_withdrawal(request_id=req.id, admin=admin_user)


# ==================== ENDPOINTS ====================


class TestLockEndpoints:
    def test_locks_require_auth(self, api_client):
        resp = api_client.get(reverse("investments:quantum-locks"))
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_user_sees_own_locks_only(self, auth_client, user, second_user, quantum_fund):
        _make_lock(user, quantum_fund)
        _make_lock(second_user, quantum_fund)
        resp = auth_client.get(reverse("investments:quantum-locks"))
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["count"] == 1

    def test_staff_sees_all_locks(self, admin_client, user, second_user, quantum_fund):
        _make_lock(user, quantum_fund)
        _make_lock(second_user, quantum_fund)
        resp = admin_client.get(reverse("investments:quantum-locks"))
        assert resp.data["count"] == 2

    def test_withdraw_endpoint_blocked_during_lock(self, auth_client, user, quantum_fund):
        lock = _make_lock(user, quantum_fund)
        resp = auth_client.post(
            reverse("investments:quantum-lock-withdraw", args=[lock.id]),
            {"amount": "100"},
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "not available" in resp.data["error"]

    def test_withdraw_endpoint_after_maturity(self, auth_client, user, quantum_fund):
        lock = _force_mature(_make_lock(user, quantum_fund))
        resp = auth_client.post(
            reverse("investments:quantum-lock-withdraw", args=[lock.id]),
            {"amount": "100"},
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data["status"] == "pending"

    def test_withdraw_missing_amount(self, auth_client, user, quantum_fund):
        lock = _force_mature(_make_lock(user, quantum_fund))
        resp = auth_client.post(
            reverse("investments:quantum-lock-withdraw", args=[lock.id]), {}, format="json"
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_withdraw_foreign_lock_404(self, auth_client, second_user, quantum_fund):
        lock = _force_mature(_make_lock(second_user, quantum_fund))
        resp = auth_client.post(
            reverse("investments:quantum-lock-withdraw", args=[lock.id]),
            {"amount": "100"},
            format="json",
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_credit_endpoint_forbidden_for_users(self, auth_client, user, quantum_fund):
        lock = _force_mature(_make_lock(user, quantum_fund))
        resp = auth_client.post(
            reverse("investments:quantum-lock-credit", args=[lock.id]),
            {"pct": "5"},
            format="json",
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_credit_endpoint_admin_flow(self, admin_client, admin_user, user, quantum_fund):
        lock = _force_mature(_make_lock(user, quantum_fund))
        resp = admin_client.post(
            reverse("investments:quantum-lock-credit", args=[lock.id]),
            {"pct": "5"},
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data["capital_after"] == "1050.00000000"
        assert resp.data["term_number"] == 1  # term that was credited
        assert resp.data["current_term"] == 2  # term now running

    def test_credit_endpoint_early_maturity_400(self, admin_client, user, quantum_fund):
        lock = _make_lock(user, quantum_fund)
        resp = admin_client.post(
            reverse("investments:quantum-lock-credit", args=[lock.id]),
            {"pct": "5"},
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_credit_endpoint_missing_pct(self, admin_client, user, quantum_fund):
        lock = _force_mature(_make_lock(user, quantum_fund))
        resp = admin_client.post(
            reverse("investments:quantum-lock-credit", args=[lock.id]), {}, format="json"
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_withdrawal_requests_user_scoped(self, auth_client, user, second_user, quantum_fund):
        lock = _force_mature(_make_lock(second_user, quantum_fund))
        QuantumLockService.request_withdrawal(user=second_user, lock_id=lock.id, amount=D("50"))
        resp = auth_client.get(reverse("investments:quantum-withdrawal-requests"))
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["count"] == 0  # other user's request not visible

    def test_decide_requires_action(self, admin_client, user, admin_user, quantum_fund):
        lock = _force_mature(_make_lock(user, quantum_fund))
        req = QuantumLockService.request_withdrawal(user=user, lock_id=lock.id, amount=D("50"))
        resp = admin_client.post(
            reverse("investments:quantum-withdrawal-decide", args=[req.id]),
            {"action": "maybe"},
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_decide_approve_requires_payout_amount(self, admin_client, user, quantum_fund):
        lock = _force_mature(_make_lock(user, quantum_fund))
        req = QuantumLockService.request_withdrawal(user=user, lock_id=lock.id, amount=D("50"))
        resp = admin_client.post(
            reverse("investments:quantum-withdrawal-decide", args=[req.id]),
            {"action": "approve"},
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "payout_amount" in resp.data["error"]

    def test_decide_approve_flow(self, admin_client, user, quantum_fund):
        lock = _force_mature(_make_lock(user, quantum_fund))
        req = QuantumLockService.request_withdrawal(user=user, lock_id=lock.id, amount=D("500"))
        resp = admin_client.post(
            reverse("investments:quantum-withdrawal-decide", args=[req.id]),
            {"action": "approve", "payout_amount": "510", "notes": "fee-included"},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["status"] == "approved"
        lock.refresh_from_db()
        assert lock.amount == D("490")  # 1000 - 510

    def test_decide_reject_flow(self, admin_client, user, quantum_fund):
        lock = _force_mature(_make_lock(user, quantum_fund))
        req = QuantumLockService.request_withdrawal(user=user, lock_id=lock.id, amount=D("500"))
        resp = admin_client.post(
            reverse("investments:quantum-withdrawal-decide", args=[req.id]),
            {"action": "reject", "notes": "docs missing"},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["status"] == "rejected"
        lock.refresh_from_db()
        assert lock.amount == D("1000")

    def test_decide_forbidden_for_users(self, auth_client, user, quantum_fund):
        lock = _force_mature(_make_lock(user, quantum_fund))
        req = QuantumLockService.request_withdrawal(user=user, lock_id=lock.id, amount=D("50"))
        resp = auth_client.post(
            reverse("investments:quantum-withdrawal-decide", args=[req.id]),
            {"action": "approve", "payout_amount": "50"},
            format="json",
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_matured_filter_for_credit_queue(self, admin_client, user, quantum_fund):
        matured = _force_mature(_make_lock(user, quantum_fund))
        _make_lock(user, quantum_fund)  # still running
        resp = admin_client.get(reverse("investments:quantum-locks") + "?matured=1")
        assert resp.data["count"] == 1
        assert resp.data["results"][0]["id"] == str(matured.id)


# ==================== A5 SUPERSESSION ====================


class TestA5Supersession:
    def test_quantum_beat_entries_removed(self):
        """§A5 replaces the biweekly/hourly distribution schedule."""
        from config.celery import app

        assert "distribute-quantum-ai-profits" not in app.conf.beat_schedule
        assert "accrue-quantum-ai-profits" not in app.conf.beat_schedule
        # Unrelated schedules untouched (scoped removal)
        assert "run-active-bots" in app.conf.beat_schedule

    def test_legacy_task_functions_still_importable(self):
        """Legacy task functions stay for their pinned unit tests (G3)."""
        from apps.trading.tasks import (  # noqa: F401
            accrue_quantum_ai_profits,
            distribute_quantum_ai_profits,
        )
