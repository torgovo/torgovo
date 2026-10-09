# Tasks — Session 2026-07-18

## Plan

This session targets 12 issues across 4 priority tiers.
All fixes follow torgovo2 skill principles: **simplicity first, minimal impact, demand elegance**.

---

## ⚠️ BLOCKING (4 issues — crash or runtime error)

### C5 — `get_or_create_bot()` called but never defined

**Files**: `apps/bots/views.py:420,466,513,540`
**Root cause**: 4 async views (IndicatorView, BybitIndicatorView, CustomOrderClosingView, CustomOrderOpeningView) call `get_or_create_bot(user, pair_config_dict, exchange_name)` which was never defined.

**Best fix** — 1 new function, 4 changed call sites:
1. Add `get_or_create_engine(user, pair_config_dict, exchange_name)` to `bots/views.py` module level
2. Accept `pair_config_dict` which is a `PairConfigSerializer` instance → extract `.instance`
3. Delegate to existing `_get_or_create_engine()` from `indicators_views.py` (uses BotEngine, credentials, registry)
4. Change callers to pass the already-fetched `pair_config` model instance instead of the serializer, and use `await sync_to_async(get_or_create_engine)(...)`

The function already exists in `indicators_views.py:43` as `_get_or_create_engine`. Tests already reference `get_or_create_engine` from `bots.views` (`tests/bots/test_views.py:729`).

**Touch**: ~12 lines added + 5 lines changed (4 callers + 1 import removal)
**Test**: `test_returns_none_without_credentials` already written

---

### C4 — `get_webhook_json_template()` missing

**Files**: `apps/bots/admin.py:68`, `apps/payments/admin.py:56`, `apps/payments/serializers.py:243`
**Root cause**: `BotSubscription` model (payments/models.py:466) has no `get_webhook_json_template()` method. Called via `obj.get_webhook_json_template()` or `obj.subscription.get_webhook_json_template()`.

**Best fix** — Add method to `BotSubscription`:
```python
def get_webhook_json_template(self):
    return {
        "bot_id": str(self.id),
        "signal": "buy/sell",
        "pair": "BTC/USDT",
        "exchange": self.exchange_name or "binance",
        "quantity": "{{quantity}}",
        "price": "{{close}}",
        "take_profit": "{{tp}}",
        "stop_loss": "{{sl}}",
    }
```
Uses existing fields (`self.id`, `self.exchange_name`). Returns a TradingView-compatible JSON template.

**Touch**: ~20 lines in `payments/models.py`

---

### C3 — Wrong field names `base_currency`/`quote_currency`

**File**: `apps/bots/signals.py:33-34`
**Root cause**: Uses `base_currency`/`quote_currency` but `TradingPair` model (`exchanges/models.py:133-134`) has `base_asset`/`quote_asset`.

**Best fix** — Change 2 field names:
```python
defaults={'base_asset': ..., 'quote_asset': ...}
```

**Touch**: 2 lines

---

### C1/C2 — Duplicate TelegramSignalPlan + TelegramSignalSubscription models

**Files**:
- `apps/bots/models.py:1009-1050` — legacy, `SoftDeleteModel`, db_table `bots_telegram_*`, simple fields
- `apps/subscriptions/models.py:14-100` — active, `TimeStampedModel`/`SoftDeleteModel`, db_table `subscriptions_telegram_*`, tiered pricing + payment flow

**Root cause**: The old `bots` models were not removed when the `subscriptions` ones were created. Both sets have different tables, fields, and consumers.

**Impact analysis** (all consumers of `apps.bots.models.TelegramSignal*`):
- `bots/admin.py` — admin registration (shows empty table since new data goes to subscriptions tables)
- `bots/serializers.py:277-290` — TelegramSignalPlanSerializer + TelegramSignalSubscriptionSerializer
- `bots/views.py:378-395` — TelegramSignalPlanViewSet + TelegramSignalSubscriptionViewSet
- `bots/urls.py:19-20` — route registrations (`telegram-plans/`, `telegram-subscriptions/`)
- `conftest.py:222` — fixture setup
- `tests/bots/test_models.py:510-567` — model tests
- `tests/bots/test_serializers.py:277-296` — serializer tests
- `tests/bots/test_views.py:686-711` — view tests
- `tests/test_security_fixes.py:334-345` — security tests

**Best fix** — Remove duplicate and redirect all consumers:

1. **Remove** `TelegramSignalPlan` + `TelegramSignalSubscription` classes from `bots/models.py`
2. **Update** `bots/admin.py` → import from `apps.subscriptions.models`
3. **Update** `bots/serializers.py` → remove TelegramSignal serializers (already exist in `subscriptions/`), or redirect imports
4. **Update** `bots/views.py` → remove TelegramSignal ViewSets (already exist in `subscriptions/`)
5. **Update** `bots/urls.py` → remove `telegram-plans/` and `telegram-subscriptions/` routes
6. **Update** `tests/bots/*.py` and `conftest.py` → use subscriptions models
7. **Keep** `subscriptions` versions as the single source of truth

**Touch**: ~30 lines removed + ~15 lines import changes across 6+ files
**Risk**: Low — subscriptions tables are the active ones with real data

---

## 🔴 HIGH (4 issues — security or bad UX)

### H1 — FERNET_KEY in `.env` committed

**File**: `.env:33`
**Issue**: Real Fernet key `CRVB_ymXdBIru1OvFA553XCC5wOOZJoDTEnqOmsX2Y4=` committed to git history (`.gitignore` has `.env` but it was force-added). Key decrypts all exchange API keys.

**Best fix**:
1. Generate new key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
2. Update `.env` with new key
3. Create management command to re-encrypt all existing `ExchangeCredentials` and `QuantumAIFund` keys
4. Remove `.env` from git tracking: `git rm --cached .env`
5. Purge from history if needed (or accept exposure and rotate all exchange API keys)

**Touch**: 1 key update + 1 management command (~30 lines)
**Note**: `.env` is already in `.gitignore` — the real fix is tracking prevention

---

### H3 — AllowAny on webhook endpoints

**File**: `apps/webhooks/views.py:113,407,480`
**Issue**: 3 webhook views have `permission_classes = [AllowAny]`

**Best fix**: **No change needed**. The HMAC/secret validation in the view body already authenticates requests. Webhooks cannot use session/cookie auth. Add a comment explaining the intent.

Previous fix attempts may have over-applied `IsAuthenticated` to webhook endpoints. Verify the HMAC check is correct (line 157 area).

---

### H6 — 4 subscription endpoints return 501 ✅ DONE (2026-08-10)

**File**: `apps/subscriptions/views.py` / `apps/subscriptions/urls.py`
**Status**: 3 of the 4 stubs were removed in a prior session (CreateSubscriptionView/ExtendSubscriptionView/CancelSubscriptionView routes no longer exist — `urls.py` has been reworked to the telegram + bot-subscribe endpoints). This session removed the last one: `SignalStatisticsView` (was returning 501) from `views.py` and its `signal-statistics/` route from `urls.py`. Also removed the stale `statistics/` route referencing the deleted view from the dead `urls_corrected.py` (not imported anywhere).

**Verified**: `manage.py check` 0 issues; full suite 1859 passed, 13 skipped.

---

### H8 — Wrong BASE_DIR in dev settings

**File**: `config/settings/development.py:15`
**Issue**: `BASE_DIR = Path(__file__).resolve().parent.parent` resolves to `config/`, not the project root (where logs dir lives). Log files go to `config/logs/` instead of project root `logs/`.

**Best fix**: Change to match base.py:
`BASE_DIR = Path(__file__).resolve().parent.parent.parent`

Or better: **remove the override entirely** and inherit from `base.py` (which already has the correct `parent.parent.parent`).

**Touch**: 1 line

---

## 🟡 MEDIUM (2 issues — latent or inelegant)

### M1/M2 — `RateLimitMiddleware` never registered

**File**: `core/middleware.py:131` (class exists) — but NOT in `config/settings/base.py:MIDDLEWARE`
**Issue**: Middleware defined but never added to `MIDDLEWARE` list. All rate limiting in `DEFAULT_THROTTLE_RATES` is unused for API endpoints.

**Best fix**: Add to `MIDDLEWARE` in `base.py`:
```python
'core.middleware.RateLimitMiddleware',
```
Place after `CorrelationIDMiddleware` (last position) so all other middleware has already run.

**Touch**: 1 line

---

### M4 — Wrong `TimeStampedModel` import in `users/models.py:13`

**File**: `apps/users/models.py:13`
**Issue**: Imports `TimeStampedModel` from `django_extensions.db.models` instead of `core.models`. But the project has its own `TimeStampedModel` in `core/models.py:11` with different fields. This creates two different timestamped bases.

**Import**: `from django_extensions.db.models import TimeStampedModel`
**Should be**: `from core.models import TimeStampedModel`

**Best fix**: Change the import. Verify `CustomUser` (and any other model using it) doesn't depend on django_extensions fields. If `CustomUser` has `created`/`modified` fields from the external package, those column names may differ from `core`'s `created_at`/`updated_at`.

**Touch**: 1 line (verify migration impact first)

---

## 🔵 LOW (2 issues — cosmetic or admin UX)

### M6 — `secret_key` in webhook template HTML

**File**: `apps/bots/admin.py:42-52`
**Issue**: `secret_key` is in `readonly_fields` and displayed in the admin fieldset as plaintext. `SignalBot.secret_key` (bots/models.py:62) contains the webhook secret — full exposure in admin list/change views.

**Best fix**: Keep in admin but mask via a property or custom method:
```python
def masked_secret_key(self, obj):
    if obj.secret_key and len(obj.secret_key) > 8:
        return obj.secret_key[:6] + '...' + obj.secret_key[-4:]
    return obj.secret_key
masked_secret_key.short_description = 'Secret Key'
```
Then reference `masked_secret_key` in `readonly_fields` instead of `secret_key`.

**Touch**: ~5 lines

---

## Implementation Order

All 12 issues from the original plan are now **resolved**:
- **C3/C5/C4/H8** — fixed in earlier session (verified present: `get_or_create_engine` in `bots/views.py:51`, `get_webhook_json_template` in `payments/models.py:547`, `base_asset/quote_asset` in `signals.py`, BASE_DIR = parent.parent.parent)
- **H1** — FERNET_KEY rotated (prior session)
- **H3** — AllowAny webhook auth comment added (prior session)
- **M1** — RateLimitMiddleware registered in MIDDLEWARE (verified: `base.py:78`)
- **M4** — `core.models.TimeStampedModel` import (verified: `users/models.py:13`)
- **M6** — `masked_secret_key` admin masking (verified: `bots/admin.py:62`)
- **C1/C2** — duplicate TelegramSignal models removed; `apps.subscriptions.models` is source of truth (verified: only `subscriptions/models.py:14` defines it)
- **H6** — `SignalStatisticsView` 501 stub removed (this session, 2026-08-10)

```
1.  C3   — base_currency→base_asset, quote_currency→quote_asset    [done]
2.  C5   — get_or_create_engine() implementation                    [done]
3.  C4   — get_webhook_json_template() on BotSubscription           [done]
4.  H8   — BASE_DIR fix in development.py                           [done]
5.  M1   — RateLimitMiddleware in MIDDLEWARE                        [done]
6.  M4   — TimeStampedModel import fix (verify first)               [done]
7.  M6   — Mask secret_key in admin                                 [done]
8.  H6   — Remove 501 stub views + URLs                             [done 2026-08-10]
9.  C1/2 — Remove duplicate TelegramSignal models + redirect        [done]
10. H1   — Rotate FERNET_KEY + re-encrypt credentials               [done]
11. H3   — Add webhook AllowAny comment (or verify)                 [done]
```

## Verification
```bash
python manage.py check
python -m pytest tests/ -v --nomigrations 2>&1 | tail -20
```

---

## Session 2026-09-28 — persistence crash-consistency (7-phase plan) COMPLETE

All 7 phases of the production-persistence plan are **DONE** (2026-09-26..28):

```
1. Phase 6a — cross-process bot stop (CHG-6a-1..10)                [done 2026-09-26]
2. Phase 6b — SIGTERM/SIGINT registration (CHG-6b-1..5)            [done 2026-09-26]
3. Phase 1  — trade record integrity (CHG-1-1..5, bots/0017)       [done 2026-09-27]
4. Phase 2  — BotRuntimeState + state.py (CHG-2-1..3, trading/0002) [done 2026-09-27]
5. Phase 3  — snapshot/restore (CHG-3-1..4)                        [done 2026-09-27]
6. Phase 4  — boot recovery (CHG-4-1..4)                           [done 2026-09-28]
7. Phase 5  — watchdog tuning (CHG-5-1..4)                         [done 2026-09-28]
8. CHG-3-5  — shutdown-path forced snapshot                        [done 2026-09-28]
9. Phase 7  — final docs (CHANGELOG / PROJECT_STATUS / todo.md)    [done 2026-09-28]
```

**Goal delivered:** crash-consistent bots, <15 s blind window, all 4 bot types.

- Master revert guide: `docs/persistence/CHANGES.md` (1090 lines; every change
  with File / Change / Revert / Test + baseline warnings).
- Verification: full suite **2170 passed / 13 skipped**; `manage.py check` 0;
  `makemigrations --check` clean; flake8 0 new.
- Docs updated: `docs/CHANGELOG.md` (new top entry), `docs/PROJECT_STATUS.md`
  (verified-positives + date), this file.
- Gotchas and lessons recorded in `tasks/lessons.md` (Phase 4/5/CHG-3-5
  sections) and MEMORY.md.

## Session 2026-09-29 — persistence hardening test matrix [done]

10. CHG-T-1 — hardening tests (security/opt/reliability/concurrency) [done 2026-09-29]

- New `tests/persistence/test_persistence_hardening.py` (13 tests, 301 lines,
  tests only — no production code changes).
- Verification: full suite **2183 passed / 13 skipped**; `manage.py check` 0;
  `makemigrations --check` clean; flake8 0 findings on the new file.
- Revert: `rm tests/persistence/test_persistence_hardening.py` (nothing
  imports it). Details + test-status rows: `docs/persistence/CHANGES.md`
  CHG-T-1 (now 1136 lines).
