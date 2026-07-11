# Torgovo — Changelog

All notable changes to the platform are documented here.

## [1.1.0] - 2026-05-19

### Changed
- **Renamed `CustomBot` → `SignalBot`** across models, serializers, views, and API endpoints.
- Signal bot API endpoint: `/api/bots/signal-bots/` (was `/api/bots/webhook-alerts/`).
- Quantum AI deposit/balance endpoints moved to `/api/investments/quantum/`.
- **Removed obsolete models** `BotConfiguration` and `TradingBot` from `apps/trading/models.py`.
- **Rewrote bot engine** — ported from `oldbybit.py` to `BotEngine` using raw CCXT (no `trading_manager`).
- **Replaced `BotExecutorService`** with Celery tasks + plain dict configs.

### Added
- `QuantumAIBot` model (admin-managed trading bot for pooled funds).
- `shown_percentage` field (5–20%) to `QuantumAIFund` — admin configurable.
- `CLAUDE.md` — single source of AI assistant coding rules.
- `CHANGELOG.md` — this file.

### Fixed
- `apps/bots/indicators_views.py` — now uses `BotEngine` via `_engine_registry` instead of broken `BotExecutionLog`.
- `apps/bots/admin.py` — correct start/stop action methods for all bot types.
- `apps/bots/urls.py` — imports from `apps.bots` (not `apps.payments`).
- `apps/trading/tasks.py` — includes `quantum_ai` in `_get_bot_instance()`.
- `apps/trading/engines/execution.py` — routes all bot types to `engine.startBot()`.
- `services/bot_executor.py` — uses Celery tasks (no `trading_manager`).
- `config/urls.py` — includes `investments` and `referrals` routing.
- `QUICK_START.md` — corrected `Exchange` import path (`apps.trading.models`, not `apps.bots.models`).

### Removed
- `trading/manager.py` — unused legacy code.
- All references to `BotBridge`, `from_bot_instance()`, `execute_with_indicators()`.
- Stale "Resolved Confusions" section from `ISSUES.md`.
- Outdated interrupted-tasks section from `latest_details.md`.

## [1.0.0] - 2024-01-15

- Initial release with core trading features, webhook alerts, grid/martingale bots, Quantum AI deposit system, and multi-exchange support.
