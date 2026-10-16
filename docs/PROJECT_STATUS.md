# Torgovo2 Project Status

> Source of truth for the current engineering status of the project.
> This document supersedes informal completion claims and marketing-style status files.
>
> Last verified: 2026-09-28
>
## Executive status

The project is a substantial Django backend with real functionality, but it is not yet a verified production-ready launch platform.

Current status:
- Core backend structure: present and functional in parts
- Security hardening: partially verified and improved, but not fully complete
- Architecture hygiene: still has duplication and legacy overlap
- Compliance/legal readiness: not ready for real-money launch
- Deployment/operations readiness: not yet fully verified
- Documentation quality: mixed; some audits are strong, some claims are stale or contradictory

## Source-of-truth rule

**Product requirements:** `docs/FUNCTIONAL_REQUIREMENTS.md` Part A (locked 2026-10-11 grill-me). Engineering status: this document.

The following documents are historical or supplemental, not authoritative live status:
- `IMPLEMENTATION_COMPLETE.md`
- `ZERO_ERRORS_VERIFICATION.md`
- `docs/todo.md` (archived 2026-10-11 — stale)
- older status summaries that claim full production readiness without current evidence

Current operational status must be read from this document and the active audit reports in `docs/`.

## Verified status by category

### 1) Engineering
Status: Partially verified, but not fully clean.

Verified positives:
- Redis-backed rate limiting exists in the live settings and middleware
- crash-consistent trading-bot persistence shipped 2026-09-28: cross-process
  stop, SIGTERM/SIGINT forced snapshot, per-trade integrity columns,
  `BotRuntimeState` snapshots + boot recovery, 10 s/30 s heartbeat watchdog
  (full suite 2170 passed / 13 skipped; evidence: `docs/persistence/CHANGES.md`)
- Django check has been re-run successfully in recent audits
- multiple app modules have functional implementations
- test suite improvements have been documented in recent reports

Known remaining issues:
- duplicate app ecosystems remain
- legacy and canonical layers overlap
- some modules still have uncertain ownership or stale routes
- architecture cleanup is still required before a clean production handoff

### 2) Security
Status: Improved, but not final.

Verified positives:
- secret rotation and env hygiene are now treated seriously
- token and auth hardening were improved in recent audit iterations
- webhook auth and replay protection are documented as stronger than the earlier state
- 2FA and OTP handling have been corrected in major parts of the codebase

Known remaining issues:
- every financial path must continue to be verified against server-side authorization rules
- no launch sign-off should be given without final security verification on the active branch

### 3) Compliance / legal / finance
Status: Not launch-ready.

Open blockers:
- terms and privacy acceptance are not fully in place (**hard launch blocker**)
- automated billing lifecycle: manual payment codes + live quote lock shipped (FR A3 / G2, 2026-10-12); card rails (Stripe/PayPal) deferred to a later phase
- finance reporting, risk controls, and customer-ops processes are still incomplete

Deliberately deferred (decided 2026-10-11, FR A1 — not blockers):
- KYC/AML — flag reserved, not built at launch; entity formation (Seychelles/RAK) later
- US/EU marketing restrictions and geo gating — requirement noted (A1), enforcement not built

### 4) Operations / deployment
Status: In progress.

Required before production launch:
- deployment runbook
- rollback plan
- incident response plan
- backup/restore validation
- monitoring and alerting review
- release gate enforcement with evidence

### 5) Documentation / audit quality
Status: Mixed.

Strong examples:
- `docs/security-evaluation/REPORT.md`
- `docs/evaluations/RECOMMENDATIONS.md`
- `docs/duplication-audit.md`

Weak or stale examples:
- statements of “complete implementation” without current evidence
- contradictory status claims across multiple documents
- historical status reports kept without a clear archive label

## Current launch recommendation

Recommendation: do not describe the project as production-ready or complete.

The correct status is:
- active platform project with strong backend work
- partially hardened and improved
- still needs architecture cleanup, compliance work, and operational verification before launch

## P0 issues currently tracked

1. Canonical architecture cleanup
2. Duplicate app/domain ownership resolution
3. Final financial and permission verification
4. Launch-blocking compliance and legal gate setup
5. Production deployment runbook and rollback verification
6. Implement FR Part D gaps (G1–G9) — queue and detail in `FUNCTIONAL_REQUIREMENTS.md` Part D; Model C plans must be admin-driven (no hard-coded prices)

## P1 issues currently tracked

1. Legacy route and dead code removal
2. Final operational monitoring setup
3. User/developer documentation consolidation
4. Final QA and regression verification before release

## Status wording to use in project communications

Use this wording instead of “complete” or “fully done”:

"The project is in active engineering and hardening mode. Core backend functionality is present, but final launch readiness requires architecture cleanup, compliance completion, and production verification."

This wording reflects the current verified state without overstating confidence.
