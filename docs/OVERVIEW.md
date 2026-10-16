# Torgovo2 — Project Overview

> **Product requirements SoT:** `docs/FUNCTIONAL_REQUIREMENTS.md` — when this
> document and that one disagree on product behavior, Part A there wins.

## Vision

A subscription-based cryptocurrency trading bot platform where users create automated trading bots, connect exchange accounts via API keys, receive TradingView webhook signals, and execute trades across major exchanges — all without writing code.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Django 5.2 + Django REST Framework 3.17 |
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
| **QuantumAIBot** | Admin trades pooled user funds. **Target (FR A5):** 30–365d locks, no early withdrawal, profit-only withdrawals after lock processed manually within 7 days, hidden 20% profit pool. **Current code:** biweekly proportional P/L with reserve/smoothing — to be replaced | Admin | Yes |

## Key Features

- Launch exchanges: Bybit + Binance (other CCXT adapters exist but are not launch-supported)
- Webhook-driven signal trading (TradingView integration)
- Automated grid and martingale strategies
- Quantum AI pooled fund with 30–365d locks and profit-only withdrawals (target; see FR A5)
- Subscription plans per Model C (Free / Basic $15 / Standard $25 / Premium $49 / Creator $20; annual = 20% off) — not yet implemented
- Hybrid referrals (Creator → 10% cash; other tiers → referee gets 15% discount) — not yet implemented
- JWT authentication with refresh token rotation
- Fernet-encrypted exchange API key storage
- Rate limiting, brute-force protection, audit logging
- Admin dashboard with KPIs and user management
- Celery async task processing with heartbeat monitoring

## Subscription Plans

**Target (FR A2):** one Model C tier ladder — Free / Basic $15 / Standard $25 / Premium $49 / Creator $20 (annual = 20% off). Free = Signal bots only, 10 signals/mo, 1 bot, 1 exchange, spot only.

**Current code** still has three distinct plan systems (to be consolidated):

| System | Granularity | Pricing |
|--------|-------------|---------|
| **TelegramSignalPlan** | Monthly / Quarterly / Yearly | Telegram signal subscription |
| **SubscriptionPlan** | Free / Basic / Premium / Enterprise | User tier with bot limits (placeholder prices — not Model C) |
| **BotSubscriptionPlan** | 30 / 90 / 180 / 365 days | Per-bot-type pricing |

All payments currently require manual admin approval (crypto deposits). Per FR A3 the launch payment flow is manual multi-coin with unique payment codes, quote expiry, and live-price lock; Stripe/PayPal are a later phase.

## Current Status

- **Core trading engine:** Working (Signal, Grid, Martingale, Quantum AI — current biweekly Quantum distribution)
- **Exchange adapters:** Code exists for Binance, Bybit, OKX, MEXC, Alpaca, Coinbase; **launch scope is Bybit + Binance only** (adapters ≠ launch support)
- **Webhook system:** Functional with EMA/RSI/BB indicator processing
- **Security:** Fernet encryption, JWT auth, rate limiting, credential redaction
- **Tests:** 2170 passed / 13 skipped (full suite, verified 2026-09-28)
- **Frontend:** Not started (React + Vite scaffold exists)
- **Payments:** Manual approval only — no automated billing, no payment codes/quotes yet (FR A3)

## Known Critical Issues

1. **Duplicate app ecosystems** — `apps/bots/` vs `apps/investments/` have parallel model/view hierarchies
2. ~~**RateLimitMiddleware**~~ — resolved: now Redis/cache-backed
3. ~~**TradingViewWebhookView**~~ — resolved: functional with EMA/RSI/BB indicator processing
4. ~~**CreateSubscriptionView**~~ — resolved: subscription views functional
5. ~~**django_prometheus**~~ — resolved: installed and working
6. No ToS/privacy acceptance gate (open launch blocker). KYC deliberately deferred (FR A1: field/flag reserved, not built now)
