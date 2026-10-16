# Torgovo Backend – Production & Missing Features Tasks

**Target AI:** Kimi 2.6 (Hermes)
**Goal:** Transform the current Django REST API into a production‑ready, secure, and complete backend that a frontend can safely integrate with.

> **Product requirements SoT:** `docs/FUNCTIONAL_REQUIREMENTS.md` Part A.
> When the example payloads below and Part A disagree, Part A wins — update the
> example. (Examples in Module 1 were aligned to Part A on 2026-10-11.)

---

## Important – Security Risks You Must Mitigate

| Risk | Explanation | Your Mitigation (implement) |
|------|-------------|-----------------------------|
| **Man‑in‑the‑middle (MITM)** | Without HTTPS, API keys and JWTs are sent in plain text. | Enforce HTTPS, HSTS, secure cookies. |
| **API key leakage** | Exchange API keys stored in DB must never be exposed in logs or responses. | Use Fernet encryption (already there). Never log the decrypted value. |
| **Webhook replay attacks** | An attacker could replay a valid TradingView signal to execute duplicate trades. | Include a `timestamp` in the webhook JSON; reject signals older than 60 seconds. Also use a nonce or idempotency key. |
| **Brute‑force login** | Attackers can guess passwords. | Add rate limiting on login endpoint (e.g., 5 attempts per minute). |
| **Insufficient withdrawal checks** | Users might withdraw more than their balance. | Always validate `amount <= available_balance` before creating a withdrawal request. Admin must approve. |
| **SQL injection** | Raw SQL queries are rare in Django ORM, but still possible. | Always use ORM or parameterised queries. Never concatenate user input into SQL. |
| **Cross‑site scripting (XSS)** | Malicious scripts could be injected via user‑provided data. | Sanitise any user input that is rendered in admin panels. Use Django’s auto‑escaping. |
| **Privilege escalation** | Regular users accessing admin endpoints. | Every admin endpoint must check `request.user.is_superuser`. Use DRF permissions. |

**Rule:** Never trust user input. Validate everything.

---

## Module 1: Missing User‑Facing Endpoints

Add these to `apps/subscriptions/views.py`, `apps/referrals/views.py`, `apps/investments/views.py`.

### 1.1 Subscription Plans (User)

**Endpoint:** `GET /api/subscriptions/bot-plans/` (public, cached 1h; note — `/api/subscriptions/plans/` and `/public/plans/` serve the *Telegram* plan model, not this one)
**Status: DONE (G1, 2026-10-12).** Served by `PlanListView` from `payments.SubscriptionPlan`, seeded by `manage.py seed_model_c_plans`.
**Response (flat shape, all fields admin-driven):**
```json
{
  "plans": [
    {"id": 1, "name": "Free", "slug": "free", "description": "…",
     "price_monthly": "0.00", "price_yearly": "0.00", "annual_discount_pct": 0,
     "sort_order": 10, "max_bots_allowed": 1, "max_webhooks_allowed": 10,
     "bot_types": ["signal"], "market": "spot",
     "max_signals_per_month": 10, "max_exchanges": 1,
     "features": [], "trial_days": 0},
    {"name": "Basic", "slug": "basic", "price_monthly": "15.00", "price_yearly": "144.00", "annual_discount_pct": 20, "sort_order": 20, "…": "…"},
    {"name": "Standard", "slug": "standard", "price_monthly": "25.00", "price_yearly": "240.00", "annual_discount_pct": 20, "sort_order": 30, "…": "TBD paid-tier features"},
    {"name": "Premium", "slug": "premium", "price_monthly": "49.00", "price_yearly": "470.40", "annual_discount_pct": 20, "sort_order": 40, "…": "TBD"},
    {"name": "Creator", "slug": "creator", "price_monthly": "20.00", "price_yearly": "192.00", "annual_discount_pct": 20, "sort_order": 50, "…": "TBD (includes referral cash commissions, FR A7)"}
  ]
}
```
Annual prices = monthly × 12 × 0.8 (20% annual discount, FR A2). Display order = `sort_order` asc (Free→Creator), never price.

**Admin-driven (hard requirement) — met:** prices, sort order, `bot_types`, `market`, and every limit are Django-admin fields on `SubscriptionPlan` (admin: *Payments → Subscription plans*); edits invalidate `subscription_plans_v2` via `payments.signals` and propagate on the next request. No hard-coded plan values in views/serializers. Paid-tier feature details are seeded as placeholders — admin must finish them per FR A2 before launch.

**Status: DONE (G2 / FR A3, 2026-10-12).** Manual multi-coin payment codes (Stripe/PayPal remain a later phase). Endpoints:

> **Rule change 2026-10-14 (user decision, FR A3) — IMPLEMENTED 2026-10-15.**
> The old 1–60 s TTL / silent re-lock is gone. Live rule: the quote shows
> the **combined payable amount** (plan price + chain fee, e.g.
> `15.00 + 0.20 → 15.20 USDT`) that **auto-updates every 5 minutes**
> (`PAYMENT_QUOTE_TTL_SECONDS` default 300, clamped 60–3600), hard
> **expires after the payment window** (`PaymentCoin.quote_window_seconds`,
> default 6 h, admin-configurable) → user must `POST …/quote/` to re-request
> at the then-current price (no silent re-lock; window restarts).

- `GET /api/payments/payment-coins/` (public) → configured receive coins/chains (`deposit_address` only when set; `network_fee` per chain for the fee breakdown; seed: `manage.py seed_payment_coins`, idempotent, addresses left blank until admin sets them).
- `POST /api/payments/payment-codes/` — `{order_kind: "telegram_signal"|"bot", plan_id, billing_cycle}` → 201 `{"code", "fiat_amount", "status": "awaiting_payment", …}`. Pre-flight mirrors legacy subscribe: 409 duplicate (`error.details.subscription_id`), 409 capacity, 400 when no receive coin is configured. Bot orders force `monthly` at the monthly price.
- `GET /api/payments/payment-codes/<code>/` → detail + live `quote` (`rate`, `crypto_amount` = combined amount incl. `coin.network_fee`, `expires_at`, `is_expired`, nested `coin`) + `quote_window_expires_at`. TTL cadence 5 min; `expires_at` truncated at the window end. While the window is open an expired quote re-locks automatically; **after window expiry GET returns the expired quote unchanged** (never re-prices silently). `?coin_id=` switches coin (400 unknown). Price feed down → 503 `SERVICE_UNAVAILABLE` (standard envelope; never a fallback amount).
- `POST /api/payments/payment-codes/<code>/quote/` — `{coin_id?}` explicit re-request: re-locks at the then-current price, restarts the payment window, returns the same payload as GET. 400 unknown coin / non-awaiting code; 404 other user's code; 401 unauthenticated.
- `POST /api/payments/payment-codes/<code>/proof/` → TX hash + `telegram_handle`, or `payment_screenshot` multipart → 201 `{"subscription_id", "status": "submitted", "locked_rate", "locked_crypto_amount", …}`; creates the same `pending_approval` rows as legacy subscribe. Re-prices once at submission **only while the window is open** (window closed → freezes the stale quote, no re-price), then freezes `locked_*` on the code.
- Admin approval (`telegram/subscribe/`-style approve/reject, `payments/subscriptions/bot/…`) mirrors onto the code via `payments.signals` → `approved`/`rejected`.

Code read side: `apps/payments/services/quote.py` (`is_window_open` / `renew_quote`); fulfillment: `apps/payments/services/fulfill.py`. Tests: `tests/payments/test_g2_payment_codes.py` (76).

Endpoint: GET /api/subscriptions/my-usage/
Response:
```json
{"plan": "basic", "limits": {"max_bots": 2, "max_exchanges": 1}, "usage": {"bots_created": 1, "signals_used": 4}}
```

1.2 Referral System (FR A7 — hybrid model)

Endpoint: GET /api/referrals/my-stats/
Response:
```json
{"referral_code": "ABC123",
 "referrer_tier": "creator",
 "total_referrals": 5,
 "cash_commissions_usd": "12.50",
 "discounts_granted": {"count": 2, "percent": 15},
 "referral_link": "https://torgovo.com/signup?ref=ABC123"}
```
Semantics: if referrer is on **Creator**, they earn **10% cash commission** on referee payments; on **any other tier**, the **referee gets a 15% discount** on their payment. No "total_bonus_usdt" USDT-bonus model — that is superseded.

Endpoint: POST /api/referrals/apply/
Request: {"referral_code": "ABC123"} (authenticated)
Response: {"message": "Referral code applied"}

Modify registration endpoint (POST /api/auth/register/) to accept optional field referral_code and apply it immediately.

1.3 Quantum AI Withdrawals (FR A5)

Endpoint: POST /api/investments/quantum/withdraw/
Request: {"amount": "150.00", "address": "0x...", "blockchain": "TRC20"}
Response: {"withdrawal_id": "uuid", "status": "pending", "message": "Processed manually within 7 days after lock expiry"}

Endpoint: GET /api/investments/quantum/withdrawals/
Response: list of withdrawals with status (pending/approved/rejected).

Important: Withdrawals are **profit-only** and only allowed **after the lock period expires** (30/90/180/365 days; no early withdrawal — FR A5). Validate that amount <= current withdrawable profit balance. Admin processes manually **within 7 days**. Create a WithdrawalRequest model with status field. Admin approval endpoint required (see Module 2).

**STATUS 2026-10-16 — IMPLEMENTED** (supersedes the sketch above where they differ; grilling locked the exact semantics):

- Models (`apps/bots/models.py`): `InvestorLock` (balance-of-record capital, `matures_at` derived, term counters), `QuantumProfitCredit` (one-per-term audit, DB unique backstop), `QuantumWithdrawalRequest` (pending/approved/rejected, admin-entered payout incl. fees per grill Q12).
- Service (`services/quantum_locks.py`): `create_lock` / `credit_maturity` (free-form admin %, compounds capital, rolls window from credit moment — no instant re-fire) / `request_withdrawal` (hard rule: **blocked during lock**, amount ≤ capital — full capital incl. rolled profit, not profit-only) / `approve_withdrawal` (debits lock, creates `PaymentTransaction` type `quantum_withdrawal`, closes lock at zero; **never** touches `UserBalance`) / `reject_withdrawal`.
- Endpoints (`apps/investments/`): `GET|POST .../quantum-ai/locks/` (own; staff all; `?status=`, `?matured=1` credit queue), `POST .../locks/{id}/withdraw/`, `POST .../locks/{id}/credit/` (staff), `GET .../quantum-ai/withdrawal-requests/`, `POST .../withdrawal-requests/{id}/decide/` (staff). Locks auto-created on Quantum subscription approve + deposit approve (hard-fail 400 without active fund).
- Supersession: beat entries `distribute-quantum-ai-profits` / `accrue-quantum-ai-profits` **removed** from `config/celery.py`; legacy task functions kept importable for pinned unit tests.
- Tests: `tests/bots/test_quantum_locks_a5.py` (53: lifecycle, compounding, unique backstop, lock hard rule, approve/reject accounting, UserBalance untouched, endpoint permissions/404/400/403, beat removal). Full suite **2422 passed / 13 skipped**.
Module 2: Admin Endpoints (for Dashboard)

Add to `apps/users/views.py` (admin views) or create a new `apps/admin/` module.
2.1 Manage Subscription Plans

    GET /api/admin/subscription-plans/

    POST /api/admin/subscription-plans/ (create new plan)

    PUT /api/admin/subscription-plans/{id}/ (update price, features)

    DELETE /api/admin/subscription-plans/{id}/

2.2 Withdrawal Approval

    GET /api/admin/withdrawals/pending/

    PUT /api/admin/withdrawals/{id}/approve/ (body: {"tx_hash": "...", "notes": "..."})

    PUT /api/admin/withdrawals/{id}/reject/ (body: {"reason": "..."})

2.3 Existing Admin Endpoints

Ensure /api/admin/pending/ includes both investments and crypto payments. Add filters.
Module 3: Security Hardening (Critical)
3.1 Environment Variables

Install django-environ. Create .env file (never commit). Update settings.py:
python

import environ
env = environ.Env()
SECRET_KEY = env("SECRET_KEY")
DB_PASSWORD = env("DB_PASSWORD")
FERNET_KEY = env("FERNET_KEY")  # used for encrypting API keys

3.2 HTTPS & Security Headers

Create settings/production.py (or add to base with if not DEBUG):
python

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

3.3 Rate Limiting (DRF throttling)

In REST_FRAMEWORK settings:
python

'DEFAULT_THROTTLE_CLASSES': [
    'rest_framework.throttling.AnonRateThrottle',
    'rest_framework.throttling.UserRateThrottle',
],
'DEFAULT_THROTTLE_RATES': {
    'anon': '100/hour',
    'user': '1000/hour',
    'login': '5/minute',   # custom scope for login
}

Apply @throttle_classes([AnonRateThrottle]) on login view.
3.4 Webhook Security (Replay Protection)

In TradingView webhook view:

    Check secret_key → 403 if invalid.

    Validate timestamp (if present) is within last 60 seconds.

    (Optional) store a cache of used nonces (e.g., signal_bot_id:nonce) for 1 hour to prevent replay.

3.5 Input Validation

All serializers must use serializers.CharField(max_length=...), DecimalField with min_value, max_digits, etc. Never trust raw JSON.
3.6 Admin Permission Checks

Every admin view must have:
python

permission_classes = [permissions.IsAdminUser]

Module 4: Performance Optimisation
4.1 Database Indexes

Add db_index=True to:

    user_id in all bot models and orders

    created_at (for ordering)

    status (for filtering)

    exchange_name and trading_pair

Example migration (Django auto‑generates after adding to model fields).
4.2 N+1 Query Fix

In DRF views, use select_related and prefetch_related. Example:
python

queryset = SignalBot.objects.select_related('user').prefetch_related('orders')

4.3 Caching with Redis

Install django-redis. Configure CACHES:
python

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': os.getenv('REDIS_URL'),
    }
}

Cache subscription plans for 1 hour:
python

from django.core.cache import cache
plans = cache.get('subscription_plans')
if not plans:
    plans = list(SubscriptionPlan.objects.all())
    cache.set('subscription_plans', plans, 3600)

Module 5: Observability & Monitoring
5.1 Structured Logging (JSON)

Install python-json-logger. In LOGGING dict:
python

'formatters': {
    'json': {
        '()': 'pythonjsonlogger.jsonlogger.JsonFormatter',
        'format': '%(asctime)s %(levelname)s %(name)s %(message)s',
    },
},
'handlers': {
    'console': {
        'class': 'logging.StreamHandler',
        'formatter': 'json',
    },
},

Log all API requests, bot actions, and errors with context: user_id, bot_id, exchange.
5.2 Health Check Endpoint

GET /health/ returns:
json

{"status": "ok", "database": "ok", "redis": "ok", "celery": "ok"}

Implement using django-health-check or manually.
5.3 Error Tracking (Sentry)

Add sentry-sdk to settings.py:
python

import sentry_sdk
sentry_sdk.init(dsn=env("SENTRY_DSN"), environment=env("ENVIRONMENT"))

5.4 Prometheus Metrics (Optional)

Add django-prometheus and expose /metrics endpoint for scraping.
Module 6: Testing (Minimum Coverage)

Write tests using APITestCase. At minimum cover:

    User registration & login (including referral code)

    Creating signal/grid/martingale bot

    Starting/stopping a bot (mock BotEngine)

    Submitting a deposit (Quantum AI)

    Withdrawal request

    Admin approval of investment/withdrawal

Example test for signal bot:
python

def test_create_signal_bot(self):
    self.client.force_authenticate(user=self.user)
    response = self.client.post('/api/bots/signal-bots/', {...})
    assert response.status_code == 201
    assert 'webhook_url' in response.json()

Run tests: python manage.py test --parallel
Module 7: CI/CD (GitHub Actions)

Create .github/workflows/ci.yml:
yaml

name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: testpass
        options: >-
          --health-cmd pg_isready
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: python manage.py test

(Optional) Add deployment job that builds Docker image and pushes to registry.
Module 8: Signal Bot Webhook – Final Details

Ensure the webhook view:

    Receives JSON: {"secret": "...", "action": "buy", "tv_instrument": "BTCUSDT", "amount": "0.001", "timestamp": 1234567890}

    Validates secret against SignalBot.secret_key.

    Rejects if timestamp older than 60 seconds.

    Executes trade asynchronously (Celery task) – leave # TODO: Implement CCXT trade execution but complete all other logic (validation, logging, order creation).

Response on success: {"status": "accepted"}, on failure: {"error": "...", "code": 403/400}.
How to Use This Document

    Read all modules before starting.

    Implement in this order: Module 1 (missing endpoints) → Module 2 (admin) → Module 3 (security) → Module 4 (performance) → Modules 5–7 (observability, tests, CI).

    For each module, write the necessary code files. Keep existing functionality intact.

    Provide complete file contents (not just snippets) when possible.

    After implementation, run python manage.py check --deploy and fix any warnings.

Final Warning for the AI

    Do not hardcode secrets. Use environment variables.

    Never log API keys or secret_key. Even in debug mode.

    Validate all user inputs – assume every field can be malicious.

    Test your changes – provide a brief test plan.

If you follow this document, the backend will be secure, production‑ready, and fully compatible with the frontend.
text
