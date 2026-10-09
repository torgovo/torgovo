# Architecture Overview

## System Diagram

```
                           Internet
                              |
                         +----+----+
                         |  nginx  |  TLS termination, rate limiting,
                         |  :443   |  static/media serving
                         +----+----+
                              |
                    +---------+----------+
                    |  upstream django   |
                    |  web:8000          |
                    +---------+----------+
                              |
              +---------------+---------------+
              |               |               |
      +-------+-------+ +----+----+ +--------+--------+
      |  Gunicorn     | | Celery  | | Celery          |
      |  + Uvicorn    | | Worker  | | Beat            |
      |  (ASGI)       | | :tasks  | | :scheduled      |
      +-------+-------+ +----+----+ +--------+--------+
              |              |               |
              +--------------+---------------+
                             |
                    +--------+--------+
                    |     Redis       |  Cache, Channels, Celery broker
                    +--------+--------+
                             |
                    +--------+--------+
                    |  PostgreSQL 15  |  Primary data store
                    +-----------------+
```

## App Structure (10 local apps)

| App | Purpose | Key Models |
|-----|---------|------------|
| **bots** | Bot CRUD, indicators, orders | SignalBot, GridBot, MartingaleBot, QuantumAIBot, QuantumAIFund, BotOrder, Indicator, PairConfig, InvestorPortfolio |
| **trading** | Trading engine, strategies, exchange adapters | StrategyConfig (imports Exchange, TradingPair from exchanges) |
| **exchanges** | Canonical exchange data + credentials | Exchange, TradingPair, ExchangeCredentials |
| **investments** | Quantum AI deposit display models | SupportedBlockchain, ExchangeRate, ExchangeStatus, InvestmentBalance, Order, Position, TechnicalIndicator, InvestorDeposit |
| **payments** | Subscriptions, deposits, withdrawals, admin approval | PaymentTransaction, SubscriptionPlan, InvestorDeposit, WithdrawalRequest, BlockchainAddress |
| **subscriptions** | Telegram signal subscription management | TelegramSignalPlan, TelegramSubscription |
| **authentication** | JWT auth, OAuth, OTP, profile | (view-based, no custom models) |
| **users** | User profiles, admin dashboards | CustomUser, UserProfile, UserActivityLog |
| **webhooks** | TradingView signal webhook receiver | (view-based) |
| **referrals** | Referral system | ReferralCode, ReferralReward |

## URL Structure

```
api/admin/              Custom admin site
api/auth/               Register, login, refresh, OAuth, password reset
api/users/              User profile, admin dashboards, orders
api/bots/               Bot CRUD + start/stop (Signal, Grid, Martingale, Quantum AI)
api/payments/           Subscriptions, deposits, withdrawals
api/trading/            Exchange lists, symbols, rates, strategy configs
api/exchanges/          Exchange credentials, status
api/subscriptions/      Telegram signal subscriptions
api/investments/        Quantum AI investments, blockchain addresses
api/referrals/          Referral codes, stats
api/webhooks/custombot/ Webhook signal processing (EMA, RSI, BB)
```

## Bot Execution Flow

```
User creates bot  ->  POST /api/bots/signal-bots/
         |
         v
Serializer validates  ->  Bot model created (status: STOPPED)
         |
         v
User starts bot  ->  POST /api/bots/signal-bots/{id}/start/
         |
         v
BotExecutorService.start_bot()  (services/bot_executor.py)
         |
         +-- Celery task: run_trading_bot  (apps/trading/tasks.py)
         |       |
         |       v
         |   BotExecutor.from_config(dict)  (apps/trading/engines/execution.py)
         |       |
         |       +-- get_adapter(config) -> ExchangeAdapter(CCXT)
         |       +-- get_strategy(config) -> Strategy class
         |       +-- BotEngine(adapter, strategy).startBot()
         |               |
         |               +-- create_order() via raw CCXT
         |               +-- Monitor thread (grid/SL/TP)
         |               +-- On exit -> cleanup
         |
         +-- DB status updated: RUNNING
```

## Exchange Adapter Pattern

```
BaseAdapter  (apps/trading/exchanges/base_adapter.py)
+-- BinanceAdapter     (fully implemented)
+-- BybitAdapter       (fully implemented)
+-- OKXAdapter         (fully implemented)
+-- MEXCAdapter        (fully implemented)
+-- AlpacaAdapter      (fully implemented)
+-- CoinbaseAdapter    (fully implemented)
```

Adapters wrap raw CCXT calls. `BotEngine` calls `self.exchange.create_order()` directly.

**MockAdapter:** Used only for unit tests, not for live or development trading.

## Strategy Pattern

| Strategy | Behavior |
|----------|----------|
| `SignalStrategy` | Execute single trade from webhook signal |
| `GridStrategy` | Place buy/sell orders at grid levels |
| `MartingaleStrategy` | Double position on losses, reset on win |
| `QuantumAIStrategy` | Admin-managed pool trading |

## Celery Tasks

**Worker** (4 concurrent, `acks_late=True`, `prefetch_multiplier=1`):
- `run_trading_bot` — start a bot engine
- `stop_bot` — gracefully stop a bot
- `check_all_active_bots` — periodic heartbeat (every 60s)
- Webhook signal processing

**Beat** (DatabaseScheduler via django-celery-beat):
- Heartbeat check — every 60s
- Signal reset — every 24h
- Profit accrual/distribution (Quantum AI) — every 2 weeks
- Process fund payouts — periodic
- Cleanup old audit logs — periodic

## Key Design Decisions

- **Engine accepts plain dict config**, not Django model instances — keeps engine pure Python
- **StrategyConfig stays as a model** with default presets per strategy type
- **UUID primary keys** on all domain models
- **SoftDeleteModel** base for all domain models (from `core/models.py`)
- **ExchangeCredentials** canonical in `apps/exchanges/`, backward-compat import in `apps/trading/`
- **bot_engine.py uses raw CCXT** — direct `self.exchange.create_order()` calls
- **Fernet encryption** for all API keys at rest

## Monitoring

| Tool | Integration | Endpoint |
|------|-------------|----------|
| django-health-check | DB, Redis, Celery | `GET /ht/` |
| django-prometheus | Request metrics, DB stats | `GET /metrics` |
| Sentry | Error tracking + performance | `SENTRY_DSN` |
| Grafana / Prometheus | Dashboard + alerting | `deploy/monitoring/` |
