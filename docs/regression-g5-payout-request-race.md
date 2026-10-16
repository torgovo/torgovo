# Regression: G5 payout-request race + discount race + payout bound

**Date**: 2026-10-16
**Severity**: Medium (financial integrity)
**Component**: `services/referral_rewards.py`, `apps/payments/models.py`,
`apps/payments/views.py`, `apps/subscriptions/views.py`

Three holes found in a post-ship grilling pass of G5/FR A7. All fixed;
suite grew 48 → 58 tests, full suite 2470 → 2480 passed / 13 skipped.

---

## 1. Payout-request race — duplicate pending requests

### What was broken

`ReferralRewardService.request_payout` checked for an existing pending
`ReferralPayoutRequest` via a non-locking `.exists()` inside a transaction,
then inserted a new row. Two concurrent POST requests could both pass the
check (READ COMMITTED) and both insert → **two pending payout requests for
the same user**. Admin could approve both, double-paying the referrer.

### Root cause

Missing DB-level uniqueness. A service-level `.exists()` is not race-safe
under default isolation.

### Fix

1. **DB constraint** (`apps/payments/models.py`, migration
   `0014_referralpayoutrequest_uniq_pending_payout_request_per_user.py`):

   ```python
   models.UniqueConstraint(
       fields=["user"],
       condition=models.Q(status="pending"),
       name="uniq_pending_payout_request_per_user",
   )
   ```

2. **Belt-and-suspenders** (`services/referral_rewards.py`): wrap the
   insert in `try/except IntegrityError` → re-raise the clean domain error
   `ReferralRewardError("A pending payout request already exists.")`
   instead of leaking a raw `IntegrityError` (would surface as HTTP 500).

### Tests

- `test_duplicate_pending_rejected` (existing — sequential path)
- Full suite green on SQLite (constraint applies).

---

## 2. Referee-discount race — concurrent first-purchases

### What was broken

`referee_discount_pct` is a read-only check (referrer-not-creator + no prior
paid subscription). Two concurrent first-subscribe POSTs for the same referred
user could both see `has_prior=False` and both apply the 15% referee
discount. Tiny revenue leak; hard to exploit (needs two simultaneous first
purchases from one user) but a real check-then-act race.

### Fix — atomic conditional claim (`SELECT ... FOR UPDATE`)

`ReferralRewardService.claim_referee_discount(user)`:

- Locks the caller's `Referral` row (if any) with `select_for_update`.
- Re-runs eligibility under the held lock.
- A second concurrent request blocks on the lock until the first commits
  (having created its subscription); after the first commits, the second's
  `has_prior` check sees that subscription → returns 0.
- MUST be called inside `transaction.atomic()` together with the
  subscription create — otherwise `select_for_update` raises
  `TransactionManagementError`, or the lock is released before the
  subscription row is visible to the blocked peer.

Both subscribe views now wrap discount-compute + subscription create in
`transaction.atomic()` and call `claim_referee_discount` instead of
`referee_discount_pct`:

- `apps/payments/views.py` — `CreateBotSubscriptionView.post`
- `apps/subscriptions/views.py` — `TelegramSubscribeView.post`

`referee_discount_pct` stays as the read-only variant for display (my-stats).

### Tests (SQLite ignores FOR UPDATE — lock is a no-op there; the true race
is Postgres-only, covered by this doc. Tests verify eligibility + atomic
integration.)

- `test_eligible_first_time_gets_pct` — claim returns 15 for eligible user
- `test_zero_after_subscription_exists` — second request post-commit gets 0
- `test_unreferred_gets_zero`
- `test_creator_referrer_gets_zero`
- `test_matches_referee_discount_pct` — single-threaded claim == read

---

## 3. Admin payout_amount unbounded (typo guard)

### What was broken

`approve_payout_request` accepted any `payout_amount > 0`. An admin typo
(e.g. entering `5000` instead of `50`) would book a huge `referral_payout`
ledger row. Admin-trusted, but a cheap sanity check was missing.

### Fix

Business-rule guard — fees reduce the net payout, never increase it:
`payout_amount` (what was ACTUALLY paid) must not exceed `amount_requested`.
A fee-reduced payout is `payout_amount < amount_requested` (normal); paying
more than requested is an error.

```python
if payout_amount > req.amount_requested:
    raise ReferralRewardError(
        f"Payout amount {payout_amount} exceeds the requested "
        f"{req.amount_requested} — fees reduce the net payout, "
        f"they never increase it."
    )
```

### Tests

- `test_payout_above_requested_rejected` — 75 > 50 → domain error
- `test_payout_equal_to_requested_ok` — 50 == 50 → approved (normal path)
- `test_partial_fifo` updated: was using `payout_amount=52 > requested=50`
  (relied on the unbounded behavior); now uses `48` (realistic fee-reduced
  net) — FIFO assertion unchanged, plus asserts `admin_entered_payout==48`.

---

## Verification

- G5 suite: **58/58** (was 48; +10 tests across the three fixes)
- Full suite: **2480 passed, 13 skipped** (was 2470/13)
- Postgres down on this box → migration `0014` applies on SQLite via the
  test runner; run `manage.py migrate payments` when the real DB is back.

## Prevention

- Any "check-then-insert" uniqueness pattern needs a DB-level constraint.
  Service-level `.exists()` checks are UX niceties, not race guards.
- Any "check eligibility then freeze a one-time benefit" pattern needs an
  atomic claim (conditional UPDATE or `select_for_update`) held across the
  resource create.
- Financial "actual amount entered by admin" fields need an explicit
  upper/lower business-rule bound, even when admin-trusted.
