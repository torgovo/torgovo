# Torgovo2 Frontend Connectivity Document

> This document is the single source of truth for building the Torgovo2 frontend.
> It covers every API endpoint, auth flow, WebSocket connection, data type, and UI pattern.
> No additional research should be needed — build every page, component, and state transition from this doc.

---

## Table of Contents

1. [Stack & Tech Decisions](#1-stack--tech-decisions)
2. [Auth Flow (JWT)](#2-auth-flow-jwt)
3. [API Base URL & Conventions](#3-api-base-url--conventions)
4. [WebSocket Connection](#4-websocket-connection)
5. [Page-by-Page Endpoint Reference](#5-page-by-page-endpoint-reference)
6. [Data Models / TypeScript Types](#6-data-models--typescript-types)
7. [Error Handling](#7-error-handling)
8. [UI/UX Patterns to Adopt](#8-uiux-patterns-to-adopt)
9. [Special Behaviors](#9-special-behaviors)

---

## 1. Stack & Tech Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Framework** | React 18+ with Vite | Already set up in `frontend/` |
| **Routing** | react-router-dom v6 | Standard for React SPAs |
| **HTTP client** | Axios | Interceptors for token refresh |
| **State management** | React Context + useReducer for auth; React Query (TanStack Query) for server data | No Redux needed for this scope |
| **UI library** | TailwindCSS + Headless UI | Already configured in `frontend/` |
| **WebSocket** | Native WebSocket API | No library needed; lightweight |
| **Charts** | TradingView Lightweight Charts or Recharts | For portfolio/bot performance |
| **Forms** | React Hook Form + Zod validation | Clean form handling with type-safe schemas |

---

## 2. Auth Flow (JWT)

### 2.1 Token Structure

```
Access token:  short-lived (default 15 min, configurable)
Refresh token: long-lived  (default 7 days, configurable)
Rotation:      ON — each refresh returns a new refresh token and blacklists the old one
Blacklist:     ON — logout and password change invalidate all outstanding refresh tokens
```

### 2.2 Registration

```
POST  /api/auth/register/
Body: { "email": "string", "password": "string", "password_confirm": "string",
        "first_name?": "string", "last_name?": "string", "phone_number?": "string" }
200:  { "user": { "id", "email", "username", "first_name", "last_name", "full_name",
                  "phone_number", "is_email_verified", "is_phone_verified",
                  "date_joined", "last_login", "timezone", "two_factor_enabled",
                  "profile": {...} },
        "tokens": { "access_token": "string", "refresh_token": "string" },
        "message": "Registration successful...",
        "verification_sent": true }
```

**Frontend action:** Save both tokens to localStorage. Redirect to dashboard.

### 2.3 Login

```
POST  /api/auth/login/
Body: { "email": "string", "password": "string" }
200:  { "user": { ... }, "tokens": { "access_token", "refresh_token" }, "message": "Login successful." }
429:  { "error": { "code": "LOCKED_OUT", "message": "Too many failed attempts..." } }
```

**Frontend action:** Save tokens. If 429, show lockout message (5 failed attempts lock 15 min).

### 2.4 Token Storage

```typescript
// Store on login/register
localStorage.setItem('access_token', data.tokens.access_token);
localStorage.setItem('refresh_token', data.tokens.refresh_token);

// Axios interceptor — attach to every request
axios.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});
```

### 2.5 Token Refresh (Axios interceptor)

```typescript
// On any 401 response, try refresh. If refresh fails, redirect to /login.
axios.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      const refreshToken = localStorage.getItem('refresh_token');
      if (refreshToken) {
        try {
          const { data } = await axios.post('/api/auth/refresh-token/', {
            refresh_token: refreshToken
          });
          localStorage.setItem('access_token', data.access_token);
          localStorage.setItem('refresh_token', data.refresh_token); // NEW refresh token
          error.config.headers.Authorization = `Bearer ${data.access_token}`;
          return axios(error.config); // retry original request
        } catch {
          localStorage.clear();
          window.location.href = '/login';
        }
      } else {
        localStorage.clear();
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);
```

**Critical:** The refresh endpoint returns a **new** `refresh_token` (rotation). Always update both tokens, not just access_token.

### 2.6 Logout

```
POST  /api/auth/logout/
Auth:  Bearer token
Body:  { "refresh_token": "string (optional but recommended)" }
200:   { "message": "Logout successful." }
```

**Frontend action:** Call endpoint, clear localStorage, redirect to `/login`.

### 2.7 Password Change

```
POST  /api/auth/change-password/
Auth:  Bearer token
Body:  { "old_password", "new_password", "new_password_confirm" }
200:   { "message": "Password changed successfully." }
```

**Side effect:** ALL existing refresh tokens are blacklisted. User must log in again.

### 2.8 Password Reset

```
POST  /api/auth/password-reset/
Body:  { "email" }
200:   { "message": "If an account exists, a password reset link has been sent." }

POST  /api/auth/password-reset/confirm/
Body:  { "token", "new_password", "new_password_confirm" }
200:   { "message": "Password reset successful." }
```

### 2.9 Email/Phone Verification

```
POST  /api/auth/verify-email/            (sends verification email)
GET   /api/auth/verify-email/<token>/    (click link from email)

POST  /api/auth/verify-phone/            (sends SMS code)
Body: { "phone_number" }
POST  /api/auth/verify-phone/confirm/
Body: { "code", "phone_number" }
```

### 2.10 Google OAuth

```
POST  /api/auth/google/
Body:  { "access_token": "Google OAuth token from frontend" }
200:   { "user": {...}, "tokens": { "access_token", "refresh_token" },
         "message": "...", "is_new_user": true }
```

---

## 3. API Base URL & Conventions

### Base URL
```
Development: http://localhost:8000
Production:  https://api.torgovo.com
```

All endpoints are prefixed with `/api/`.

### Headers
```
Authorization: Bearer <access_token>        (most endpoints)
Content-Type:  application/json
X-Webhook-Token: <uuid>                     (only for indicator webhooks)
```

### Pagination

All list endpoints return paginated responses when `pagination_class` is set:

```typescript
interface PaginatedResponse<T> {
  count: number;        // total items
  next: string | null;  // URL to next page (or null)
  previous: string | null;
  results: T[];         // current page data
}
```

Query params: `?page=1&page_size=20` (page_size defaults to 20, max 100).

### Error Response Shape

```typescript
interface ErrorResponse {
  error: string | { code: string; message: string; details?: any };
}
```

HTTP status codes:
- 400: Validation error / bad request
- 401: Not authenticated
- 403: Not authorized (permission denied)
- 404: Resource not found
- 429: Rate limited
- 500: Server error (never contains internal details)

---

## 4. WebSocket Connection

### Endpoint
```
ws://localhost:8000/ws/bot/<bot_id>/?token=<jwt_access_token>
wss://api.torgovo.com/ws/bot/<bot_id>/?token=<jwt_access_token>
```

### Auth
- Token is the same JWT **access** token used for REST API
- Passed as `?token=` query parameter
- Server validates and checks bot ownership
- Close codes: `4001` = auth failed, `4003` = forbidden/not owner

### Messages from Server

```typescript
// Bot state update
{ "type": "bot_update", "data": { ... } }

// Error
{ "type": "error", "message": "string" }
```

### Connection Lifecycle

```typescript
// Connect
const ws = new WebSocket(`ws://host/ws/bot/${botId}/?token=${accessToken}`);

ws.onopen = () => console.log('Connected');
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  if (msg.type === 'bot_update') { /* update bot state in UI */ }
  if (msg.type === 'error') { /* show error toast */ }
};
ws.onclose = (event) => {
  if (event.code === 4001) { /* auth failed — redirect to login */ }
  if (event.code === 4003) { /* forbidden — show access denied */ }
};

// Disconnect (e.g., on page leave)
ws.close();
```

### Recommended: Custom React Hook

```typescript
// src/hooks/useBotWebSocket.ts
function useBotWebSocket(botId: string | null) {
  // connect on botId set, disconnect on cleanup
  // auto-reconnect on token refresh
  // return { connected, lastMessage, error }
}
```

---

## 5. Page-by-Page Endpoint Reference

### 5.1 Login Page (`/login`)

| Endpoint | Method | Notes |
|----------|--------|-------|
| `/api/auth/login/` | POST | Also redirect here after register |

### 5.2 Register Page (`/register`)

| Endpoint | Method | Notes |
|----------|--------|-------|
| `/api/auth/register/` | POST | After success, redirect to dashboard |

### 5.3 Forgot Password (`/forgot-password`)

| Endpoint | Method | Notes |
|----------|--------|-------|
| `/api/auth/password-reset/` | POST | Step 1: send email |
| `/api/auth/password-reset/confirm/` | POST | Step 2: reset with token |

### 5.4 Dashboard (`/dashboard`)

| Endpoint | Method | Notes |
|----------|--------|-------|
| `/api/auth/profile/` | GET | User info + subscription status |
| `/api/investments/balances/summary/` | GET | Total portfolio value |
| `/api/bots/signal-bots/` | GET | Webhook bots list |
| `/api/bots/grid-bots/` | GET | Grid bots list |
| `/api/bots/martingale-bots/` | GET | Martingale bots list |
| `/api/bots/orders/recent/` | GET | Last 50 orders |
| `/api/investments/users/my-orders/` | GET | Paginated order history (query params: `?category=&pair=&exchange=&start_date=&end_date=`) |
| `/api/bots/quantum-investments/balance/` | GET | Quantum AI investment balance |

**Dashboard widgets:**
- Portfolio value (balances summary)
- Active bots count + status summary
- Recent orders (last 10)
- Profit/loss summary
- Quick actions: create bot, deposit

### 5.5 Bot Management (`/bots`)

**List all bots:**

| Endpoint | Method | Notes |
|----------|--------|-------|
| `/api/bots/signal-bots/` | GET | List webhook signal bots |
| `/api/bots/grid-bots/` | GET | List grid bots |
| `/api/bots/martingale-bots/` | GET | List martingale bots |

**Create bot (per type):**

| Endpoint | Method | Notes |
|----------|--------|-------|
| `/api/bots/signal-bots/` | POST | Body: `{ bot_name, exchange_name, market_type, trading_pair, default_amount, take_profit_percent, stop_loss_percent }` |
| `/api/bots/grid-bots/` | POST | Body: `{ bot_name, exchange_name, trading_pair, base_amount, favor_levels, against_levels, level_spacing_percent }` |
| `/api/bots/martingale-bots/` | POST | Body: `{ bot_name, exchange_name, trading_pair, base_amount, favor_levels, against_levels, multiplier_factor }` |

**Bot detail / edit / delete:**

| Endpoint | Notes |
|----------|-------|
| `GET /api/bots/signal-bots/<pk>/` | Full bot details |
| `PUT /api/bots/signal-bots/<pk>/` | Update |
| `PATCH /api/bots/signal-bots/<pk>/` | Partial update |
| `DELETE /api/bots/signal-bots/<pk>/` | Soft delete |

**Bot start/stop:**

| Endpoint | Notes |
|----------|-------|
| `POST /api/bots/grid/<bot_id>/start/` | Start grid bot (via Celery) |
| `POST /api/bots/grid/<bot_id>/stop/` | Stop grid bot |
| `POST /api/bots/martingale/<bot_id>/start/` | Start martingale bot |
| `POST /api/bots/martingale/<bot_id>/stop/` | Stop martingale bot |

### 5.6 Create Bot Flow

**Step 1:** Select bot type (signal | grid | martingale)

**Step 2:** Select exchange — fetch available exchanges:
```
GET /api/trading/exchanges/list/
Response: { "success": true, "data": [{ name, display_name, is_active, supports_testnet, supported_features, fee_rates }] }
```

**Step 3:** Select trading pair — fetch pairs for chosen exchange:
```
GET /api/trading/exchanges/<exchange_name>/symbols/
Response: { "success": true, "exchange": "bybit", "symbols": ["BTC/USDT", "ETH/USDT", ...] }
```

**Step 4:** Configure bot parameters (see bot-specific fields above)

**Step 5:** Submit → bot created. For signal bots, the response includes `webhook_url` and `webhook_id` — display these to the user so they can configure TradingView.

### 5.7 Bot Detail Page (`/bots/:id`)

| Endpoint | Notes |
|----------|-------|
| `GET /api/bots/grid-bots/<pk>/` | Bot details |
| `GET /api/bots/orders/?category=grid&bot=<bot_id>` | Orders for this bot |
| WebSocket `ws/bot/<bot_id>/?token=<access_token>` | Real-time updates |

**Show:** Bot status, configuration, performance stats, order history, real-time WebSocket feed.

### 5.8 Signal Bot Webhook Config

When a signal bot is created, display to the user:
```
Webhook URL: https://api.torgovo.com/api/webhooks/custombot/
Bot ID:     <UUID>
Secret Key: <show once, allow copy + regenerate>
```

### 5.9 Exchange Credentials (`/settings/exchanges`)

| Endpoint | Method | Notes |
|----------|--------|-------|
| `/api/trading/exchanges/` | GET | Available exchanges |
| `/api/trading/exchanges/list/` | GET | Same data, flat format |
| `/api/trading/credentials/` | GET, POST | List / create credentials |
| `/api/trading/credentials/active/` | GET | Active credentials only |

**Create credential:**
```
POST /api/trading/credentials/
Body: { exchange_name, api_key, secret_key, passphrase?, is_testnet? }
```

**Response:** API keys are masked as `****` in read responses.

### 5.10 TradingView Webhook Settings

For signal bots, the webhook integration works as follows:

1. User creates a SignalBot → gets `webhook_url` and `secret_key`
2. User configures TradingView alert to POST to:
   ```
   POST https://api.torgovo.com/api/webhooks/custombot/
   ```
3. TradingView alert payload includes `bot_id`, `side`, `Pair`, `timestamp`
4. **Auth mode 1 (preferred):** Compute HMAC-SHA256 hex digest of raw body using `secret_key`, send as `X-Signature` header
5. **Auth mode 2 (legacy):** Include `"secret": "<secret_key>"` in JSON payload

### 5.11 Subscriptions / Plans (`/subscriptions`)

| Endpoint | Method | Notes |
|----------|--------|-------|
| `/api/payments/subscription-plans/` | GET | Available plans with pricing |
| `/api/payments/subscriptions/bot/` | GET | User's subscriptions |
| `/api/payments/subscriptions/bot/create/` | POST | Create (requires plan_id + payment proof) |

**Create subscription:**
```
POST /api/payments/subscriptions/bot/create/
Body: FormData with:
  - plan_id (UUID)
  - exchange_name
  - payment_screenshot (file upload)
  - payment_transaction_hash
  - payment_blockchain
```

### 5.12 Deposits (`/deposits`)

| Endpoint | Method | Notes |
|----------|--------|-------|
| `/api/investments/bots/blockchain-addresses/` | GET | Get deposit addresses by coin/blockchain |
| `/api/investments/bots/quantum-ai/<bot_id>/deposit/` | POST | Submit deposit |

**Submit deposit:**
```
POST /api/investments/bots/quantum-ai/<bot_id>/deposit/
Body: FormData with:
  - amount (decimal)
  - coin_type
  - blockchain
  - transaction_hash
  - from_address
  - screenshot (file upload)
Response: { message, deposit_id, status }
```

### 5.13 Withdrawals (`/withdrawals`)

| Endpoint | Method | Notes |
|----------|--------|-------|
| `/api/payments/withdrawals/` | GET, POST | List / create |
| `/api/payments/withdrawals/<pk>/cancel/` | POST | Cancel pending |

**Create withdrawal:**
```
POST /api/payments/withdrawals/
Body: { amount, currency, blockchain, to_address, two_factor_code }
```

**Security gates:** Email must be verified, 2FA code required, max 3 pending withdrawals.

### 5.14 Transactions History (`/transactions`)

| Endpoint | Method | Notes |
|----------|--------|-------|
| `/api/payments/transactions/` | GET | Paginated list |
| `/api/payments/transactions/recent/` | GET | Last 20 |
| `/api/payments/transactions/by_type/?type=deposit` | GET | Filtered |

### 5.15 Orders History (`/orders`)

| Endpoint | Method | Notes |
|----------|--------|-------|
| `/api/investments/orders/` | GET, POST | Paginated, filterable |
| `/api/bots/orders/recent/` | GET | Last 50 |
| `/api/investments/orders/<pk>/cancel/` | POST | Cancel pending order |

**Order filters:** `?category=&pair=&exchange=&start_date=&end_date=&status=&side=&order_type=`

### 5.16 Positions (`/positions`)

| Endpoint | Method | Notes |
|----------|--------|-------|
| `/api/investments/positions/` | GET, POST | List / create |
| `/api/investments/positions/<pk>/close/` | POST | Close position |

### 5.17 Technical Indicators (`/indicators`)

| Endpoint | Method | Notes |
|----------|--------|-------|
| `/api/investments/technical-indicators/` | GET | Filtered by type, pair, exchange |
| `/api/webhooks/custombot/indicators/ema/?symbol=BTC/USDT&period=20&timeframe=1h&exchange=binance` | GET | Compute EMA (no auth needed) |
| `/api/webhooks/custombot/indicators/rsi/?symbol=BTC/USDT&period=14&timeframe=1h&exchange=binance` | GET | Compute RSI (no auth needed) |

### 5.18 Pair Configs (`/pair-configs`)

| Endpoint | Method | Notes |
|----------|--------|-------|
| `/api/bots/pair-configs/` | GET, POST | CRUD for per-pair bot configuration |

**PairConfig fields:** `pair_symbol, bot_type, quantity, favor_levels, against_levels, Order_Type, Amount_Type, SLTP_Type, Stop_Loss, Take_Profit, RSI_Lower, RSI_Upper, RSI_Entry, BB_Entry, EMA_RSI_Entry, EMA_BB_Entry, BB_RSI_Entry, EMA_BB_RSI_Entry, BB_Exit, RSI_Exit, EMA_RSI_Exit, EMA_BB_Exit, BB_RSI_Exit, EMA_BB_RSI_Exit, SL_Exit`

### 5.19 Exchange Rates

```
GET /api/trading/rates/?pairs=BTC/USDT,ETH/USDT&exchange=bybit
Response: { "success": true, "rates": {
  "BTC/USDT": { "price": "12345.67", "exchange": "bybit", "volume_24h": 12345.67, ... }
}, "timestamp": "..." }
```

### 5.20 Referrals (`/referrals`)

| Endpoint | Method | Notes |
|----------|--------|-------|
| `/api/referrals/my-stats/` | GET | Referral code, count, bonus, link |
| `/api/referrals/apply/` | POST | Apply another user's code |

### 5.21 Telegram Signal Subscriptions (`/telegram`)

| Endpoint | Method | Notes |
|----------|--------|-------|
| `/api/subscriptions/plans/` | GET | Telegram signal plans |
| `/api/subscriptions/subscriptions/` | GET, POST | User's subscriptions |
| `/api/subscriptions/telegram/subscribe/` | POST | Subscribe (requires payment proof) |

### 5.22 User Profile / Settings (`/settings/profile`)

| Endpoint | Method | Notes |
|----------|--------|-------|
| `GET /api/auth/profile/` | GET | Full profile |
| `PUT /api/auth/profile/update/` | PUT, PATCH | Update: timezone, notifications, trading_preferences |
| `POST /api/auth/change-password/` | POST | Change password |
| `POST /api/auth/verify-email/` | POST | Request email verification |
| `POST /api/auth/verify-phone/` | POST | Request phone verification |

### 5.23 Admin Pages (`/admin/*`) — Staff Only

| Endpoint | Method | Notes |
|----------|--------|-------|
| `/api/users/admin/dashboard/stats/` | GET | Platform stats |
| `/api/users/admin/bots/overview/` | GET | Bot overview by type + exchange |
| `/api/users/admin/` | GET | User list (filterable) |
| `/api/users/admin/<pk>/` | GET, PUT, PATCH | User detail |
| `/api/users/admin/trade-logs/` | GET | All trade logs |
| `/api/users/admin/blockchain-addresses/` | POST | Create deposit address |
| `/api/users/admin/users/<pk>/restrict/` | POST | Enable/disable/restrict user |
| `/api/users/admin/emails/send/` | POST | Send system email |
| `/api/users/admin/withdrawals/process/` | POST | Batch process withdrawals |
| `/api/payments/admin/deposits/<id>/approve/` | POST | Approve deposit |
| `/api/payments/admin/deposits/<id>/reject/` | POST | Reject deposit |
| `/api/payments/subscriptions/bot/<id>/approve/` | POST | Approve subscription |
| `/api/payments/subscriptions/bot/<id>/reject/` | POST | Reject subscription |
| `/api/payments/withdrawals/<pk>/approve/` | POST | Approve withdrawal |
| `/api/payments/withdrawals/<pk>/reject/` | POST | Reject withdrawal |

---

## 6. Data Models / TypeScript Types

### 6.1 User

```typescript
interface User {
  id: string;              // UUID
  email: string;
  username?: string;
  first_name: string;
  last_name: string;
  full_name: string;
  phone_number: string;
  is_email_verified: boolean;
  is_phone_verified: boolean;
  two_factor_enabled: boolean;
  date_joined: string;     // ISO datetime
  last_login: string;      // ISO datetime
  timezone: string;
  profile: UserProfile;
}

interface UserProfile {
  subscription_plan: string;
  subscription_plan_display: string;
  max_bots_allowed: number;
  timezone: string;
  trading_preferences: Record<string, any>;
  demo_trading_enabled: boolean;
  email_notifications: boolean;
  sms_notifications: boolean;
  push_notifications: boolean;
  is_subscription_active: boolean;
  referral_code: string;
  total_trades_executed: number;
  total_volume_traded: number;
}
```

### 6.2 Auth Tokens

```typescript
interface AuthTokens {
  access_token: string;   // JWT, expires ~15min
  refresh_token: string;  // JWT, expires ~7 days
}
```

### 6.3 Bot Models

```typescript
// Base fields (all bots share these)
interface BotBase {
  id: string;                    // UUID
  user: string;                  // User UUID
  bot_name: string;
  category: 'webhook' | 'grid' | 'martingale' | 'quantum_ai';
  exchange: string;              // Exchange UUID
  trading_pair: string;          // TradingPair UUID
  status: 'idle' | 'running' | 'paused' | 'stopped' | 'error';
  is_active: boolean;
  total_trades: number;
  successful_trades: number;
  total_profit_loss: string;     // Decimal as string
  take_profit_percent: string;
  stop_loss_percent: string;
  max_position_size: string;
  started_at: string | null;
  stopped_at: string | null;
  created_at: string;
  updated_at: string;
}

interface SignalBot extends BotBase {
  webhook_id: string;            // UUID
  webhook_url: string;
  secret_key: string;
  default_amount: string;
  last_triggered: string | null;
}

interface GridBot extends BotBase {
  base_amount: string;
  favor_levels: number;
  against_levels: number;
  level_spacing_percent: string;
  current_grid_level: number;
  total_invested: string;
  is_running: boolean;
  // BotSubscription link
  subscription: string | null;
  bot_name: string;
  exchange_name: string;
  trading_pair: string;
  favor_level_qty: number;
  against_level_qty: number;
  favor_level_difference: number;
  against_level_difference: number;
  take_profit_percent: number;
  stop_loss_percent: number;
  amount_type: string;
}

interface MartingaleBot extends BotBase {
  base_amount: string;
  favor_levels: number;
  against_levels: number;
  level_spacing_percent: string;
  multiplier_factor: string;
  current_level: number;
  consecutive_losses: number;
  // same subscription/exchange fields as GridBot
  is_running: boolean;
  subscription: string | null;
  bot_name: string;
  exchange_name: string;
  trading_pair: string;
}
```

### 6.4 Orders

```typescript
interface Order {
  id: string;
  user: string;
  pair: string;
  side: 'BUY' | 'SELL';
  category: string;        // 'signal_bot', 'grid', 'martingale', 'quantum_ai'
  order_type: string;      // 'market', 'limit'
  quantity: number;
  price: number;
  exchange: string;
  status: 'pending' | 'executed' | 'cancelled' | 'failed';
  signal_bot: string | null;
  grid_bot: string | null;
  martingale_bot: string | null;
  quantum_ai_investment: string | null;
  description: string;
  details: Record<string, any>;
  created_at: string;
}
```

### 6.5 Exchange Credentials

```typescript
interface ExchangeCredentials {
  id: string;
  user: string;
  exchange_name: string;   // 'binance', 'bybit', 'okx', 'mexc', 'alpaca'
  api_key: string;         // Masked: 'abcd****1234'
  is_testnet: boolean;
  is_active: boolean;
  permissions: string[];
  notes: string;
  created_at: string;
}
```

### 6.6 Subscription / Plan

```typescript
interface SubscriptionPlan {
  id: string;
  name: string;
  slug: string;
  price_monthly: string;
  price_yearly: string;
  max_bots_allowed: number;
  max_webhooks_allowed: number;
  features: Record<string, any>;
  is_active: boolean;
  trial_days: number;
}

interface BotSubscription {
  id: string;
  user: string;
  plan: SubscriptionPlan;
  status: 'pending_payment' | 'pending_approval' | 'active' | 'expired' | 'rejected';
  payment_screenshot: string | null;
  payment_transaction_hash: string;
  payment_blockchain: string;
  exchange_name: string;
  started_at: string | null;
  expires_at: string | null;
  is_expired: boolean;
}
```

### 6.7 Balances

```typescript
interface BalanceSummary {
  total_usdt_value: string;
  balances: UserBalance[];
}

interface UserBalance {
  id: string;
  user: string;
  currency: string;       // 'USDT', 'BTC', 'ETH', etc.
  available: string;
  hold: string;
}
```

### 6.8 Deposit / Withdrawal

```typescript
interface QuantumAIDeposit {
  id: string;
  user: string;
  bot_name: string;
  amount: string;
  currency: string;
  status: 'pending' | 'approved' | 'rejected';
  blockchain: string;
  transaction_hash: string;
  from_address: string;
  created_at: string;
}

interface WithdrawalRequest {
  id: string;
  user: string;
  amount: string;
  currency: string;
  blockchain: string;
  to_address: string;
  status: 'pending' | 'processing' | 'completed' | 'rejected' | 'cancelled';
  network_fee: string;
  processing_fee: string;
  total_amount: string;
  is_flagged: boolean;
  created_at: string;
}
```

### 6.9 Payment Transaction

```typescript
interface PaymentTransaction {
  id: string;
  user: string;
  transaction_type: 'deposit' | 'withdrawal' | 'quantum_ai_payout' | 'referral_bonus' | 'subscription';
  amount: string;
  currency: string;
  status: 'pending' | 'completed' | 'failed';
  description: string;
  created_at: string;
}
```

### 6.10 Exchange / Trading Pairs

```typescript
interface Exchange {
  id: string;
  name: string;
  display_name: string;
  is_active: boolean;
  supports_testnet: boolean;
  supported_features: string[];
  rate_limit_per_minute: number;
  fee_rates: Record<string, any>;
}

interface TradingPair {
  id: string;
  exchange: string;
  symbol: string;
  base_currency: string;
  quote_currency: string;
  price_precision: number;
  quantity_precision: number;
  min_quantity: string;
  is_active: boolean;
}
```

### 6.11 Exchange Rate

```typescript
interface ExchangeRate {
  [symbol: string]: {
    price: number;
    exchange: string;
    volume_24h: number;
    change_24h: number;
    high_24h: number;
    low_24h: number;
    bid: number;
    ask: number;
    timestamp: string;
  };
}
```

### 6.12 Referral

```typescript
interface ReferralStats {
  referral_code: string;
  total_referrals: number;
  total_bonus_usdt: string;
  referral_link: string;      // e.g. "https://api.torgovo.com/signup?ref=TOR..."
}
```

---

## 7. Error Handling

### Common error types and how to handle them:

| Status | Meaning | Frontend Action |
|--------|---------|-----------------|
| 200 | Success | Use response data |
| 201 | Created | Show success toast, redirect or refresh list |
| 400 | Validation error | Show field-level errors from response |
| 401 | Not authenticated | Attempt token refresh; if fails, redirect to `/login` |
| 403 | Not authorized | Show "permission denied" message |
| 404 | Resource not found | Show 404 page or "not found" toast |
| 429 | Rate limited | Show "too many requests, try later" with retry-after |
| 500 | Server error | Show "something went wrong" toast (never show details) |
| 503 | Service unavailable | Show maintenance page |

### Axios interceptor pattern:

```typescript
// src/lib/api.ts
import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000/api',
  headers: { 'Content-Type': 'application/json' },
});

// Request interceptor: attach auth token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Response interceptor: handle 401 → refresh → retry
// (see Section 2.5 for full implementation)

export default api;
```

---

## 8. UI/UX Patterns to Adopt

### Loading States
- Use skeleton loaders for all list pages (bots list, orders, transactions)
- Use spinner buttons for action forms (start/stop bot, create)
- Use progress indicators for file uploads (payment screenshots)

### Empty States
- "No bots yet. Create your first bot to get started." + CTA button
- "No orders found." for empty order history
- "No transactions yet." for empty transaction list

### Error States
- Toast notifications for success/error (auto-dismiss success, manual dismiss for errors)
- Inline field errors for forms (below each input)
- Network error banner when API is unreachable

### Confirmations
- Start/Stop bot: confirmation dialog "Are you sure you want to start/stop [bot_name]?"
- Cancel order: confirmation dialog
- Delete bot: confirmation dialog with bot name typed out
- Withdrawal: confirmation with summary (amount, address, fees)

### Forms
- Side-by-side label + input for profile settings
- Step-by-step wizard for bot creation (type → exchange → pair → parameters → review)
- File upload with drag-and-drop + preview for payment screenshots

### Data Display
- Tables with sortable columns for orders, transactions, bots
- Cards for bot summary (status badge, name, pair, P&L)
- Charts for portfolio performance over time
- Status badges: green (running/active), yellow (paused/pending), red (error/stopped), gray (idle)

### Notifications
- Real-time toast for bot state changes (via WebSocket)
- WebSocket reconnection indicator (subtle yellow bar when reconnecting)

---

## 9. Special Behaviors

### 9.1 Token Refresh Race Condition

When multiple API calls are in-flight and get 401 simultaneously, only ONE refresh should occur. Use a promise-based lock:

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

// Inside 401 interceptor:
if (!isRefreshing) {
  isRefreshing = true;
  try {
    const { data } = await axios.post('/api/auth/refresh-token/', {
      refresh_token: localStorage.getItem('refresh_token')
    });
    localStorage.setItem('access_token', data.access_token);
    localStorage.setItem('refresh_token', data.refresh_token);
    processQueue(null, data.access_token);
    return api(error.config);
  } catch (err) {
    processQueue(err, null);
    localStorage.clear();
    window.location.href = '/login';
  } finally {
    isRefreshing = false;
  }
} else {
  return new Promise((resolve, reject) => {
    failedQueue.push({ resolve, reject });
  }).then((token) => {
    error.config.headers.Authorization = `Bearer ${token}`;
    return api(error.config);
  });
}
```

### 9.2 WebSocket Reconnection

```typescript
// Exponential backoff: 1s, 2s, 4s, 8s, ... max 30s
// On reconnect: use latest access_token
// Don't reconnect on close codes 4001 or 4003 (auth/permanent failures)
```

### 9.3 Pagination for Infinite Scroll

Use the `page` and `page_size` query params. The `next` field in the response contains the URL for the next page. Implement either:
- "Load more" button, OR
- Intersection Observer for infinite scroll

### 9.4 File Uploads

Payment screenshots use `multipart/form-data`. Handle via FormData:

```typescript
const formData = new FormData();
formData.append('payment_screenshot', file);
formData.append('plan_id', planId);
// ... for create subscription

// Axios will auto-detect FormData and set correct Content-Type
```

### 9.5 Date/Time Handling

- All timestamps from API are ISO 8601 strings (e.g., `2026-07-15T10:30:00Z`)
- Convert to user's timezone (from profile) for display
- Use `dayjs` or `date-fns` for formatting
- Timestamps are in UTC — always convert to local time for display

### 9.6 Feature Flags (from User Profile)

Check `profile.subscription_plan` to determine:
- `max_bots_allowed`: limit bot creation
- Feature access (some features may be premium-only)

### 9.7 Bot Start/Stop Idempotency

- Starting an already-running bot returns a 400/error
- Stopping a not-running bot returns a 400/error
- Always show loading state while the operation completes
- UI should reflect the actual bot status after action completes

### 9.8 Admin-Only Pages

- Admin endpoints return 403 for non-staff users
- Hide admin navigation items from non-staff users
- Check `user.is_staff` from profile response

---

## Key Files Structure (for the frontend project)

```
frontend/src/
├── api/
│   ├── client.ts           # Axios instance + interceptors
│   ├── auth.ts             # login, register, refresh, logout
│   ├── bots.ts             # all bot CRUD + start/stop
│   ├── payments.ts         # subscriptions, deposits, withdrawals
│   ├── trading.ts          # exchanges, pairs, rates, credentials
│   └── admin.ts            # admin-only endpoints
├── hooks/
│   ├── useAuth.ts          # auth context + provider
│   ├── useBotWebSocket.ts  # WebSocket connection hook
│   └── usePagination.ts    # pagination helper
├── pages/
│   ├── Login.tsx
│   ├── Register.tsx
│   ├── Dashboard.tsx
│   ├── BotManager.tsx      # list all bots
│   ├── CreateBot.tsx       # multi-step bot creation
│   ├── BotDetail.tsx       # single bot view with WebSocket
│   ├── Settings.tsx        # profile, exchange creds, security
│   ├── Subscriptions.tsx
│   ├── Deposits.tsx
│   ├── Withdrawals.tsx
│   ├── Orders.tsx
│   ├── Referrals.tsx
│   └── admin/              # admin-only pages
│       ├── Dashboard.tsx
│       ├── Users.tsx
│       ├── Deposits.tsx
│       └── Withdrawals.tsx
├── components/
│   ├── Layout.tsx           # sidebar + header + main
│   ├── BotCard.tsx          # bot summary card
│   ├── StatusBadge.tsx      # running/stopped/error badge
│   ├── OrderTable.tsx
│   └── ...
└── types/
    └── index.ts             # all TypeScript interfaces
```
