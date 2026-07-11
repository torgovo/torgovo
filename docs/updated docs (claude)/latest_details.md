# Torgovo — Project Context (Last Updated: 2026-06-03)

## What Is This File
Reference for AI assistants and new developers. Contains architecture decisions, bot type descriptions, and coding rules.

For current status: see `CODEBASE.md` and `CHANGELOG.md`.
For coding rules: see `CLAUDE.md`.

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

## 3. Architecture

```
apps/bots/           → Bot domain models + API views (user-facing CRUD)
  models.py          → SignalBot, GridBot, MartingaleBot, QuantumAIFund, QuantumAIBot,
                       QuantumAIInvestment, QuantumDeposit, QuantumWeeklyProfit,
                       PairConfig, Indicator, Order, TelegramSignal*
  views.py           → All bot ViewSets
  indicators_views.py → Async indicator webhook views (EMA/RSI/BB)
  admin.py           → Admin with start/stop actions
  urls.py            → Bot API routes

apps/trading/        → Trading engine (internal, pure Python where possible)
  strategies/        → BaseStrategy, QuantumAI, Grid, Martingale, Signal (pure Python)
  exchanges/         → CCXT adapters: Binance, Bybit, OKX, MEXC, Alpaca (pure Python)
  engines/           → BotEngine (core logic), BotExecutor (orchestration)
  models.py          → Exchange, ExchangeCredentials, TradingPair, ExchangeStatus,
                       SupportedBlockchain, ExchangeRate, StrategyConfig
  tasks.py           → Celery async tasks

apps/payments/       → Payment-only views (subscriptions, deposits, withdrawals, admin approval)
apps/exchanges/      → Exchange CRUD + ExchangeCredentials (canonical location)
apps/investments/    → Quantum AI investment views + serializers
apps/webhooks/       → SignalBot webhook receiver (TradingView → CCXT trade)
apps/authentication/ → JWT auth, OAuth, OTP
apps/users/          → User profiles
apps/referrals/      → Referral system
apps/subscriptions/  → Subscription plans

config/              → Django settings, URLs, Celery
core/                → Base models (TimeStampedModel, SoftDeleteModel), utils (encryption)
services/            → BotExecutorService, QuantumAIFundService, SubscriptionService
trading/             → OLD legacy code (oldbybit.py manager) — DO NOT MODIFY, reference only
```

**Key Design Decisions:**
- **Adapter pattern** for exchanges (`get_adapter()` factory)
- **Strategy pattern** for trading logic (`get_strategy()` factory)
- **Engine accepts plain dict config**, NOT Django models — keeps engine pure Python
- **StrategyConfig stays as a model** — provides default presets per strategy type
- **UUID primary keys** everywhere
- **SoftDeleteModel** base for all domain models
- **ExchangeCredentials** canonical in `apps/exchanges/`, backward-compat import in `apps/trading/`
- **bot_engine.py uses raw CCXT** — direct `self.exchange.create_order()` calls

---

## 4. Current Status (as of 2026-05-19)

All critical architecture issues have been resolved. See `CODEBASE.md` for the full module status table and `CHANGELOG.md` for what changed.

**Remaining low-priority items** (see `todo.md` Phase 3):
- `get_exchange_rates()` returns placeholder prices
- OKX/MEXC/Alpaca adapters are minimal stubs
- `manage.py check` logging error (fix: `Torgovo.settings` → `config.settings.base` in LOGGING dict)
- `QuantumAIStrategy` is redundant (logic lives in bot_engine.py) — keep or delete

**Not yet started:**
- Frontend (React + Vite)
- Tests (80%+ coverage target)
- Telegram notifications
- Admin dashboard endpoints

---

## 5. BotExecutor Config Dict Pattern

Views build a plain dict and pass it to the engine — never pass Django model instances:

```python
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
        # ...
    }
}
executor = BotExecutor.from_config(config)
executor.run()
```

Merge order: `StrategyConfig defaults` → `bot model field overrides` → `final config dict`

---

## 6. Deleted / Renamed (Never Reference These)

| Old Name | Current Name | Location |
|----------|-------------|----------|
| `CustomBot` | `SignalBot` | `apps/bots/models.py` |
| `BotConfiguration` | removed | — |
| `TradingBot` | removed | — |
| `trading_manager` | removed | use `BotEngine` |
| `BotBridge` | never existed | — |
| `from_bot_instance()` | removed | use `from_config()` |
| `execute_with_indicators()` | removed | use `startBot()` |
