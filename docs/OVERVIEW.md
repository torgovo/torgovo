# Torgovo2 — Project Overview

## Vision

A subscription-based cryptocurrency trading bot platform where users create automated trading bots, connect exchange accounts via API keys, receive TradingView webhook signals, and execute trades across major exchanges — all without writing code.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Django 5.x + Django REST Framework 3.17 |
| Database | PostgreSQL 15 (prod), SQLite (tests) |
| Cache/Broker | Redis (cache, Celery broker, WebSocket channel layer) |
| Task Queue | Celery + Celery Beat (periodic scheduler) |
| ASGI Server | Daphne + Gunicorn + Uvicorn workers |
| Exchanges | CCXT (Binance, Bybit, OKX, MEXC, Alpaca, Coinbase) |
| Encryption | Fernet (symmetric) for exchange API keys |
| Auth | JWT via djangorestframework-simplejwt (rotation enabled) |
| Containerization | Docker + docker-compose |
| Monitoring | django-health-check, django-prometheus, Sentry |

## Four Bot Types

| Bot | How It Works | Who Manages | Runs Continuously? |
|-----|-------------|-------------|---------------------|
| **SignalBot** | Receives TradingView webhook → executes 1 trade → done | User | No |
| **GridBot** | Places buy/sell orders at defined grid levels, auto-manages positions | User | Yes |
| **MartingaleBot** | Progressive strategy — doubles position on loss, resets on win | User | Yes |
| **QuantumAIBot** | Admin trades pooled user funds, distributes proportional P/L every 2 weeks | Admin | Yes |

## Key Features

- Multi-exchange support (Binance, Bybit fully implemented; OKX, MEXC, Alpaca, Coinbase stubs)
- Webhook-driven signal trading (TradingView integration)
- Automated grid and martingale strategies
- Quantum AI pooled fund with proportional profit/loss distribution
- Subscription plans with tiered bot limits
- Referral system with USDT bonus payouts
- JWT authentication with refresh token rotation
- Fernet-encrypted exchange API key storage
- Rate limiting, brute-force protection, audit logging
- Admin dashboard with KPIs and user management
- Celery async task processing with heartbeat monitoring

## Subscription Plans

Three distinct plan systems:

| System | Granularity | Pricing |
|--------|-------------|---------|
| **TelegramSignalPlan** | Monthly / Quarterly / Yearly | Telegram signal subscription |
| **SubscriptionPlan** | Free / Basic / Premium / Enterprise | User tier with bot limits |
| **BotSubscriptionPlan** | 30 / 90 / 180 / 365 days | Per-bot-type pricing |

All payments currently require manual admin approval (crypto deposits). Automated payment processing (Stripe) is planned.

## Current Status

- **Core trading engine:** Working (Signal, Grid, Martingale, Quantum AI)
- **Exchange adapters:** Binance + Bybit complete; other exchanges are stubs
- **Webhook system:** Functional with EMA/RSI/BB indicator processing
- **Security:** Fernet encryption, JWT auth, rate limiting, credential redaction
- **Tests:** 254 passing (webhook + strategy + security + regression)
- **Frontend:** Not started (React + Vite scaffold exists)
- **Payments:** Manual approval only — no automated billing

## Known Critical Issues

1. **Duplicate app ecosystems** — `apps/bots/` vs `apps/investments/` have parallel model/view hierarchies
2. **RateLimitMiddleware** uses in-memory dict (not thread-safe, not process-safe)
3. **TradingViewWebhookView** is unimplemented stub (accepts webhooks, does nothing)
4. **CreateSubscriptionView** and Extend/Cancel views return 501 "Not implemented"
5. **django_prometheus** missing from requirements — breaks `manage.py check`
6. No KYC/AML, no GDPR compliance, no ToS acceptance
