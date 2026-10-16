# Changelog

## 2026-10-16 — G3: per-investor Quantum AI locks (FR A5)

Closes gap G3: biweekly fund distribution replaced by investor-level
term locks (30/90/180/365d). Nothing is withdrawable during the lock;
post-lock withdrawals are admin-approved manual payouts within 7 days.

- **Models** (`apps/bots/models.py`, migration `0018`): `InvestorLock`
  (capital balance-of-record incl. rolled profit; `matures_at` derived
  date-math, no sweep task — G4 lesson; term counters),
  `QuantumProfitCredit` (audit row per maturity credit, DB unique
  `(lock, term_number)` backstop mirroring G4 CAS),
  `QuantumWithdrawalRequest` (pending/approved/rejected; admin-entered
  payout incl. chain fees per grill Q12).
- **Service** (`services/quantum_locks.py`): `create_lock` (guards:
  valid term, amount > 0, active fund) / `credit_maturity`
  (select_for_update; free-form admin % — 2–5% is guidance only, 0%
  allowed, negative rejected; compounds capital; window rolls from the
  credit moment so a late credit cannot double-fire) /
  `request_withdrawal` (**hard rule**: raises while the lock is running;
  amount ≤ capital; one pending request per lock) /
  `approve_withdrawal` (debits lock, `PaymentTransaction` type
  `quantum_withdrawal`, closes lock at zero, **never** touches
  `UserBalance` — external crypto payout) / `reject_withdrawal`.
- **Endpoints** (`apps/investments/`): `GET|POST
  /api/investments/bots/quantum-ai/locks/` (own; staff see all;
  `?status=`, `?matured=1` admin credit queue), `POST .../locks/{id}/
  withdraw/`, `POST .../locks/{id}/credit/` (staff), `GET
  .../quantum-ai/withdrawal-requests/`, `POST
  .../withdrawal-requests/{id}/decide/` (staff; approve requires
  `payout_amount`). Credit response reports `term_number` (credited)
  and `current_term` (now running).
- **Creation wiring**: lock auto-created when a Quantum subscription is
  approved and when a Quantum deposit is approved (hard-fail 400 with no
  active fund — no silent capital loss).
- **Supersession**: beat entries `distribute-quantum-ai-profits` /
  `accrue-quantum-ai-profits` removed from `config/celery.py`; legacy
  task functions kept importable for their pinned unit tests.
- **Tests**: `tests/bots/test_quantum_locks_a5.py` — 53 tests (creation
  guards, maturity credit + compounding + unique backstop, lock-window
  hard rule, approve/reject accounting incl. UserBalance-untouched,
  endpoint auth/404/400/403 mapping, beat-entry removal). Full suite
  **2422 passed / 13 skipped**.

## 2026-10-15 — G4: subscription expiry lifecycle (FR A6)

Closes gap G4: 2-day grace, hard stop, D-7/5/3/1 reminders, re-subscribe
restore, indefinite data retention.

- **Settings** (`config/settings/base.py`): `SUBSCRIPTION_GRACE_PERIOD_DAYS`
  (default `2`) and `SUBSCRIPTION_REMINDER_OFFSET_DAYS` (default
  `7,5,3,1`) — no hard-coded business values.
- **Model** (`apps/payments/models.py`, migration `0012`):
  `BotSubscription.grace_until` + `expiry_reminders_sent` (JSON ledger of
  offsets already emailed this term).
- **Expiry state machine** (`apps/payments/services/expiry.py`): live
  date-math only — `subscription_state()` → `active` (≤ expires_at) /
  `grace` (≤ grace_until; **full access**) / `hard_stopped` (after grace;
  legacy rows with `grace_until=NULL` hard-stop at `expires_at`, grace is
  never invented) / `inactive` (status ≠ active); `is_hard_stopped()`;
  `get_usable_subscription(user, bot_type)` as the gate's single source of
  truth; `transition_expired_subscriptions()` persistence sweep (active →
  expired past grace; grace rows untouched).
- **Gate** (`apps/bots/views.py`): all 5 create paths (grid/signal/
  martingale/quantum-fund/quantum-invest) blocked with 403
  `PERMISSION_DENIED` only when hard-stopped or no usable subscription;
  active **and** grace rows allowed. Never touches open positions — they
  keep riding SL/TP (grill Q9).
- **Reminders** (`apps/payments/tasks.py` + `config/celery.py` beat
  entry): daily `check_subscription_expiry` = sweep + D-N emails; ledger
  stamped only after successful send (retry on transient failure);
  hard-stopped rows never emailed.
- **Email** (`core/email.py`): `send_email()` SMTP primary → Resend API
  fallback → `False`, never raises (A6 email is the only support channel).
- **Re-subscribe restore**: `approve()` now accepts status `expired`
  (`services/subscription_service.py`) — stamps fresh
  `started_at`/`expires_at` from `plan.duration_days`, recomputes
  `grace_until` from settings, clears the reminder ledger; same row PK
  retained → bot FKs/history/settings restored (indefinite retention,
  grill Q17). `payments:bot-subscription-create` reuses the unique
  `[user, plan]` row (no IntegrityError).
- **Tests**: `tests/payments/test_subscription_expiry_g4.py` — **36
  cases** (approve clock stamping, every state boundary incl. exact
  expiry/grace-end instants, gate 403 vs allowed end-to-end, sweep,
  reminder idempotency/retry, re-subscribe restore, email fallback);
  `tests/services/test_subscription_service.py` expired-approval test
  flipped to the new contract. Full suite: **2368 passed / 13 skipped**.

## 2026-10-15 — FR A3 rule change: 5-min refresh + 6-h payment window + explicit re-request

Implements the 2026-10-14 user decision that replaced the 1–60 s TTL /
silent re-lock on payment-code quotes (combined amount only while the
payment window is open; explicit re-request after expiry).

- **Settings** (`config/settings/base.py`): `PAYMENT_QUOTE_TTL_SECONDS`
  default `15` → `300` (5-min FE auto-update cadence; still clamped
  60–3600 in `services/quote.py`).
- **Models** (`apps/payments/models.py`, migration `0011`):
  `PaymentCoin.network_fee` (per-chain fee buffer in coin units, default
  0) + `PaymentCoin.quote_window_seconds` (default 6 h) — both
  admin-configurable; `PaymentCode.quote_window_expires_at` (starts on
  the first quote, never reset by automatic refreshes).
- **Quote service** (`services/quote.py`): `crypto_amount` now includes
  `network_fee` (combined payable, e.g. `15.00 + 0.20 → 15.20 USDT`);
  `expires_at` truncated at the window end; new `is_window_open()`
  (window closed → `get_or_refresh_quote` returns the expired quote,
  never re-prices) and `renew_quote()` (explicit re-request: awaiting
  codes only, resets the window, re-locks at the current rate).
- **API**: new `POST /api/payments/payment-codes/<code>/quote/`
  (`{coin_id?}` → 200 fresh quote + restarted window; 400 unknown
  coin/non-awaiting, 404 cross-user, 401). Detail payload gained
  `quote_window_expires_at`; `quote.coin.network_fee` and the coin list
  expose the fee for the `TRC20 (fee: …)` breakdown. Proof submitted
  after window expiry freezes the stale quote (no re-price).
- **Admin**: `PaymentCoin` lists/edits `network_fee` +
  `quote_window_seconds`; `PaymentCode` shows `quote_window_expires_at`
  readonly.
- **Tests**: `tests/payments/test_g2_payment_codes.py` — 3 TTL-clamp
  cases rewritten (60/3600/300) + `TestQuoteWindowAndCombinedAmount`
  (11 cases: combined amount, window start/truncation/no-extend,
  closed-window no-relock incl. coin switch, renew rules) +
  `TestPaymentCodeQuoteRerequest` (7 view cases) + window-closed detail
  and proof-freeze cases → **76 in-file**. Full suite: **2332 passed /
  13 skipped**, flake8 clean, `manage.py check` clean.
- **Docs**: FRONTEND_PROMPT §8 (re-request endpoint, payload fields,
  stale-proof rule) + flow row; BACKEND_PRODUCTION_TASKS rule-change
  note marked implemented.

## 2026-10-12 — G2: manual multi-coin payment codes (FR A3)

Closes gap G2: users pick a receive coin, get a live quoted crypto
amount, pay on-chain, and submit proof — with a server-clamped price
lock instead of flat-USD assumptions.

- **Models** (`apps/payments/models.py`): `PaymentCoin` (receive
  coin/chain + address, idempotent `manage.py seed_payment_coins`,
  `--dry-run` supported; addresses left blank until admin fills them),
  `PaymentCode` (unique code, `order_kind`, status
  `awaiting_payment → submitted → approved|rejected`, `locked_rate` /
  `locked_crypto_amount`), `PaymentQuote` (rate + crypto amount + TTL).
- **Services**: `services/quote.py` — `get_or_refresh_quote` re-locks an
  expired quote at the current price, raises `QuoteUnavailable` when the
  feed is down (never serves a stale amount as current);
  `services/fulfill.py` — `check_order_allowed` / `plan_fiat_amount` /
  `fulfill_payment_code` mirror the legacy subscribe row creation
  (duplicate 409 with `details.subscription_id`, plan-capacity 409).
- **API** (`apps/payments/urls.py` + `views.py`): `GET payment-coins/`
  (public picker), `POST payment-codes/` (create + first quote; bot
  orders forced to monthly), `GET payment-codes/<code>/` (detail + live
  quote, `?coin_id=` switch, 400 on unknown coin), `POST
  payment-codes/<code>/proof/` (TX hash or screenshot → pending_approval
  subscription; final re-price then freeze). All errors use the standard
  envelope — `ServiceUnavailable` (503 `SERVICE_UNAVAILABLE`) for feed
  outages (`core/exceptions.py`). Admin approve/reject mirrors onto the
  code status via `payments.signals`.
- **Tests**: `tests/payments/test_g2_payment_codes.py` — 54 cases
  (quote expiry/re-lock, coin switch, feed-down 503 envelope,
  duplicate/capacity 409, proof validation + double-submit 409, cross-user
  404, status mirroring, no-coin 400). Full suite: **2310 passed /
  13 skipped**, flake8 clean.
- **Docs**: FRONTEND_PROMPT §8 (endpoints + 3-step flow), §11 (503 row),
  §12 (code lifecycle); BACKEND_PRODUCTION_TASKS A3 replaced the stale
  `/api/subscriptions/subscribe/` contract; FR gap table G1+G2 marked
  closed; PROJECT_STATUS blocker list updated.

## 2026-10-12 — G1: admin-driven Model C subscription plans (FR A2)

Plans are now fully DB-driven; editing a plan row propagates to every
client with zero code changes. Docs were consolidated first against the
locked grill-me (FUNCTIONAL_REQUIREMENTS.md Part A).

- **Model** (`apps/payments/models.py` `SubscriptionPlan`): added
  `description`, `sort_order` (display order — canonical Free→Creator, replaces
  price sort), `bot_types` (JSON), `market` (spot/spot_futures),
  `max_signals_per_month`, `max_exchanges`; derived `annual_discount_pct`
  property (str-coerced, float/Decimal safe); `Meta.ordering` =
  `sort_order, price_monthly`.
- **Migration** `payments/0009_model_c_admin_driven_plans` (schema only) +
  idempotent seeder `manage.py seed_model_c_plans` (`--dry-run` supported;
  upserts locked Model C prices: Free 0, Basic 15, Standard 25, Premium 49,
  Creator 20 monthly; annual = ×12×0.8). Seeding is a command, not a data
  migration — test fixtures create plans with these slugs and would collide.
  Free-tier limits per FR A2 (`['signal']`, spot, 10 signals/mo, 1 exchange,
  1 bot); paid-tier non-priced limits are explicit placeholders (TBD FR A2).
- **Admin**: `SubscriptionPlanAdmin` registered on the custom admin_site —
  fieldsets (tier/pricing/limits/features), inline price+sort editing
  (`list_display_links` set to satisfy admin.E124), derived annual-% column.
- **API**: both plan endpoints (`subscriptions:bot-plans/`,
  `payments:subscription-plans/`) expose all new fields; bot-plans cache key
  bumped `subscription_plans_v1→v2` (old key dropped too); ordering by
  `sort_order`. Cache-invalidation signals now clear v1+v2.
- **Docs**: FRONTEND_PROMPT §4 + `SubscriptionPlan` TS interface updated
  (contract sync rule); BACKEND_PRODUCTION_TASKS §1.1 corrected (endpoint is
  `bot-plans/`, not `plans/` which serves Telegram plans) and marked DONE;
  DEPLOYMENT.md gains the seed step.
- **Tests**: `tests/payments/test_model_c_plans.py` (12 tests: seeder
  create/idempotence/dry-run/drift-reassert/non-canonical preservation, API
  field exposure, sort_order ordering, derived discount, admin-edit→API
  propagation). Suite: **2256 passed / 13 skipped**; flake8 clean
  (max-line-length=100).

## 2026-10-07 — c3b_report API-consistency fixes (A5/A7/A8/A9/A10/A14/A15/A16)

Batch of report items across subscriptions, referrals and the shared error
handler. Existing response contracts kept working; only the four tests the
report deliberately changed were updated.

- **A5 — pk-or-slug on both subscribe endpoints** (`apps/subscriptions/views.py`
  `_resolve_plan`): `telegram/subscribe` accepts UUID/int pk *or* slug,
  `bot-subscribe/` accepts slug *or* numeric pk (was: 400 `Invalid plan_id` for
  the "other" form). Both lookups filter `is_active=True`.
- **A7 — telegram subscribe semantics**: `billing_cycle` honoured
  (monthly/quarterly/yearly charge `price_*`; default monthly; invalid → 400)
  instead of hardcoded monthly; duplicate active/pending subscription →
  **409** with `error.details.{subscription_id,status}` (mirrors bot-subscribe);
  `max_subscribers` capacity enforced over non-terminal rows (`null` = unlimited);
  terminal rows (expired/cancelled/rejected) no longer block a new subscription.
- **A8 — `my-subscription` always 200**: `{"subscription": null}` when empty
  (was 404 flat `{"message": ...}`); pending states now visible; active row
  preferred, else latest own row.
- **A9 — canonical plan-endpoint map** documented in the
  `apps/subscriptions/views.py` module docstring (two models, four routes,
  three response shapes).
- **A10 — `features` on telegram/plans**: `source="feature_dict"` (property
  that exists only on the detail serializer) replaced by
  `SerializerMethodField` computing `{max_daily_signals, exchanges_covered,
  risk_level, include_premium_signals}`; the key was silently dropped before.
- **A14 — uniform error envelope**: `telegram/subscribe` and `bot-subscribe`
  guards raise DRF/`Conflict` instead of flat `{"error": "..."}` Responses;
  referrals `ApplyReferralCodeView` (invalid/self/already-applied/IntegrityError)
  likewise; `core/exceptions.py` gained `Conflict` (409, `error_code=CONFLICT`)
  and `get_error_message` extraction for dict details with a `message` key.
  All errors now render `{"error": {code, message, details}, "timestamp"}`.
- **A15 — plan-cache invalidation on save** (was: subscribe-time
  `cache.delete("telegram_plans_v1")` only — an event that cannot change plan
  data — and `subscription_plans_v1` never invalidated at all): new
  `apps/subscriptions/signals.py` + `apps/payments/signals.py` receivers
  (post_save/post_delete on `TelegramSignalPlan` / `SubscriptionPlan`, wired
  via `Config.ready()`) drop **both** keys.
- **A16 — dead code**: `ReferralStatsSerializer` (never referenced) and the
  now-unused `status` import removed from `apps/referrals/views.py`.

Tests: `tests/subscriptions/` + `tests/referrals/` **148 passed** — 28 new
(pk-or-slug ×5, billing/limits ×8, envelope ×6, features ×2, cache ×5,
A8 pending-visible ×1, referrals envelope-shape ×1) + 4 updated for the
report-driven contract changes (404→200, flat→envelope ×3). Verified: full suite **2244 passed / 13 skipped**,
`manage.py check` 0, `makemigrations --check` clean (no lint tooling is
configured in this repo — venv has no flake8/ruff/black).
Authoring gotchas: `TelegramSignalPlan.price_quarterly/yearly` are NOT NULL
without default (every test factory needs them), and
`SubscriptionPlanSerializer.id` is an `IntegerField` fed a UUID pk, so the
payload id is `int(uuid)` — compare with `int(plan.id)`.
Docs: `FRONTEND_PROMPT.md` + `docs/frontend-integration-brief.md` re-synced
with today's contracts (envelope/409 in §11, subscribe + null-state contracts
in §4, response shapes in §9, public plan endpoints in §12, two new §13
checklist items) — both copies byte-identical.

## 2026-09-29 — Persistence hardening test matrix (CHG-T-1)

New `tests/persistence/test_persistence_hardening.py` — **13 tests** over the
completed 7-phase persistence stack: security (hostile-key injection, cross-bot
/ cross-type payload leakage, tampered-DB schema refusal), optimization
(20-tick burst = 1 write, zero-query collect, single-UPDATE heartbeat),
reliability (pre-write collect failure, plain-JSON Decimal safety, exact 15 s
stale boundary) and concurrency (8-thread snapshot bounded + exception-free).
Tests only — no production code touched. Complements, never duplicates, the
phase suites; revert = delete the one file (see `docs/persistence/CHANGES.md`
CHG-T-1).

Verified: full suite **2183 passed / 13 skipped**, `manage.py check` 0,
`makemigrations --check` clean, flake8 0 findings on the new file.

## 2026-09-28 — Production persistence (crash-consistency): 7-phase plan DONE

Every bot, open trade, monitoring loop and P/L snapshot now survives
worker/process death with a **<15 s blind window** and is restored on boot as if
nothing happened (all 4 bot types: grid, martingale, quantum, signal + webhook
engines). Master revert guide with per-edit reverse snippets and full test
matrix: **`docs/persistence/CHANGES.md`** (1093 lines).
Verified: full suite **2170 passed / 13 skipped**, `manage.py check` 0,
`makemigrations --check` clean, flake8 0 new.

### Phase 6a — cross-process bot stop (CHG-6a-1..10, 2026-09-26)
- Stop-request primitives (`task_requested_stop` keys + per-iteration
  `check_task_requested_stop`) in `execution.py`; `stop_bot` reports
  `engine_found`; stale flag cleared on start.
- `GridPositionMonitor.stop_cb` hook + `_check_remote_stop()` poll wired into
  both monitor loops → a stop issued from another process/worker ends the loop
  within one iteration; `_notify_stopped()`/`_on_remote_stop()` extracted;
  `tasks.stop_bot` now stops the engine (was DB-flag only).

### Phase 6b — SIGTERM/SIGINT registration (CHG-6b-1..5, 2026-09-26)
- `_running_engines_lock` → `threading.RLock()` (handler runs on main thread,
  may interrupt the lock holder).
- `apps/trading/apps.py` Celery-aware hook re-installs handlers;
  `execution.py` idempotent `_install_shutdown_handler()` + previous-handler
  chaining (Django runserver + Celery worker + gunicorn all covered).

### Phase 1 — trade record integrity (CHG-1-1..5, 2026-09-27)
- `BotOrder` additive columns + migration `bots/0017`: entry reason, live/closed
  marks, price resolution, bot linkage; `order_service.py` + `BotEngine.
  save_order` forward them; all call sites (incl. webhook `_log_trade`) record
  linkage.

### Phase 2 — `BotRuntimeState` + `apps/trading/state.py` (CHG-2-1..3, 2026-09-27)
- New model (migration `trading/0002`) + `save_snapshot`/`collect_state`/
  `apply_state` helpers — single source of truth for a bot's volatile runtime
  state (levels, positions, counters).

### Phase 3 — snapshot / restore (CHG-3-1..4, 2026-09-27)
- `snapshot_engine` (5 s throttle)/`restore_engine` primitives;
  `GridPositionMonitor.snapshot_cb` in ctor + both loops; `BotEngine.
  _snapshot_tick` (periodic + force); `tasks.stop_bot` step-4 STOPPED flush.

### Phase 4 — boot recovery (CHG-4-1..4, 2026-09-28)
- `recover_running_bots()` on Celery `worker_ready` (15 s min-stale gate):
  re-dispatches `status=running` bots from their last snapshot;
  `startBot(restore_mode=True)` applies the snapshot BEFORE attach; no
  `worker_process_init` (avoids per-pool-child duplicate dispatch).

### Phase 5 — watchdog tuning (CHG-5-1..4, 2026-09-28)
- Heartbeat 60→10 s (`grid_monitor` both loops + `bot_engine`), stale cutoff
  5 min→30 s (`check_stale_bots`), beat `check-stale-bots` 120→30 s +
  `heartbeat-check` 300→60 s → dead-worker worst case ~60 s (was ~5-10 min).
- Two-tier contract: boot restore = 15 s min-stale vs 5 s snapshots; watchdog =
  10 s heartbeat / 30 s cutoff / 30 s beat.

### CHG-3-5 — shutdown-path forced snapshot (2026-09-28)
- `_shutdown_handler` now force-snapshots every live engine (bypasses the 5 s
  throttle) BEFORE teardown, best-effort (never blocks shutdown); status left
  untouched → a SIGTERM'd bot stays `running` + fresh payload and Phase 4
  restores it on the next boot. 4 new DB-free tests in
  `tests/persistence/test_shutdown_signals.py` (file: 35 passed).

---

## 2026-08-18 — Security, financial, scalability & code quality audit fixes

12 issues from independent deep analysis, all implemented and verified (1949 passed / 2 pre-existing / 13 skipped).

### Security
- **SEC-1 (CRITICAL)**: Google OAuth audience bypass — boot-time `ImproperlyConfigured` check
  in `apps/authentication/apps.py` (skips during pytest); defense-in-depth in
  `apps/authentication/serializers.py` (`if not settings.GOOGLE_OAUTH_CLIENT_ID`). Test:
  `test_rejects_when_google_client_id_empty`.
- **SEC-2**: Dead `two_factor_code` column removed from `apps/payments/models.py` + migration
  `0007_remove_two_factor_code_field.py`. `two_factor_code` field in serializer converted to
  standalone `CharField`. Tests: `tests/core/test_permissions.py` updated.

### Financial correctness
- **FIN-1**: `process_payouts()` was never called by Celery — created `apps/investments/tasks.py`
  with `process_fund_payouts` task; added beat schedule (`crontab(hour=0, minute=5)`) in
  `config/celery.py`. Tests: `tests/services/test_quantum_ai_fund.py` (2 new).
- **FIN-2**: `SoftDeleteModel.delete()` no longer triggers `post_delete` signal. Default manager
  now filters soft-deleted records (`SoftDeleteManager`); `all_with_deleted()` for unfiltered
  queries. New `hard_delete()` for permanent removal. `test_bulk_objects_not_affected` updated.

### Scalability
- **SCAL-1**: `SiteConfig.get()` now uses `@lru_cache(maxsize=1)` with `cache_clear()` on
  `save()`. Eliminates a DB hit on every bot-limit check.
- **SCAL-2**: Monthly AuditLog cleanup task (`core.tasks.cleanup_old_audit_logs`, 90-day
  default). Beat schedule: 1st of month at 02:00 UTC. Tests: `tests/core/test_tasks.py` (3 new).

### Infrastructure
- **CONFIG-1**: `docker-compose.yml` now dev-only (`.:/app` mounts, `runserver`). New
  `docker-compose.prod.yml` (no mounts, `gunicorn`). Prod services reference image-baked code.
- **CONFIG-2**: Dockerfile `collectstatic` no longer silenced with `|| true` — fails build on
  errors (catches issues pre-deploy).
- **CONFIG-3**: Nginx webhook `location = /api/webhooks/custombot/` — removed hardcoded
  TradingView IP allowlist. HMAC `secret_key` in body is the sole auth mechanism.

### Code quality
- **DEAD-1**: Deleted dead `BOT_CONFIG` dict from `config/settings/base.py`. Comment points to
  `SiteConfig.get_plan_limit()`.
- **DEAD-2**: `_collect_engine_state()` in `apps/trading/engines/execution.py` — fixed attribute
  names to match actual BotEngine attributes (`favor_lvl`/`against_lvl`, `Unrealized_Pnl`).
- **C6**: Renamed `QuantumAIDeposit` → `InvestorDeposit` and `QuantumAIInvestment` →
  `InvestorPortfolio` across entire codebase (~40 files). Backward-compatible aliases added
  (`QuantumAIDeposit = InvestorDeposit`, etc.) for external consumers.

---

<!-- 2026-08-09 (opencode): Docs-sync entry added — CODEBASE.md re-synced (1859 green, known issues #2/#5 resolved) and engineering-evaluation REPORT.md re-scored D → B−. No code changes in this section. -->

## 2026-08-17 — COMPLIANCE Phase-1: consent capture at registration

- **Model** (`apps/users/models.py`): `CustomUser.terms_accepted_at` (DateTimeField, null) +
  `privacy_version` (CharField(20), default `settings.PRIVACY_POLICY_VERSION = "2026-08-1"`).
  No backend privacy flag — acceptance is a precondition for the 201, never stored.
- **Serializer** (`apps/authentication/serializers.py`): `terms_accepted` /
  `privacy_policy_accepted` are `BooleanField(write_only=True, required=True)` with
  `validate_*` rejecting falsy values (missing → 400 field error, `False` → 400). `create()`
  pops both booleans (never persisted), then after `create_user` stamps
  `user.terms_accepted_at = timezone.now()` + `user.privacy_version =
  settings.PRIVACY_POLICY_VERSION` and saves with `update_fields=[...]`. `UserSerializer`
  exposes both fields `read_only` — PATCH/backdate attempts are silently ignored.
- **CustomUser.save() interaction (verified)**: the stamping `save(update_fields=[...])` does
  NOT trip the payment-gate `PermissionError` in `users/models.py:219` — the guard only fires
  for `sensitive_fields = ("subscription_plan", "is_subscription_active")`. Side effects of the
  stamping save are benign: `max_bots_allowed` is recomputed but not persisted (update_fields),
  and the Referral `update_or_create` is idempotent and runs before
  `apply_referral_after_registration` (no claim conflict).
- **Migration**: `apps/users/migrations/0006_customuser_privacy_version_and_more.py`
  (dep 0005). **NOT yet applied to Postgres** — DB down (127.0.0.1:5432 refused); test runner
  applies it to the SQLite test DB.
- **Tests**: consent fields added to registration payloads in `tests/authentication/test_serializers.py`,
  `tests/authentication/test_views.py`, `tests/users/test_views.py`, and all 6 payload dicts in
  `tests/referrals/test_referral_registration.py`. New coverage: missing-consent rejection,
  explicit-False rejection, metadata stamping, read-only exposure. Full suite **1896 passed /
  13 skipped** (~2m13s); flake8 clean; `makemigrations --check` → no changes detected.

## 2026-08-17 — GDPR account endpoints: self-deactivation + data export

- **`POST /api/users/deactivate/`** (`apps/users/views.py` `DeactivateAccountView`): password
  required (400 if wrong or missing); sets `user.is_active = False`, marks `all_tokens_invalidated`,
  revokes every outstanding refresh token and blacklists them, logs `UserActivityLog`
  (`account_deactivated`) + `AuditLog` (`user_account`). Response includes `sessions_revoked`.
  A deactivated user cannot login again.
- **`GET /api/users/export-data/`** (`UserDataExportView`): GDPR Art. 15 JSON export of all
  user-owned data — profile, balances, masked exchange credentials (`api_key`/`secret_key`/
  `passphrase` masked via `_mask_credential` **after decryption** — the raw fields are Fernet
  ciphertext), bots (signal + grid), subscriptions, referrals, orders, deposits, withdrawals,
  payment transactions, profits, activity logs. Soft-delete aware (`is_deleted=False`).
- **Management command** `manage.py deactivate_user --email/--pk [--reason]`: same deactivation
  path for admins, records reason in the audit trail.
- **Routes**: `deactivate/` and `export-data/` registered in `apps/users/urls.py`.
- **Refactor within `views.py`**: added `from apps.payments.models import BlockchainAddress` —
  fixes a pre-existing `NameError` (500) in `admin_create_blockchain_address` (line 213 used the
  class without importing it).
- **Tests**: `tests/users/test_deactivate_export.py` (16 tests: 8 deactivation + 8 export,
  incl. all-tokens-revoked via `OutstandingToken`/`BlacklistedToken`, old-refresh rejection,
  full export shape + credential masking). Gotchas: simplejwt 5.5.1 `RefreshToken(str(token))`
  runs `verify()` → blacklist raises `TokenError` at construction, use `verify=False`;
  `GridBot` requires `favor_levels`/`against_levels`; `UserBalance` fields are
  `available`/`hold`, not `balance`. Full suite **1912 passed / 13 skipped** (~2m11s); flake8
  clean on changed files; `manage.py check` 0 issues.

## 2026-08-13 — flake8 cleanup (0 findings) + 2 latent runtime bugs fixed

- **flake8 now clean**: `python3 -m flake8 .` (project `.flake8` config, `max-line-length = 100`)
  reports **0 findings** (was 49: 31 F401, 6 E501, 4 F811, 4 F841, 3 F821, 1 E741). All were
  unused imports, unused local vars, overly long lines, and ambiguous names — no dead code removed.
- **F821 real bugs fixed** (would raise `NameError` at runtime in those code paths):
  - `apps/trading/tasks.py` `_handle_stale_bot`: `timezone` was undefined — added a function-local
    `from django.utils import timezone` (matches the file's established per-function import pattern).
  - `apps/users/views.py`: `get_user_model` was undefined at call site — added the import.
- **E741**: ambiguous name `l` renamed to `low` in `apps/trading/exchanges/mock_adapter.py`.
- **F811**: `apps/exchanges/management/commands/reencrypt_credentials.py` duplicate module-level
  imports (Fernet/InvalidToken/settings) removed; function-local imports retained.
- **Verification**: `manage.py check` 0 issues; full suite **1859 passed / 13 skipped** (~2m15s).

## 2026-08-09 — Documentation sync

- `docs/CODEBASE.md`: test coverage section updated to **1859 passed / 13 skipped** (1872
  collected, per-directory table); `core/middleware` now Redis/cache-backed; Known Issues
  #2 (`RateLimitMiddleware` in-memory) and #5 (`django_prometheus` missing) marked resolved;
  metrics table test-count bumped from 1718 → 1859.
- `docs/engineering-evaluation/REPORT.md`: appended **2026-08-09 Re-assessment D → B−** section
  (verified `manage.py check` clean, green suite, trading-tasks fixes, Redis middleware).
  Remaining grade blocker: `.env` still tracked in git with live exchange keys + `DEBUG=True`.
- No code changes in this entry; engine/task fixes are documented in the Unreleased section below.

## Unreleased — Phase 1: Redis Rate Limiter + Exchange Kill-Switch

### Security / Reliability
- **RateLimitMiddleware is now distributed (Redis-backed)** — request counters live in the
  shared cache backend (`CACHES['default']`, Redis db 1 in production) via atomic
  `cache.incr` / `cache.add`, so limits are enforced consistently across all web/worker
  processes instead of per-process. If the cache backend is unreachable the middleware
  degrades gracefully to the in-process dict fallback so the API never 500s on rate limiting.
  Same 429 contract, window (60s) and per-subscription limits as before.
- **Exchange kill-switch via `DISABLED_EXCHANGES` env var** — `get_adapter()` in
  `apps/trading/exchanges/__init__.py` now refuses to create adapters for any exchange listed
  in the comma-separated, case-insensitive env var, raising a new `ExchangeDisabledError`
  (`ValueError` subclass). The var is re-read on every call so operators can flip the switch
  without a restart. The `MockAdapter` demo fallback (mexc/coinbase in demo mode) is exempt so
  demo/testing flows keep working during an incident.

### Bug Fixes
- **`reset_monthly_signal_limits` referenced the wrong model** — `apps/trading/tasks.py`
  queried `TelegramSubscription.signals_used_this_month`, a field that only exists on
  `SignalBot`, which raised `FieldError` at runtime. The task now resets `SignalBot`
  `signals_used_this_month` counters to 0.
- **`_credit_reserve` raised `NameError: name 'Decimal' is not defined`** — the helper in
  `apps/trading/tasks.py` used `Decimal` without importing it, so any excess-return reserve
  credit crashed after computing the distribution. The import is now done inside the helper.
- **SignalBot webhook rejected every real TradingView alert** — TradingView webhooks can only
  POST a JSON body (no HTTP headers), but `SignalBotWebhookView.post()` (June security pass)
  required the `X-Signature` HMAC header, so the unique per-bot `secret_key` embedded in each
  bot's generated webhook message was never validated and every alert 401'd. The handler now
  accepts the `secret` from the JSON payload as the primary credential, verified in constant
  time with `hmac.compare_digest` against `bot.secret_key` (no timing oracle for brute force);
  `X-Signature` HMAC remains an optional upgrade path for header-capable clients. Shared URL
  `/api/webhooks/custombot/` and the per-bot key design are unchanged. Tests updated:
  `test_secret_in_body_authenticates` (TradingView-realistic 200), `test_invalid_body_secret_rejected`
  (403), `test_missing_credentials_returns_401`, plus a model test locking that `webhook_message`
  contains every field the handler needs to execute via CCXT.

### Exchange Adapters
- **CoinbaseAdapter now implements `create_stop_loss_order` / `create_take_profit_order`** —
  the only non-base methods any production consumer calls (grid bots via
  `grid_monitor.py:626,649`). A full parity audit of all 8 adapters against `BaseAdapter` +
  every consumer call-site confirmed Coinbase was the sole adapter missing the stop/take pair,
  so a grid bot on Coinbase would silently skip SL/TP placement. Both methods mirror the
  alpaca pattern: market order + `stopPrice` in params (trigger), with `format_symbol`,
  `amount_to_precision`, `price_to_precision`, `_make_request`, and `_normalize_order` applied.
- New `tests/exchanges/test_coinbase_adapter.py` (19 tests): exchange init (passphrase →
  `config["password"]`, demo mode via `enable_demo_trading`, load_markets + failure), str/repr,
  `format_symbol` futures-suffix stripping, limit-order `post_only` default, the two new
  stop/take methods (symbol/type/side/params assertions), and spot position semantics
  (`fetch_positions` → `[]`, `close_position` opposite-side market).
- `tests/exchanges/test_stub_adapters.py` extended (37 → 49 tests): OKX, MEXC, and Alpaca now
  cover `create_stop_loss_order` / `create_take_profit_order` (positional args to
  `_make_request`, `triggerPrice`/`stopPrice` + `reduceOnly` params merge), plus MEXC/Alpaca
  `create_market_order` and Alpaca `create_limit_order` — closing the last adapter-coverage
  gap so every consumer-required order method on every adapter is tested.

### Tests
- `tests/engines/test_trading_tasks.py`: new 30-test suite covering `apps/trading/tasks.py` —
  `run_trading_bot` (cache-dedup, engine dispatch, restore-mode forwarding, not-found
  no-retry, retry + exception→Retry semantics), `start_bot`/`stop_bot` (grid/martingale/
  quantum + not-found), `check_all_active_bots` (per-type dispatch, inactive/deleted skip),
  `check_stale_bots`/`_handle_stale_bot` (restore vs mark-stopped, no-position and
  position-check-error paths), `heartbeat_check`, `reset_monthly_signal_limits`, and
  `accrue_quantum_ai_profits`/`distribute_quantum_ai_profits` (proportional crediting,
  smoothing cap/excess-reserve, no-distribution cases).

### Tests
- `tests/core/test_middleware.py`: rate-limit-exceeded test now seeds the cache backend; added
  in-window counter increment and cache-outage fallback tests.
- `tests/exchanges/test_adapter_factory.py`: new `TestKillSwitch` suite (env parsing,
  disabled-exchange raise, case-insensitivity, non-target exchange unaffected, mock exemption,
  unknown-exchange precedence).
- `tests/engines/test_grid_monitor.py`: new 36-test suite covering `GridPositionMonitor`
  construction/state, thread lifecycle (`start_monitoring`/`stop_all`), real-time price/side
  tracking, loss/profit monitoring with one-shot-position thread tests, SL/TP order placement
  (dollar and percentage modes, sentinel and inverted-price handling), and `_refresh_sltp_if_changed`
  / `_update_heartbeat` refresh logic.
- `tests/bots/test_behaviour.py`: new 40-test suite covering `SignalBot` generation
  (`bot_id`/`webhook_url`/`secret_key`/`webhook_message` template), signal accounting
  (`increment_signal_count`, `signals_remaining`, `success_rate`), `SoftDeleteModel`
  flag/restore/hard-delete semantics, one-per-subscription constraints for grid and
  martingale bots, `ReserveFund` target/coverage/transaction audit rows, and Quantum
  fund smoothing (floor/pass-through/cap) plus investment share and profit-share math.
- `tests/engines/test_order_service.py`: new 26-test suite covering `BotOrderService`
  order creation (`dollar` vs coin/market vs limit, unknown order types, adapter-exception
  tolerance), position closing (no/zero position, long/short, percentage mode, unknown side,
  exceptions), cancel-all-orders, and order persistence (`save_order` — user resolution,
  non-dict `Details` wrapping, indicator wiring, Telegram alert behaviour, signal-driven
  no-user sync path).

## v2.0.0 — 2025-Q4 — Major Refactor

### Architecture & Structure
- **First working complete system** — 4 bot types, exchange adapters, webhooks, subscriptions
- **Legacy `trading/` moved to archive** — new `apps/trading/` with clean engine/strategy/adapter separation
- **10 local Django apps** — modular, single-responsibility per app
- **Services layer** — `BotExecutorService`, `QuantumAIFundService` for cross-app orchestration
- **Config split** — 6 env settings files (base, dev, prod, test, staging, docker)
- **Core utilities** — base models (UUID, SoftDelete, Timestamped), encryption, middleware

### Trading Engine (replaced legacy bot_runner.py)
- `apps/trading/` with engines/strategies/adapters separation
- **BotEngine** — generic CCXT-based engine accepting dict config (model-agnostic)
- **GridStrategy** — creates buy/sell grid levels; restart bug (sells existing holdings) unresolved
- **MartingaleStrategy** — progressive position doubling; take-profit checks on every candle
- **SignalStrategy** — one-shot trade execution from webhook signal
- **MockAdapter** — sandbox for exchanges without testnet
- 120+ strategy engine tests
- PROFIT_CURRENCY bug: `{"MODE": "..."}` dict assigned instead of `BaseAdapter.__init__`

### Exchange Adapters
- **BinanceAdapter** — fully implemented (watchOrders/health/ticker/sandbox)
- **BybitAdapter** — fully implemented (watchOrders/health/ticker/sandbox)
- **OKXAdapter** — minimal stub (coins, leverageTiers)
- **MEXCAdapter** — stub (MockAdapter for testing)
- **AlpacaAdapter** — stub (minimal markets/balance)
- **CoinbaseAdapter** — stub (MockAdapter for testing)
- Adapter resolution: `get_adapter(config)` in `apps/trading/exchanges/`

### Webhook System (54 tests)
- Signal processing for EMA, RSI, Bollinger Bands
- Signal resolution with configurable thresholds
- Signal reset endpoint (admin)
- **TradingViewWebhookView** — stub (accepts POST, does nothing)

### Quantum AI
- P/L distribution engine (service-layer)
- User-specific balance tracking with proportional P/L
- Fernet encryption for master exchange keys
- `encrypt_quantum_fund_keys` management command
- Accrual/distribution via Celery Beat (every 2 weeks)

### Security
- **Fernet symmetric encryption** for all API keys at rest
- **JWT with refresh token rotation** (djangorestframework-simplejwt)
- **Credential redaction** — keys masked in logs/admin
- **Auth flow** — register, login, refresh, password reset (OTP), password change
- **Rate limiting** — in-memory (not thread-safe)
- **Brute force protection** — login throttling
- **Audit logging** — user activity log (admin viewable)
- **Session control** — logout invalidates refresh token
- **CORS** — configurable allowed origins

### Subscriptions & Payments
- TelegramSignalPlan, SubscriptionPlan, BotSubscriptionPlan models
- Deposit-withdrawal model with admin approval flow
- Referral system with code generation and reward tracking
- **Subscription create/extend/cancel** — return 501
- **Frontend** — not started

## Fix Log (from AGENTS.md)

### 2025-11-15 — Grid restart bug
GridBot restart sells existing holdings instead of detecting position. No fix yet.

### 2025-11-14 — Webhook serialization
Field-level validation for all webhook signal fields. Serializer passes 14 tests.

### 2025-11-13 — Migration conflicts
`apps.bots.0038` — renamed SignalBot field `type` → `order_type` causing migration chain issues.

### 2025-10-30 — MartingaleStopLoss auto-approve
Removed auto-approve for Martingale stop-loss. Now requires explicit admin approval.

### 2025-10-28 — Quantum AI 10x deposit display
Investors saw 10x inflated deposits. Fixed by capping display at actual amounts.

### 2025-10-29 — ExchangeCredentials backward-compat
`apps.trading.models.ExchangeCredentials` → `from apps.exchanges.models import ExchangeCredentials`.

### 2025-10-25 — Fernet key migration
Encryption management command created. Plain text keys in DB migrated to encrypted.

### 2025-10-20 — PROFIT_CURRENCY bug
`{"MODE": "..."}` dict assigned instead of `BaseAdapter.__init__`. Introduced during refactor.

### 2025-10-10 — BotExecutorService created
Extracted bot start/stop orchestration from views into `services/bot_executor.py`.

### 2025-10-05 — Rate limit refactor
Switched from token bucket to sliding window. Still in-memory.

## Past Versions (pre-refactor)

### v1.x — 2023-2024
- Monolithic `trading/` directory (legacy, archived)
- All trading logic in single `bot_runner.py`
- No tests, no encryption, no subscription system
- Single bot type (SignalBot)
- No Docker, no Celery, no Redis
- Single settings file with no environment separation

### v0.x — 2022
- Initial Django project scaffolding
- Basic user authentication
- No trading functionality
