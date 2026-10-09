# Torgovo2 Cleanup Plan

## Status
After inspecting the live code, the prior critical breakage issues from `docs/latest_details.md` are already resolved:
- `apps/trading/admin.py` no longer references `BotConfiguration`.
- `apps/trading/serializers.py` no longer imports deleted models.
- `apps/trading/views.py` `get_exchange_rates()` now uses live CCXT tickers with DB fallback.
- `apps/bots/admin.py` and `apps/webhooks/views.py` already use `SignalBot`.

This plan focuses on remaining work that still needs pairing, ordering, and execution.

## Phase 1 — Reduce Duplication & Runtime Risk
1. Audit `trading/` vs `apps/trading/` + `trading/strategies/` vs `apps/trading/strategies/`.
2. Pick a single import path for non-legacy code; keep the other layer as a shim only if needed.
3. Delete duplicate bot classes from `apps/investments/models.py` if they are redundant with `apps/bots/models.py`.

## Phase 2 — Decide QuantumAI Ownership
**DONE:** QuantumAI logic lives in `bot_engine.py` (canonical). `apps/trading/strategies/quantum_ai.py` exists as the strategy class and is used by the engine.

## Phase 3 — Minimize Document Drift
1. Make one authoritative tracker: prefer `docs/todo.md`.
2. Update `docs/latest_details.md` so known issues reflect current code.
3. Align `docs/CODEBASE.md`, `PROJECT.md`, and `README.md` with current app/module reality.

## Phase 4 — Frontend Kickoff
1. Start skeleton in `frontend/`.
2. Mirror backend endpoints from `apps/*/urls.py` first, then implement views.

## Phase 5 — Tests & CI
1. Add a small test surface for:
   - `get_exchange_rates()` CCXT + fallback
   - webhook validation → execution path
   - bot start/stop lifecycle
2. Add a minimal CI workflow that installs deps and runs tests.
