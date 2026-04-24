# Torgovo — Project Context & Status (Last Updated: 2026-04-23)

## What Is This File
Single source of truth for any AI assistant continuing work on this project. Read this FIRST before touching code.

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
  views.py           → All bot ViewSets (moved FROM payments)
  serializers.py     → Bot serializers
  urls.py            → Bot API routes
  indicators_views.py → Async indicator webhook views (EMA/RSI/BB)

apps/trading/        → Trading engine (internal)
  strategies/        → BaseStrategy, QuantumAI, Grid, Martingale, Signal (pure Python)
  exchanges/         → CCXT adapters: Binance, Bybit, OKX, MEXC, Alpaca (pure Python)
  engines/           → BotEngine (the main executor), BotExecutor (factory/adapter bridge)
  models.py          → Exchange, ExchangeCredentials, TradingPair, ExchangeStatus,
                       SupportedBlockchain, ExchangeRate, StrategyConfig
  tasks.py           → Celery async tasks

apps/payments/       → Payment-only views (subscriptions, deposits, withdrawals, admin approval)
apps/exchanges/      → Exchange CRUD (has its own ExchangeCredentials — DUPLICATE, see issues)
apps/investments/    → Quantum AI investment views + serializers
apps/webhooks/       → Webhook receiver endpoints
apps/authentication/ → JWT auth, OAuth, OTP
apps/users/          → User profiles
apps/referrals/      → Referral system
apps/subscriptions/  → Subscription plans

config/              → Django settings (base.py, urls.py)
core/                → Base models (TimeStampedModel, SoftDeleteModel), utils (encryption)
services/            → Service layer (SubscriptionService, BotExecutorService, QuantumAIFundService)
trading/             → OLD legacy code — DO NOT MODIFY, reference only
oldbybit.py          → Original Bybit bot code — reference only
```

**Key Design Decisions:**
- **Adapter pattern** for exchanges (`get_adapter()` factory)
- **BotEngine uses raw CCXT** — `self.exchange` is the CCXT instance directly. All calls (`create_order`, `fetch_open_orders`, `fetch_order`, `cancel_all_orders`, etc.) go through CCXT, NOT wrapper methods
- **Engine accepts plain dict config** for initialization, but all runtime state is on the engine instance (same pattern as `oldbybit.py`)
- **StrategyConfig stays as a model** — provides default presets per strategy type
- **UUID primary keys** everywhere
- **SoftDeleteModel** base for all domain models

---

## 4. What Has Been Done

### ✅ Completed
| Change | Files |
|--------|-------|
| Renamed `CustomBot` → `SignalBot` everywhere | models, serializers, views, admin, urls |
| Added `QuantumAIBot` model | `apps/bots/models.py` |
| Added `shown_percentage` to `QuantumAIFund` | `apps/bots/models.py` |
| Moved bot ViewSets to `apps/bots/views.py` | `apps/bots/`, `apps/payments/` |
| Removed `BotConfiguration`, `TradingBot` models | `apps/trading/models.py` |
| Kept `StrategyConfig` with updated choices | `apps/trading/models.py` |
| Rewrote `apps/payments/views.py` — payment-only | `apps/payments/views.py` |
| Fixed `apps/trading/serializers.py` — removed deleted model refs | `apps/trading/serializers.py` |
| Fixed `apps/trading/views.py` — removed stale BotBridge/BotConfig code | `apps/trading/views.py` |
| Fixed `apps/trading/admin.py` — updated to StrategyConfig | `apps/trading/admin.py` |
| Fixed `apps/bots/admin.py` — SignalBot + QuantumAIBot | `apps/bots/admin.py` |
| Fixed `apps/webhooks/` — SignalBotWebhookView | views.py, urls.py |
| Fixed `apps/trading/urls.py` — StrategyConfigViewSet | `apps/trading/urls.py` |
| **Rewrote `BotEngine`** — full port of `oldbybit.py` using raw CCXT | `apps/trading/engines/bot_engine.py` |
| **Ported `monitor_grid_orders`** — order-ID based monitoring loop | `bot_engine.py` |
| **Ported `monitor_lossProfit`** — SL/TP background thread | `bot_engine.py` |
| **Ported `calculated_grid_orders`** — initial order + grid placement | `bot_engine.py` |
| **Ported `close_all_orders` / `close_open_order`** — position closing | `bot_engine.py` |
| **Ported `create_order`** — dollar/coin CCXT branching | `bot_engine.py` |
| **Ported `prepare_order_data` / `calculate_grids`** — grid math | `bot_engine.py` |
| Reverted `base_adapter.py` — no custom wrappers needed | `base_adapter.py` |
| Fixed `execution.py` `_handle_error()` — was calling `.status`/`.save()` on dict | `apps/trading/engines/execution.py` |
| Added `_update_bot_status()` static method for proper model updates | `apps/trading/engines/execution.py` |
| Fixed missing `settings` import in `bots/admin.py` | `apps/bots/admin.py` |
| **Resolved duplicate `ExchangeCredentials`** — removed from `apps/trading/models.py`, canonical is `apps.exchanges` | `apps/trading/models.py`, `admin.py` |
| Fixed duplicate admin registrations in `apps/trading/admin.py` — now only `StrategyConfig` | `apps/trading/admin.py` |
| Added missing `Exchange` admin registration to `apps/exchanges/admin.py` | `apps/exchanges/admin.py` |

✅ **`python manage.py check` passes** — only infra warnings (Daphne ordering + missing static dir). **No blocking bugs remain.**

---

## 5. BotEngine Architecture (NEW — Important)

`BotEngine` in `apps/trading/engines/bot_engine.py` is now a **direct port of `oldbybit.py`**.

- `self.exchange` = raw CCXT exchange instance (from adapter)
- All CCXT calls are identical to `oldbybit.py`: `self.exchange.create_order()`, `self.exchange.fetch_open_orders()`, `self.exchange.fetch_order()`, `self.exchange.create_market_buy_order_with_cost()`, `self.exchange.fetch_position()`, `self.exchange.cancel_all_orders()`, `self.exchange.amount_to_precision()`
- State fields match exactly: `self.count`, `self.current_side`, `self.monitoring`, `self.favor_lvl`, `self.against_lvl`, `self.Percentage`, `self.Unrealized_Pnl`, etc.
- Entry point: `engine.startBot()` (evaluates conditions → opens position → starts grid + SL/TP threads)
- `execute_once()` is an alias that wraps `startBot()` in try/except and returns a result dict

---

## 6. Remaining Work (Future — No Blocking Bugs)

1. ~~Celery Beat scheduling~~ ✅ Done — `check_all_active_bots` every 60s, `distribute_quantum_ai_profits` every 14 days
2. ~~Quantum AI profit distribution Celery task~~ ✅ Done — `apps/trading/tasks.py`
3. Admin dashboard endpoints
4. Frontend (React + Vite)
5. Tests (80%+ coverage target)

---

## 7. Rules for AI Assistants

- Read this file FIRST before any code changes
- For non-trivial tasks: plan → approve → execute
- Keep explanations short and precise
- `BotEngine` uses raw CCXT directly — do NOT add wrapper methods
- Engine gets initialized with a config dict, works with CCXT after that
- All models use UUID PKs via `SoftDeleteModel` or `TimeStampedModel`
- API keys encrypted using Fernet (`core/utils.py`)
- Bot views in `apps/bots/`, payment views in `apps/payments/`
- Old code (`trading/`, `oldbybit.py`) is reference-only — DO NOT MODIFY
- Do NOT remove `oldbybit.py` until user says so
