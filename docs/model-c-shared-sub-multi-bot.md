# Model C shared-subscription: multiple grid/martingale bots per sub

**Date:** 2026-10-18
**Decision:** user-approved fix for the open product question raised in the
FR A2 Model C gates session (seats said "allowed", the legacy duplicate guard
said 400).

## What was wrong

Under Model C every bot attaches to ONE shared subscription
(`subscription = limits.subscription`), counted cross-type against
`max_bots_allowed`. But grid/martingale carried a **1-bot-per-subscription**
invariant twice over:

1. **DB:** `unique_together = ["subscription"]` on `GridBot` +
   `MartingaleBot` → a seat-eligible 2nd create raised `IntegrityError`
   (HTTP 500).
2. **View:** pre-check in `perform_create` → `400 "You already have a Grid
   Bot for this subscription…"`.

Result: a Model C user with `max_bots_allowed = 5` could only ever have
1 grid + 1 martingale (400/500 on the 2nd); only signal bots used full seats.

## The fix (scope-limited to source=`model_c`)

| Layer | Change | Legacy (source != model_c) |
|---|---|---|
| `apps/bots/models.py` | dropped `unique_together = ["subscription"]` from GridBot + MartingaleBot Meta (migration `bots/0019_alter_gridbot_unique_together_and_more`) | DB backstop gone — acceptable: no production code creates these rows except the view (grep-verified), and the view check still guards legacy |
| `apps/bots/views.py` | duplicate pre-check wrapped in `if limits.source != "model_c":` | byte-stable 400, message unchanged |

Seat gating for Model C was already correct (`enforce_bot_creation` runs
before the check; 429 `BOT_LIMIT_EXCEEDED` when full).

## Behaviour matrix after the fix

- Legacy sub, 1st grid → 201; 2nd grid → **400** (unchanged, pinned by
  `tests/bots/test_views.py::test_create_duplicate_grid_bot_fails` + martingale twin).
- Model C, seats available, 2nd grid/martingale → **201**, both rows share
  the one subscription id.
- Model C, seats full → **429** (first).
- SignalBot never had the constraint — unchanged.

## Tests

- New: `tests/test_model_c_gates.py`
  `test_second_grid_allowed_under_model_c`,
  `test_second_martingale_allowed_under_model_c` (201 + both rows on shared sub).
- Updated invariants (they asserted the removed constraint):
  - `tests/bots/test_behaviour.py::test_two_grid_bots_may_share_subscription`
    + `test_two_martingale_bots_may_share_subscription` (was
    `test_one_*_per_subscription` expecting `IntegrityError`);
    unused `IntegrityError` import dropped.
  - `tests/bots/test_models.py::test_meta_no_subscription_uniqueness`
    (was `test_meta_unique_together` asserting the constraint existed).
- Run: gates + `tests/bots/` → **251 passed**; full suite → see session log
  (2518+ passed before this change; re-run after).

## Docs updated

- `docs/BOTS_API.md` §5 Gate 2 + §6 martingale + `message` example note.
- `docs/FRONTEND_PROMPT.md` key-contracts line (one-per-sub → legacy-only).

## Side effect (improvement, previously broken)

Recreating a grid/martingale after **soft-deleting** one used to hit the DB
constraint (deleted row still occupied the unique) → 500; now allowed
(view check already filters `is_deleted=False`). No test asserted the 500.

## Migration applied (2026-10-18)

`bots/0019_alter_gridbot_unique_together_and_more` applied to the real
Postgres on 2026-10-18. Live DB setup changed that day: 5432 was taken by
the ClearAlignersHub user-space cluster (left untouched), so torgovo2 now
runs its own cluster from `/home/arcore/pgdata` on **port 5433** (PG 18.6,
role `postgres`, db `torgovo`, `.env` `DB_PORT=5433`). Verified:
`manage.py migrate --check` OK, no UNIQUE index on `subscription` in
`bots_grid_bots`/`bots_martingale_bots` (pkey only), `seed_model_c_plans`
idempotently created the 5 plans.
