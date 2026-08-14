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

### SignalBot

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/bots/signal-bots/` | GET | List user's SignalBots |
| `/api/bots/signal-bots/` | POST | Create SignalBot |
| `/api/bots/signal-bots/{id}/` | GET | Retrieve details |
| `/api/bots/signal-bots/{id}/` | PATCH | Partial update |
| `/api/bots/signal-bots/{id}/` | DELETE | Soft-delete |
| `/api/bots/signal-bots/{id}/start/` | POST | Start bot |
| `/api/bots/signal-bots/{id}/stop/` | POST | Stop bot |
| `/api/bots/signal-bots/{id}/get-signals/` | GET | View signals |
| `/api/bots/signal-bots/{id}/orders/` | GET | View orders |

**Create SignalBot:**
```json
{
  "name": "My EMA Bot",
  "symbol": "BTC/USDT",
  "exchange_id": 1,
  "exchange": 1,
  "signal_type": "webhook",
  "rsi_period": 14,
  "rsi_overbought": 70,
  "rsi_oversold": 30,
  "ema_short_period": 9,
  "ema_long_period": 21,
  "bb_period": 20,
  "bb_std_dev": 2,
  "trade_direction": "both",
  "amount": "0.001"
}
```

### GridBot

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/bots/grid-bots/` | GET | List |
| `/api/bots/grid-bots/` | POST | Create |
| `/api/bots/grid-bots/{id}/` | GET/PATCH/DELETE | CRUD |
| `/api/bots/grid-bots/{id}/start/` | POST | Start |
| `/api/bots/grid-bots/{id}/stop/` | POST | Stop |
| `/api/bots/grid-bots/{id}/grid-status/` | GET | Grid order status |

**Create GridBot:**
```json
{
  "name": "BTC Grid",
  "symbol": "BTC/USDT",
  "exchange_id": 1,
  "upper_price": "70000",
  "lower_price": "60000",
  "grid_count": 10,
  "total_investment": "1000"
}
```

### MartingaleBot

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/bots/martingale-bots/` | GET | List |
| `/api/bots/martingale-bots/` | POST | Create |
| `/api/bots/martingale-bots/{id}/` | GET/PATCH/DELETE | CRUD |
| `/api/bots/martingale-bots/{id}/start/` | POST | Start |
| `/api/bots/martingale-bots/{id}/stop/` | POST | Stop |

**Create MartingaleBot:**
```json
{
  "name": "ETH Martingale",
  "symbol": "ETH/USDT",
  "exchange_id": 1,
  "base_order_size": "0.01",
  "safety_order_size": "0.02",
  "max_safety_orders": 3,
  "price_deviation": 1.0,
  "take_profit": 1.5
}
```

### QuantumAIBot (Admin)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/bots/quantum-ai-bots/` | GET | List |
| `/api/bots/quantum-ai-bots/` | POST | Create |
| `/api/bots/quantum-ai-bots/{id}/` | GET/PATCH/DELETE | CRUD |
| `/api/bots/quantum-ai-bots/{id}/start/` | POST | Start |
| `/api/bots/quantum-ai-bots/{id}/stop/` | POST | Stop |
| `/api/bots/quantum-ai-bots/{id}/performance/` | GET | P/L metrics |

**Create QuantumAIBot:**
```json
{
  "name": "Quantum Pool A",
  "symbol": "BTC/USDT",
  "exchange_id": 1,
  "min_investment": "100",
  "max_investors": 1000,
  "profit_share_percentage": 20
}
```

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

```json
{
  "detail": "Error message",
  "code": "validation_error",
  "field_errors": {
    "email": ["This field is required."]
  }
}
```

Status codes: 200 OK, 201 Created, 400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not Found, 429 Too Many Requests.
