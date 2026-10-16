# Torgovo — Functional & Non-Functional Requirements

> **This file is the single source of truth for product requirements.**
> Part A records the locked product decisions from the 2026-10-11 grill-me session
> (no other written record exists — this file IS the record). Where the grill-me
> did not specify a value, it is marked `TBD` — never invent values.
> When product requirements and any other document contradict, **Part A wins**.
>
> **2026-10-14 update:** the 2026-10-13 grill (24 decisions; final A5 mechanism
> locked 2026-10-14) has now been folded into Part A as well — it previously had
> no written record anywhere. Where a 2026-10-13/14 decision conflicts with
> 2026-10-11 text, **the later grill wins**.

---

# Part A — Product Requirements (2026-10-11 grill-me; extended by the 2026-10-13 grill — 24 decisions — with A5 finalized 2026-10-14; later decisions win)

## A1. Product identity & launch posture

| Item | Decision |
|------|----------|
| Public name | **Torgovo** |
| Language | **English only** at launch |
| Support channel | **Email only** |
| KYC | **Not at launch.** Field/flag reserved for a future KYC/AML flow; do not build KYC now. Manual review, ToS/privacy acceptance, and geo-blocking stay **open as pre-real-money blockers** (grill Q1) |
| Company registration | **None at launch.** Entity to be formed later in **Seychelles or RAK (UAE)** |
| Payment rails | **Crypto-only** at launch (no card rails) |
| Geography | **No US persons.** No US marketing; no US/EU marketing for Quantum AI (influencer contracts must carry this restriction). Technical geo-blocking is **deferred until the company entity is formed** (grill Q2) |

## A2. Subscription pricing — Model C

| Plan | Monthly | Annual (20% off) |
|------|---------|------------------|
| Free | $0 | — |
| Basic | **$15** | **$144** *(derived: 15×12×0.8)* |
| Standard | **$25** | **$240** *(derived)* |
| Premium | **$49** | **$470** *(derived)* |
| Creator | **$20** | **$192** *(derived)* |

Annual prices are derived from the locked 20% annual discount rule.

**Free tier entitlements (fully specified in grill-me):**
- Signal bots only (no Grid/Martingale/Quantum AI)
- Max **10 signals/month**
- **1 bot**, **1 exchange connection**, **spot only**

**Paid-tier entitlements (grill 2026-10-13, Q6 — replaces the old `TBD`):**

| Plan | Signals/month | Max bots | Exchange connections |
|------|---------------|----------|----------------------|
| Free | 10 | 1 | 1 |
| Basic | 50 | 3 | 3 |
| Standard | 300 | 5 | 6 |
| Premium | 1500 | 10 | 15 |
| Creator | 100 | 5 | 3 |

Bot types & markets stay as approved in A4 (signal: spot+futures; grid/martingale:
futures only). The whole matrix is **DB-seeded and admin-editable** — the same
rule as prices; never hard-code it.

**Mid-term plan changes (grill Q15):** **upgrades only** — the user pays the price
difference (or full new plan price) via payment code; new limits apply instantly
and the plan end date extends by the purchased term from that date.
**Downgrades are not available mid-term** (they take effect at expiry): no
proration math, no credit ledger, no refunds.

**Admin-driven pricing (hard requirement, 2026-10-11):** every plan attribute —
name, monthly/annual price, annual discount %, feature limits, enabled flag —
must live in the database and be editable from **Django admin only**. The plans
API and any frontend must read from the DB; **no price/plan values may be
hard-coded** in views, serializers, settings, or frontend. Changing a plan in
admin must propagate everywhere with no deploy/rebuild.

**Creator tier:** $20/mo; its distinguishing entitlement is referral **cash
commissions** (see A7). Numeric entitlements: matrix above; any non-numeric
Creator-only extras were not specified in the grill → `TBD`.

No "Enterprise" tier exists (grill Q8): custom/enterprise deals are handled as
an **admin-created plan row + a manual invoice** — no special code path, no
separate tier.

## A3. Payments — manual multi-coin

- Launch flow is **manual multi-coin crypto**, not payment gateways.
- **Admin-configurable** coin/chain list. Launch set: **USDT on TRC20, BEP20, ERC20**.
- Flow:
  1. User selects plan → system generates a **unique payment code** for the order.
  2. A **quote** is created: amount in crypto computed at **live price lock** at
     quote time; the quote has an **expiry**, and its **combined payable amount
     auto-updates every 5 minutes** while the payment window is open (user
     decision 2026-10-14).
   3. User pays on-chain. Verification = **auto-deposit watcher + unique payment
      amounts** (grill Q4): the watcher matches the exact unique amount for the
      code (plan price + chain buffer). The user may also submit a **TX hash** or
      **screenshot** as proof for manual admin verify.
   4. **Admin approval** activates the subscription.
- **Fee display (grill Q5):** the quote is **plan price + per-chain buffer**; the
   UI must show it in the format `TRC20 (fee: 0.20 USDT)`; the payment matcher
   requires the **received amount ≥ plan price** (the buffer covers network fees —
   the user never subsidizes the difference).
- **Final payable amount (user decision 2026-10-14):** the address/proof screen
   MUST show the **combined amount** the user has to send — plan price + chain
   fee — as one figure, e.g. Basic `$15.00` on TRC20 → **`15.20 USDT`**, never
   the plan price alone.
- **Quote expiry (grill Q3): admin-configurable per coin, default 6 hours.**
   After expiry the user must re-request a quote at the then-current price.
- **Stripe/PayPal: later phase**, not launch.
- No US persons; crypto rails only (ties to A1).

## A4. Trading bots

| Bot | Market | Interface |
|-----|--------|-----------|
| **Signal** | **Spot + futures** | Dashboard + JSON webhook |
| **Grid** | **Futures only** | Dashboard + JSON webhook |
| **Martingale** | **Futures only** | Dashboard + JSON webhook |
| **Quantum AI** | Admin-managed pooled fund (traded on **Bybit**) | Deposit/withdraw UI only; users never configure trades |

- **1 bot instance = 1 coin (pair).** No multi-pair bots.
- **Launch exchanges: Bybit + Binance only.** Other existing adapters (OKX, MEXC,
  Alpaca, Coinbase) are **not launch-supported** and must not be advertised.
- **All exchange pairs are selectable** — no pair whitelist (grill Q10).
- **No leverage cap** in our UI: the exchange's own maximum applies, covered by
  the terms of service (grill Q11).
- **Exchange-ID internal transfers: post-launch only** — gated on a 1-day Bybit
  spike check; dedicated sub-account, **never the QAI fund account** (grill Q7).

## A5. Quantum AI — investment terms

*(Fully re-specified by the 2026-10-13 grill, mechanism finalized & locked
2026-10-14 — this replaces the earlier "profit pool" model entirely.)*

- **Lock periods: 30 / 90 / 180 / 365 days.**
- **No early withdrawal during lock** (hard rule): during a lock nothing is ever
  withdrawable, no exceptions.
- **Open to all tiers including Free** (grill Q13); returns are **identical for
  every tier** — the tier-multiplier idea recorded during the grill was dropped
  2026-10-14 as unusable, and no tier differentiation exists in this model.
- **Return crediting (locked mechanism):**
  - Payout is **admin-triggered**, near term maturity: the admin enters a profit
    **percentage (free-form)** based on the actual P/L visible in the admin panel.
    **2–5%** is shown as the committed band / guidance only.
  - The system does exactly one thing with it: `capital × (1 + %/100)` → credits
    the investor's capital. **Nothing else** — no fee split, no reserve/smoothing,
    no profit-pool math, no second calculation.
  - **Credit event: per investor, when their own lock matures** (not a global
    date). Entering/updating the % early credits nothing and unlocks nothing.
  - **Compounding:** credited amounts become capital; an unwithdrawn balance
    carries into the next term and earns again at that maturity.
  - **Rate is lock-independent:** the same % applies to 30/90/180/365-day locks.
- **Withdrawals after lock:** **any amount up to capital + profit** (partial
  withdrawals allowed) via a withdrawal request; admin approves **within 7 days**
  of a valid (post-lock) request. Status shown: **pending / approved / rejected**.
  On approval the admin enters the payout amount **including chain fees** and the
  system debits the ledger (grill Q12).
- **Never stated:** no "system keeps X%" / profit-split figures anywhere — profit
  varies with the fund and must never be guaranteed in UI or marketing.
- Marketing may state the committed band **2–5%** with appropriate fine print
  (this replaces the old 2–10% line).
- Fund assets are held/traded on **Bybit**.
- **Replaces current behavior** (biweekly proportional P/L with reserve/smoothing —
  see Part C §4 and gap G3).

## A6. Subscription expiry lifecycle

- Reminders at **D-7, D-5, D-3, D-1** before expiry (email; in-app notice if
  available). Email is the assumed channel (only support channel at launch).
- **Grace period: 2 days** after expiry — full access retained.
- **Hard stop** after grace: **no new entries are opened**; open positions keep
  riding their existing stop-loss/take-profit; paid access revoked (grill Q9).
- **Data is kept indefinitely** after expiry (bots, history, settings) — purge only
  on account deletion (grill Q17). Re-subscribing restores access to retained data.

## A7. Referrals — hybrid model

- Referrer on **Creator tier** → earns **10% cash commission** on the referee's
  payment(s). Payout (grill Q19): the **10% accrues in the referrer's dashboard →
  they file a payout request (admin-set minimum) → admin pays in crypto and enters
  the amount including fees → the system debits the ledger.**
- Referrer on **any other tier** (incl. Free) → the **referee gets a 15% discount**
  on their payment — **first payment only** (grill Q18).
- **Anti-abuse:** self-referral blocked, duplicate-account detection, idempotent
  code application. (Current implementation already has CSPRNG codes and
  self-referral guards — keep them.)

## A8. Telegram

- Telegram bot = **post-only** notifications to a channel. No interactive trading
  or account actions via Telegram.

## A9. Telegram channel content (grill 2026-10-13)

- The Telegram channel posts **entry + exit only** (grill Q20) — nothing else.
- Stays **post-only** (extends A8): no interactive commands or callbacks.

---

# Part B — Non-Functional Requirements

| Area | Requirement |
|------|-------------|
| Security | Keep current posture: Fernet encryption for exchange keys, JWT rotation, Redis rate limiting, webhook secret + replay protection, **admin approval on every financial operation**, HTTPS/HSTS in production, never log secrets |
| Availability | Celery workers + beat; heartbeat watchdog; crash-consistent bot persistence (shipped 2026-09-28) must not regress |
| Performance | Proposed targets: typical API p95 < 500 ms; webhook → queued order placement < 2 s |
| Observability | Structured logs with user_id/bot_id context; health checks; Prometheus; **Sentry added on top of these (grill Q23) — retained together, nothing replaced** |
| Testing | Full suite green before merge (last verified 2026-09-28: **2170 passed / 13 skipped**); every new feature ships with tests |
| Data retention | Soft-delete models; **user data retained after subscription expiry** (A6) |
| Localization | English only at launch (A1) |
| Rate limiting | Existing DRF throttles + Redis middleware remain |
| Admin-driven config | Plans, prices, payment coins/chains, and Quantum AI fund parameters must be DB-backed and admin-editable — zero hard-coded business values in code or frontend |
| Email delivery | **Own SMTP primary** (SPF/DKIM/DMARC records on the launch checklist) with **Resend/SendGrid as fallback**, both behind a single `send_email()` helper (grill Q22) |
| Backups | **Daily `pg_dump`**, keep **7 daily + 4 weekly**, stored on a separate path, plus a **documented periodic restore test** (grill Q24) |
| Compliance gates | ToS + privacy-policy acceptance required before real-money launch (open blocker, tracked in PROJECT_STATUS.md) |

---

# Part C — As-Is Implementation Baseline

> Implemented behavior, derived from the codebase (`apps/*`, `services/*`,
> `apps/trading/engines/*`) on 2026-08-10; spot re-verified 2026-10-11.
> This section describes **current code**, not requirements. Where current code
> conflicts with Part A, **Part A wins** and the difference is a gap (Part D).

## C1. Authentication (`apps/authentication`)
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

## C2. Users (`apps/users`)
- Custom user (`CustomUser` extends `AbstractUser`) with balance wallet (`UserBalance`).
- Admin panel: user list/detail, dashboard stats, bots overview, create blockchain addresses, trade logs, restrict users, send emails, process withdrawals.

## C3. Exchanges (`apps/exchanges` + `apps/trading`)
- CRUD exchange credentials (`ExchangeCredentials`), encrypted secrets.
- List supported pairs, symbols per exchange (CCXT), exchange status, exchange rates.
- Ownership note: older text claimed `apps/exchanges/*` is legacy and `apps/trading/*`
  is canonical; `docs/PROJECT.md` states the reverse for `ExchangeCredentials`.
  Unresolved at time of writing — see cleanup_plan.md "Issues found 2026-10-11".

## C4. Bots (`apps/bots`)
- **SignalBot** — webhook-driven manual/auto entries, monthly signal limits, positions via condition updates.
- **GridBot** — grid levels both favor/against, dynamic SL/TP placement, loss/profit percent monitoring; start/stop via `grid/<id>/start|stop/`.
- **MartingaleBot** — martingale step sizing, start/stop endpoints.
- **Quantum AI** — `QuantumAIFund` + `ReserveFund` (smoothing/reserve accounting), `QuantumAIBot`, `InvestorPortfolio` (profit sharing), `InvestorDeposit`/`QuantumDepositWallet`, `QuantumWeeklyProfit` distributions. **Current distribution cadence: every 2 weeks (celery beat 14-day interval) — superseded by A5.**
- Configuration: `PairConfig` (per-pair strategy config) and `Indicator` presets.
- Order book: `ActiveOrder`, `BotOrder`.
- Indicator compute endpoints: `indicators/ema/`, `indicators/rsi/`, `indicators/bb/` (live values via CCXT OHLCV).
- `apps/bots/signals.py` syncs `BotOrder` creation to `investments.Order` post-save.

## C5. Trading engine (`apps/trading` + `apps/trading/engines` + `services/bot_executor.py`)
- **BotEngine** (`engines/bot_engine.py`) — strategy config load, condition updates, buy/sell/close orders, grid calculation, grid order monitoring thread, position-based SL/TP (`_place_sltp_orders`, `_refresh_sltp_if_changed`), loss/profit monitor, heartbeat, start/stop, reset state.
- **GridPositionMonitor** (`engines/grid_monitor.py`) — detached thread monitoring open grid positions with injected order-execution callbacks.
- **BotOrderService** (`engines/order_service.py`) — create/close cancel orders (dollar/coin/market/limit, reduceOnly on close, telegram notify).
- **Execution helpers** (`engines/execution.py`) — `BotExecutor.from_config` exists (line 178; verified 2026-10-11); Redis-based locks/state: dedupe via `cache.add`, `_try_redis_lock`, start/stop markers, bot state save/load/clear to prevent double runs.
- **Celery tasks** (`tasks.py`) — `run_trading_bot` (bind/dedupe, restore mode), start/stop bot, `check_all_active_bots`, `check_stale_bots` (dead-bot recovery), `heartbeat_check`, `reset_monthly_signal_limits`, `accrue_quantum_ai_profits` / `distribute_quantum_ai_profits` (exist at tasks.py:405/447; verified 2026-10-11) with reserve crediting.
- **BotExecutorService** (`services/bot_executor.py`) — start/stop grid & martingale bots; execute SignalBot trades via ccxt.
- **WebSocket** — `consumers.py` + `routing.py` real-time bot/trade updates.

## C6. Investments (`apps/investments`)
- `Order`, `Position`, `TechnicalIndicator`, `InvestmentBalance` display models (unified view of trading activity).
- Router: orders, positions, technical-indicators, balances.
- TradingView webhook ingest `tradingview/<webhook_id>/`.
- Indicator webhooks: `indicators/ema/`, `indicators/rsi/` (compute + trigger matching bots).
- User orders, user profile, blockchain addresses, quantum deposit endpoints.

## C7. Payments & subscriptions (`apps/payments` + `services/subscription_service.py`)
- `SubscriptionPlan`, `BotSubscriptionPlan`, `BotSubscription` (approval workflow).
- Admin approve/reject deposits (`admin/deposits/<id>/approve|reject/`) and bot subscriptions.
- Create deposit for Quantum AI (`quantum-ai/<bot_id>/deposit/`), `InvestorDeposit`.
- `WithdrawalRequest` + admin processing; `PaymentTransaction` ledger; `ReferralPayout`.
- `BlockchainAddress` management + list endpoint.
- **SubscriptionService** — approve (creates `InvestorPortfolio` for the plan amount), reject (records reason), pending list, dashboard stats.
- Three plan systems exist: `TelegramSignalPlan`, `SubscriptionPlan` (Free/Basic/Premium/Enterprise — **not Model C**, see gap G1), `BotSubscriptionPlan` (30/90/180/365-day per-bot pricing).

## C8. Referrals (`apps/referrals`)
- Apply referral code `apply/` (CSPRNG codes, self-referral/duplicate/idempotency guards).
- My stats `my-stats/` — legacy stats + G5 hybrid reward fields (`reward_model`, commission pending/paid, payout minimum, referee discount).
- Payout requests `payout-requests/` GET+POST (G5/FR A7 — accrual → request → admin pays → ledger debit).

## C9. Telegram signals subscriptions (`apps/subscriptions`)
- Plans (public), channels admin CRUD, `TelegramSubscription` + subscription↔channel links.
- `TradingSignal` (broadcast to subscribed channels) + `SignalResult` (fill results) + `SignalStatistics`.
- Employee/plan usage: `telegram/my-usage/`, `my-subscription/`, subscribe flow.
- Bot subscriptions: `bot-plans/`, `bot-subscribe/` (creates `BotSubscription` pending_payment, 409 on duplicate), `bot-my-usage/`.
- This module is a **Telegram signal-broadcast product**, distinct from the A8 post-only notification bot (gap G7).

## C10. Webhooks (`apps/webhooks`)
- `SignalBotWebhookView` (POST) — single endpoint at `/api/webhooks/custombot/`; AllowAny auth; validates + executes signal bot trades via `execute_trade` using ccxt.
- `WebhookLog` records every ingested webhook for audit.

## C11. Cross-cutting
- Health checks (`/ht/`), Prometheus metrics (`/` via django-prometheus), Django admin (`/admin/`), SILK + Django Debug Toolbar (dev only).
- Rate limiting middleware (Redis/cache-backed) on API.
- Auditing: `WebhookLog`, `PaymentTransaction`, `ReserveTransaction`.

---

# Part D — Gaps: requirements (A) vs implementation (C)

Code-level issue register: `docs/CODE_AUDIT_REPORT.md` (re-verify before acting —
B1 already disproven, C2 likely stale; see cleanup_plan.md).

| ID | Gap | Target |
|----|-----|--------|
| G1 | Pricing: no Model C tiers (Free/Basic $15/Standard $25/Premium $49/Creator $20; annual 20% off; free-tier limits) | A2 |
| G2 | Payments: no unique payment code, no quote expiry, no live-price lock, no admin-configurable coin/chain list (TRC20/BEP20/ERC20) | A3 |
| G3 | Quantum AI: biweekly reserve/smoothing distribution ≠ locks 30–365d + admin-entered 2–5% capital credit at per-investor maturity (compounding, lock-independent rate) + post-lock withdrawable capital+profit with ≤7-day manual payout (specified 2026-10-14) | A5 |
| G5 | Referrals: rewards ≠ Creator 10% cash (accrual → request → admin pays crypto → ledger debit) / else 15% first-payment referee discount | A7 |
| G6 | Bots: Grid/Martingale not futures-only; 1-bot-1-coin not enforced; exchanges beyond Bybit/Binance advertised | A4 |
| G7 | No post-only Telegram notification bot (current `apps/subscriptions` is a different product) | A8 |
| G8 | Compliance: no KYC flag, no geo-restriction (US), no ToS/privacy acceptance gate | A1 |
| G9 | Legacy root `trading/` directory still on disk (0 active imports from `apps/` — verified 2026-10-11); Phase 0 roadmap: remove | cleanup |

**Closed:** G1 (2026-10-12 — Model C admin plans) · G2 (2026-10-12 — payment codes, live quote lock, admin coin list; CHANGELOG) · G3 (2026-10-16 — per-investor Quantum AI locks; CHANGELOG) · G4 (2026-10-15 — grace/hard-stop/reminders/restore; CHANGELOG) · G5 (2026-10-16 — hybrid commission/referee-discount rewards + payout requests; 48 tests). Row kept above for audit trail.
