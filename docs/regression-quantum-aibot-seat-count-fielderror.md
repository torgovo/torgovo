# Regression: QuantumAIBot seat-count FieldError (Model C gates)

**Date:** 2026-10-17
**Severity:** P0 — every Model C bot-create request (signal/grid/martingale) and the
`CanCreateBots` permission path returned HTTP 500 instead of 201/403/429.
**Caught by:** `tests/test_model_c_gates.py` (new FR A2 scenario matrix, 38 tests).

## What broke

Any call path that reached the cross-type seat count raised:

```
django.core.exceptions.FieldError: Cannot resolve keyword 'user' into field.
Choices are: bot_name, created_at, deleted_at, exchange_name, fund, fund_id, id,
is_deleted, is_running, last_error, last_heartbeat, last_trade_at,
quantum_deposits, started_at, stopped_at, strategy_parameters,
total_profit_loss, trading_pair, updated_at
```

The listed choices are the **QuantumAIBot** model.

## Root cause

Two helpers summed seats as Signal + Grid + Martingale + **QuantumAIBot**, each
filtered by `user=`:

- `services/plan_limits.py:count_user_bots()` (Model C seat gate, line ~119)
- `apps/users/models.py:CustomUser.can_create_more_bots()` (used by
  `core/permissions.py:CanCreateBots`)

But `QuantumAIBot` has **no `user` field** — it FKs to `QuantumAIFund`
(`apps/bots/models.py` ~667), which is the admin-managed *Master Trading Fund*.
Quantum AI purchases create `InvestorPortfolio` investment rows, never
`QuantumAIBot` rows; the bot table is a global/admin surface, not per-user.
So `QuantumAIBot.objects.filter(user=...)` can never resolve and always raises
`FieldError` (Django rejects unknown field keywords at query build time, so it
crashes regardless of whether any rows exist).

Latent status before this fix: the Model C gate is brand new (only reachable
with `source="model_c"`), and `CanCreateBots` tests mock `can_create_more_bots`
(`tests/core/test_permissions.py`) — so no previously-green test ever executed
the real query. The bug shipped invisible and detonated on the first real
Model C create.

## Fix

Drop `QuantumAIBot` from both sums (identical basis preserved between the two
helpers). Seat basis is now exactly: Signal + Grid + Martingale, all
`is_deleted=False`.

- `services/plan_limits.py` — `count_user_bots()` + module docstring count-gate note
- `apps/users/models.py` — `can_create_more_bots()` + comment

Quantum-investment creation stays gated by G4 + the Model C seat count via the
*other* bot types; its own rows no longer (and never correctly could) occupy a seat.

## How it was tested

- `tests/test_model_c_gates.py` — 38/38 pass, including:
  - `TestBotCreationGates::test_type_gate_allows_listed_and_attaches_shared_sub` (201 path that previously 500'd)
  - `test_seat_gate_429_at_plan_limit` (count reached → 429)
  - `test_quantum_type_exempt_but_seat_gated` (empty `bot_types` list, signal bot fills seat, quantum create → 429 not 403)
  - `test_grid_seat_gate_counts_other_bot_types`
- Full suite re-run after the fix (see session log) — no collateral failures.

## Lessons

1. **Never mirror a query you haven't executed.** The docstring claimed
   "identical basis to `User.can_create_more_bots`" — both copies were wrong;
   parity of two broken things is still broken. When copying a count for
   parity, run both paths once before trusting them.
2. **Model-shape check before filtering:** a FK to an *admin/global* object
   (`QuantumAIFund` master fund) means the child table has no per-user
   dimension. Any `filter(user=…)` on it is invalid by construction.
3. **Permission-layer mocks hide crashes:** `CanCreateBots` was only ever
   tested with `user.can_create_more_bots` replaced by a MagicMock, so the
   permission could never surface the FieldError in CI. Prefer at least one
   integration test that runs the real helper.
