# Torgovo — Project Context & Status (Last Updated: 2026-06-21)

## What Is This File
Single source of truth for any AI assistant continuing work on this project. Read this FIRST before touching code.

---

## 1. Project Overview

Subscription-based crypto trading bot platform. Users create bots, connect exchanges, receive TradingView webhook signals, and auto-execute trades via CCXT.

**Stack:** Django 5.x + DRF, PostgreSQL, Celery + Redis, CCXT, Docker  
**Frontend:** React + Vite (separate, not started yet)

---

## 2. Four Bot Types

| Bot | How It Works | Who Manages | Runs Continuously? |
|-----|-------------|-------------|---------------------|
| **SignalBot** | Receives TradingView webhook → executes 1 trade → done | User | No |
| **GridBot** | Places buy/sell at grid levels, auto-manages | User | Yes |
| **MartingaleBot** | Progressive strategy, doubles on loss | User | Yes |
| **QuantumAIBot** | Admin trades pooled user funds, distributes proportional P/L | Admin | Yes |

**Quantum AI Flow:**
1. User deposits USDT → `QuantumDeposit` (pending)
2. Admin approves → updates `QuantumAIInvestment.amount` + `QuantumAIFund.total_deposits`
3. Admin runs `QuantumAIBot` against fund's master API keys
4. Every 2 weeks: calculate P/L × `shown_percentage` (5-20%, admin-configurable), distribute proportionally
5. Users see ONLY their balance + changes — NO trade details

---

## 3. Architecture (Decided)

```
apps/bots/           → Bot domain models + API views (user-facing CRUD)
  models.py          → SignalBot, GridBot, MartingaleBot, QuantumAIFund, QuantumAIBot,
                       QuantumAIInvestment, QuantumDeposit, QuantumWeeklyProfit,
                       PairConfig, Indicator, Order, TelegramSignal*
  views.py           → All bot ViewSets (moved FROM payments)
  serializers.py     → Bot serializers
  urls.py            → Bot API routes
  indicators_views.py → Async indicator webhook views (EMA/RSI/BB)

apps/trading/        → Trading engine (internal, pure Python where possible)
  strategies/        → BaseStrategy, QuantumAI, Grid, Martingale, Signal (pure Python)
  exchanges/         → CCXT adapters: Binance, Bybit, OKX, MEXC, Alpaca (pure Python)
  engines/           → BotEngine, BotExecutor (orchestration)
  models.py          → Exchange, ExchangeCredentials, TradingPair, ExchangeStatus,
                       SupportedBlockchain, ExchangeRate, StrategyConfig
  tasks.py           → Celery async tasks

apps/payments/       → Payment-only views (subscriptions, deposits, withdrawals, admin approval)
apps/exchanges/      → Exchange CRUD (has its own ExchangeCredentials — DUPLICATE, see issues)
apps/investments/    → Quantum AI investment views + serializers
apps/webhooks/       → Webhook receiver endpoints
apps/authentication/ → JWT auth, OAuth, OTP
apps/users/          → User profiles
apps/referrals/      → Referral system
apps/subscriptions/  → Subscription plans

config/              → Django settings (base.py, urls.py)
core/                → Base models (TimeStampedModel, SoftDeleteModel), utils (encryption)
services/            → Service layer (SubscriptionService, BotExecutorService, QuantumAIFundService)
trading/             → OLD legacy code (oldbybit.py manager) — DO NOT MODIFY, reference only
oldbybit.py          → Original Bybit bot code — reference for QuantumAI strategy logic
```

**Key Design Decisions:**
- **Adapter pattern** for exchanges (`get_adapter()` factory)
- **Strategy pattern** for trading logic (`get_strategy()` factory)
- **Engine accepts plain dict config**, NOT Django models — keeps strategies/adapters pure Python
- **StrategyConfig stays as a model** — provides default presets per strategy type (user can override)
- **UUID primary keys** everywhere
- **SoftDeleteModel** base for all domain models
- **API keys encrypted** via Fernet (`core/utils.py`) — shared `looks_encrypted()` guard prevents double-encryption
- **Admin key fields** — `PasswordInput(render_value=False)`, `required=False`, `save_model()` restores blank→existing
- **Webhook indicator auth** — `X-Webhook-Token` header validated against `user.webhook_token` (UUID)

---

## 4. Security Audit (2026-06-21) — 15 Vulnerabilities Fixed

### 🔒 Encryption & Key Management
| # | Vulnerability | Severity | Fix |
|---|---------------|----------|-----|
| 1 | QuantumAIFund master API keys stored in plain TextField — no encryption enforcement. Admin form showed keys as `<input type="text">`. | **CRITICAL** | `save()` override with `looks_encrypted()` guard; `get_decrypted_credentials()`; custom admin form with `PasswordInput(render_value=False)` widgets; fieldset description warning |
| 2 | `FERNET_KEY` had placeholder default (`your-encryption-key-32-chars-long!`) — all exchange API keys decryptable if `.env` unset | **CRITICAL** | Made required with format validation in production settings |
| 3 | `looks_encrypted()` logic duplicated across ExchangeCredentials, QuantumAIFund, and management command with inconsistent empty-value handling | **MEDIUM** | Extracted to `core/utils.py` as single source of truth; skips empty/None values (returns True) |
| 4 | No management command to encrypt pre-existing plaintext keys | **MEDIUM** | Created `encrypt_quantum_fund_keys` mgmt command with `--dry-run` |

### 🔐 Authentication & Authorization
| # | Vulnerability | Severity | Fix |
|---|---------------|----------|-----|
| 5 | ExchangeStatusViewSet — no authentication, anyone could read status | **HIGH** | Added `permission_classes = [IsAuthenticated]` |
| 6 | BlockchainAddressViewSet — any authenticated user could create/delete addresses | **HIGH** | `get_permissions()` — read for all, write for staff only |
| 7 | IndicatorView / BybitIndicatorView / CustomOrderClosingView / CustomOrderOpeningView — no auth, any user could see any user's data and open/close orders | **CRITICAL** | Added `is_staff` check to each view |
| 8 | CustomOrderClosingView / CustomOrderOpeningView — state-changing operations via GET with `csrf_exempt` | **HIGH** | Converted from `get()` to `post()`; removed `csrf_exempt` from ClosingView |
| 9 | Webhook indicator views (EMA/RSI/BB) — no auth, anyone could POST indicator values and influence any user's bot | **HIGH** | Added `_resolve_webhook_user()` validating `X-Webhook-Token` header against `user.webhook_token` |
| 10 | Indicator webhook URLs placed after DRF router — router's `indicators/{pk}` intercepted webhook POSTs | **HIGH** | Moved specific paths BEFORE router include in `apps/bots/urls.py` |

### 🛡️ Data Protection
| # | Vulnerability | Severity | Fix |
|---|---------------|----------|-----|
| 11 | Webhook `secret` logged in plaintext | **CRITICAL** | Redacted before logging (`{k: v ... if k != 'secret'}`) |
| 12 | Decrypted API keys persisted in `BotEngine.config` for bot lifetime — leaked via tracebacks and TelegramService | **HIGH** | Stripped from `self.config` after adapter init (`pop('api_key', None)` etc.) |
| 13 | `subscription` FK writable on 5 bot serializers — user could hijack another's subscription | **HIGH** | Added to `read_only_fields` on all 5 serializers |
| 14 | QuantumAIFundSerializer — master API keys exposed in API responses | **MEDIUM** | Removed from `Meta.fields` — keys only accessible via Django admin |
| 15 | TelegramSubscriptionViewSet — no `perform_create`, `fields = '__all__'`, no user enforcement | **HIGH** | Added `HiddenField(user)`, `read_only_fields`, `perform_create` with `user=self.request.user` |

### ✅ Completed This Session
| Change | Files |
|--------|-------|
| QuantumAIFund encryption (model + admin + serializer) | `apps/bots/models.py`, `admin.py`, `serializers.py` |
| `looks_encrypted()` extracted to `core/utils.py` | `core/utils.py`, `apps/bots/models.py`, `apps/exchanges/models.py` |
| Admin view auth (is_staff gate, GET→POST, csrf_exempt removed) | `apps/bots/views.py` |
| Webhook indicator auth + URL ordering fix | `apps/bots/indicators_views.py`, `views.py`, `urls.py` |
| Webhook secret redaction | `apps/webhooks/views.py` |
| Exchange/Blockchain view auth | `apps/exchanges/views.py` |
| Subscription write-once + user enforcement | `apps/subscriptions/views.py` |
| Bot engine key stripping | `apps/trading/engines/bot_engine.py` |
| `webhook_token` field on CustomUser | `apps/users/models.py`, migration 0005 |
| Encrypt management command | `apps/bots/management/commands/encrypt_quantum_fund_keys.py` |
| Comments added to all modified files | Docstrings, inline comments, key-rotation warning |
| Tests — 44 unit + 31 integration (75 pass) | `tests/test_security_fixes_unit.py`, `tests/test_security_fixes.py` |

### ⚠️ Remaining Security Gaps (Not Fixed)
| Item | Severity | Details |
|------|----------|---------|
| 10 `exc_info=True` logging calls in credential scope | **HIGH** | Decrypted API keys in traceback locals — need removal or sanitization |
| 17 bare `except:` blocks (5 dangerous) | **HIGH** | Catch `KeyboardInterrupt`/`SystemExit` — should be `except Exception:` |
| HMAC webhook validation function exists but never called | **HIGH** | Webhook verification uses DB lookup instead of constant-time HMAC |
| No 2FA (`two_factor_enabled` field exists, no flow) | **HIGH** | Trading platform handling user funds with no 2FA |
| `.env` FERNET_KEY is invalid 41-char ASCII (not valid base64 Fernet key) | **HIGH** | Will crash at runtime on first encrypt/decrypt |
| No rate limiting on password-reset email sending | **MEDIUM** | Could be abused for account enumeration / spam |

---

## 5. Previous Session (2026-05-19): Architecture Cleanup

### ✅ Completed
| Change | Files Modified |
|--------|---------------|
| Added `drf_yasg` to `THIRD_PARTY_APPS` | `config/settings/base.py` |
| Fixed Celery task import | `apps/trading/tasks.py` |
| Renamed `CustomBot` → `SignalBot` | `apps/bots/models.py`, `serializers.py`, `views.py` |
| Added `QuantumAIBot` model | `apps/bots/models.py` |
| Moved bot ViewSets from payments → bots | Both files rewritten |
| Removed `BotConfiguration` and `TradingBot` | `apps/trading/models.py` |
| Rewrote `apps/payments/views.py` | Payment-only |
| Renamed `Order.custom_bot` FK → `Order.signal_bot` | `apps/bots/models.py` |

### ⚠️ Interrupted / NOT Completed
| Item | Status | Details |
|------|--------|---------|
| `apps/trading/serializers.py` still imports `BotConfiguration` | **BROKEN** | Needs removal |
| `apps/trading/views.py` has `BotBridge` import | **BROKEN** | Stale code |
| `bot_engine.py` calls non-existent methods | **BROKEN** | Needs `from_config()` with dict |
| `BotExecutor` rework to accept plain dict | **NOT DONE** | References deleted `TradingBot` |
| `apps/bots/admin.py` references `CustomBot` | **STALE** | Needs rename |
| `apps/webhooks/views.py` `CustomBotWebhookView` | **STALE** | Needs rename |

---

## 6. Remaining Issues

### P0 — Launch Blockers (Security)
1. **10 `exc_info=True` logging calls in credential scope** — Decrypted API keys in traceback locals. Remove or sanitize.
2. **HMAC webhook validation function exists but is never called** — Webhook verification relies on DB lookup instead of constant-time HMAC comparison. Wire it in.
3. **`.env` FERNET_KEY is invalid 41-char ASCII string** — Not valid base64 Fernet key. Will crash at runtime on first encrypt/decrypt. Generate a real key.
4. **No CI/CD pipeline** — No automated test runner in CI. Pytest exists (1727 tests) but never runs outside dev.

### P0 — Launch Blockers (Infrastructure)
5. **Frontend is a skeleton** — Only `App.jsx`, `main.jsx`, and `AuthContext.jsx` exist. No page components, no build pipeline. Platform has no UI for end users.

### P1 — Critical (Will crash at runtime)
6. **`apps/trading/serializers.py`** — imports deleted `BotConfiguration` model
7. **`apps/trading/views.py`** — `BotConfigurationViewSet` references deleted model + `BotBridge` import broken
8. **`apps/trading/admin.py`** — `BotConfigurationAdmin` references deleted model
9. **`apps/trading/engines/bot_engine.py`** — calls 2 non-existent methods
10. **`apps/trading/engines/execution.py`** — `BotExecutor.from_config()` references deleted `TradingBot`/`StrategyConfig`

### P1 — High Risk
11. **17 bare `except:` blocks (5 dangerous)** — Catch `KeyboardInterrupt`/`SystemExit`. Change to `except Exception:`.
12. **No 2FA** — `two_factor_enabled` field exists on model but no 2FA flow. Trading platform with user funds.
13. **Duplicate `ExchangeCredentials`** — Exists in both `apps/trading/models.py` and `apps/exchanges/models.py`. Pick one canonical location.

### P2 — Moderate
14. **`apps/webhooks/views.py`** — references `CustomBot`, needs `SignalBot`
15. **`apps/bots/admin.py`** — references `CustomBot`, needs `SignalBot`
16. **OKX/MEXC/Alpaca adapters** — minimal implementations (47, 75, 52 lines), only Binance/Bybit complete
17. **Placeholder data** — `get_exchange_rates()` returns hardcoded prices
18. **`services/` directory** — references need verification
19. **No rate limiting on password-reset email sending** — Account enumeration vector

### P3 — Future Work
20. Bot start/stop integration with `BotExecutor` service
21. Celery Beat scheduling for bot monitoring
22. Complete webhook flow (signal → validate → execute → log)
23. Quantum AI profit distribution Celery task
24. Admin dashboard endpoints
25. Frontend (React + Vite)
26. Tests (80%+ coverage target)
27. API versioning (`/api/v1/`)
28. Wire up drf-yasg or drf-spectacular for live API docs
29. Add structured logging (structlog is already a dependency)
30. Prometheus metrics endpoint
31. Database migration testing in CI

### ⚠️ Documented Risks (Accepted)
- **FERNET_KEY rotation hazard**: `looks_encrypted()` decrypts under current key. Rotating the key will cause double-encryption → garbage. Never rotate without a dedicated re-encryption migration.
- **Key-rotation landmine**: Same risk applies to `ExchangeCredentials` and `QuantumAIFund` encryption. Documented in `core/utils.py` docstring.
- **Duplicate Telegram models**: `apps.bots` has `TelegramSignalSubscription`; `apps.subscriptions` has `TelegramSubscription`. Two different models at two different URLs (`api/bots/telegram-subscriptions/` and `api/subscriptions/subscriptions/`). Both are live and both are protected. The `subscriptions` versions may overlap with bots versions — worth auditing for consolidation.

---

## 7. Solution for BotExecutor Rework

The engine currently tries to load `TradingBot` and `StrategyConfig` models. Since we removed `TradingBot`, the engine should work with plain dicts:

```python
# How views should call the engine:
config = {
    'bot_id': str(grid_bot.id),
    'bot_type': 'grid',
    'strategy': 'grid',
    'exchange_name': grid_bot.exchange_name,
    'trading_pair': grid_bot.trading_pair,
    'api_key': decrypt(credentials.api_key),
    'secret_key': decrypt(credentials.secret_key),
    'parameters': {
        'favor_levels': grid_bot.favor_levels,
        'against_levels': grid_bot.against_levels,
        ...
    }
}
executor = BotExecutor.from_config(config)
executor.run()
```

`StrategyConfig` stays in DB for default presets. When building the config dict, merge:  
`defaults from StrategyConfig` → `overrides from bot model fields` → `final config dict`

---

## 7. Rules for AI Assistants

### Workflow
- For ANY non-trivial task (3+ steps): enter plan mode, get approval first
- If something goes sideways: STOP and re-plan, don't keep pushing
- After ANY correction from user: update lessons learned
- Never mark a task complete without proving it works

### Code Standards
- Keep `apps/trading/strategies/` and `apps/trading/exchanges/` as pure Python (no Django imports)
- Engine accepts plain dict configs, NOT Django model instances
- All models use UUID PKs via `SoftDeleteModel` or `TimeStampedModel` from `core/`
- API keys encrypted using Fernet (`core/utils.py`)
- Use factory functions (`get_adapter()`, `get_strategy()`) for dependency injection
- Bot ViewSets live in `apps/bots/views.py`, payment views in `apps/payments/views.py`
- Old code in `trading/` and `oldbybit.py` is reference-only — DO NOT MODIFY

### What NOT to Do
- Don't merge `StrategyConfig` into bot models — user wants it separate
- Don't create new Django models for engine runtime state — use dicts
- Don't put bot views in `apps/payments/`
- Don't remove `oldbybit.py` or the `trading/` legacy directory
- Don't implement actual CCXT trade execution — leave as `# TODO: Implement CCXT trade execution`
