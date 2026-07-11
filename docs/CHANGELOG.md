# Torgovo — Changelog

## 2026-06-21: Security Audit — 15 Vulnerabilities Fixed

- **`core/utils.py`** — Extracted `looks_encrypted()` as single source of truth for Fernet detection, shared by QuantumAIFund, ExchangeCredentials, and management command. Added key-rotation hazard warning.
- **`apps/bots/models.py`** — `QuantumAIFund.save()` now auto-encrypts master API keys via `looks_encrypted()` guard (matching ExchangeCredentials pattern). Added `get_decrypted_credentials()`.
- **`apps/bots/admin.py`** — Added `QuantumAIFundForm` with `PasswordInput(render_value=False)` widgets, `required=False` on key fields, helpful fieldset description. `QuantumAIFundAdmin.save_model()` restores existing encrypted values when key fields submitted blank.
- **`apps/bots/serializers.py`** — Removed `master_api_key`/`master_secret_key`/`master_passphrase` from `QuantumAIFundSerializer` fields. Added `subscription` to `read_only_fields` on 5 bot serializers.
- **`apps/bots/views.py`** — Added `is_staff` gate to IndicatorView/BybitIndicatorView/CustomOrderClosingView/CustomOrderOpeningView. Converted closing/opening views from GET to POST (removed CSRF bypass). Fixed 400→404 for missing credentials. Added `_resolve_webhook_user()` auth to 3 indicator webhook views.
- **`apps/bots/indicators_views.py`** — Replaced silent `ImportError` fallback with `_resolve_webhook_user()`. Added `is_staff` gate. Fixed 400→404 for missing credentials.
- **`apps/bots/urls.py`** — Moved indicator-specific paths (`ema/`, `rsi/`, `bb/`) before router include so they aren't intercepted by the `IndicatorViewSet` catch-all.
- **`apps/bots/management/commands/encrypt_quantum_fund_keys.py`** — New management command to encrypt pre-existing plaintext QuantumAIFund keys. Supports `--dry-run`.
- **`apps/webhooks/views.py`** — Redacted `secret` from logged webhook payload.
- **`apps/exchanges/views.py`** — Added `IsAuthenticated` to ExchangeStatusViewSet. Added write-protection (staff-only CUD) to BlockchainAddressViewSet.
- **`apps/subscriptions/views.py`** — Added `HiddenField(user)`, `read_only_fields` (status, approval fields, amount_paid), and `perform_create(user)` to TelegramSubscriptionViewSet. Added `update()` override with write-once guards for plan and payment proof fields; full update rejection once status leaves `pending_payment`.
- **`apps/trading/engines/bot_engine.py`** — Strips decrypted API keys from `self.config` after adapter init (`pop('api_key')` etc.) to prevent key leakage via tracebacks or TelegramService.
- **`apps/users/models.py`** — Added `webhook_token` UUID field for webhook endpoint authentication.
- **`tests/test_security_fixes_unit.py`** — 44 unit tests covering all fixes (encryption, admin blank guard, webhook auth, permission logic, serializer read-only enforcement).
- **`tests/test_security_fixes.py`** — 31 integration tests (31 pass) covering admin view auth, webhook endpoint auth, subscription protection, bot engine key stripping.

## 2026-05-19: Critical Fixes & Cleanup

- **`services/bot_executor.py`** — Rewrote entirely. Removed `CustomBot`, `trading_manager`, `ExchangeExecutor`. Now uses Celery tasks for start/stop and raw CCXT for signal execution.
- **`apps/bots/admin.py`** — Fixed import path (`services.bot_executor_service` → `services.bot_executor`). Martingale admin now calls `start_martingale_bot()` / `stop_martingale_bot()` instead of grid methods.
- **`apps/bots/indicators_views.py`** — Full rewrite. Removed non-existent `BotExecutionLog` and broken `QuantumAIBot.user` FK. Now uses in-memory `_engine_registry`: webhook → `_get_or_create_engine()` → set indicator → `engine.startBot()`.
- **`apps/bots/views.py`** — Replaced legacy `get_or_create_bot()` (used `trading.manager`) with `get_or_create_engine()` (uses `BotEngine`).
- **`apps/bots/models.py`** — `GridBot.save_state()` no longer imports `trading_manager`. Accepts direct args.
- **`config/urls.py`** — Added `investments` and `referrals` URL includes.

## 2026-05-16: Quantum AI Bot Engine Integration

- **`apps/trading/engines/bot_engine.py`** — Complete rewrite. Direct port from `oldbybit.py` using raw CCXT. All 12 entry cases + 8 exit cases. Grid monitoring via order-ID tracking. SL/TP as background thread.
- **`apps/trading/engines/execution.py`** — Routes `quantum_ai`, `grid`, `martingale` to `engine.startBot()`.
- **`apps/trading/tasks.py`** — Added `quantum_ai` to `_get_bot_instance()`.
- **`apps/trading/exchanges/base_adapter.py`** — Reverted custom wrapper methods (CCXT called directly by engine).

## Earlier Sessions: Architecture Migration

- Renamed `CustomBot` → `SignalBot` across models, serializers, views
- Added `QuantumAIBot` model
- Added `shown_percentage` (5–20%) to `QuantumAIFund`
- Moved bot ViewSets from `apps/payments/` → `apps/bots/`
- Removed `BotConfiguration` and `TradingBot` from `apps/trading/models.py`
- Kept `StrategyConfig` with updated choices (`quantum_ai`, `grid`, `martingale`, `signal`)
- Rewrote `apps/payments/views.py` — payment-only
- Fixed `apps/bots/urls.py` (was importing from `apps.payments`)
- `ExchangeCredentials` consolidated to `apps/exchanges/`, backward-compat import in `apps/trading/`
