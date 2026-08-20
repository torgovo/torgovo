# Torgovo — Frontend Integration Brief (Prompt for Frontend AI)

> **What this is:** a complete, verified reference for building/adapting a frontend against the Torgovo backend API. Every route below was read directly from Django `urls.py` and views/serializers source on **2026-08-21**. Treat this as the single source of truth for contracts, auth, security constraints, and limitations.
>
> **What to do:** use this document as the working prompt for the frontend AI. Your existing frontend is the target — the now-deleted `frontend/` scaffold stub in the repo is NOT to be resurrected.

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
| Pagination | DRF `LimitOffsetPagination`-style where viewsets paginate (`count`, `next`, `previous`, `results`) |
| Health check | `GET /ht/` (django-health-check) |
| Metrics | `GET /metrics/` (Prometheus, ops only) |
| Django Admin | `GET /admin/` (staff only — never expose to end users) |

### Global webhook (public, secret-in-body)
- `POST /api/webhooks/custombot/` — TradingView alert delivery. **No auth header.** Authenticates via `X-Signature` HMAC **or** a `secret` field in the JSON body matched against the bot's `secret_key`. `401` = missing credentials, `403` = wrong secret. **Frontend never calls this** — it exists for external alert services.

---

## 2. Authentication & Security

### 2.1 Auth header
```
Authorization: Bearer <access_token>
```
All endpoints requiring a user (or admin) need this header. Omit it → `401 {"detail": "Authentication credentials were not provided."}`.

### 2.2 Token lifecycle (frontend must implement)
1. **Login** → `POST /api/auth/login/` returns `access` + `refresh`.
2. Store both (HttpOnly cookie or secure storage — never in plain JS-visible storage if possible; at minimum guard against XSS).
3. **Every API call** attaches `access`.
4. **Before expiry / on `401`** → `POST /api/auth/refresh-token/` with `{"refresh": "<refresh>"}` → new `access` + rotated `refresh`.
   ⚠️ Rotation on: each refresh invalidates the old refresh token. On refresh failure the whole session is dead — **force re-login**, do not retry in a loop.
5. **Logout** → `POST /api/auth/logout/` blacklists the refresh token server-side.

### 2.3 Security rules (non-negotiable)
- No hardcoded secrets, API keys, or passphrases anywhere client-side.
- Exchange API credentials are **fernet-encrypted at rest** and are **never returned in full**. Serializers expose them with `masked_secret_key`-style masked values only.
- Admin endpoints return `403 {"detail": "You do not have permission to perform this action."}` for non-staff — build UI that hides admin sections from non-admins rather than letting users hit 403s.
- Throttles exist — the UI must handle `429` (rate-limit) responses gracefully (see §6.8).
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
| GET | `my-subscription/` | user | My current subscription + limits |
| GET | `admin/channels/` | admin | All channels (admin) |
| POST | `admin/channels/create/` | admin | Create channel |
| GET | `telegram/plans/` | user | Telegram-specific plans |
| GET | `telegram/my-usage/` | user | Signal quota usage this period |
| POST | `telegram/subscribe/` | user | Subscribe to Telegram signal plan |
| GET | `bot-plans/` | user | Bot-automation plans |
| POST | `bot-subscribe/` | user | Subscribe to bot plan |
| GET | `bot-my-usage/` | user | Bot quota usage |

**Key contracts:**
- `bot-my-usage/` → `{"signals_used_this_month": int, "monthly_signal_limit": int, ...}`. The UI must gate/disable actions when usage ≥ limit.
- `my-subscription/` → current plan, balance, expiry — drives nav/feature gating.
- Plan capacity is enforced server-side on this model family (SignalBot uniqueness per subscription).

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
- **Grid monitoring is FAILURE-POLLING:** status/fills are fetched by the backend monitor; the frontend must poll (`/api/bots/grid-bots/` + `/api/bots/orders/`) on a cadence — **there is no websocket**.
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

**Key contracts:**
- **Withdrawal requires 2FA**: `POST withdrawals/` payload must include the current TOTP `code` (validated, not stored) and the user must have `two_factor_enabled=True`. Missing/weak/no-2FA → error telling the user to enable 2FA first.
- `subscriptions/bot/create/` creates a **pending** subscription awaiting admin approval — UI must show "pending approval" state.
- Deposits are admin-approve/reject gated (Quantum AI) — UI must show pending status until approved.

---

## 9. Referrals (`/api/referrals/`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `my-stats/` | user | Referral stats + codes |
| POST | `apply/` | user | Apply a referral code (`{"code": "..."}`) at first login |

Self-referral, duplicates, and invalid codes are rejected server-side. Referral codes are CSPRNG-generated.

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
| Admin | `users/admin/dashboard/stats/` → `users/admin/bots/overview/` → `users/admin/trade-logs/` → `payments/admin/deposits/<id>/approve|reject/` → `payments/subscriptions/bot/<id>/approve|reject/` → `users/admin/withdrawals/process/` |

---

## 11. Error Contract

| Status | Shape | Meaning |
|---|---|---|
| 400 | `{"field": ["error message"]}` or `{"detail": "..."}` | Validation / bad request |
| 401 | `{"detail": "Authentication credentials were not provided."}` | Missing/invalid token → try refresh, else re-login |
| 403 | `{"detail": "You do not have permission to perform this action."}` | Logged in but not allowed (admin gating) |
| 404 | `{"detail": "Not found."}` | Unknown resource/ID |
| 429 | DRF throttle detail | Rate limited — show wait/retry state; do NOT hammer (OTP, phone_verification, two_factor are 5/hour) |
| 500 | server error | Backend fault — surface generic error + retry |

**Client rule:** when a 401 arrives on an authenticated call, attempt one `refresh-token/` rotation and replay; if rotation also 401s, terminate session and force sign-in.

---

## 12. Known Issues & Limitations (verified)

1. **No websockets** — all live data (grid fills, bot status, positions) is **polling-based**. Set a sensible interval; the backend monitor is the source of truth.
2. **Payment rails**: deposits/bot-subscriptions require **admin approval**; withdrawals require **admin processing**. The UI must reflect lifecycle states (`pending`, `approved`, `rejected`).
3. **2FA is a hard gate on withdrawals** — enable-2FA flow (`2fa/setup/` → `2fa/confirm/`) must be polished; users cannot withdraw without it.
4. **Register needs consent booleans** — missing them fails validation; frontend must present an explicit terms/privacy acceptance UI.
5. **Exchange credentials are masked** on every read — a "connected: yes/no + masked key" pattern is the only allowed display.
6. **Legacy `exchanges/` vs main `trading/`** — both live; prefer `trading/` for new integration, but `exchanges/credentials/` is the connect flow. Don't create parallel duplicate UI.
7. **Public plans before auth** (`subscriptions/public/plans/`) for the marketing/pricing page — everything else requires auth.
8. **Refresh rotation** — old refresh tokens die on every use; don't cache/share a refresh token across tabs without re-login sync.
9. **Single-owner display models** — `investments/orders|positions|balances` are account-scoped; 404/empty for other users (never leak cross-user data).
10. **No `/users/profile/` at the auth scope** — profile lives at `auth/user/` and `investments/users/profile/`. Do not hardcode `/users/profile/`.

---

## 13. Demanding acceptance checklist for the frontend build

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
