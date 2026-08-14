# Torgovo2 — Functional Requirements (by module)

Derived from the codebase (`apps/*`, `services/*`, `apps/trading/engines/*`) on 2026-08-10.
Every requirement below reflects implemented behavior, not planned features.

---

## 1. Authentication (`apps/authentication`)
- Register `/api/auth/register/` — create account, auto-generate referral code.
- Login `/api/auth/login/` — JWT access + refresh issued on success.
- Logout `/api/auth/logout/`.
- User detail `/api/auth/user/` — current profile.
- Email verification — request + confirm via token (`verify-email/`, `verify-email/<token>/`).
- Phone verification — request + confirm (`verify-phone/`, `verify-phone/confirm/`).
- Password reset — request + confirm token (`password-reset/`, `password-reset/confirm/`).
- Change password `/api/auth/change-password/`.
- Google OAuth `/api/auth/google/`.
- Refresh token `/api/auth/refresh-token/`.
- Data models: `EmailVerification`, `PhoneVerification`, `PasswordResetToken`, `LoginAttempt`.

## 2. Users (`apps/users`)
- Custom user (`CustomUser` extends `AbstractUser`, into-users models) with balance wallet (`UserBalance`).
- Admin panel: user list/detail, dashboard stats, bots overview, create blockchain addresses, trade logs, restrict users, send emails, process withdrawals.

## 3. Exchanges (`apps/exchanges` + `apps/trading` legacy layer)
- CRUD exchange credentials (`ExchangeCredentials`), encrypted secrets.
- List supported pairs, symbols per exchange (CCXT), exchange status, exchange rates.
- Note: `apps/exchanges/*` is a legacy duplicated layer; `apps/trading/*` is the current unified API (router: exchanges, credentials, pairs, status, strategy-configs).

## 4. Bots (`apps/bots`)
- **SignalBot** — webhook-driven manual/auto entries, monthly signal limits, positions via condition updates.
- **GridBot** — grid levels both favor/against, dynamic SL/TP placement, loss/profit percent monitoring; start/stop via `grid/<id>/start|stop/`.
- **MartingaleBot** — martingale step sizing, start/stop endpoints.
- **Quantum AI** — `QuantumAIFund` + `ReserveFund` (smoothing/reserve accounting), `QuantumAIBot`, `QuantumAIInvestment` (profit sharing), `QuantumDeposit`/`QuantumDepositWallet`, `QuantumWeeklyProfit` distributions.
- Configuration: `PairConfig` (per-pair strategy config) and `Indicator` presets.
- Order book: `ActiveOrder`, `BotOrder`.
- Indicator compute endpoints: `indicators/ema/`, `indicators/rsi/`, `indicators/bb/` (live values via CCXT OHLCV).
- `apps/bots/signals.py` syncs `BotOrder` creation to `investments.Order` post-save.

## 5. Trading engine (`apps/trading` + `apps/trading/engines` + `services/bot_executor.py`)
- **BotEngine** (`engines/bot_engine.py`) — strategy config load, condition updates, buy/sell/close orders, grid calculation, grid order monitoring thread, position-based SL/TP (`_place_sltp_orders`, `_refresh_sltp_if_changed`), loss/profit monitor, heartbeat, start/stop, reset state.
- **GridPositionMonitor** (`engines/grid_monitor.py`) — detached thread monitoring open grid positions with injected order-execution callbacks.
- **BotOrderService** (`engines/order_service.py`) — create/close cancel orders (dollar/coin/market/limit, reduceOnly on close, telegram notify).
- **Execution helpers** (`engines/execution.py`) — Redis-based locks/state: dedupe via `cache.add`, `_try_redis_lock`, start/stop markers, bot state save/load/clear to prevent double runs.
- **Celery tasks** (`tasks.py`) — `run_trading_bot` (bind/dedupe, restore mode), start/stop bot, `check_all_active_bots`, `check_stale_bots` (dead-bot recovery), `heartbeat_check`, `reset_monthly_signal_limits`, `accrue_quantum_ai_profits` / `distribute_quantum_ai_profits` with reserve crediting.
- **BotExecutorService** (`services/bot_executor.py`) — start/stop grid & martingale bots; execute SignalBot trades via ccxt.
- **WebSocket** — `consumers.py` + `routing.py` real-time bot/trade updates.

## 6. Investments (`apps/investments`)
- `Order`, `Position`, `TechnicalIndicator`, `InvestmentBalance` display models (unified view of trading activity).
- Router: orders, positions, technical-indicators, balances.
- TradingView webhook ingest `tradingview/<webhook_id>/`.
- Indicator webhooks: `indicators/ema/`, `indicators/rsi/` (compute + trigger matching bots).
- User orders, user profile, blockchain addresses, quantum deposit endpoints.

## 7. Payments & subscriptions (`apps/payments` + `services/subscription_service.py`)
- `SubscriptionPlan`, `BotSubscriptionPlan`, `BotSubscription` (approval workflow).
- Admin approve/reject deposits (`admin/deposits/<id>/approve|reject/`) and bot subscriptions.
- Create deposit for Quantum AI (`quantum-ai/<bot_id>/deposit/`), `QuantumAIDeposit`.
- `WithdrawalRequest` + admin processing; `PaymentTransaction` ledger; `ReferralPayout`.
- `BlockchainAddress` management + list endpoint.
- **SubscriptionService** — approve (creates `QuantumAIInvestment` for the plan amount), reject (records reason), pending list, dashboard stats.

## 8. Referrals (`apps/referrals`)
- Apply referral code `apply/` (CSPRNG codes, self-referral/duplicate/idempotency guards).
- My stats `my-stats/` — earned rewards/denominations.

## 9. Telegram signals subscriptions (`apps/subscriptions`)
- Plans (public), channels admin CRUD, `TelegramSubscription` + subscription↔channel links.
- `TradingSignal` (broadcast to subscribed channels) + `SignalResult` (fill results) + `SignalStatistics`.
- Employee/plan usage: `telegram/my-usage/`, `my-subscription/`, subscribe flow.
- Bot subscriptions: `bot-plans/`, `bot-subscribe/` (creates `BotSubscription` pending_payment, 409 on duplicate), `bot-my-usage/`.

## 10. Webhooks (`apps/webhooks`)
- `SignalBotWebhookView` (POST) — single endpoint at `/api/webhooks/custombot/`; AllowAny auth; validates + executes signal bot trades via `execute_trade` using ccxt.
- `WebhookLog` records every ingested webhook for audit.

## 11. Cross-cutting
- Health checks (`/ht/`), Prometheus metrics (`/` via django-prometheus), Django admin (`/admin/`), SILK + Django Debug Toolbar (dev only).
- Rate limiting middleware (Redis/cache-backed) on API.
- Auditing: `WebhookLog`, `PaymentTransaction`, `ReserveTransaction`.
