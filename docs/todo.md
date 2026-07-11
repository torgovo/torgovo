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

### Low Priority (functional but imperfect)
- [ ] `get_exchange_rates()` in `apps/trading/views.py` — returns placeholder prices (Decimal('45000'))
- [ ] OKX/MEXC/Alpaca adapters — minimal stubs only (Bybit + Binance are complete)
- [ ] `QuantumAIStrategy` in `strategies/quantum_ai.py` — redundant (logic lives in bot_engine.py). Decide: keep as reference or remove

### Features (Not Yet Started)
- [ ] Telegram notifications — Port `print_details()`, `SendTelegramMessage()`
- [ ] Frontend (React + Vite) — not started
- [ ] Tests — 80%+ coverage target
- [x] Celery Beat scheduling for bot monitoring
- [ ] Admin dashboard endpoints
