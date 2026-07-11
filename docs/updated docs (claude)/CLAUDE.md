# CLAUDE.md — AI Assistant Rules for Torgovo

This file is the single source of coding rules and conventions for AI assistants working on this codebase. It supersedes duplicate rule sections in `PROJECT.md` and `latest_details.md`.

---

## Workflow Rules

- For ANY non-trivial task (3+ steps or architectural decisions): write a plan first, get approval, then implement.
- If something goes wrong mid-task: STOP and re-plan. Do not keep pushing.
- Never mark a task complete without verifying it works.
- After any correction: note the pattern to avoid repeating it.

---

## Code Standards

### Module boundaries
- `apps/trading/strategies/` and `apps/trading/exchanges/` = **pure Python only** — no Django imports.
- Engine (`BotEngine`, `BotExecutor`) accepts **plain dict configs**, never Django model instances.
- Bot CRUD views → `apps/bots/views.py`. Payment views → `apps/payments/views.py`. Never mix.

### Models
- All domain models use UUID PKs via `SoftDeleteModel` or `TimeStampedModel` from `core/`.
- API keys always encrypted with Fernet (`core/utils.py`). Never store plaintext.
- ExchangeCredentials canonical location: `apps/exchanges/models.py`.

### Bot execution flow
```
View → BotExecutorService (services/bot_executor.py)
     → Celery task (apps/trading/tasks.py)
     → BotExecutor.from_config(dict) (apps/trading/engines/execution.py)
     → BotEngine.startBot() (apps/trading/engines/bot_engine.py)
```

### CCXT
- Leave all actual trade execution as: `# TODO: Implement CCXT trade execution`
- Never call CCXT synchronously in a request/response cycle — always via Celery task.

### Logging
- Use Python `logging` module. Never `print()` in production code.
- Levels: `DEBUG` = detailed flow, `INFO` = business events, `WARNING` = recoverable issues, `ERROR` = failures, `CRITICAL` = system down.
- Always include context: `user_id`, `bot_id`, `exchange`, `pair` in log messages.
- Never log API keys, passwords, or `secret_key` values.

### DRF conventions
- All validation in serializers, never in views.
- Error response format: `{"error": {"code": "...", "message": "...", "details": {...}}}`.
- List endpoints always return `{count, next, previous, results}`.

---

## Deleted / Renamed — Never Reference

| Old | Current |
|-----|---------|
| `CustomBot` | `SignalBot` (`apps/bots/models.py`) |
| `BotConfiguration` | removed |
| `TradingBot` | removed |
| `trading_manager` | removed → use `BotEngine` |
| `BotBridge` | never existed |
| `from_bot_instance()` | removed → use `from_config()` |
| `execute_with_indicators()` | removed → use `startBot()` |

---

## What NOT to Do

- Don't merge `StrategyConfig` into bot models — keep it separate.
- Don't create new Django models for engine runtime state — use dicts.
- Don't reference `oldbybit.py` or `trading/` legacy directory in new code — reference only.
- Don't implement actual CCXT trade execution — leave as TODO.
- Don't put bot views in `apps/payments/`.

---

## Open Issues (Low Priority)

1. `manage.py check` logging error — fix: change `Torgovo.settings.TimezoneFormatter` → `config.settings.base.TimezoneFormatter` in `config/settings/base.py` LOGGING dict.
2. `get_exchange_rates()` returns placeholder prices — fix: call CCXT `fetch_ticker()`.
3. OKX/MEXC/Alpaca adapters are stubs — Bybit + Binance are complete.
4. `QuantumAIStrategy` in `strategies/quantum_ai.py` is unused — logic lives in `bot_engine.py`. Decide: keep as reference or delete.

---

## Not Yet Started

- Frontend (React + Vite)
- Tests (80%+ coverage target)
- Telegram notifications
- Admin dashboard endpoints
- WebSocket support
