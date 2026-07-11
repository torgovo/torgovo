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
- **Fix:** Change `Torgovo.settings.TimezoneFormatter` → `config.settings.base.TimezoneFormatter` (or wherever `TimezoneFormatter` is defined) in the LOGGING dict.

### 3. `get_exchange_rates()` Placeholder
- **Location:** `apps/trading/views.py` line ~194
- **Problem:** Returns `Decimal('45000.00')` for all pairs.
- **Fix:** Call CCXT `fetch_ticker()` for live prices, or use `ExchangeRate` model if populated.
