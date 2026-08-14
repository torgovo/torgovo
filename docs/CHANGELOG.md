# Changelog

<!-- 2026-08-09 (opencode): Docs-sync entry added — CODEBASE.md re-synced (1859 green, known issues #2/#5 resolved) and engineering-evaluation REPORT.md re-scored D → B−. No code changes in this section. -->

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
