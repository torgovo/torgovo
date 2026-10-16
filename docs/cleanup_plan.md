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
1. ~~Make one authoritative tracker: prefer `docs/todo.md`~~ superseded — `docs/todo.md` archived at `docs/archive/todo.md` (2026-10-11, stale counts/closed items); live tracker = `PROJECT_STATUS.md`; product requirements = `FUNCTIONAL_REQUIREMENTS.md`.
2. ~~Update `docs/latest_details.md`~~ superseded — archived at `docs/archive/latest_details.md` (2026-10-09; live status = `PROJECT_STATUS.md`).
3. Align `docs/CODEBASE.md`, `PROJECT.md`, and `README.md` with current app/module reality. **DONE** (README index current; CODEBASE re-synced 2026-08-20; frontend-docs consolidation Steps 2–3 archived FRONTEND.md / connectivity / API.md / legacy frontend prompt, route-verified API_DOCUMENTATION.md 2026-10-07).

## Phase 4 — Frontend Kickoff
1. Start skeleton in `frontend/`.
2. Mirror backend endpoints from `apps/*/urls.py` first, then implement views.

## Phase 5 — Tests & CI
1. Add a small test surface for:
   - `get_exchange_rates()` CCXT + fallback
   - webhook validation → execution path
   - bot start/stop lifecycle
2. Add a minimal CI workflow that installs deps and runs tests.

---

## Issues found 2026-10-11 (docs consolidation + audit re-verification)

Context: grill-me decisions (2026-10-11) were consolidated into
`FUNCTIONAL_REQUIREMENTS.md` Part A; contradicting doc claims were replaced.

### Doc contradictions found & resolved (same day)
| # | Was | Now |
|---|-----|-----|
| 1 | OVERVIEW: "Referral system with USDT bonus payouts" | Hybrid referrals (Creator 10% cash / else 15% referee discount), FR A7 |
| 2 | OVERVIEW: "All 6 exchanges complete" as status | Launch scope = Bybit + Binance; adapters exist ≠ launch support, FR A4 |
| 3 | OVERVIEW: Quantum "every 2 weeks" as product behavior | Labeled current code; target = locks + 7-day manual profit-only payouts, FR A5 |
| 4 | OVERVIEW: tests "~1949 passing" | 2170 passed / 13 skipped (full suite, 2026-09-28) |
| 5 | BACKEND_PRODUCTION_TASKS: plans $29.99/$99.99, subscribe = Stripe-first, "Processed every 2 weeks", `total_bonus_usdt` | Model C prices, manual payment-code flow, 7-day post-lock payout, hybrid referral stats |
| 6 | PROJECT: "DO NOT MODIFY" legacy root `trading/` | Removal approved (Phase 0); 0 active imports from `apps/` verified 2026-10-11 |
| 7 | FUNCTIONAL_REQUIREMENTS: stale "1967/6 skipped" + outdated payment flow | Fully rewritten (Parts A–D); stale `trading/` references dropped |

### CODE_AUDIT_REPORT.md re-verification
- **B1 (Celery beat "missing") — DISPROVEN 2026-10-11.** `python manage.py check` → "System check identified no issues (0 silenced)". Beat is configured via config/celery.py periodic schedule. Do not act on B1; audit doc is stale here.
- **C2 (missing 00:03 crontab — pending 0016 migrations) — LIKELY STALE.** A 00:05 crontab now exists (`crontab -l`). Re-verify migration state (`showmigrations`) before any 0016 work.
- General rule: re-run the failing commands from the audit before acting on any item; the audit predates several fixes.

### Unresolved / open questions
- **ExchangeCredentials ownership:** `FUNCTIONAL_REQUIREMENTS.md` C3 originally described `apps/exchanges/*` as legacy and `apps/trading/*` as canonical; `PROJECT.md` states the reverse ("ExchangeCredentials canonical in `apps/exchanges/`, backward-compat import in `apps/trading/`"). Not resolved this pass — decide during Phase 0 legacy cleanup (the directory to delete must be the non-canonical one).
- **FR A2 paid-tier feature limits, A3 quote-expiry duration, A5 principal-after-lock terms, A7 discount scope + cash payout mechanics:** marked `TBD` in FUNCTIONAL_REQUIREMENTS.md — grill-me did not specify; must be defined before the corresponding Phase B code work.
