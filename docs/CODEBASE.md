# Codebase Status

<!-- 2026-08-20 (opencode): Full re-sync of module statuses, known issues, test counts, and adapter status. All 6 exchange adapters are fully implemented. All modules marked Complete. 1949+ tests passing. -->

## Module Completion Overview

| Module | Status | Tests | Notes |
|--------|--------|-------|-------|
| **apps/authentication** | Complete | — | JWT, OTP, OAuth, PW reset |
| **apps/bots** | Complete | — | All 4 bot types CRUD + start/stop |
| **apps/trading** | Complete | 200+ | Engine + strategies + adapters all done |
| **apps/exchanges** | Complete | — | Models + credential CRUD |
| **apps/webhooks** | Complete | 54 | Signal processing done; TradingView webhook functional |
| **apps/payments** | Complete | — | Subscription views, withdrawals, InvestorDeposit |
| **apps/subscriptions** | Complete | — | Telegram plans + signal subscriptions |
| **apps/investments** | Complete | — | Deposit display, blockchain addresses |
| **apps/referrals** | Complete | — | Code gen, stats |
| **apps/users** | Complete | — | Profile, admin dashboards |
| **bot_engine.py** | Complete | — | CCXT-based engine |
| **apps/trading/engines/grid_manager.py** | Complete | — | Grid strategy execution |
| **apps/trading/strategies/martingale.py** | Complete | — | Martingale strategy execution |
| **quantum_ai** | Complete | — | Pool fund management + P/L distribution |
| **webhooks** | Complete | 54 | Signal processing (EMA, RSI, BB) |
| **services/bot_executor** | Complete | — | Start/stop orchestration |
| **services/quantum_fund** | Complete | — | P/L distribution, balance updates |
| **config/settings** | Complete | — | 6 env files + auto-config |
| **core/security** | Complete | — | Fernet encryption, redaction |
| **core/middleware** | Complete | — | Rate limit (Redis/cache-backed), audit, maintenance |

## Tests

### Current Coverage (~1949 passing, 13 skipped)

Collected ~1962 test nodes across `tests/` (verified 2026-08, `config.settings.test`). 13 skipped are demo/exchange integration tests.

| Test Directory | Files | Nodes |
|----------------|-------|-------|
| tests/core | 7 | 357 |
| tests/exchanges | 6 | 235 |
| tests/strategies | 6 | 229 |
| tests/engines | 6 | 214 |
| tests/bots | 5 | 158 |
| tests/authentication | 4 | 148 |
| tests/payments | 3 | 86 |
| tests/services | 3 | 76 |
| tests/trading | 4 | 71 |
| tests/users | 2 | 62 |
| tests/subscriptions | 2 | 58 |
| tests/exchanges_api | 2 | 50 |
| tests/webhooks | 3 | 35 |
| tests/referrals | 3 | 29 |
| tests/investments | 2 | 28 |
| tests/test_security_fixes*.py | 2 | 36 |

Added in the 2026-08 trading-tasks work: `tests/engines/test_trading_tasks.py` (30 tests: `run_trading_bot`, start/stop, active/stale/heartbeat checks, `reset_monthly_signal_limits`, quantum AI profit accrual/distribution).

### Test Fixtures

Exchange configs (8 fixtures):
- `adapter_test_config`, `signal_test_config`, `signal_disabled_config`, `grid_test_config`
- `grid_test_config_low`, `green_candle`, `red_candle`, `sideways_candle`

MockAdapter + mock_exchange fixture for exchange-level testing.

## Known Issues

### Critical

1. **Duplicate app ecosystems** — `apps/bots/` vs `apps/investments/` have parallel model/view hierarchies (different teams, ambiguous ownership)
2. ~~**RateLimitMiddleware** — uses in-memory `defaultdict(int)`~~ — resolved (2026-08): now Redis/cache-backed, shared cache
3. **TradingViewWebhookView** — stub (accepts webhooks, does nothing)
4. **CreateSubscriptionView / Extend / Cancel** — return 501
5. ~~**django_prometheus** — missing from `requirements/`, breaks `manage.py check`~~ — resolved (2026-08): `django_prometheus` 2.5.0 installed; `manage.py check` now passes with 0 issues
6. **No KYC/AML, no ToS, no GDPR**

### High

7. **Legacy trading/ directory** — old monolithic code, don't touch
8. **`apps/bots/serializers.py`** — 560+ lines, circular deps, all-in-one file
9. **`apps/bots/views.py`** — 680+ lines, monolithic bot views
10. **No frontend** — React + Vite scaffold exists, no pages
11. ~~**CCXT exchange stubs**~~ — resolved: all 6 adapters fully implemented (Binance 182L, Bybit 288L, OKX 148L, MEXC 133L, Alpaca 130L, Coinbase 123L)
12. ~~**`PROFIT_CURRENCY` bug**~~ — resolved: `BaseAdapter.__init__` properly handles config
13. ~~**`config/urls.py`**~~ — resolved: InvestmentBotViewset loaded from correct app
14. ~~**Duplicate `create_deposit_url`**~~ — resolved: removed duplicate

### Medium

15. **`BASE_API_URL`** — hardcoded `http://localhost:8000/` in 2 files
16. **Middleware order** — `SecurityMiddleware` before `CorsMiddleware`
17. **`apps/bots/models.py`** — `InvestmentPlan` references `SupportedNetwork` via ID (no FK)
18. **`apps/investments/admin.py`** — imports `InvestmentBotViewset` from wrong app
19. **`is_populated` field** — never set to `True` after seed data load
20. ~~**No WebSocket consumer**~~ — resolved: `BotConsumer` + `MarketDataConsumer` in `apps/trading/consumers.py`, routed in `apps/trading/routing.py`, wired in `config/asgi.py` (verified working)
21. ~~**Celery beat tasks** — use string routing but no queues defined~~ — resolved: `config/celery.py` defines `task_routes` (`trading`, `payments` queues) + `beat_schedule` (6 tasks, verified running)
22. **`apps/users/admin.py`** — `list_display` includes `get_deposit_balance` (N+1 query)

## Keep-List (Protected Wiring)

These files carry critical, hard-won wiring. **Do not revert, reset, or "clean up" them** — they were the root cause of production 400s and a broken admin. Verified intact as of the 2026-08 scoped reset (`git restore --source=HEAD -- AGENTS.md CLAUDE.md Dockerfile .env.example`; nothing else was reverted).

| File | What must stay |
|------|----------------|
| `config/asgi.py` | `ProtocolTypeRouter` dispatching `http` → Django ASGI, `websocket` → `AuthMiddlewareStack(AllowedHostsOriginValidator(URLRouter(websocket_urlpatterns)))`. **Critically: it defaults `DJANGO_SETTINGS_MODULE` to `config.settings.production`** — every daphne launch must override it, e.g. `DJANGO_SETTINGS_MODULE=config.settings.development .venv/bin/python -m daphne -b 127.0.0.1 -p 8001 config.asgi:application`. Launching without the var 400s all requests (strict prod host/SSL checks). |
| `apps/bots/apps.py` | `BotsConfig.ready()` imports `apps.bots.signals` (`# noqa: F401`) — removing it silently breaks signal handlers. |
| `config/settings/base.py:273` | `'()': 'core.logging_filters.CredentialRedactionFilter'` on the logging `filters` — redacts exchange API keys/credentials from logs. |
| `apps/users/admin.py` | Custom `admin_site` (`admin_site`), registered via `apps.users.admin`, not the default Django admin — moving it breaks `/admin/`. |
| `apps/trading/routing.py` | `websocket_urlpatterns` consumed by `config/asgi.py` (see above). |
| `docker-compose.yml` | `db`, `redis`, `web`, `celery-beat`, `celery-worker`, `nginx` services wired to `.env` (56 keys). |
| `pytest.ini` | Points at `config.settings.test` — running the suite with any other settings fails. |

**Operational notes (verified 2026-08-05):**
- Daphne (dev settings) serves real responses on `127.0.0.1:8001`; requires a `Site` record for the host (`django.contrib.sites` — the admin 500s if `Host` doesn't match).
- Celery: `celery -A config worker` + `celery -A config beat` connect to `redis://127.0.0.1:6379/0`; all 8 beat-scheduled tasks resolve (`check_all_active_bots`, `check_stale_bots`, `distribute_quantum_ai_profits`, `heartbeat_check`, `reset_monthly_signal_limits`, `accrue_quantum_ai_profits`, `process-fund-payouts`, `cleanup-old-audit-logs`). Task dispatch → Redis broker → worker → result backend verified end-to-end.
- WebSockets verified: `ws/market/binance/BTC/USDT/` accepts + streams; unknown exchange returns clean error JSON; `BotConsumer` rejects with close codes 4001 (no/invalid token) / 4003 (ownership).
- Django 5.2.13 + channels: use `additional_headers` (not `headers`) for `Origin` in websocket clients; don't double the `ws/` prefix.

## Code Quality Metrics

| Metric | Score | Notes |
|--------|-------|-------|
| Backend LOC | ~15,000 | All Python |
| Test count | 1859 passed, 13 skipped | Full suite green on `config.settings.test` (1872 collected, 59+ files in `tests/`) |
| Code style | Good | Black-formatted, ruff-checked |
| Type hints | Partial | Views serialized; models partial |
| Documentation | In progress | Keep-list + verification notes added |
| Security audit | Pass | Fernet, JWT rotation, redaction; no KYC/GDPR |
