# API Reference

Base URL: `http://localhost:8000/api/`

## Authentication

### Register
`POST /api/auth/register/`
```json
{"email": "...", "password": "..."}
```
Response: `{"id", "email", "tokens": {"access", "refresh"}}`

### Login
`POST /api/auth/login/`
```json
{"email": "...", "password": "..."}
```
Response: `{"access", "refresh", "user": {"id", "email", "username"}}`

### Token Refresh
`POST /api/auth/token/refresh/` (body: `refresh`)

### Logout
`POST /api/auth/logout/` (body: `refresh`)

### Password Reset
`POST /api/auth/password-reset/` — sends OTP email
`POST /api/auth/password-reset/confirm/` — validates OTP + sets new password
`POST /api/auth/password-change/` — authenticated password change

### OAuth
`GET /api/auth/social/login/{provider}/?redirect=...` (Provider: `google`, `telegram`)

---

## Bot Management

Full code-verified reference (routes, payloads, gates, error contract, known
gaps): **[BOTS_API.md](BOTS_API.md)**. Summary of the live surface:

| Prefix | Methods | Notes |
|--------|---------|-------|
| `/api/bots/signal-bots/`, `/{id}/` | GET, POST, PUT, PATCH, DELETE | CRUD; POST needs active `custom` subscription; DELETE = soft-delete |
| `/api/bots/signal-bots/{id}/toggle_active/` | POST | Owner/staff only |
| `/api/bots/grid-bots/`, `/{id}/` | GET, POST, PUT, PATCH, DELETE | POST needs active `grid` subscription (1 bot per subscription) |
| `/api/bots/grid-bots/{id}/start/`, `/stop/` | POST | Executor control (flat success/error bodies) |
| `/api/bots/martingale-bots/`, `/{id}/` | GET, POST, PUT, PATCH, DELETE | POST needs active `martingale` subscription |
| `/api/bots/martingale-bots/{id}/start/`, `/stop/` | POST | Executor control |
| `/api/bots/quantum-funds/`, `/{id}/` | GET | Read-only, staff only (`IsAdminUser`) |
| `/api/bots/quantum-investments/`, `/{id}/` | GET, POST, PUT, PATCH, DELETE | POST needs active `quantum_ai` subscription |
| `/api/bots/quantum-investments/balance/` | GET | Totals of active investments (unpaginated) |
| `/api/bots/pair-configs/`, `/{id}/` | GET, POST, PUT, PATCH, DELETE | POST needs active subscription for the posted `bot_type` |
| `/api/bots/orders/`, `/{id}/`, `/recent/` | GET | Read-only order history (recent = latest 50) |
| `/api/bots/indicators/`, `/{id}/` | GET, POST, PUT, PATCH, DELETE | Indicator rows CRUD |
| `/api/bots/indicators/ema/`, `/rsi/`, `/bb/` | POST | TradingView webhooks; auth via `X-Webhook-Token` |

**Not part of this surface:** legacy aliases
`/api/bots/grid/{bot_id}/start|stop/` and
`/api/bots/martingale/{bot_id}/start|stop/` are declared but broken
(url kwarg mismatch → HTTP 500). There are no
`signal-bots/{id}/start|stop|get-signals|orders`, `grid-status`,
or `quantum-ai-bots/*` routes.

---

## Trading

### Dashboard
`GET /api/trading/dashboard/` — user position summary (admins: all users)

### Exchanges
`GET /api/trading/exchanges/` — supported exchange list
`GET /api/trading/exchanges/{id}/` — exchange detail

### Trading Pairs
`GET /api/trading/pairs/` — all pairs
`GET /api/trading/pairs/{id}/` — pair detail

### Exchange Rates
`GET /api/trading/exchange-rates/` — real-time rates (CCXT)

### Strategy Configs
`GET /api/trading/strategy-configs/` — preset strategy templates

---

## Exchange Credentials

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/exchanges/credentials/` | GET | List user's credentials |
| `/api/exchanges/credentials/` | POST | Create (key encrypted via Fernet) |
| `/api/exchanges/credentials/{id}/` | GET/PATCH/DELETE | CRUD |
| `/api/exchanges/credentials/{id}/test/` | POST | Test connection |

---

## Payments & Subscriptions

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/payments/subscriptions/` | GET | List subscription plans |
| `/api/payments/subscriptions/{id}/subscribe/` | POST | Create subscription (501) |
| `/api/payments/subscriptions/{id}/extend/` | POST | Extend (501) |
| `/api/payments/subscriptions/{id}/cancel/` | POST | Cancel (501) |
| `/api/payments/deposits/` | GET | List deposits |
| `/api/payments/deposits/` | POST | Create deposit request |
| `/api/payments/deposits/{id}/confirm/` | POST | Admin confirm |
| `/api/payments/withdrawals/` | GET | List withdrawals |
| `/api/payments/withdrawals/` | POST | Request withdrawal |
| `/api/payments/withdrawals/{id}/approve/` | POST | Admin approve |
| `/api/payments/withdrawals/{id}/reject/` | POST | Admin reject |
| `/api/payments/transactions/` | GET | Transaction history |

---

## Investments (Quantum AI)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/investments/blockchains/` | GET | Supported blockchains |
| `/api/investments/deposit-address/{blockchain_id}/` | GET | Deposit address |
| `/api/investments/create-deposit/` | POST | Initiate deposit |
| `/api/investments/transactions/` | GET | Investment transactions |

---

## Referrals

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/referrals/code/` | GET | Get referral code |
| `/api/referrals/code/` | POST | Generate referral code |
| `/api/referrals/stats/` | GET | Referral statistics |
| `/api/referrals/referrals/` | GET | Referred users list |
| `/api/referrals/rewards/` | GET | Reward history |
| `/api/referrals/apply/` | POST | Apply referral code |

---

## Webhooks (External)

### TradingView Signal Webhook
`POST /api/webhooks/custombot/`

Accepts TradingView webhook POST. Body includes action, symbol, exchange, indicators.

**Note:** Currently a stub — validates request format but does not execute trades.

### Indicator View (authenticated)
`GET /api/webhooks/signals/?type=rsi&symbol=BTC/USDT`
Returns indicator data from the latest processed signal.

---

## Subscriptions (Telegram)

`GET /api/subscriptions/plans/` — list Telegram subscription plans
`POST /api/subscriptions/plans/{id}/subscribe/` — subscribe

---

## User Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/users/profile/` | GET/PATCH | User profile |
| `/api/users/admin/dashboard/` | GET | Admin KPIs |
| `/api/users/admin/users/` | GET | User list |
| `/api/users/admin/users/{id}/` | GET | User detail |
| `/api/users/admin/users/{id}/toggle-active/` | POST | Toggle status |
| `/api/users/admin/users/{id}/update-balance/` | POST | Adjust balance |
| `/api/users/admin/audit-logs/` | GET | Audit logs |

---

## Error Response Format

Produced by the global DRF exception handler `core.exceptions.custom_exception_handler`:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Validation failed. Please check your input.",
    "details": {"email": ["This field is required."]},
    "field_errors": {"email": ["This field is required."]}
  },
  "timestamp": "2026-10-02T12:00:00.123456+00:00"
}
```

- `field_errors` only when errors are field-keyed; `details` carries the raw
  DRF detail; with `DEBUG=True` a `debug` object is appended.
- Codes: `AUTHENTICATION_REQUIRED`/`AUTHENTICATION_FAILED` (401),
  `PERMISSION_DENIED` (403), `VALIDATION_ERROR` (400), `RESOURCE_NOT_FOUND` (404),
  `METHOD_NOT_ALLOWED` (405), `RATE_LIMIT_EXCEEDED` (429),
  `INTERNAL_SERVER_ERROR` (500), plus trading-specific codes
  (`EXCHANGE_API_ERROR`, `INSUFFICIENT_BALANCE`, …).

**Exceptions:** bot action endpoints (`start`, `stop`, `toggle_active`) return a
flat `{"error": "..."}` body on failure and `{"success": true, "message": "..."}`
on success, and indicator webhook endpoints use `{"status": "success|error", ...}`
— see [BOTS_API.md](BOTS_API.md) §2.

Status codes: 200 OK, 201 Created, 400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not Found, 429 Too Many Requests.
