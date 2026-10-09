# Torgovo2 — Todo Tracker

## Phase 1: Bot Engine Port (from oldbybit.py)

### Completed ✅
- [x] `bot_engine.py` — Full rewrite using raw CCXT (`self.exchange.create_order()`, `fetch_open_orders()`, etc.)
- [x] Order-ID based `monitor_grid_orders()` — exact port from oldbybit.py
- [x] `monitor_lossProfit()` — SL/TP background thread
- [x] `close_all_orders()` / `close_open_order()` — exact port
- [x] `create_order()` — dollar/coin branching via raw CCXT
- [x] `prepare_order_data()` / `calculate_grids()` — exact port
- [x] `startBot()` — all 12 entry cases + 8 TP exit cases
- [x] `base_adapter.py` — reverted custom wrappers (CCXT called directly)

---

## Phase 2: Architecture Cleanup

### Completed ✅
- [x] Removed `BotConfiguration` + `TradingBot` models from `apps/trading/models.py`
- [x] `StrategyConfig` kept with correct choices (quantum_ai, grid, martingale, signal)
- [x] `apps/trading/serializers.py` — clean, no broken imports
- [x] `apps/trading/views.py` — clean, no BotBridge/BotConfiguration references
- [x] `apps/trading/admin.py` — clean, only StrategyConfigAdmin
- [x] `apps/webhooks/views.py` — uses `SignalBot` (not CustomBot)
- [x] `apps/bots/admin.py` — uses `SignalBot`, correct import paths
- [x] `apps/bots/urls.py` — imports from `apps.bots` (not `apps.payments`)
- [x] `apps/bots/models.py` — `GridBot.save_state()` fixed (no trading_manager)
- [x] `apps/bots/views.py` — `get_or_create_engine()` uses BotEngine (no trading_manager)
- [x] `apps/bots/indicators_views.py` — rewritten with BotEngine + `_engine_registry`
- [x] `apps/trading/tasks.py` — correct imports, `quantum_ai` in `_get_bot_instance()`
- [x] `apps/trading/engines/execution.py` — calls `engine.startBot()` for all bot types
- [x] `services/bot_executor.py` — rewritten with Celery tasks (no trading_manager)
- [x] `config/urls.py` — added investments + referrals URL includes
- [x] `drf_yasg` in INSTALLED_APPS
- [x] `ExchangeCredentials` — canonical in `apps/exchanges/`, backward-compat import in `apps/trading/`
- [x] Model field verification — `Order`/`Indicator` have all required fields

---

## Phase 3: Known Remaining Items

> Status verified against the codebase 2026-08-18 (several items below were
> closed in the meantime by later sessions — see `docs/CHANGELOG.md`).

### Low Priority (functional but imperfect)
- [x] `get_exchange_rates()` in `apps/trading/views.py` — now fetches live CCXT tickers (no longer placeholder Decimal('45000')); falls back to DB when CCXT fails
- [ ] OKX/MEXC/Alpaca adapters — modules exist in `apps/trading/exchanges/` (`okx.py`, `mexc.py`, `alpaca.py`, plus `bybit.py`, `binance.py`, `coinbase.py`, `mock_adapter.py`) but parity/stub status unverified — audit before claiming complete
- [x] `QuantumAIStrategy` in `strategies/quantum_ai.py` — removed (no root `strategies/` dir; logic lives in `bot_engine.py`)

### Features (Not Yet Started)
- [ ] Telegram notifications — `SendTelegramMessage()`/`print_details()` NOT ported from `oldbybit.py`; only partial wiring exists (`apps/trading/engines/order_service.py` notifies when `user.telegram_token`/`telegram_chat_id` attrs exist)
- [ ] Frontend (React + Vite) — scaffold exists (`frontend/` with `src/components`, `contexts`, `services`) but completeness unverified
- [ ] Tests — 80%+ coverage target (current suite 1912 passed / 13 skipped)
- [x] Celery Beat scheduling for bot monitoring
- [ ] Admin dashboard endpoints — no admin analytics/dashboard views found; only per-app Django admin
