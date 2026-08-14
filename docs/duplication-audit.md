# Torgovo2 — Cross-App Structural Duplication Audit

> **Generated:** 2026-07-24
> **Scope:** All 8 Django apps (`bots`, `trading`, `exchanges`, `investments`, `users`, `authentication`, `payments`, `webhooks`)
> **Status:** Approved for execution. 4 phases, 4 separate commits/PRs in phase order, run full test suite after each phase.

---

## Table of Contents

1. [Project Context](#1-project-context)
2. [Overview of Findings](#2-overview-of-findings)
3. [Duplicate App: exchanges ↔ trading](#3-duplicate-app-exchanges--trading)
4. [Competing Indicator Endpoints (4 pipelines, 14 endpoints)](#4-competing-indicator-endpoints)
5. [UserProfile vs CustomUser](#5-userprofile-vs-customuser)
6. [Two UserBalance Models](#6-two-userbalance-models)
7. [Two Order Models](#7-two-order-models)
8. [Two Deposit Models](#8-two-deposit-models)
9. [Exchange Choices (5+ locations)](#9-exchange-choices-5-locations)
10. [Admin-Editable Plan Limits (Phase 0)](#10-admin-editable-plan-limits-phase-0)
11. [Implementation Phases](#11-implementation-phases)
12. [Full Audit Trail](#12-full-audit-trail)

---

## 1. Project Context

### Tech Stack
- **Framework:** Django 5.x + Django REST Framework 3.15
- **Database:** PostgreSQL
- **Async:** Celery + Redis
- **Exchange API:** CCXT
- **Auth:** JWT (SimpleJWT)
- **Encryption:** Fernet (symmetric, for API keys)

### App Architecture at a Glance

| App | Primary Purpose |
|-----|----------------|
| `apps/bots/` | Bot models (SignalBot, GridBot, MartingaleBot, QuantumAIBot), views, serializers, indicator webhook views, legacy Order/PairConfig/Indicator |
| `apps/trading/` | **Unified** trading API — Exchange CRUD, ExchangeCredentials, TradingPair, StrategyConfig. Also houses the trading engine (`engines/`, `strategies/`, `exchanges/`) |
| `apps/exchanges/` | **Legacy** exchange CRUD — ExchangeCredentials, TradingPair, ExchangeStatus, BlockchainAddress views (marked "will be removed" in `config/urls.py`) |
| `apps/investments/` | Portfolio display — modern Order, Position, TechnicalIndicator, UserBalance, ExchangeRate |
| `apps/users/` | CustomUser model + per-currency UserBalance |
| `apps/authentication/` | JWT auth, OTP, UserProfile (extends CustomUser — but mostly duplicates fields) |
| `apps/payments/` | Subscription plans, deposits (QuantumAIDeposit), BlockchainAddress, WithdrawalRequest, BotSubscription, ReferralPayout |
| `apps/webhooks/` | Webhook receiver — signal bot webhook + indicator GET calculators |

### Key Design Decisions
- UUID primary keys on all domain models (except `users.UserBalance` which uses BigAutoField)
- `SoftDeleteModel` base class for all domain models
- API keys encrypted at rest via Fernet (`core/utils.py`)
- `apps/trading/models.py` re-exports `Exchange`, `ExchangeCredentials`, `TradingPair` from `apps.exchanges.models`
- `config/urls.py` registers both `api/trading/` and `api/exchanges/`, with a comment on the latter: "Legacy, will be removed"

---

## 2. Overview of Findings

| # | Duplication | Severity | Apps Involved | Recommendation |
|---|-------------|----------|---------------|----------------|
| — | Missing: admin-editable plan limits | — | `users` ↔ `authentication` | **Phase 0:** Add `SiteConfig` model with `plan_limits` JSONField (3/10/25/100 fallback) |
| 1 | Exchange CRUD views/serializers/URLs | High | `exchanges` ↔ `trading` | **Phase 2:** Remove `exchanges/` views/URLs, merge `BlockchainAddressViewSet` into `trading/` |
| 2 | Competing indicator endpoints (14 views, 4 pipelines) | High | `bots` ×2, `investments` ×2, `webhooks` | **Phase 2:** Delete superseded + liability endpoints, keep two canonical pipelines |
| 3 | UserProfile fully duplicates CustomUser fields | Medium | `authentication` ↔ `users` | **Phase 3:** Delete `UserProfile` + table (resolved by Phase 0 plan limits) |
| 4 | Two UserBalance models (different scope) | Low | `users` ↔ `investments` | **Phase 1:** Rename `investments.UserBalance` → `InvestmentBalance` (RenameModel only, no SQL) |
| 5 | Two Order models (different eras, different purpose) | Low | `bots` ↔ `investments` | **Phase 1:** Rename `bots.Order` → `BotOrder` (RenameModel only, no SQL) |
| 6 | Two deposit models (different features) | Low | `payments` ↔ `bots` | Keep `payments.QuantumAIDeposit`, deprecate `bots.QuantumDeposit` (no active work needed) |
| 7 | Exchange choices in 5+ locations | Medium | Cross-cutting | **Phase 4:** Centralize to `apps.exchanges.models.ExchangeCredentials.EXCHANGE_CHOICES` |

---

## 3. Duplicate App: exchanges ↔ trading

### What's Duplicated

**`config/urls.py:32-33`:**
```python
path('api/trading/', include('apps.trading.urls', namespace='trading')),     # New unified API
path('api/exchanges/', include('apps.exchanges.urls', namespace='exchanges')),  # Legacy, will be removed
```

Both register nearly identical views:

| Route | `trading/urls.py` | `exchanges/urls.py` |
|-------|-------------------|---------------------|
| `credentials/` | ExchangeCredentialsViewSet | ExchangeCredentialsViewSet |
| `pairs/` / `supported-pairs/` | TradingPairViewSet | TradingPairViewSet |
| `status/` | ExchangeStatusViewSet | ExchangeStatusViewSet |
| `list/` | `list_exchanges()` function | `list_exchanges()` function |
| `<name>/symbols/` | `get_exchange_symbols()` function | `get_exchange_symbols()` function |
| `rates/` | `get_exchange_rates()` function | `get_exchange_rates()` function |
| `strategy-configs/` | StrategyConfigViewSet **(unique)** | — |
| `blockchain-addresses/` | — | BlockchainAddressViewSet **(unique)** |

**Models are already consolidated** — `trading/models.py` re-exports from `exchanges.models`:
```python
from apps.exchanges.models import Exchange          # noqa
from apps.exchanges.models import ExchangeCredentials  # noqa
from apps.exchanges.models import TradingPair         # noqa
```

The only unique model in `trading/` is `StrategyConfig` (strategy presets).

### Action: Keep `trading/`, remove `exchanges/` view layer
1. Move `BlockchainAddressViewSet` + `BlockchainAddressSerializer` → `trading/`
2. Add `blockchain-addresses/` route to `trading/urls.py`
3. Delete `apps/exchanges/views.py`, `apps/exchanges/serializers.py`, `apps/exchanges/urls.py`
4. Remove `path('api/exchanges/', ...)` from `config/urls.py`
5. **Keep** `apps/exchanges/models.py` and `apps/exchanges/admin.py`

---

## 4. Competing Indicator Endpoints

### What was originally flagged
The original audit compared route tables across 3 apps (`bots` ×1 pipeline + `investments` + `webhooks`) and found 9 views. But `bots/` itself has **two** parallel indicator pipelines. The real count is **14 views across 4 pipelines**:

### Pipeline 1: `bots/indicators_views.py` — Engine trigger (CANONICAL)

| # | Path | View | Method | Auth | What It Does |
|---|------|------|--------|------|-------------|
| 1 | `bots/indicators/ema/` | `EMAIndicatorView` | POST async | X-Webhook-Token | Sets `engine.EMA`, saves to `Indicator`, calls `engine.startBot()` |
| 2 | `bots/indicators/rsi/` | `RSIIndicatorView` | POST async | X-Webhook-Token | Sets `engine.RSI`/`PrevRSI`/colors, saves, calls `startBot()` |
| 3 | `bots/indicators/bb/` | `BollingerBandsView` | POST async | X-Webhook-Token | Sets `engine.BB`, saves, calls `startBot()` |

**Verdict: KEEP.** These are the canonical engine pipeline with proper token-based auth.

### Pipeline 2: `bots/views.py` — Legacy admin views (SUPERSEDED)

| # | Path | View | Method | Auth | What It Does |
|---|------|------|--------|------|-------------|
| 4 | `bots/indicators/binance/<user>/<pair>/` | `IndicatorView` | POST | staff | URL-path user resolution, legacy indicator pipeline |
| 5 | `bots/indicators/bybit/<user>/<pair>/` | `BybitIndicatorView` | POST | staff | Same pattern |
| 6 | `bots/indicators/close/<user>/<pair>/` | `CustomOrderClosingView` | POST | staff | Legacy order closing |
| 7 | `bots/indicators/open/<user>/<pair>/<side>/` | `CustomOrderOpeningView` | POST | staff | Legacy order opening |

**Verdict: DELETE.** Superseded by Pipeline 1 which does the same job with strictly better auth (token-based instead of URL-path user resolution). Security audit already hardened these (section 3 of `test_security_fixes.py`), but they're dead code walking. Also covered by `bots/urls.py`:19 DRF router's `IndicatorViewSet` (read-only CRUD for `bots.Indicator` model) — keep that one.

### Pipeline 3: `investments/views.py` — Portfolio data storage (DISTINCT PURPOSE)

| # | Path | View | Method | Auth | What It Does |
|---|------|------|--------|------|-------------|
| 8 | `investments/indicators/ema/` | `EMAWebhookView` | POST | `IsAdminUser` | Stores EMA in `TechnicalIndicator`, returns success |
| 9 | `investments/indicators/rsi/` | `RSIWebhookView` | POST | `IsAdminUser` | Stores RSI in `TechnicalIndicator`, returns success |
| 10 | `investments/indicators/ema/manual/` | `EMAIndicatorView` | POST | `IsAdminUser` | Returns: "Use webhooks for automated signals" |
| 11 | `investments/indicators/rsi/manual/` | `RSIIndicatorView` | POST | `IsAdminUser` | Returns: "Use webhooks for automated signals" |

**Items 8-9 verdict: KEEP.** Admin-gated, tested on both write and read paths (`tests/investments/test_views.py:227/262`), stores data consumed by `TechnicalIndicatorViewSet`. Different purpose from Pipeline 1 (display data, not engine trigger). Low risk, no security exposure.

**Items 10-11 verdict: DELETE.** Dead code returning placeholder text. Also delete `TestIndicatorManualViews` at `tests/investments/test_views.py:328`.

### Pipeline 4: `webhooks/views.py` — Public GET calculators (LIABILITY)

| # | Path | View | Method | Auth | What It Does |
|---|------|------|--------|------|-------------|
| 12 | `webhooks/custombot/indicators/ema/` | `EMAIndicatorView` | GET | `AllowAny` | Calls CCXT OHLCV → computes EMA → returns value |
| 13 | `webhooks/custombot/indicators/rsi/` | `RSIIndicatorView` | GET | `AllowAny` | Calls CCXT OHLCV → computes RSI → returns value |

**Verdict: DELETE.** These are:
- Fully implemented (real EMA/RSI math over CCXT)
- But **`AllowAny`** with no rate limiting, no caching, no tests
- Each request calls a live exchange API — trivial DoS/cost-exhaustion vector
- No confirmed product need (no frontend consumer)
- No tests exist for these endpoints
- Not covered by the security audit

If a public indicator-calculator API is ever on the roadmap, it should come back as a deliberately scoped feature (auth strategy, rate limit, caching layer, tests).

### Net Result: 14 → 9 endpoints

| Pipeline | Before | After |
|----------|--------|-------|
| 1: `bots/indicators_views.py` (engine trigger) | 3 | **3 — keep** |
| 2: `bots/views.py` legacy (superseded) | 4 | **0 — delete** |
| 3a: `investments/` webhooks (data storage) | 2 | **2 — keep** |
| 3b: `investments/` manual stubs (dead code) | 2 | **0 — delete** |
| 4: `webhooks/` calculators (liability) | 2 | **0 — delete** |
| `bots/` DRF IndicatorViewSet | 1 | **1 — keep** |
| **Total** | **14** | **6** |

---

## 5. UserProfile vs CustomUser

### What's Duplicated

Both models carry identical fields:
```
subscription_plan, max_bots_allowed, timezone, total_trades_executed,
total_volume_traded, referral_code, referred_by, demo_trading_enabled,
email_notifications, sms_notifications, push_notifications
```

**UserProfile** (`authentication/models.py`) also has `api_keys_encrypted = JSONField()` — superseded by `exchanges.ExchangeCredentials`.

**`save()` methods disagree on values:**
```python
# CustomUser.save()
plan_limits = {'free': 3, 'basic': 10, 'premium': 999999, 'enterprise': 999999}

# UserProfile.update_bot_limits()
limits = {'free': 3, 'basic': 5, 'premium': 15, 'enterprise': 50}
```

### Action: Phase 0 + Phase 3

- **Phase 0:** Add `SiteConfig` with `plan_limits` JSONField (fallback: `{free:3, basic:10, premium:25, enterprise:100}`). `CustomUser.save()` reads from `SiteConfig` with fallback.
- **Phase 3:** Delete `UserProfile` model + `auth_user_profiles` table. Grep for `UserProfile`, `user.profile`, `user_profile` across entire project and migrate references to `CustomUser` fields. Delete `UserProfile.update_bot_limits()` (redundant since `CustomUser.save()` handles it).

---

## 6. Two UserBalance Models

| Aspect | `users.UserBalance` | `investments.UserBalance` |
|--------|---------------------|---------------------------|
| File | `apps/users/models.py:246` | `apps/investments/models.py:255` |
| Table | `users_balances` | `investments_user_balance` |
| Scope | Per user + per currency | Per user + per exchange + per currency |
| PK | BigAutoField | UUID (TimeStampedModel) |
| Fields | `currency`, `available`, `hold` | `exchange` FK, `currency`, `available`, `locked`, `total` |
| Unique | `(user, currency)` | `(user, exchange, currency)` |

**Verdict: Genuinely separate models, rename for disambiguation.**

- `users.UserBalance` = simple wallet (one row per currency across all exchanges)
- `investments.UserBalance` = per-exchange balance tracking
- Different schema, different PK, different unique constraints, different purposes

**Action (Phase 1):** `RenameModel` only. `investments.UserBalance` → `InvestmentBalance`. DB table stays `investments_user_balance` (pinned in Meta). Zero SQL.

---

## 7. Two Order Models

| Aspect | `bots.Order` | `investments.Order` |
|--------|-------------|---------------------|
| File | `apps/bots/models.py:957` | `apps/investments/models.py:136` |
| Table | `bots_orders` | `investments_order` |
| FK targets | `PairConfig`, `Indicator`, `SignalBot`, `GridBot`, `MartingaleBot`, `QuantumAIInvestment` | `Exchange`, `TradingPair` |
| Unique fields | `Category`, `Exchange` (CharField), `Details` (JSON), `Time`, `Pair` | `filled_quantity`, `average_price`, `status` (choices), `profit_loss`, `executed_at` |
| Convention | CamelCase | snake_case |
| `user` FK | Nullable | Required |
| Purpose | Bot execution history | Portfolio/display order |

**Verdict: Genuinely separate models, rename for disambiguation.**

Same class name, different schema, different FKs, different purpose — identical pattern to the indicator views. No consolidation work, no data merging, no complexity.

**Action (Phase 1):** `RenameModel` only. `bots.Order` → `BotOrder`. DB table stays `bots_orders` (pinned in Meta). Zero SQL.

---

## 8. Two Deposit Models

| Aspect | `payments.QuantumAIDeposit` | `bots.QuantumDeposit` |
|--------|---------------------------|----------------------|
| Table | `payments_quantum_deposits` | `bots_quantum_deposits` |
| Risk scoring | ✅ `risk_score` (0-100), `flagged_for_review` | ❌ None |
| Expiry | ✅ 48-hour auto-expiry (`is_expired()`) | ❌ None |
| Attachments | ✅ `transaction_screenshot`, `transaction_proof` | ✅ `screenshot` |
| Verification | ✅ `verified_by`, `verified_at`, `verification_method` | ✅ `reviewed_by`, `reviewed_at` |
| Audit | ✅ Creates `AuditLog` on approve/reject | ❌ None |

**Verdict:** Keep `payments.QuantumAIDeposit` (fully featured). Deprecate `bots.QuantumDeposit` — mark with a comment, leave data in place. No active development.

---

## 9. Exchange Choices (5+ Locations)

### Locations Found
1. **`apps/bots/models.py:15`** — Top-level `EXCHANGE_CHOICES` constant used by 4 bot models
2. **`apps/exchanges/models.py:46`** — `ExchangeCredentials.EXCHANGE_CHOICES`
3. **`apps/payments/models.py:492`** — Imports from `ExchangeCredentials.EXCHANGE_CHOICES` (already correct)
4. Various views with inline `if exchange_name not in ['binance', 'bybit', ...]` checks

**Action (Phase 4):** Replace each with:
```python
from apps.exchanges.models import ExchangeCredentials
EXCHANGE_CHOICES = ExchangeCredentials.EXCHANGE_CHOICES
```

---

## 10. Admin-Editable Plan Limits (Phase 0)

### Problem
`CustomUser.save()` and `UserProfile.update_bot_limits()` hardcode different bot-count limits, creating a sync bug.

### Solution: `core/models.py` — SiteConfig singleton

```python
from django.db import models

class SiteConfig(models.Model):
    """Singleton for admin-editable site-wide configuration."""
    plan_limits = models.JSONField(
        default=dict,
        help_text="Bot limits per plan, e.g. {'free': 3, 'basic': 10, 'premium': 25, 'enterprise': 100}"
    )

    class Meta:
        verbose_name = "Site Configuration"
        verbose_name_plural = "Site Configuration"

    def __str__(self):
        return "Site Configuration"
```

**`core/admin.py`:**
```python
from django.contrib import admin
from .models import SiteConfig

@admin.register(SiteConfig)
class SiteConfigAdmin(admin.ModelAdmin):
    pass
```

**`CustomUser.save()` update:**
```python
def save(self, *args, **kwargs):
    from core.models import SiteConfig

    config = SiteConfig.objects.first()
    overrides = config.plan_limits if config else {}

    plan_limits = {
        'free': 3,
        'basic': 10,
        'premium': 25,
        'enterprise': 100,
        **overrides,  # admin overrides win
    }
    self.max_bots_allowed = plan_limits.get(self.subscription_plan, 3)
    super().save(*args, **kwargs)
```

### Migration
- One migration: `core/migrations/0001_initial.py` — creates `core_siteconfig` table
- Seed data: create one `SiteConfig` row with empty `plan_limits` dict (falls back to defaults)

### Why Admin-Editable vs Hardcoded
- Limits change as you scale (promotions, enterprise tiers, seasonal offers)
- A JSONField in a singleton avoids: (a) redeploying for limit changes, (b) adding a full `django-constance` dependency, (c) env var complexity
- Read from DB once per `save()` — negligible overhead for an admin-only operation

---

## 11. Implementation Phases

### Execution Order
> **IMPORTANT:** Land these as **four separate commits/PRs in phase order**. Run the full test suite after each phase. Bisectable history is what lets you isolate which phase introduced a regression if the test suite catches something after Phase 1 that only surfaces in Phase 3's grep sweep.

---

### Phase 0 — Admin-Editable Plan Limits

**Files to create:**
- [ ] `core/models.py` — `SiteConfig` model with `plan_limits = JSONField(default=dict)`
- [ ] `core/admin.py` — `SiteConfigAdmin` registration
- [ ] `core/migrations/0001_initial.py` — create `core_siteconfig` table
- [ ] Data migration or seed script to create one `SiteConfig` row

**Files to modify:**
- [ ] `apps/users/models.py:203` — update `CustomUser.save()` to read from `SiteConfig` with fallback

**Files to delete/revert:**
- (None yet — UserProfile still exists, but its `update_bot_limits()` is superseded)

**Test update:**
- [ ] Add or update tests for `CustomUser.save()` limits (verify fallback works, verify override works)

**Verify:**
```bash
python manage.py makemigrations core
python manage.py migrate
python -m pytest apps/users/tests/ -v --nomigrations
```

---

### Phase 1 — Safe Renames (RenameModel only, no SQL)

> **⚠️ CRITICAL WARNING FOR `makemigrations`:** When Django detects the model rename, it will prompt interactively — *"Did you rename bots.Order to bots.BotOrder? [y/N]"*. The answer must be **yes**. If someone runs `makemigrations --noinput` or answers wrong, Django will generate a `DeleteModel` + `CreateModel` pair instead of `RenameModel`, which (combined with the pinned `db_table`) would try to drop and recreate `bots_orders` for real. `RenameModel` is also what triggers Django's contenttypes app to update the existing `ContentType` row in place rather than orphaning it — so permissions and admin-log references stay intact automatically, but only if the migration is genuinely a `RenameModel` operation.
>
> **Add this one-line comment to each generated migration file:**
> ```python
> # Generated as RenameModel — do not regenerate non-interactively
> ```

**No `AlterModelTable` needed** — both models already have pinned `db_table` in `Meta`:
- `bots.Order`: `db_table = 'bots_orders'` → stays `bots_orders`
- `investments.UserBalance`: `db_table = 'investments_user_balance'` → stays `investments_user_balance`

The rename generates **zero SQL on PostgreSQL** — purely Django state migration.

**Grep targets (update every import/reference):**

For `Order` → `BotOrder` in `apps/bots/`:
- [ ] `apps/bots/models.py` — class rename
- [ ] `apps/bots/serializers.py` — import + serializer Meta.model
- [ ] `apps/bots/views.py` — import + queryset reference
- [ ] `apps/bots/admin.py` — admin registration
- [ ] `apps/bots/urls.py` — router registration (if model name appears in URL)
- [ ] `apps/bots/tasks.py` — any Celery task referencing Order
- [ ] `apps/webhooks/views.py` — imports it? (check: it uses `bots/models.py` imports)
- [ ] `tests/bots/test_views.py` — test references
- [ ] Any other file importing `from apps.bots.models import Order`

For `UserBalance` → `InvestmentBalance` in `apps/investments/`:
- [ ] `apps/investments/models.py` — class rename
- [ ] `apps/investments/serializers.py` — import + serializer Meta.model
- [ ] `apps/investments/views.py` — import + viewset queryset
- [ ] `apps/investments/admin.py` — if registered
- [ ] `apps/investments/urls.py` — if basename references model name
- [ ] `tests/investments/test_views.py` — fixture references (line 112: `UserBalance.objects.create(...)`)
- [ ] Any other file importing `from apps.investments.models import UserBalance`

**Verify:**
```bash
python manage.py makemigrations bots investments
# Answer YES to the RenameModel prompts
python manage.py migrate
python -m pytest apps/bots/tests/ apps/investments/tests/ -v --nomigrations
```

---

### Phase 2 — Route & View Consolidation

#### 2a. Delete manual stub views (investments/)

**Files to modify:**
- [ ] `apps/investments/views.py` — delete `EMAIndicatorView` class (line 285), `RSIIndicatorView` class (line 296)

**Files to modify (URLs):**
- [ ] `apps/investments/urls.py` — remove:
  ```python
  path('indicators/ema/manual/', views.EMAIndicatorView.as_view(), name='ema-indicator'),
  path('indicators/rsi/manual/', views.RSIIndicatorView.as_view(), name='rsi-indicator'),
  ```

**Files to delete/modify (tests):**
- [ ] `tests/investments/test_views.py` — delete `TestIndicatorManualViews` class (lines 328-337)

#### 2b. Delete webhooks calculator views

**Files to modify:**
- [ ] `apps/webhooks/views.py` — delete `EMAIndicatorView` class (line 414), `RSIIndicatorView` class (line 486)

**Files to modify (URLs):**
- [ ] `apps/webhooks/urls.py` — remove:
  ```python
  path('indicators/ema/', views.EMAIndicatorView.as_view(), name='ema_indicator'),
  path('indicators/rsi/', views.RSIIndicatorView.as_view(), name='rsi_indicator'),
  ```

#### 2c. Delete legacy bots/views.py indicator endpoints

**Files to modify:**
- [ ] `apps/bots/views.py` — delete classes: `IndicatorView` (line 410), `BybitIndicatorView` (line 455), `CustomOrderClosingView` (line 501), `CustomOrderOpeningView` (line 527)

**Files to modify (URLs):**
- [ ] `apps/bots/urls.py` — remove:
  ```python
  path('indicators/binance/<str:username>/<str:pair>/', views.IndicatorView.as_view(), ...),
  path('indicators/bybit/<str:username>/<str:pair>/', views.BybitIndicatorView.as_view(), ...),
  path('indicators/close/<str:username>/<str:pair>/', views.CustomOrderClosingView.as_view(), ...),
  path('indicators/open/<str:username>/<str:pair>/<str:side>/', views.CustomOrderOpeningView.as_view(), ...),
  ```

**Files to delete/modify (tests):**
- [ ] `tests/test_security_fixes.py` — delete `TestOldAdminViewsAuthZ` class (section 3, lines 148-238)

#### 2d. Move BlockchainAddressViewSet from exchanges/ to trading/

**Files to create/modify:**
- [ ] `apps/trading/views.py` — add `BlockchainAddressViewSet` class (moved from `apps/exchanges/views.py:93`)
- [ ] `apps/trading/serializers.py` — add `BlockchainAddressSerializer` class (moved from `apps/exchanges/serializers.py:125`)
- [ ] `apps/trading/urls.py` — add:
  ```python
  router.register(r'blockchain-addresses', views.BlockchainAddressViewSet, basename='blockchain-addresses')
  ```

#### 2e. Remove exchanges/ view layer

**Files to delete:**
- [ ] `apps/exchanges/views.py`
- [ ] `apps/exchanges/serializers.py`
- [ ] `apps/exchanges/urls.py`

**Files to modify:**
- [ ] `config/urls.py` — remove:
  ```python
  path('api/exchanges/', include('apps.exchanges.urls', namespace='exchanges')),  # Legacy, will be removed
  ```

**Files to keep:**
- [ ] `apps/exchanges/models.py` (canonical model location)
- [ ] `apps/exchanges/admin.py`

**Verify (after Phase 1 tests pass):**
```bash
python -m pytest tests/ -v --nomigrations
# Expected: 0 failures (some tests for deleted views may need removal — check carefully)
```

---

### Phase 3 — Model Deletion (UserProfile)

**Files to modify:**
- [ ] `apps/authentication/models.py` — delete `UserProfile` class (line 17)
- [ ] `apps/authentication/views.py` — replace any `user.profile.field` with `user.field`
- [ ] `apps/authentication/serializers.py` — replace any `UserProfile` references

**Grep targets** (search whole project, not just authentication/):
```
UserProfile       — direct import
user.profile      — related_name access
user_profile      — variable name
UserProfile       — in any serializer or view
```

**Migration:**
```bash
python manage.py makemigrations authentication
```
This should generate:
1. `DeleteModel` for `UserProfile` → drops `auth_user_profiles` table

**Verify:**
```bash
python manage.py migrate
python -m pytest tests/ -v --nomigrations
```

---

### Phase 4 — Centralize Exchange Choices

**Grep targets:**
```bash
grep -rn "EXCHANGE_CHOICES" apps/ --include="*.py"
grep -rn "'binance', 'Binance'" apps/ --include="*.py"
```

**Files to modify:**
- [ ] `apps/bots/models.py:15` — Replace top-level constant with:
  ```python
  from apps.exchanges.models import ExchangeCredentials
  EXCHANGE_CHOICES = ExchangeCredentials.EXCHANGE_CHOICES
  ```
- [ ] Any views with inline exchange lists — replace with import

**No migration needed** — this is a pure import refactor.

**Verify:**
```bash
python -m pytest tests/ -v --nomigrations
```

---

## 12. Full Audit Trail

### Key Files Referenced in This Document

| File | Role |
|------|------|
| `config/urls.py` | Master URL config — registers all apps' routes |
| `core/models.py` | **Phase 0** — new `SiteConfig` model |
| `core/admin.py` | **Phase 0** — `SiteConfigAdmin` |
| `apps/bots/models.py:957` | `Order` → rename to `BotOrder` (Phase 1) |
| `apps/bots/indicators_views.py` | Canonical engine trigger indicators (keep) |
| `apps/bots/views.py:368` | `IndicatorViewSet` — DRF CRUD for Indicator model (keep) |
| `apps/bots/views.py:410-555` | Legacy indicator views (delete Phase 2c) |
| `apps/bots/urls.py` | Remove 4 legacy routes, keep 3 canonical routes |
| `apps/trading/models.py` | Already refactored — re-exports from exchanges |
| `apps/trading/views.py` | Receives BlockchainAddressViewSet from exchanges |
| `apps/trading/serializers.py` | Receives BlockchainAddressSerializer from exchanges |
| `apps/trading/urls.py` | Add blockchain-addresses/ route |
| `apps/exchanges/models.py` | Canonical model location — keep |
| `apps/exchanges/views.py` | Delete (Phase 2e) — except BlockchainAddressViewSet (moved) |
| `apps/exchanges/serializers.py` | Delete (Phase 2e) — except BlockchainAddressSerializer (moved) |
| `apps/exchanges/urls.py` | Delete (Phase 2e) |
| `apps/investments/models.py:136` | Order model (keep, no rename needed — already named differently) |
| `apps/investments/models.py:255` | `UserBalance` → rename to `InvestmentBalance` (Phase 1) |
| `apps/investments/views.py:200/240` | EMAWebhookView/RSIWebhookView (keep Phase 2a) |
| `apps/investments/views.py:285/296` | Manual stubs (delete Phase 2a) |
| `apps/investments/urls.py` | Remove manual stub routes |
| `apps/webhooks/views.py:414/486` | Calculator views (delete Phase 2b) |
| `apps/webhooks/urls.py` | Remove calculator routes |
| `apps/authentication/models.py:17` | `UserProfile` — delete (Phase 3) |
| `apps/users/models.py:203` | `CustomUser.save()` — add `SiteConfig` lookup (Phase 0) |
| `apps/payments/models.py:68` | `QuantumAIDeposit` — canonical deposit model (keep) |
| `tests/investments/test_views.py:328` | `TestIndicatorManualViews` — delete (Phase 2a) |
| `tests/test_security_fixes.py:148` | `TestOldAdminViewsAuthZ` — delete (Phase 2c) |

---

## Appendix: How This Document Was Generated

- Every model file in `apps/*/models.py` was read and compared field-by-field
- Every URL file in `apps/*/urls.py` was read and cross-referenced against `config/urls.py`
- View files in `trading/`, `exchanges/`, `investments/`, `bots/`, `webhooks/` were read at the class level (not just name-matched)
- The `torgovo2` skill context provided project architecture overview and known production issues
- Phase ordering accounts for dependency: Phase 0 (plan limits) must precede Phase 3 (UserProfile deletion) so the limits logic is in `CustomUser.save()` before the conflicting `UserProfile` code is removed
- Each phase can be merged independently with full test suite between them
