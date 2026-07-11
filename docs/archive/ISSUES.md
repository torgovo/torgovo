# Torgovo — Known Issues & Decisions

## Open Decisions

### 1. `QuantumAIStrategy` class — Keep or Remove?
- **Location:** `apps/trading/strategies/quantum_ai.py`
- **Problem:** All actual logic now lives in `bot_engine.py` (direct port from `oldbybit.py`). The strategy class is a thin wrapper that's never called.
- **Options:** (a) Delete it. (b) Keep as documentation/reference for the algorithm.
- **Recommendation:** Keep as reference, add `# NOTE: Not used in execution — see bot_engine.py` at top.

### 2. `manage.py check` Logging Error
- **Error:** `Cannot resolve 'Torgovo.settings.TimezoneFormatter'`
- **Cause:** `config/settings/base.py` LOGGING config references old module name `Torgovo` instead of `config`.
- **Fix:** Change `Torgovo.settings.TimezoneFormatter` → `config.settings.base.TimezoneFormatter` (or wherever it lives) in the LOGGING dict.

### 3. `get_exchange_rates()` Placeholder
- **Location:** `apps/trading/views.py` line 194
- **Problem:** Returns `Decimal('45000.00')` for all pairs.
- **Fix:** Call CCXT `fetch_ticker()` for live prices, or use `ExchangeRate` model if populated.

---

## Resolved Confusions (For Reference)

| Confusion | Resolution |
|-----------|------------|
| `BotBridge` vs `trading_manager` vs `BotEngine` | All replaced by `BotEngine`. `BotBridge` never existed. `trading_manager` was legacy from `trading/manager.py`. |
| `BotConfiguration` vs `TradingBot` vs bot models | `BotConfiguration` and `TradingBot` removed. Bot models live in `apps/bots/models.py`. Engine uses plain dicts. |
| `ExchangeCredentials` — which one? | Canonical: `apps/exchanges/models.py`. `apps/trading/models.py` has `from apps.exchanges.models import ExchangeCredentials` for backward compat. |
| `CustomBot` vs `SignalBot` | Renamed to `SignalBot` everywhere. Old `CustomBot` references are gone. |
| `execute_with_indicators()` vs `execute()` | Neither — `bot_engine.py` handles all logic internally via `startBot()`. Strategy classes are not called during execution. |
| `from_bot_instance()` vs `from_config()` | `BotExecutor.from_config()` is the correct method. Accepts plain dict. |
| `services/bot_executor_service.py` import path | File is `services/bot_executor.py`, class is `BotExecutorService`. |
