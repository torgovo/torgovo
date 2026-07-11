# Torgovo Backend – Production & Missing Features Tasks

**Target AI:** Kimi 2.6 (Hermes)  
**Goal:** Transform the current Django REST API into a production‑ready, secure, and complete backend that a frontend can safely integrate with.

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

**Endpoint:** `GET /api/subscriptions/plans/`  
**Response:**
```json
{
  "plans": [
    {"id": "free", "name": "Free", "price_monthly": 0, "currency": "USD",
     "features": {"max_bots": 1, "webhook_alerts": 50}},
    {"id": "premium", "name": "Premium", "price_monthly": 29.99, "currency": "USD",
     "features": {"max_bots": 10, "webhook_alerts": 1000}},
    {"id": "enterprise", "name": "Enterprise", "price_monthly": 99.99, "currency": "USD",
     "features": {"max_bots": 50, "webhook_alerts": "unlimited"}}
  ]
}

Endpoint: POST /api/subscriptions/subscribe/
Request (Stripe/PayPal):
json

{"plan_id": "premium", "payment_method": "stripe", "payment_nonce": "tok_xxx"}

Request (crypto):
json

{"plan_id": "premium", "payment_method": "crypto", "crypto_tx_hash": "0x...", "crypto_amount": 29.99, "crypto_coin": "USDT"}

Also accept a screenshot file (multipart/form-data).
Response: subscription object with status (active/pending_admin), expires_at.

Endpoint: GET /api/subscriptions/my-usage/
Response:
json

{"plan": "premium", "limits": {"max_bots": 10}, "usage": {"bots_created": 3, "webhook_alerts_used": 42}}

1.2 Referral System

Endpoint: GET /api/referrals/my-stats/
Response:
json

{"referral_code": "ABC123", "total_referrals": 5, "total_bonus_usdt": "25.50", "referral_link": "https://torgovo.com/signup?ref=ABC123"}

Endpoint: POST /api/referrals/apply/
Request: {"referral_code": "ABC123"} (authenticated)
Response: {"message": "Referral code applied"}

Modify registration endpoint (POST /api/auth/register/) to accept optional field referral_code and apply it immediately.
1.3 Quantum AI Withdrawals

Endpoint: POST /api/investments/quantum/withdraw/
Request: {"amount": "150.00", "address": "0x...", "blockchain": "BEP20"}
Response: {"withdrawal_id": "uuid", "status": "pending", "message": "Processed every 2 weeks"}

Endpoint: GET /api/investments/quantum/withdrawals/
Response: list of withdrawals with status (pending/approved/rejected).

Important: Validate that amount <= current_balance. Create a WithdrawalRequest model with status field. Admin approval endpoint required (see Module 2).
Module 2: Admin Endpoints (for Dashboard)

Add to apps/admin/views.py (or extend existing admin views).
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




