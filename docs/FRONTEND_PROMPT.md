# Torgovo — Frontend Integration Brief (Prompt for Frontend AI)

> **What this is:** a complete, verified reference for building/adapting a frontend against the Torgovo backend API. Every route below was read directly from Django `urls.py` and views/serializers source on **2026-08-21**, re-verified and updated **2026-10-07** (API-consistency fixes A5/A7/A8/A9/A10/A14/A15/A16: uniform error envelope, 409 conflicts, always-200 `my-subscription/`, pk-or-slug plan ids, public plan lists). Treat this as the single source of truth for contracts, auth, security constraints, and limitations.
>
> **What to do (grill Q21, 2026-10-13):** the frontend is the real dashboard repo **`MuhammadUlHasnain/torgovo-quantum-trader`** — it is THE frontend (the local `torgovo2/frontend/` scaffold stub is dead and must NOT be resurrected). It already contains `src/App.tsx` (routes, §14.5), `src/lib/api.ts` (fetch `ApiClient`), `src/lib/authToken.ts`, and `src/types/api.ts` (⚠️ models the OLD backend — replace from §14.4). This doc is NOT yet a complete handoff: first **finish these sections + sync them with that repo's actual code**, then hand it to the frontend AI.
>
> **Merged (2026-10-07):** `docs/frontend-connectivity.md` and `docs/FRONTEND.md` were absorbed into this file (originals preserved in `docs/archive/`). Auth token keys, refresh body, pagination type, and WebSocket status were re-verified against source on 2026-10-07 — where this doc previously disagreed (e.g. `access`/`refresh` keys), **this doc is now corrected**.

---

## 1. Project Overview

| Item | Value |
|---|---|
| Backend | Django + Django REST Framework (Python 3.12) |
| API prefix | `https://<host>/api/` |
| Auth | JWT (djangorestframework-simplejwt), **rotate + blacklist**, separate signing key |
| Access token TTL | 15 minutes |
| Refresh token TTL | 7 days |
| Data format | JSON (`application/json`), snake_case keys as DRF emits them |
| Pagination | DRF **page-number** pagination (`core.pagination.StandardResultsSetPagination`, default 20/page, `?page=&page_size=` max 100) where viewsets paginate → `count`, `next`, `previous`, `results` |
| Health check | `GET /ht/` (django-health-check) |
| Metrics | `GET /metrics/` (Prometheus, ops only) |
| Django Admin | `GET /admin/` (staff only — never expose to end users) |

### Global webhook (public, secret-in-body)
- `POST /api/webhooks/custombot/` — TradingView alert delivery. **No auth header.** Authenticates via `X-Signature` HMAC **or** a `secret` field in the JSON body matched against the bot's `secret_key`. `401` = missing credentials, `403` = wrong secret. **Frontend never calls this** — it exists for external alert services.

### Base URLs & headers
```
Development: http://localhost:8000
Production:  https://api.torgovo.com
```
```
Authorization: Bearer <access_token>        (most endpoints)
Content-Type:  application/json
X-Webhook-Token: <uuid>                     (only for indicator webhooks — backend/external, not frontend)
```

### Stack decisions (recommended)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Framework | React 18+ with Vite + TypeScript | TS-first; interfaces in §14.4 |
| Routing | react-router-dom v6 | Standard for React SPAs |
| HTTP client | **`fetch`** via the existing `src/lib/api.ts` ApiClient (upgraded — §14.1) | Already present, zero dependencies; **no Axios** (decision ②, 2026-10-13) |
| State management | React Context + useReducer for auth; React Query (TanStack Query) for server data | No Redux needed for this scope |
| UI library | TailwindCSS + **shadcn/ui** | Already installed (not Headless UI) |
| WebSocket | Native WebSocket API | No library needed (§13) |
| Charts | **Recharts** (installed) | For portfolio/bot performance |
| Forms | React Hook Form + Zod validation | Type-safe schemas |

---

## 2. Authentication & Security

### 2.1 Auth header
```
Authorization: Bearer <access_token>
```
All endpoints requiring a user (or admin) need this header. Omit it → `401 {"detail": "Authentication credentials were not provided."}`.

### 2.2 Token lifecycle (frontend must implement)
1. **Login** → `POST /api/auth/login/` returns `{"user": {...}, "tokens": {"access_token", "refresh_token"}, "message"}`.
2. **Store tokens via the existing `src/lib/authToken.ts`** — in-memory + `sessionStorage` mirror (approved; `sessionStorage` is tab-scoped/cleared-on-close, and the module migrates legacy `localStorage` tokens off). Do not add a second storage path.
3. **Every API call** attaches `access_token` as `Authorization: Bearer <access_token>`.
4. **Before expiry / on `401`** → `POST /api/auth/refresh-token/` with `{"refresh_token": "<refresh_token>"}` → `{"access_token", "refresh_token", "message"}`.
   ⚠️ Rotation on: each refresh invalidates the old refresh token — **always store BOTH returned tokens**, not just the access token. On refresh failure the whole session is dead — **force re-login**, do not retry in a loop.
5. **Logout** → `POST /api/auth/logout/` with optional `{"refresh_token": "..."}` blacklists the refresh token server-side.

**Required additions to the current code (grill Q21):**
- Refresh-on-401 with rotation is **not yet implemented** in `src/lib/api.ts` — add it (single-flight, §14.1).
- Logout must actually **call `auth/logout/`** (currently only clears local state).
- 🐛 **Redirect bug:** `src/lib/api.ts` sends unauthenticated users to `/login` (line ~27) but the app route is **`/auth/login`** — fix or every forced re-login 404s.

**Verified auth response shapes (source: `apps/authentication/views.py`, 2026-10-07):**
- `register/` → **201** `{"user": {...}, "tokens": {"access_token", "refresh_token"}, "message": "...", "verification_sent": true}`
- `login/` → **200** `{"user", "tokens": {"access_token", "refresh_token"}, "message"}`; **401** `{"error": {"code": "LOGIN_FAILED", "message": "Invalid credentials."}}`; **429** `{"error": {"code": "LOCKED_OUT", "message": "Too many failed attempts. Try again later."}}` — **5 failed attempts lock the account for 15 minutes** (per email+IP+UA; tunable via `AUTH_LOCKOUT_THRESHOLD`/`AUTH_LOCKOUT_WINDOW`). Show a countdown, not a generic error.
- `refresh-token/` → **200** `{"access_token", "refresh_token", "message"}` (flat keys, top-level — not nested).
- `logout/` → `{"message": "Logout successful."}`; invalid/expired token → 400 `{"message": "Invalid refresh token."}`.
- `google/` → `{"user", "tokens": {...}, "message", "is_new_user": bool}`.
- ⚠️ These auth responses are **returned directly**, bypassing the §11 envelope: read `error.code`/`error.message` from `{"error": {...}}` and expect **no `timestamp`** key.

### 2.3 Security rules (non-negotiable)
- No hardcoded secrets, API keys, or passphrases anywhere client-side.
- Exchange API credentials are **fernet-encrypted at rest** and are **never returned in full**. Serializers expose them with `masked_secret_key`-style masked values only.
- Admin endpoints return `403 {"detail": "You do not have permission to perform this action."}` for non-staff — build UI that hides admin sections from non-admins rather than letting users hit 403s.
- Throttles exist — the UI must handle `429` (rate-limit) responses gracefully (see §11).
- Passwords: minimum 8 chars (registration requires password + `password_confirm` match and consent booleans — see §3.1).
- IDs are opaque strings/UUIDs — treated as opaque, never parsed client-side.

### 2.4 Auth endpoints (prefix `/api/auth/`)
| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `register/` | none | Create account (see payload below) |
| POST | `login/` | none | Password login → `access`+`refresh` |
| POST | `logout/` | user | Revoke refresh token (blacklist) |
| GET | `user/` | user | Current user profile / identity |
| POST | `verify-email/` | user | Request email verification |
| GET | `verify-email/<token>/` | none | Confirm email via emailed link |
| POST | `verify-phone/` | user | Request OTP SMS verification |
| POST | `verify-phone/confirm/` | user | Confirm phone with OTP code |
| POST | `2fa/setup/` | user | Re-auth with password → returns TOTP secret + `otpauth_uri` (does NOT enable yet) |
| POST | `2fa/confirm/` | user | Enable 2FA on valid TOTP code |
| POST | `2fa/disable/` | user | Disable 2FA (requires password **and** current TOTP code) |
| POST | `password-reset/` | none | Request password reset |
| POST | `password-reset/confirm/` | none | Complete reset with token + new password |
| POST | `change-password/` | user | Change password (requires current password) |
| POST | `google/` | none | Social Google auth exchange |
| POST | `refresh-token/` | none | Rotate refresh → new `access`+`refresh` |

**`register/` payload:**
```json
{
  "first_name": "string",
  "last_name": "string",
  "email": "user@example.com",
  "username": "string",
  "password": "min 8 chars",
  "password_confirm": "must match",
  "phone_number": "+923001234567",
  "referral_code": "optional string",
  "terms_accepted": true,
  "privacy_policy_accepted": true
}
```
- Both consent booleans are **required** and must be `True`; missing or `False` → `400` field errors. They are never persisted (stamped as `terms_accepted_at` + `privacy_version` server-side).
- Referral code is optional; self-referral / duplicate / invalid are guarded server-side.

**`2fa/setup/` flow:** must re-authenticate with current password in the body. Returns a base32 TOTP secret + provisioning `otpauth_uri` (QR code source). 2FA is **presence-only until confirmed** — the withdrawal gate (`POST /api/payments/withdrawals/`) requires `two_factor_enabled` **and** a real valid TOTP code in the request.

**Other auth payloads (verified):**
- `change-password/` → `{"old_password", "new_password", "new_password_confirm"}` → `{"message": "Password changed successfully."}`. **Side effect: ALL outstanding refresh tokens are blacklisted — force re-login.**
- `password-reset/` → `{"email"}` → `{"message": "If an account exists, a password reset link has been sent."}` (generic message defeats user enumeration).
- `password-reset/confirm/` → `{"token", "new_password", "new_password_confirm"}`.
- `verify-phone/` → `{"phone_number"}`; `verify-phone/confirm/` → `{"code", "phone_number"}`.
- `google/` → `{"access_token": "<Google OAuth token from frontend>"}`.

**Profile lives at `GET/PUT/PATCH /api/auth/user/`** (`UserDetailView`) — there is **no** `/api/auth/profile/` route. (Investments-scope profile: `investments/users/profile/`.)

---

## 3. Users (`/api/users/`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `deactivate/` | user | GDPR self-deactivation — password required in body; sets `is_active=False`, revokes ALL sessions. **Irreversible from UI.** |
| GET | `export-data/` | user | GDPR Art. 15 — full JSON export of all user data |
| GET | `admin/` | admin | List users |
| GET | `admin/<pk>/` | admin | User detail |
| GET | `admin/dashboard/stats/` | admin | Platform KPIs (MRR, churn, LTV, active users) |
| GET | `admin/bots/overview/` | admin | All bots across users |
| POST | `admin/blockchain-addresses/` | admin | Create blockchain address rule |
| GET | `admin/trade-logs/` | admin | Trade audit log |
| POST | `admin/users/<pk>/restrict/` | admin | Restrict/ban user |
| POST | `admin/emails/send/` | admin | Send bulk/system email |
| POST | `admin/withdrawals/process/` | admin | Admin-process withdrawals |

**`deactivate/` payload:** `{"password": "..."}` — wrong/missing password → `400`. Response includes `sessions_revoked` count.

**`export-data/`:** exchange credentials are **decrypted then masked** before export — never raw secrets.

---

## 4. Subscriptions & Signaling (`/api/subscriptions/`)

ViewSet routes (DRF default: list/create/retrieve/update/partial_update/destroy as applicable):

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `plans/` | user | All Telegram signal plans |
| GET/POST | `subscriptions/` | user | My Telegram subscriptions (create = subscribe) |
| GET | `channels/` | user | Telegram channels catalog |
| GET | `signals/` | user | Trading signals feed |
| GET | `signal-results/` | user | Signal outcomes/history |
| GET | `public/plans/` | none | Public plan listing (unauthenticated pricing page) |
| GET | `my-subscription/` | user | Current subscription — **always 200** (null-state instead of 404) |
| GET | `admin/channels/` | admin | All channels (admin) |
| POST | `admin/channels/create/` | admin | Create channel |
| GET | `telegram/plans/` | none | Telegram-specific plans (public, cached) |
| GET | `telegram/my-usage/` | user | Signal quota usage this period |
| POST | `telegram/subscribe/` | user | Subscribe to Telegram signal plan (409 on duplicate) |
| GET | `bot-plans/` | none | Bot-automation plans (public, cached) |
| POST | `bot-subscribe/` | user | Subscribe to bot plan (409 on duplicate) |
| GET | `bot-my-usage/` | user | Bot quota usage |

**Key contracts:**
- `bot-my-usage/` → `{"signals_used_this_month": int, "monthly_signal_limit": int, ...}`. The UI must gate/disable actions when usage ≥ limit.
- `my-subscription/` → **always 200, never 404.** Two shapes: a flat subscription object (fields incl. `status`, `end_date`, plan data) when any own row exists — active rows are preferred, otherwise the latest row of any status (so `pending_payment`/`pending_approval` are visible and renderable) — or `{"subscription": null}` when the user has never subscribed. Parse defensively: `data.subscription === null` → "no subscription"; otherwise treat the top-level object as the subscription.
- `telegram/subscribe/` **request** (multipart): `plan_id` (UUID/int pk **or** slug), `telegram_handle` (required), payment proof — either `payment_screenshot` (file) **or** `payment_transaction_hash` (+ optional `payment_blockchain`), `billing_cycle` (optional: `monthly` | `quarterly` | `yearly`, default `monthly`). **201** → `{"subscription_id", "status": "pending_approval", "message"}`. **409** on duplicate → envelope with `error.details.subscription_id` + `error.details.status` (link the user to their existing subscription). **409** if plan at `max_subscribers` capacity.
- `bot-subscribe/` **request**: `plan_id` (slug **or** numeric pk) — same 409-with-metadata behaviour as telegram/subscribe on duplicates.
- `telegram/plans/` → flat `{"plans": [...]}` (cached 1h, invalidated server-side on plan changes); each plan includes a `features` object (`max_daily_signals`, `exchanges_covered`, `risk_level`, `include_premium_signals`) — use it for pricing-page feature lists. `bot-plans/` → same flat shape for `payments.SubscriptionPlan`. **G1 (2026-10-12): every plan now also returns `description`, `sort_order` (display order — sort by it, not price), `bot_types` (string[]), `market` (`'spot'` | `'spot_futures'`), `max_signals_per_month`, `max_exchanges`, `annual_discount_pct` (derived, e.g. 20 = 20% off annual). All values are admin-editable DB config (Model C, FR A2) — render tiers from the response, never hardcode prices or limits. Canonical order after `sort_order` asc: free, basic, standard, premium, creator.
- Plan capacity is enforced server-side on this model family (SignalBot uniqueness per subscription; `max_subscribers` counts non-terminal rows — `null` = unlimited).

---

## 5. Bots (`/api/bots/`)

ViewSet routes:

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET/POST | `signal-bots/` | user | Signal bots CRUD |
| GET/POST | `grid-bots/` | user | Grid bots CRUD |
| GET/POST | `martingale-bots/` | user | Martingale bots CRUD |
| GET/POST | `quantum-funds/` | user | Quantum AI funds CRUD |
| GET/POST | `quantum-investments/` | user | Quantum investments CRUD |
| GET/POST | `pair-configs/` | user | Trading pair configs CRUD |
| GET/POST | `orders/` | user | Order history/reporting CRUD |
| GET/POST | `indicators/` | user | Indicator configs CRUD |

Bot control (POST):

| Method | Path | Purpose |
|---|---|---|
| POST | `grid/<str:bot_id>/start/` | Start grid bot |
| POST | `grid/<str:bot_id>/stop/` | Stop grid bot |
| POST | `martingale/<str:bot_id>/start/` | Start martingale bot |
| POST | `martingale/<str:bot_id>/stop/` | Stop martingale bot |

Indicator webhooks (TradingView push, public with `X-Webhook-Token`, **not** for frontend):
- `POST indicators/ema/`, `POST indicators/rsi/`, `POST indicators/bb/`

**Key contracts:**
- `bot_id` is a hyphenated string (`xxxxx-xxxxx-xxxxx`) — opaque.
- Each bot has a generated `secret_key` (CSPRNG) used only for webhook auth — **never shown to end users beyond creation**.
- Grid/martingale bots are one-per-subscription (`unique_together`); creating a second for the same subscription → `400`/`409`.
- `orders/` here is the bot-order model. Consumer hit: a `BotOrder` requires a user to persist (post-save sync signal) — treat bot order creation as user-scoped.

---

## 6. Exchanges (`/api/exchanges/`) & Trading (`/api/trading/`)

### 6.1 Exchanges app (legacy — stable, keep supporting)
| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET/POST | `credentials/` | user | Connect/list exchange API credentials |
| GET | `supported-pairs/` | user | Pairs supported per exchange |
| GET | `status/` | user | Exchange operational status |
| GET/POST | `blockchain-addresses/` | user | Address book (withdrawal addresses) |
| GET | `list/` | user | List available exchanges |
| GET | `<exchange_name>/symbols/` | user | Symbols for a named exchange (e.g. `binance`) |
| GET | `rates/` | user | Live exchange rates |

### 6.2 Trading app (main unified API)
| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET/POST | `exchanges/` | user | Exchange metadata |
| GET/POST | `credentials/` | user | Exchange credentials (masked on read) |
| GET/POST | `pairs/` | user | Trading pairs |
| GET/POST | `status/` | user | Pair/exchange status |
| GET/POST | `strategy-configs/` | user | Strategy configuration profiles |
| GET | `exchanges/list/` | user | Exchange list |
| GET | `exchanges/<exchange_name>/symbols/` | user | Symbol list |
| GET | `rates/` | user | Conversion rates |

### 6.3 Consumer methods (what the UI can trigger)
The engine exposes these exchange operations via adapters. Frontend-facing equivalents:
- Create market/limit orders via `trading` strategy flow (`pair-configs` → start bot).
- **Grid monitoring is FAILURE-POLLING:** status/fills are fetched by the backend monitor; the frontend must poll (`/api/bots/grid-bots/` + `/api/bots/orders/`) on a cadence. A bot WebSocket endpoint exists but has **no server-side update producer** (verified 2026-10-07) — see §13; **do not rely on WS pushes for bot status**.
- Position/balance checks happen through the engine; the frontend reads results via orders/balances viewsets.

### 6.4 Connected exchange adapters
Bybit, Binance, MEXC, Alpaca, OKX, Coinbase (all ccxt-based; Coinbase supports demo-trading mode). A `mock_adapter` exists for development. Live balance/position data reflects what the engine fetched; grid status is authoritative from the monitor.

---

## 7. Investments & Positions (`/api/investments/`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET/POST | `orders/` | user | Investment order records |
| GET/POST | `positions/` | user | Open/closed positions |
| GET/POST | `technical-indicators/` | user | Indicator values |
| GET/POST | `balances/` | user | User balances (available/hold) |
| GET | `users/my-orders/` | user | My order history |
| GET | `users/profile/` | user | User profile (investments scope) |
| GET | `bots/blockchain-addresses/` | user | Address book (investments scope) |
| POST | `bots/quantum-ai/<uuid:bot_id>/deposit/` | user | Deposit into Quantum AI fund |

Webhooks (external, not frontend):
- `POST webhooks/tradingview/<webhook_id>/`, `POST indicators/ema/`, `POST indicators/rsi/`

**Note:** `orders/`, `positions/`, `balances/` run through the investments display models (single-owner refactor). Balance model uses `available` + `hold` (no `balance` field).

---

## 8. Payments (`/api/payments/`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET/POST | `subscription-plans/` | user | Subscription plan catalog |
| GET/POST | `quantum-deposits/` | user | Quantum AI deposits |
| GET/POST | `withdrawals/` | user | Withdrawal requests |
| GET/POST | `transactions/` | user | Payment transactions |
| GET | `blockchain-addresses/` | user | Blockchain address catalog |
| POST | `admin/deposits/<uuid:deposit_id>/approve/` | admin | Approve deposit |
| POST | `admin/deposits/<uuid:deposit_id>/reject/` | admin | Reject deposit |
| GET | `subscriptions/bot/` | user | My bot subscription |
| POST | `subscriptions/bot/create/` | user | Create bot subscription (pending approval) |
| POST | `subscriptions/bot/<str:subscription_id>/approve/` | admin | Approve bot subscription |
| POST | `subscriptions/bot/<str:subscription_id>/reject/` | admin | Reject bot subscription |
| POST | `quantum-ai/<uuid:bot_id>/deposit/` | user | Deposit into Quantum AI bot |
| GET | `payment-coins/` | public | Configured receive coins/chains (deposit_address only when set) |
| POST | `payment-codes/` | user | Create unique payment code + first quote (G2/FR A3) |
| GET | `payment-codes/<code>/` | user | Payment code detail + live quote (`?coin_id=` switches coin) |
| POST | `payment-codes/<code>/quote/` | user | Explicit re-request after window expiry → fresh quote, window restarts |
| POST | `payment-codes/<code>/proof/` | user | Submit TX hash/screenshot → pending_approval subscription |

**Key contracts:**
- **Payment codes (G2/FR A3 — manual multi-coin launch flow), 3 steps:**
  1. `POST payment-codes/` `{order_kind: "telegram_signal"|"bot", plan_id, billing_cycle?}` → 201 `{code, fiat_amount, status: "awaiting_payment", …}`. Bot orders force `monthly`. 409 duplicate (`error.details.subscription_id` → "already subscribed") / plan capacity; 400 `{coin: …}` if no receive coin is configured.
  2. `GET payment-codes/<code>/` → `{…, quote_window_expires_at, quote: {coin: {coin, chain, deposit_address, network_fee}, fiat_amount, rate, crypto_amount, expires_at, is_expired}}` — **poll while awaiting payment**: the quote shows the **final combined payable amount** (plan price + per-chain fee — e.g. `15.00 + 0.20 = 15.20 USDT` for Basic on TRC20; `quote.coin.network_fee` renders as `TRC20 (fee: 0.20 USDT)`) and **auto-updates every 5 minutes**; it **expires after 6 h** (admin-configurable per coin via `quote_window_expires_at`, FR A3) — when `quote.is_expired`, show a **re-request** action → `POST payment-codes/<code>/quote/` body `{coin_id?}` → 200 same payload, re-locks at the then-current price and **restarts the window** (400 unknown coin / non-awaiting code, 404 other user's code). GET polling **never silently re-locks after window expiry** (stays expired until re-request). `?coin_id=` switches receive coin (400 unknown coin). **503 `SERVICE_UNAVAILABLE` while the price feed is down → retry with backoff, never invent a fallback amount.** Proof submitted after expiry freezes the **stale** (last-seen) amount — never re-prices at that point. After proof submission the price is frozen on the code (`locked_rate` / `locked_crypto_amount`).
  3. `POST payment-codes/<code>/proof/` — JSON `{payment_transaction_hash, payment_blockchain?, telegram_handle}` (telegram_handle required for telegram_signal) **or** multipart `payment_screenshot` → 201 `{subscription_id, status: "submitted", locked_rate, locked_crypto_amount, …}`. 409 if already submitted or a legacy subscription appeared meanwhile; 404 for another user's code. Status then flips `approved`/`rejected` by admin — keep polling step 2 for it.
- **Withdrawal requires 2FA**: `POST withdrawals/` payload must include the current TOTP code as **`two_factor_code`** (required, write-only, validated not stored — `apps/payments/serializers.py:149`) and the user must have `two_factor_enabled=True`. Missing/weak/no-2FA → error telling the user to enable 2FA first.
- `subscriptions/bot/create/` creates a **pending** subscription awaiting admin approval — UI must show "pending approval" state.
- Deposits are admin-approve/reject gated (Quantum AI) — UI must show pending status until approved.

---

## 9. Referrals (`/api/referrals/`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `my-stats/` | user | Referral stats + codes + G5 hybrid reward fields |
| POST | `apply/` | user | Apply a referral code (`{"code": "..."}`) at first login |
| GET | `payout-requests/` | user | Own commission payout requests, newest first |
| POST | `payout-requests/` | user | File a payout request `{"amount": "50.00"}` against pending commission |

### `my-stats/` response

Legacy keys (contract-stable, additive):

```json
{
  "referral_code": "ABC123",
  "total_referrals": 4,
  "total_bonus_usdt": "0.00",
  "referral_link": "https://site/signup?ref=ABC123"
}
```

G5 / FR A7 hybrid reward fields (same response — **one model per user, never both**):

```json
{
  "reward_model": "commission",          // "commission" (creator-tier) | "referee_discount" (everyone else)
  "commission_pct": "10",                // Decimal string; null when reward_model = "referee_discount"
  "commission_pending_usd": "120.00",    // unpaid accruals (ReferralPayout status="pending")
  "commission_paid_usd": "30.00",        // already-paid accruals
  "payout_minimum_usd": "50.00",         // min amount for POST payout-requests
  "referee_discount_pct": null,          // e.g. "20"; null when reward_model = "commission"
  "has_pending_payout_request": false    // true → disable the "Request payout" button
}
```

- Creator-tier referrers see `reward_model: "commission"` — render pending/paid totals + payout form.
- Everyone else sees `reward_model: "referee_discount"` — show "your referrals get X% off their first payment" and hide commission UI.
- `referral_link` = full signup URL with `?ref=` — render/copy it directly.

### `apply/`

Success (200) → `{"message": "Referral code applied successfully", "referrer": "<email>"}`.
Rejections (invalid / self / already-applied) → **400 in the standard error envelope** (§11); read `error.message` for display. Codes are CSPRNG-generated.

### `payout-requests/`

- **GET** → `{"payout_requests": [...]}` newest first. Each row: `{id, amount_requested, status, admin_entered_payout, admin_notes, decided_at, requested_at}`. `status` ∈ `"pending" | "approved" | "rejected"`.
- **POST** `{"amount": "50.00"}` → `201` with `{id, amount_requested, status, ...}`. Amount must be ≥ `payout_minimum_usd` and ≤ pending commission balance; violations → **400 in the standard error envelope** (§11).
- After filing, `has_pending_payout_request` in `my-stats/` becomes `true` — disable the button until the admin decides.

---

## 10. Connectivity Graph (page → calls)

| UI Surface | Chain of calls |
|---|---|
| Onboarding | `register/` (or `google/`) → `verify-phone/` + `verify-phone/confirm/` → `verify-email/` + emailed link → `login/` → `referrals/apply/` (if `?ref=`) |
| Dashboard/auth shell | `login/` → `refresh-token/` on 401 → `users`/`auth/user/` for identity → logout on refresh failure |
| Plans & subscribe | `subscriptions/public/plans/` → `subscriptions/bot-subscribe/` or `telegram/subscribe/` → `subscriptions/bot-my-usage/` (gate UI) |
| Bot management | `bots/signal-bots|grid-bots|martingale-bots/` → `bots/<type>/<id>/start|stop/` → poll `bots/orders/` + `investments/positions/` for status |
| Exchange connection | `exchanges/list/` → `exchanges/credentials/` (POST to connect) → `exchanges/rates/` + `exchanges/<name>/symbols/` for pair charts |
| Quantum AI | `payments/subscription-plans/` → `payments/quantum-ai/<bot_id>/deposit/` → pending → admin approve → `payments/quantum-deposits/` reflects |
| Withdrawals | 2FA prompt (`auth/2fa/`) → `payments/withdrawals/` POST (+TOTP code) → admin process |
| Referral interstitial | `referrals/apply/` → `referrals/my-stats/` on profile |
| Referral rewards page (TO ADD) | `referrals/my-stats/` (hybrid fields, §9) → `referrals/payout-requests/` GET+POST when `reward_model: "commission"` |
| Admin | `users/admin/dashboard/stats/` → `users/admin/bots/overview/` → `users/admin/trade-logs/` → `payments/admin/deposits/<id>/approve|reject/` → `payments/subscriptions/bot/<id>/approve|reject/` → `users/admin/withdrawals/process/` |
| Forgot password (TO ADD) | `auth/password-reset/` (email link) → `auth/password-reset/confirm/` → `/auth/login` |
| Subscription expiry banners (TO ADD) | poll `subscriptions/my-subscription/` → in-app banner D-7/D-5/D-3/D-1 + grace (FR A5) |
| QAI deposit via payment codes (TO ADD) | `payments/payment-coins/` → `payments/payment-codes/` (create) → poll `payment-codes/<code>/` (quote auto-updates every 5 min, 6 h expiry → `POST payment-codes/<code>/quote/` re-request, §8) → `payment-codes/<code>/proof/` → keep polling for `approved`/`rejected`; fee display `TRC20 (fee: …)` |
| Deposits & transactions (TO ADD) | `payments/quantum-deposits/` + `payments/transactions/` → pending/approved/rejected states |
| BotDetail (TO ADD) | `bots/<type>/<id>/` → poll `bots/orders/` + `investments/positions/` (§6.3 — no WS push) |

---

## 11. Error Contract

**Universal envelope.** Every error produced by a DRF exception (validation, auth, permission, not-found, conflict, throttle) is rendered by the custom exception handler (`core/exceptions.py`, wired globally in `config/settings/base.py`) as:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Human-readable summary safe to show the user.",
    "details": { "...": "raw detail payload, may be null" },
    "field_errors": { "plan_id": ["Invalid plan_id"] }
  },
  "timestamp": "2026-10-07T12:00:00Z"
}
```

`field_errors` is present only for dict-shaped validation errors. In `DEBUG`, an extra `debug` object (method/path/view/traceback) is appended — ignore it in production builds.

| Status | `error.code` | Meaning / client action |
|---|---|---|
| 400 | `VALIDATION_ERROR` | Bad input → map `error.field_errors` onto form fields; else toast `error.message` |
| 401 | `AUTHENTICATION_REQUIRED` / `AUTHENTICATION_FAILED` | Try one `refresh-token/` rotation and replay; if rotation also 401s → terminate session, force sign-in |
| 403 | `PERMISSION_DENIED` | Logged in but not allowed (admin gating) |
| 404 | `RESOURCE_NOT_FOUND` | Unknown resource/ID |
| 409 | `CONFLICT` | State conflict — **not a client bug.** Duplicates: `error.details.{subscription_id,status}` → show "already subscribed" and link to the existing one; plan capacity: "plan is full" |
| 429 | `RATE_LIMIT_EXCEEDED` | Rate limited — show wait/retry state; do NOT hammer (OTP, phone_verification, two_factor are 5/hour) |
| 500 | `INTERNAL_SERVER_ERROR` | Backend fault — generic error + retry |
| 503 | `SERVICE_UNAVAILABLE` | Live price feed down (quote/payment-code endpoints) — retry with backoff; never render a fallback crypto amount |

**Legacy flat errors (defensive parsing required).** A minority of endpoints still bypass the handler and return `{"error": "<string>"}` directly (7 in `apps/bots/views.py`, 4 in `apps/investments/views.py`, 3 in `apps/payments/views.py`, 2 in `apps/users/views.py`, 5 in `apps/webhooks/views.py`); auth views (§2.2) return `{"error": {"code", "message"}}` objects with no `timestamp`. Therefore **never assume `error` is an object**:

```js
const msg = typeof e.error === "string" ? e.error : e.error?.message;
const code = e.error?.code;
const fields = e.error?.field_errors;
```

**Do not** read a top-level `detail` key — the envelope replaces DRF's default `{"detail": "..."}` shape on handled exceptions.

**Client rule:** when a 401 arrives on an authenticated call, attempt one `refresh-token/` rotation and replay; if rotation also 401s, terminate session and force sign-in.

---

## 12. Known Issues & Limitations (verified)

1. **Bot status is polling-based** — the `ws/bot/<id>/` endpoint exists (§13) but **no server-side producer pushes `bot_update`** (verified 2026-10-07), so grid fills/bot status must be polled on a cadence; the backend monitor is the source of truth. Only the **market ticker** WS (`ws/market/<exchange>/<symbol>/`) actually streams data.
2. **Payment rails**: deposits/bot-subscriptions require **admin approval**; withdrawals require **admin processing**. The UI must reflect lifecycle states (`pending`, `approved`, `rejected`). Payment codes (G2, §8) follow `awaiting_payment → submitted → approved|rejected` with a live quote that auto-updates every 5 minutes and expires after 6 h (admin-configurable) → user re-requests, FR A3.
3. **2FA is a hard gate on withdrawals** — enable-2FA flow (`2fa/setup/` → `2fa/confirm/`) must be polished; users cannot withdraw without it.
4. **Register needs consent booleans** — missing them fails validation; frontend must present an explicit terms/privacy acceptance UI.
5. **Exchange credentials are masked** on every read — a "connected: yes/no + masked key" pattern is the only allowed display.
6. **Legacy `exchanges/` vs main `trading/`** — both live; prefer `trading/` for new integration, but `exchanges/credentials/` is the connect flow. Don't create parallel duplicate UI.
7. **Public plan endpoints pre-auth** (`subscriptions/public/plans/`, `subscriptions/telegram/plans/`, `subscriptions/bot-plans/`) for the marketing/pricing page — plan lists need no auth; everything else requires it.
8. **Refresh rotation** — old refresh tokens die on every use; don't cache/share a refresh token across tabs without re-login sync.
9. **Single-owner display models** — `investments/orders|positions|balances` are account-scoped; 404/empty for other users (never leak cross-user data).
10. **No `/users/profile/` at the auth scope** — profile lives at `auth/user/` and `investments/users/profile/`. Do not hardcode `/users/profile/`.

---

## 13. Real-time (WebSocket) — verified contract (2026-10-07)

Wiring: `config/asgi.py` → `ProtocolTypeRouter` + `AuthMiddlewareStack(URLRouter(...))`; routes in `apps/trading/routing.py`; consumers in `apps/trading/consumers.py`. Use same host: `ws://` dev / `wss://` prod.

### 13.1 Market ticker WS — functional, public (no auth)
`ws(s)://<host>/ws/market/<exchange>/<symbol>/` — e.g. `ws://host/ws/market/binance/BTC/USDT/`
- Accepts immediately (no token), starts a `ccxt.pro` ticker stream for the path symbol.
- Server → client: `{"type": "ticker", "symbol": "BTC/USDT", "bid": 50000.0, "ask": 50001.0, "last": 50000.5, "timestamp": 1712345678000}`
- Client → server: `{"action": "subscribe", "symbol": "ETH/USDT"}` → ack `{"type": "subscribed", "symbol": "ETH/USDT"}`
- Close codes: `4004` unsupported exchange, `4000` init error.
- Use for live pair charts / price tickers.

### 13.2 Bot WS — endpoint exists, **no push producer** (poll instead)
`ws(s)://<host>/ws/bot/<bot_id>/?token=<access_token>`
- Auth: JWT **access** token as `?token=` query parameter (same token as REST). Server validates token + bot ownership.
- Close codes: `4001` = auth failed → redirect to login; `4003` = not owner / bot not found → show access denied. **Never auto-reconnect on 4001/4003.**
- Contract: server → `{"type": "bot_update", "data": {...}}` or `{"type": "error", "message": "..."}`. On connect the consumer asks a `bot-management` worker to start; on disconnect, to stop.
- **⚠️ Verified gap:** no application code `group_send`s `bot_update` to the bot group and nothing consumes the `bot-management` messages — the socket connects and then stays silent. **Poll REST (`bots/grid-bots/`, `bots/orders/`, `investments/positions/`) for bot status; treat any WS payload as a bonus until a producer lands.**
- **There is no `ws/wallet/` endpoint** — an older document claimed one; it does not exist in the codebase.

```typescript
// Lifecycle (connect only while a bot detail page is open)
const ws = new WebSocket(`wss://host/ws/bot/${botId}/?token=${accessToken}`);
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  if (msg.type === 'bot_update') { /* merge msg.data into bot state (bonus path) */ }
  if (msg.type === 'error') { /* show error toast */ }
};
ws.onclose = (event) => {
  if (event.code === 4001) { /* auth failed — refresh token / redirect to login */ }
  if (event.code === 4003) { /* forbidden — show access denied */ }
};
// Recommended: wrap in a useBotWebSocket(botId) hook — connect on mount,
// close on unmount, auto-reconnect on token rotation with backoff (§13.3).
```

### 13.3 Reconnection pattern
```typescript
// Exponential backoff: 1s, 2s, 4s, 8s, ... max 30s
// On reconnect: use the LATEST access_token (it rotates every ~15 min)
// Don't reconnect on close codes 4001 or 4003 (auth/permanent failures)
// Subtle "reconnecting…" indicator (e.g. yellow bar) while retrying
```

---

## 14. Frontend implementation guide (absorbed from `frontend-connectivity.md` + `FRONTEND.md`)

### 14.1 API client & token interceptors — **extend the existing `src/lib/api.ts`**
Do **not** introduce Axios or a new client. The repo already has a `fetch`-based `ApiClient` (`src/lib/api.ts`) — extend it so every call gets the four behaviours below:

1. **Auth header** — read the token via `getAuthToken()` (`authToken.ts`), attach `Authorization: Bearer <access_token>`.
2. **Envelope parsing + typed errors** — on non-2xx, parse the §11 envelope and **throw a typed `ApiError`** (carrying `status`, `code`, `message`, `field_errors`, `details`) — not a plain `Error` (that's what it throws today). Keep the flat `{"error": "<string>"}` fallback (§11) and the auth-shaped `{"error": {code, message}}` (§2.2). Map `error.field_errors` onto forms; toast `error.message` otherwise.
3. **429 handling** — surface a wait/retry state (countdown for OTP/2FA/phone throttles, 5/hour) instead of failing silently; exponential backoff, no hammering.
4. **Refresh interceptor (to add)** — on `401`: attempt **one** `POST /auth/refresh-token/` rotation (single-flight) → store BOTH returned tokens via `authToken.ts` → replay the original request. If rotation also 401s → `clearAuthToken()` + redirect to **`/auth/login`** (§2.2 bug fix). Never loop.

**Refresh race condition** — when several calls 401 simultaneously, only ONE refresh may run; queue the rest behind a promise lock (implement inside the ApiClient's 401 path):
```typescript
let isRefreshing = false;
let failedQueue: Array<{resolve, reject}> = [];

const processQueue = (error, token = null) => {
  failedQueue.forEach(({resolve, reject}) => {
    if (error) reject(error);
    else resolve(token);
  });
  failedQueue = [];
};

// Inside the 401 path (before redirecting):
if (!isRefreshing) {
  isRefreshing = true;
  try {
    const data = await postJson('/auth/refresh-token/', {
      refresh_token: getRefreshToken()   // via authToken.ts
    });
    setAuthToken(data.access_token);     // stores BOTH (rotation!)
    setRefreshToken(data.refresh_token);
    processQueue(null, data.access_token);
    return replay(originalRequest);
  } catch (err) {
    processQueue(err, null);
    clearAuthToken();
    window.location.href = '/auth/login';   // NOT '/login' (§2.2 bug)
  } finally {
    isRefreshing = false;
  }
} else {
  return new Promise((resolve, reject) => failedQueue.push({ resolve, reject }))
    .then((token) => {
      originalRequest.headers.Authorization = `Bearer ${token}`;
      return replay(originalRequest);
    });
}
```

### 14.2 Pagination & infinite scroll
```typescript
interface PaginatedResponse<T> { count: number; next: string | null; previous: string | null; results: T[]; }
```
Query params: `?page=1&page_size=20` (default 20, max 100). Drive either a "Load more" button or Intersection Observer infinite scroll off the `next` link.

### 14.3 Special behaviors
- **File uploads** (payment screenshots, deposit proofs): `multipart/form-data` — build `FormData` (`payment_screenshot`, `plan_id`, …); with `fetch`, let `FormData` set the boundary itself — **never set `Content-Type` manually** (it would break the multipart boundary). Show upload progress.
- **Dates**: all timestamps are ISO-8601 UTC (e.g. `2026-07-15T10:30:00Z`) — convert to the user's `profile.timezone` for display (`dayjs`/`date-fns`).
- **Feature/plan gating**: read `profile.subscription_plan` + `max_bots_allowed` from the profile response; also gate by quota via `bot-my-usage/` (§4).
- **Start/stop idempotency**: starting a running bot (or stopping a stopped one) returns an error — show loading state, then re-sync UI from the actual status. Mutations are async (Celery) — poll after action.
- **Admin gating**: check `user.is_staff` from the profile response and hide admin nav; admin endpoints 403 non-staff anyway (§2.3).
- **429 handling**: exponential backoff; OTP/2FA/phone throttles are 5/hour (§11) — render countdowns.

### 14.4 TypeScript shape guide
> Illustrative shapes merged from `frontend-connectivity.md` §6 — **validate against live responses** (serializers are authoritative; `FRONTEND_PROMPT` route/contract sections win on conflict).
>
> ⚠️ **The repo's existing `src/types/api.ts` models the OLD backend** (`custom_bot` / `managed_bot` shapes that don't match these routes) — **replace it with the shapes below**, don't reconcile against it.

```typescript
interface User {
  id: string; email: string; username?: string;
  first_name: string; last_name: string; full_name: string;
  phone_number: string;
  is_email_verified: boolean; is_phone_verified: boolean;
  two_factor_enabled: boolean; is_staff?: boolean;
  date_joined: string; last_login: string; timezone: string;
  profile: UserProfile;
}
interface UserProfile {
  subscription_plan: string; subscription_plan_display: string;
  max_bots_allowed: number; timezone: string;
  trading_preferences: Record<string, any>;
  demo_trading_enabled: boolean;
  email_notifications: boolean; sms_notifications: boolean; push_notifications: boolean;
  is_subscription_active: boolean;
  referral_code: string;
  total_trades_executed: number; total_volume_traded: number;
}
interface AuthTokens { access_token: string; refresh_token: string; } // NOTE: nested under "tokens" in responses

interface BotBase {
  id: string; user: string; bot_name: string;
  category: 'webhook' | 'grid' | 'martingale' | 'quantum_ai';
  exchange: string; trading_pair: string;
  status: 'idle' | 'running' | 'paused' | 'stopped' | 'error';
  is_active: boolean;
  total_trades: number; successful_trades: number;
  total_profit_loss: string;                       // decimals as strings
  take_profit_percent: string; stop_loss_percent: string;
  max_position_size: string;
  started_at: string | null; stopped_at: string | null;
  created_at: string; updated_at: string;
}
interface SignalBot extends BotBase {
  webhook_id: string; webhook_url: string; secret_key: string;
  default_amount: string; last_triggered: string | null;
}
interface GridBot extends BotBase {
  base_amount: string;
  favor_levels: number; against_levels: number;
  level_spacing_percent: string;
  current_grid_level: number; total_invested: string;
  is_running: boolean; subscription: string | null;
  exchange_name: string; trading_pair: string;
  favor_level_qty: number; against_level_qty: number;
  favor_level_difference: number; against_level_difference: number;
  take_profit_percent: number; stop_loss_percent: number; amount_type: string;
}
interface MartingaleBot extends BotBase {
  base_amount: string;
  favor_levels: number; against_levels: number;
  level_spacing_percent: string; multiplier_factor: string;
  current_level: number; consecutive_losses: number;
  is_running: boolean; subscription: string | null;
  exchange_name: string; trading_pair: string;
}
interface Order {
  id: string; user: string; pair: string;
  side: 'BUY' | 'SELL';
  category: string;          // 'signal_bot' | 'grid' | 'martingale' | 'quantum_ai'
  order_type: string;        // 'market' | 'limit'
  quantity: number; price: number; exchange: string;
  status: 'pending' | 'executed' | 'cancelled' | 'failed';
  signal_bot: string | null; grid_bot: string | null;
  martingale_bot: string | null; investor_portfolio: string | null;
  description: string; details: Record<string, any>; created_at: string;
}
interface ExchangeCredentials {
  id: string; user: string;
  exchange_name: string;        // 'binance' | 'bybit' | 'okx' | 'mexc' | 'alpaca' | 'coinbase'
  api_key: string;              // Masked: 'abcd****1234'
  is_testnet: boolean; is_active: boolean;
  permissions: string[]; notes: string; created_at: string;
}
interface SubscriptionPlan {
  id: string; name: string; slug: string; description: string;
  price_monthly: string; price_yearly: string;
  annual_discount_pct: number;      // derived, e.g. 20 => 20% off annual
  sort_order: number;               // display order (FR A2), sort asc
  max_bots_allowed: number; max_webhooks_allowed: number;
  bot_types: string[];              // e.g. ['signal']; [] = not yet set (paid TBD)
  market: 'spot' | 'spot_futures';
  max_signals_per_month: number; max_exchanges: number;
  features: Record<string, any>; is_active: boolean; trial_days: number;
}
interface BotSubscription {
  id: string; user: string; plan: SubscriptionPlan;
  status: 'pending_payment' | 'pending_approval' | 'active' | 'expired' | 'rejected';
  payment_screenshot: string | null;
  payment_transaction_hash: string; payment_blockchain: string;
  exchange_name: string;
  started_at: string | null; expires_at: string | null; is_expired: boolean;
}
interface BalanceSummary { total_usdt_value: string; balances: UserBalance[]; }
interface UserBalance { id: string; user: string; currency: string; available: string; hold: string; }
interface InvestorDeposit {
  id: string; user: string; bot_name: string;
  amount: string; currency: string;
  status: 'pending' | 'approved' | 'rejected';
  blockchain: string; transaction_hash: string; from_address: string; created_at: string;
}
interface WithdrawalRequest {
  id: string; user: string; amount: string; currency: string;
  blockchain: string; to_address: string;
  status: 'pending' | 'processing' | 'completed' | 'rejected' | 'cancelled';
  network_fee: string; processing_fee: string; total_amount: string;
  is_flagged: boolean; created_at: string;
}
interface PaymentTransaction {
  id: string; user: string;
  transaction_type: 'deposit' | 'withdrawal' | 'quantum_ai_payout' | 'referral_bonus' | 'subscription';
  amount: string; currency: string;
  status: 'pending' | 'completed' | 'failed';
  description: string; created_at: string;
}
interface Exchange {
  id: string; name: string; display_name: string;
  is_active: boolean; supports_testnet: boolean;
  supported_features: string[]; rate_limit_per_minute: number;
  fee_rates: Record<string, any>;
}
interface TradingPair {
  id: string; exchange: string; symbol: string;
  base_currency: string; quote_currency: string;
  price_precision: number; quantity_precision: number;
  min_quantity: string; is_active: boolean;
}
interface ReferralStats {
  referral_code: string; total_referrals: number;
  total_bonus_usdt: string; referral_link: string;
  // G5 / FR A7 — hybrid reward model (one model per user, never both)
  reward_model: 'commission' | 'referee_discount';
  commission_pct: string | null;
  commission_pending_usd: string;
  commission_paid_usd: string;
  payout_minimum_usd: string;
  referee_discount_pct: string | null;
  has_pending_payout_request: boolean;
}
interface PayoutRequestRow {
  id: string; amount_requested: string;
  status: 'pending' | 'approved' | 'rejected';
  admin_entered_payout: string | null;
  admin_notes: string | null;
  decided_at: string | null;
  requested_at: string;
}
```

### 14.5 Page inventory — EXISTS vs TO ADD
**EXISTS in `src/App.tsx` (verified 2026-10-14 — build on these, don't recreate):**
- **Public:** `/` · `/pricing` · `/tutorial` · `/about` · `/terms` · `/faqs` · `/blog` · `/help-support` · bot marketing pages `/grid-bots` `/spot-bots` `/futures-bots` `/martingale-bots` `/signal-bots` `/investment-bots` · `/custom-bots` (currently renders `SignalBots`) · `/auth/login` · `/auth/signup` · `*` → NotFound.
- **Authed (under `/dashboard`, `ProtectedRoute`):** index (`DashboardHome`) · `bots` (list) · `exchanges` · `settings` · `analytics` · `create-bot` · `create-signal-bot` · `create-custom-bot` · `invest-in-bot` · `withdrawals` · `support`.

**TO ADD (gap list — grill Q21):**
- `/auth/forgot-password` — **already linked in the UI but no route → 404**; wire to `auth/password-reset/` + `auth/password-reset/confirm/`.
- **Referrals** (code + stats, §9) · **Subscriptions / plan select + upgrade** (§4, A2 matrix — upgrade-only mid-term) · **Deposits** (admin-approve lifecycle) · **Transactions** (history) · **BotDetail** (config + orders + P/L, poll §6.3) · **Orders** (order history w/ §14.8 filters).
- **Admin section** (staff-gated: dashboard KPIs, user mgmt, deposit/withdrawal/subscription approval — §10 Admin row).
- **QAI screens**: deposit (payment-code flow §8) · lock · balance · withdraw — with fee display `TRC20 (fee: 0.20 USDT)` format; the address/proof screen shows the **final payable amount** = plan price + chain fee (e.g. `15.00 + 0.20 → 15.20 USDT`), auto-updating every 5 min (FR A3; quote = plan price + chain buffer, user receives ≥ plan price).
- **In-app subscription expiry banners**: D-7 / D-5 / D-3 / D-1 + grace (FR A5).

**Recommended file structure (TS):**
```
frontend/src/
├── api/          lib/api.ts (fetch ApiClient + refresh — §14.1), lib/authToken.ts, auth.ts, bots.ts, payments.ts, trading.ts, admin.ts
├── hooks/        useAuth.ts, useBotWebSocket.ts, usePagination.ts
├── pages/        Login, Register, Dashboard, BotManager, CreateBot, BotDetail,
│                 Settings, Subscriptions, Deposits, Withdrawals, Orders, Referrals,
│                 admin/ (Dashboard, Users, Deposits, Withdrawals)
├── components/   Layout.tsx, BotCard.tsx, StatusBadge.tsx, OrderTable.tsx, ...
└── types/        index.ts (§14.4)
```
Suggested component/hook grouping (from `FRONTEND.md`): `common/` (Loading, Error, EmptyState, Pagination) · `auth/` (LoginForm, RegisterForm, PasswordReset) · `bots/` (BotCard, BotForm, BotDetail, OrderList) · `payments/` (PlanCard, DepositForm, TransactionList); hooks `useAuth`, `useBots`, `usePayments`, `useExchange`.

### 14.6 UI/UX patterns (adopt as baseline)
- **Loading**: skeleton loaders for list pages; spinner buttons for start/stop/create; progress bar for file uploads.
- **Empty states**: "No bots yet…" + CTA; "No orders/transactions found."
- **Errors**: toast (auto-dismiss success, manual-dismiss error) + inline field errors; network-error banner when API unreachable.
- **Confirmations**: start/stop bot, cancel order, delete bot (type-out name), withdrawal summary (amount/address/fees).
- **Forms**: label+input side-by-side; step-by-step bot wizard (type → exchange → pair → parameters → review); drag-and-drop upload with preview.
- **Data display**: sortable tables; bot cards (status badge, name, pair, P&L); portfolio charts; status badges — green running/active, yellow paused/pending, red error/stopped, gray idle.
- **Notifications**: toast on bot state changes; WS reconnect indicator (yellow bar).
- **Design principles** (from `FRONTEND.md`): mobile-first responsive; dark mode via Tailwind; real-time via market WS (§13); all mutations show loading+error; optimistic UI for start/stop.

### 14.7 Do-not-use list (stale paths found in archived sources)
These appeared in `docs/archive/frontend-connectivity.md` but were **verified non-existent** in the codebase on 2026-10-07 — do not call them:
`GET /api/auth/profile/` (use `auth/user/`) · `/api/bots/orders/recent/` · `/api/investments/balances/summary/` · `/api/payments/transactions/recent/` · `/api/payments/transactions/by_type/` · `/api/trading/credentials/active/` · `GET /api/webhooks/custombot/indicators/ema|rsi/` (indicators live at `POST /api/bots/indicators/ema|rsi|bb/`) · `POST /api/payments/withdrawals/<pk>/cancel/` (no cancel route in `apps/payments/urls.py`). Their originals are preserved in the archive for history only.

### 14.8 Verified request details (from connectivity §5, re-checked 2026-10-07)
- **Create-bot wizard:** Step 2 `GET trading/exchanges/list/` → `{"success": true, "data": [{"name", "display_name", "is_active", "supports_testnet", "supported_features", "fee_rates"}]}`; Step 3 `GET trading/exchanges/<exchange_name>/symbols/` → `{"success": true, "exchange": "bybit", "symbols": ["BTC/USDT", ...]}`; Step 5 submit. **Signal-bot create response includes `webhook_url` + `webhook_id`** (read-only in `apps/bots/serializers.py`) — display them so the user can configure TradingView; show the secret at creation with a copy button.
- **TradingView alert integration** (complements §1): payload includes `bot_id`, `side`, `Pair`, `timestamp` — the backend accepts pair-name aliases `Pair|pair|symbol|ticker|market|currency` (`apps/webhooks/views.py:26`). Auth: **(1 preferred)** HMAC-SHA256 hex digest of the raw body with the secret → `X-Signature` header; **(2 legacy)** `"secret"` field in JSON.
- **Order history filters** (`GET investments/orders/`, verified `OrderFilter` `apps/investments/views.py:57-65`): `?pair=&exchange=&start_date=&end_date=&status=&side=&order_type=` (date filters are `gte`/`lte` on `created_at`).
- **Create credentials body:** `{"exchange_name", "api_key", "secret_key", "passphrase?", "is_testnet?"}` — API keys masked `****` on read.

---

## 15. Demanding acceptance checklist for the frontend build

- [ ] Token lifecycle: login → attach → refresh-on-401 → rotate → logout-blacklist; single shared session across tabs.
- [ ] 429 / throttle states rendered (OTP resend countdown, 2FA attempt limits).
- [ ] Consent terms/privacy gate before register.
- [ ] 2FA setup → confirm → QR code → withdrawal gate wired with TOTP input.
- [ ] Plan/usage gating driven by `bot-my-usage`/`my-subscription` limits.
- [ ] Bot grid status polled on cadence; start/stop surfaced by state.
- [ ] Admin sections hidden for non-staff; no reliant 403 surfaces.
- [ ] Exchange creds shown masked; connect/disconnect only via credentials endpoints.
- [ ] Pending (deposit/withdrawal/subscription) lifecycle states displayed distinctly.
- [ ] No hardcoded secrets; HTTPS-only; tokens out of XSS reach.
- [ ] Error handling reads the envelope (`error.code` / `error.message` / `error.field_errors`) with the flat `{"error": "<string>"}` fallback; 409 on subscribe surfaces "already subscribed" via `details.subscription_id`.
- [ ] `my-subscription/` null-state (`{"subscription": null}`) rendered as a proper empty state, not an error.
- [ ] **401 redirect path fixed:** every forced re-login goes to `/auth/login` (not `/login` — bug in `src/lib/api.ts`).
- [ ] **WS reconnect indicator** (yellow bar) wired to the market/bot socket backoff (§13.3).
- [ ] **Charts wired** (Recharts): portfolio + bot performance fed from `investments/positions/` / `bots/orders/`.
- [ ] **Skeletons + empty states** on every list page (bots, orders, transactions, referrals — §14.6).
- [ ] Missing pages from §14.5 "TO ADD" list delivered (incl. `/auth/forgot-password` 404 fix, Referrals, Subscriptions/upgrade, QAI screens, admin section).
