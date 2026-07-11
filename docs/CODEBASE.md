# Torgovo — Codebase Status

> Current state of every module as of 2026-05-19.

## ✅ Fully Working

| File/Module | Status | Notes |
|-------------|--------|-------|
| `apps/bots/models.py` | ✅ | SignalBot, GridBot, MartingaleBot, QuantumAIBot, QuantumAIFund, Indicator, Order, PairConfig |
| `apps/bots/views.py` | ✅ | All ViewSets, admin indicator views, `get_or_create_engine()` helper |
| `apps/bots/serializers.py` | ✅ | All bot serializers |
| `apps/bots/urls.py` | ✅ | DRF router + indicator + start/stop paths |
| `apps/bots/admin.py` | ✅ | All models registered, start/stop actions use `BotExecutorService` |
| `apps/bots/indicators_views.py` | ✅ | EMA/RSI/BB webhooks → BotEngine via `_engine_registry` |
| `apps/trading/models.py` | ✅ | Exchange, TradingPair, ExchangeStatus, StrategyConfig (no stale models) |
| `apps/trading/serializers.py` | ✅ | Clean — no broken imports |
| `apps/trading/views.py` | ✅ | Exchange/TradingPair/StrategyConfig ViewSets + FBVs |
| `apps/trading/admin.py` | ✅ | StrategyConfigAdmin only |
| `apps/trading/tasks.py` | ✅ | `run_trading_bot`, `stop_bot`, `check_all_active_bots`, `_get_bot_instance` |
| `apps/trading/engines/bot_engine.py` | ✅ | Full port from oldbybit.py — raw CCXT, grid monitor, SL/TP thread |
| `apps/trading/engines/execution.py` | ✅ | `BotExecutor.from_config()` → `engine.startBot()` |
| `apps/trading/strategies/` | ✅ | BaseStrategy + 4 subclasses (pure Python) |
| `apps/trading/exchanges/` | ✅ | Adapter pattern, Bybit + Binance fully implemented |
| `apps/webhooks/views.py` | ✅ | SignalBotWebhookView with raw CCXT execution |
| `apps/exchanges/` | ✅ | ExchangeCredentials (canonical), handlers |
| `apps/payments/views.py` | ✅ | Payment-only views |
| `apps/investments/` | ✅ | Quantum AI investment views |
| `apps/referrals/` | ✅ | Referral system |
| `services/bot_executor.py` | ✅ | BotExecutorService — start/stop via Celery tasks |
| `services/quantum_ai_fund.py` | ✅ | Profit distribution logic |
| `config/settings/base.py` | ✅ | All apps + drf_yasg in INSTALLED_APPS |
| `config/urls.py` | ✅ | All apps routed including investments + referrals |

## ⚠️ Known Limitations (Not Broken)

| File | Issue | Priority |
|------|-------|----------|
| `apps/trading/views.py` `get_exchange_rates()` | Returns hardcoded placeholder prices | Low |
| `apps/trading/exchanges/okx.py` | Minimal adapter stub | Low |
| `apps/trading/exchanges/mexc.py` | Minimal adapter stub | Low |
| `apps/trading/exchanges/alpaca.py` | Minimal adapter stub | Low |
| `apps/trading/strategies/quantum_ai.py` | Redundant — logic lives in bot_engine.py | Low |

## 🔴 Pre-existing Config Issue

| Issue | Details |
|-------|---------|
| `manage.py check` fails | Logging config references `Torgovo.settings.TimezoneFormatter` — old module name. Not related to any code changes. |
