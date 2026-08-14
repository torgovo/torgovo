# Torgovo — Project Documentation

## Overview
Subscription-based crypto trading bot platform. Users create bots, connect exchanges, receive TradingView webhook signals, and auto-execute trades via CCXT.

**Stack:** Django 5.x + DRF, PostgreSQL, Celery + Redis, CCXT, Docker
**Frontend:** React + Vite (separate, not started)

---

## Four Bot Types

| Bot | How It Works | Who Manages | Continuous? |
|-----|-------------|-------------|-------------|
| **SignalBot** | TradingView webhook → execute 1 trade → done | User | No |
| **GridBot** | Places buy/sell at grid levels, auto-manages | User | Yes |
| **MartingaleBot** | Progressive strategy, doubles on loss | User | Yes |
| **QuantumAIBot** | Admin trades pooled user funds, distributes proportional P/L | Admin | Yes |

### Quantum AI Flow
1. User deposits USDT → `QuantumDeposit` (pending)
2. Admin approves → updates `QuantumAIInvestment.amount` + `QuantumAIFund.total_deposits`
3. Admin runs `QuantumAIBot` against fund's master API keys
4. Every 2 weeks: calculate P/L × `shown_percentage` (5–20%, admin-configurable), distribute proportionally
5. Users see ONLY their balance + changes — NO trade details

---

## Architecture

```
apps/bots/           → Bot domain models + API views (user-facing CRUD)
  models.py          → SignalBot, GridBot, MartingaleBot, QuantumAIFund, QuantumAIBot,
                       QuantumAIInvestment, QuantumDeposit, QuantumWeeklyProfit,
                       PairConfig, Indicator, Order
  views.py           → All bot ViewSets
  indicators_views.py → TradingView indicator webhooks (EMA/RSI/BB → BotEngine)
  admin.py           → Admin with start/stop actions
  urls.py            → Bot API routes

apps/trading/        → Trading engine (internal)
  strategies/        → BaseStrategy, QuantumAI, Grid, Martingale, Signal
  exchanges/         → CCXT adapters: Binance, Bybit, OKX, MEXC, Alpaca
  engines/           → BotEngine (core logic), BotExecutor (orchestration)
  models.py          → StrategyConfig (imports Exchange, TradingPair from apps/exchanges)
  tasks.py           → Celery async tasks (run_bot, stop_bot, check_active)

apps/payments/       → Payment-only views (subscriptions, deposits, withdrawals)
apps/exchanges/      → Exchange, TradingPair, ExchangeCredentials (canonical trading data)
apps/investments/    → SupportedBlockchain, ExchangeRate, ExchangeStatus, Quantum AI views
apps/webhooks/       → SignalBot webhook receiver (TradingView → CCXT trade)
apps/authentication/ → JWT auth, OAuth, OTP
apps/users/          → User profiles
apps/referrals/      → Referral system
apps/subscriptions/  → Subscription plans

config/              → Django settings, URLs, Celery
core/                → Base models (TimeStampedModel, SoftDeleteModel), utils (encryption)
services/            → BotExecutorService, QuantumAIFundService, SubscriptionService
```

---

## Key Design Decisions

- **Adapter pattern** for exchanges (`get_adapter()` factory)
- **Strategy pattern** for trading logic (`get_strategy()` factory)
- **BotEngine accepts plain dict config**, NOT Django models — keeps engine pure Python
- **StrategyConfig stays as a model** — provides default presets per strategy type
- **UUID primary keys** everywhere via `SoftDeleteModel` / `TimeStampedModel`
- **ExchangeCredentials** canonical in `apps/exchanges/`, backward-compat import in `apps/trading/`
- **bot_engine.py uses raw CCXT** — direct `self.exchange.create_order()` calls, no abstraction wrappers

---

## Rules for AI Assistants

### Workflow
- For ANY non-trivial task (3+ steps): plan first, get approval
- If something goes wrong: STOP and re-plan
- Never mark a task complete without verifying it works

### Code Standards
- `apps/trading/strategies/` and `apps/trading/exchanges/` = pure Python (no Django imports)
- Engine accepts plain dict configs, NOT model instances
- All models use UUID PKs via `core/` base classes
- API keys encrypted via Fernet (`core/utils.py`)
- Use factory functions (`get_adapter()`, `get_strategy()`)
- Bot views in `apps/bots/views.py`, payment views in `apps/payments/views.py`
- Old code in `trading/` and `oldbybit.py` is **reference only — DO NOT MODIFY**

### What NOT to Do
- Don't merge `StrategyConfig` into bot models
- Don't create new Django models for engine runtime state — use dicts
- Don't put bot views in `apps/payments/`
- Don't remove `oldbybit.py` or the `trading/` legacy directory
