# Torgovo Crypto Trading Platform - API Documentation

## Overview

Torgovo is a comprehensive Django REST API-based cryptocurrency trading platform that provides users with multiple automated trading strategies, signal bots, and AI-powered trading bots. The platform supports integration with major cryptocurrency exchanges (Binance, Bybit, OKX, MEXC, Alpaca, Coinbase).

**Base URL**: `https://api.torgovo.com`
**API Version**: v1
**Content-Type**: `application/json`
**Authentication**: Bearer Token (JWT)
**Route verification**: all paths below checked against `urls.py` sources on
2026-10-07 (frontend-docs consolidation Step 3). No Swagger mount exists in
`config/urls.py` — this file is the full-API reference; `/api/bots/` payloads
and gates are code-verified in [BOTS_API.md](BOTS_API.md); the frontend
integration contract is [FRONTEND_PROMPT.md](FRONTEND_PROMPT.md).

## Table of Contents

1. [Authentication](#authentication)
2. [User Management](#user-management)
3. [Trading Bots](#trading-bots)
4. [signal bots](#signal-bots)
5. [Grid Bots](#grid-bots)
6. [Martingale Bots](#martingale-bots)
7. [Quantum AI Bots](#quantum-ai-bots)
8. [Exchange Integration](#exchange-integration)
9. [Technical Indicators](#technical-indicators)
10. [Orders & Trade History](#orders--trade-history)
11. [Admin Endpoints](#admin-endpoints)
12. [Error Handling](#error-handling)

## Authentication

### Register User
```http
POST /api/auth/register/
```

**Request Body:**
```json
{
  "username": "trader123",
  "email": "trader@example.com",
  "password": "SecurePass123!",
  "password_confirm": "SecurePass123!",
  "first_name": "John",
  "last_name": "Doe",
  "phone_number": "+1234567890"
}
```

**Response (201):**
```json
{
  "user": {
    "id": "uuid",
    "email": "trader@example.com",
    "username": "trader123"
  },
  "tokens": {
    "access_token": "jwt_access_token",
    "refresh_token": "jwt_refresh_token"
  },
  "message": "Registration successful. Please check your email for verification."
}
```

### Login
```http
POST /api/auth/login/
```

**Request Body:**
```json
{
  "email": "trader@example.com",
  "password": "SecurePass123!"
}
```

**Response (200):**
```json
{
  "user": {
    "id": "uuid",
    "email": "trader@example.com",
    "subscription_plan": "basic"
  },
  "tokens": {
    "access_token": "jwt_access_token",
    "refresh_token": "jwt_refresh_token"
  },
  "message": "Login successful."
}
```

### Google OAuth
```http
POST /api/auth/google/
```

**Request Body:**
```json
{
  "access_token": "google_oauth_token"
}
```

**Response (200):** Same format as regular login

### Refresh Token
```http
POST /api/auth/refresh-token/
```

**Request Body:**
```json
{
  "refresh_token": "jwt_refresh_token"
}
```

**Response (200):**
```json
{
  "access_token": "new_jwt_access_token",
  "message": "Token refreshed successfully."
}
```

## User Management

### Get User Profile
```http
GET /api/auth/user/
Authorization: Bearer {access_token}
```

Returns the flat `UserSerializer` shape (same object embedded as `user` in
login/register responses):
```json
{
  "id": "uuid",
  "email": "trader@example.com",
  "username": "trader123",
  "first_name": "John",
  "last_name": "Doe",
  "full_name": "John Doe",
  "phone_number": "+1234567890",
  "is_email_verified": true,
  "timezone": "UTC",
  "subscription_plan": "premium",
  "max_bots_allowed": 15,
  "is_subscription_active": true,
  "referral_code": "ABC123",
  "total_trades_executed": 1250,
  "total_volume_traded": "250000.00"
}
```

### Update Profile
```http
PUT /api/auth/user/
PATCH /api/auth/user/
Authorization: Bearer {access_token}
```

Writable fields: `email`, `username`, `first_name`, `last_name`,
`phone_number`, `timezone`. Read-only (server-computed): `subscription_plan`,
`max_bots_allowed`, `is_subscription_active`, `referral_code`,
`total_trades_executed`, `total_volume_traded`, `two_factor_enabled`,
`terms_accepted_at`, `privacy_version` (`apps/authentication/serializers.py`
`UserSerializer.read_only_fields`).

**Request Body:**
```json
{
  "timezone": "America/New_York",
  "first_name": "John",
  "last_name": "Doe"
}
```

## Trading Bots

> **Payloads superseded (2026-10-02); routes corrected (2026-10-07).** The
> code-verified reference for the `/api/bots/` surface is
> **[BOTS_API.md](BOTS_API.md)** — payloads, subscription gates, and error
> contract. Non-existent routes previously shown here (`quantum-ai-bots`,
> `grid/{bot_id}/start`, `webhooks/tradingview/…`, `auth/profile/`) were fixed
> on 2026-10-07 against `urls.py`. Use BOTS_API.md for anything bots-related;
> this section is a convenience summary only.

### signal bots

#### List signal bots
```http
GET /api/bots/signal-bots/
Authorization: Bearer {access_token}
```

**Response (200):**
```json
{
  "count": 1,
  "results": [
    {
      "id": "webhook_uuid",
      "bot_name": "BTC Scalper",
      "webhook_url": "https://api.torgovo.com/api/webhooks/custombot/",
      "secret_key": "generated_secret_key",
      "exchange_name": "binance",
      "trading_pair": "BTC/USDT",
      "default_amount": "100.00",
      "take_profit_percent": "5.00",
      "stop_loss_percent": "3.00",
      "is_active": true,
      "last_triggered": "2024-01-15T10:30:00Z",
      "total_trades": 25,
      "successful_trades": 18,
      "total_profit_loss": "150.50"
    }
  ]
}
```

#### Create Webhook Alert
```http
POST /api/bots/signal-bots/
Authorization: Bearer {access_token}
```

**Request Body:**
```json
{
  "bot_name": "ETH Breakout",
  "exchange_name": "bybit",
  "trading_pair": "ETH/USDT",
  "default_amount": "50.00",
  "take_profit_percent": "8.00",
  "stop_loss_percent": "4.00"
}
```

**Response (201):**
```json
{
  "id": "new_webhook_uuid",
  "webhook_url": "https://api.torgovo.com/api/webhooks/custombot/",
  "secret_key": "generated_secret_key",
  "message": "Webhook alert created successfully"
}
```

### Grid Bots

#### List Grid Bots
```http
GET /api/bots/grid-bots/
Authorization: Bearer {access_token}
```

**Response (200):**
```json
{
  "count": 2,
  "results": [
    {
      "id": "grid_bot_uuid",
      "bot_name": "BTC Grid Bot",
      "exchange_name": "binance",
      "trading_pair": "BTC/USDT",
      "base_amount": "100.00",
      "favor_levels": 5,
      "against_levels": 5,
      "level_spacing_percent": "1.0",
      "take_profit_percent": "5.0",
      "stop_loss_percent": "3.0",
      "is_running": true,
      "current_profit_loss": "15.50",
      "total_invested": "1000.00",
      "total_trades_executed": 45
    }
  ]
}
```

#### Create Grid Bot
```http
POST /api/bots/grid-bots/
Authorization: Bearer {access_token}
```

**Request Body:**
```json
{
  "bot_name": "ETH Grid Bot",
  "exchange_name": "binance",
  "trading_pair": "ETH/USDT",
  "base_amount": "50.00",
  "favor_levels": 3,
  "against_levels": 3,
  "favor_level_qty": "10.00",
  "take_profit_percent": "6.0",
  "stop_loss_percent": "4.0"
}
```

#### Start Grid Bot
```http
POST /api/bots/grid-bots/{id}/start/
Authorization: Bearer {access_token}
```

**Response (200)** — flat body (see BOTS_API.md §2B):
```json
{"success": true, "message": "Grid bot started successfully"}
```

#### Stop Grid Bot
```http
POST /api/bots/grid-bots/{id}/stop/
Authorization: Bearer {access_token}
```

**Response (200)** — flat body:
```json
{"success": true, "message": "Grid bot stopped successfully"}
```

### Martingale Bots

#### Create Martingale Bot
```http
POST /api/bots/martingale-bots/
Authorization: Bearer {access_token}
```

**Request Body:**
```json
{
  "bot_name": "BTC Martingale",
  "exchange_name": "bybit",
  "trading_pair": "BTC/USDT",
  "base_amount": "25.00",
  "favor_levels": 3,
  "against_levels": 3,
  "multiplier_factor": "2.0",
  "take_profit_percent": "10.0",
  "stop_loss_percent": "6.0"
}
```

### Quantum AI Bots

#### Create Quantum AI Investment
```http
POST /api/bots/quantum-investments/
Authorization: Bearer {access_token}
```

Requires active subscription with `bot_type="quantum_ai"` (else 403).
Writable fields: `fund`, `amount`, `status` (`pending` default | `active` |
`withdrawn` | `cancelled`) — BOTS_API.md §8.

**Request Body:**
```json
{
  "fund": "fund-uuid",
  "amount": "1000.00",
  "status": "pending"
}
```

#### Get Blockchain Addresses for Deposits
```http
GET /api/investments/bots/blockchain-addresses/
Authorization: Bearer {access_token}
```

**Response (200):**
```json
{
  "USDT": {
    "BEP20": "0x1234...abcd",
    "ERC20": "0x5678...efgh",
    "TRC20": "TMnL...xyz",
    "SOL": "9WzDX...B1s"
  },
  "USDC": {
    "BEP20": "0xijkl...mnop",
    "ERC20": "0xqrst...uvwx"
  },
  "BTC": {
    "Bitcoin": "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
  }
}
```

#### Submit Deposit
```http
POST /api/investments/bots/quantum-ai/{bot_id}/deposit/
Authorization: Bearer {access_token}
Content-Type: multipart/form-data
```

**Form Data:**
- `amount`: "1000.00" (required, > 0)
- `coin_type`: "USDT" (required, uppercased server-side)
- `blockchain`: "BEP20" (required, uppercased server-side)
- `from_address`: "0xuser...address"
- `transaction_hash`: "0x1234...abcd" (tx-hash **or** `screenshot` required —
  else 400; duplicate tx-hash → 409)
- `screenshot`: [file]

## Exchange Integration

### List Supported Exchanges
```http
GET /api/exchanges/list/
Authorization: Bearer {access_token}
```

**Response (200)** (`apps/trading/views.py:list_exchanges`):
```json
{
  "success": true,
  "data": [
    {
      "name": "binance",
      "display_name": "Binance",
      "is_active": true,
      "supports_testnet": true,
      "supported_features": ["spot", "futures", "margin"],
      "fee_rates": {}
    },
    {
      "name": "bybit",
      "display_name": "Bybit",
      "is_active": true,
      "supports_testnet": true,
      "supported_features": ["spot", "linear", "inverse"],
      "fee_rates": {}
    }
  ]
}
```

### Add Exchange Credentials
```http
POST /api/exchanges/credentials/
Authorization: Bearer {access_token}
```

**Request Body:**
```json
{
  "exchange_name": "binance",
  "api_key": "your_binance_api_key",
  "secret_key": "your_binance_secret_key",
  "passphrase": null,
  "is_testnet": true
}
```

**Response (201):**
```json
{
  "message": "Exchange credentials added successfully",
  "exchange_name": "binance",
  "is_testnet": true,
  "is_connected": true
}
```

### Get Trading Symbols
```http
GET /api/exchanges/{exchange_name}/symbols/
Authorization: Bearer {access_token}
```

**Response (200):**
```json
{
  "exchange": "binance",
  "symbols": [
    "BTC/USDT",
    "ETH/USDT",
    "BNB/USDT",
    "ADA/USDT"
  ]
}
```

## Technical Indicators (Webhooks)

### EMA Indicator
```http
POST /api/bots/indicators/ema/
X-Webhook-Token: {webhook_token}
Content-Type: application/json
```

**Request Body:**
```json
{
  "EMA200": "45250.75",
  "username": "trader123",
  "pair": "BTC/USDT",
  "exchange": "binance"
}
```

**Response (200):**
```json
{
  "status": "success",
  "message": "EMA processed for BTC/USDT",
  "EMA": "45250.75",
  "bot_updated": true
}
```

### RSI Indicator
```http
POST /api/bots/indicators/rsi/
X-Webhook-Token: {webhook_token}
Content-Type: application/json
```

**Request Body:**
```json
{
  "RSI": "65.4",
  "PrevRSI": "62.1",
  "color": "white",
  "prev_color": "green",
  "username": "trader123",
  "pair": "ETH/USDT",
  "exchange": "bybit"
}
```

## TradingView Webhook Integration

### Webhook URL
```
https://api.torgovo.com/api/webhooks/custombot/
```
Global URL for every signal bot (`SignalBot.save()` sets
`webhook_url = {SITE_URL}/api/webhooks/custombot/`); the bot is selected from
the payload.

### Webhook Message Format
Required: `bot_id`, `secret` (body-secret mode — or `X-Signature` HMAC header
instead), `side`/`action`/`direction` (`buy`|`sell`, long/short aliases
mapped), `timestamp`. Optional: `position_size`, `order_id`.
(`apps/webhooks/views.py` SignalBotWebhookView)
```json
{
  "bot_id": "25bbfa8f-38fd-4afc-bf63-25dc209977e1",
  "secret": "generated_secret_key",
  "action": "buy",
  "timestamp": "1642248600",
  "position_size": "1.5"
}
```

## Orders & Trade History

### Get User Orders
```http
GET /api/investments/users/my-orders/
Authorization: Bearer {access_token}
```

**Query Parameters:**
- `category`: Filter by bot type (webhook, grid, martingale, quantum)
- `pair`: Filter by trading pair
- `exchange`: Filter by exchange
- `start_date`: Filter from date (YYYY-MM-DD)
- `end_date`: Filter to date (YYYY-MM-DD)
- `page`: Page number (default: 1)
- `page_size`: Items per page (default: 20)

**Response (200):**
```json
{
  "count": 154,
  "next": "https://api.torgovo.com/api/investments/users/my-orders/?page=2",
  "previous": null,
  "results": [
    {
      "id": "order_uuid",
      "Time": "2024-01-15T14:30:00+05:00",
      "Pair": "BTC/USDT",
      "Side": "buy",
      "Category": "webhook",
      "Order_type": "market",
      "Quantity": "0.00100000",
      "Price": 45250.75,
      "Exchange": "binance",
      "Take_Profit": 49775.82,
      "Stop_Loss": 42988.21,
      "Description": "TradingView webhook signal",
      "profit_loss": "12.50"
    }
  ]
}
```

## Error Handling

### Standard Error Response Format
```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable error message",
    "details": {
      "field": "Additional error details"
    }
  },
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### Common Error Codes

| Error Code | HTTP Status | Description |
|------------|-------------|-------------|
| `AUTHENTICATION_REQUIRED` | 401 | No or invalid JWT token |
| `PERMISSION_DENIED` | 403 | Insufficient permissions |
| `VALIDATION_ERROR` | 400 | Invalid input data |
| `RESOURCE_NOT_FOUND` | 404 | Requested resource doesn't exist |
| `EXCHANGE_API_ERROR` | 503 | Exchange API failure |
| `INSUFFICIENT_BALANCE` | 402 | Not enough funds for trade |
| `BOT_LIMIT_EXCEEDED` | 429 | User exceeded bot limit |
| `RATE_LIMIT_EXCEEDED` | 429 | Too many requests |
| `INTERNAL_SERVER_ERROR` | 500 | Unexpected server error |

## Rate Limiting

- **Anonymous**: 100 requests per hour
- **Authenticated Users**: 1000 requests per hour

Rate limit headers are included in responses:
- `X-RateLimit-Limit`: Your rate limit
- `X-RateLimit-Remaining`: Requests remaining

## Pagination

List endpoints support pagination with these parameters:
- `page`: Page number (default: 1)
- `page_size`: Items per page (default: 20, max: 100)

Response includes pagination info:
```json
{
  "count": 250,
  "next": "https://api.torgovo.com/api/endpoint/?page=3",
  "previous": "https://api.torgovo.com/api/endpoint/?page=1",
  "results": [...]
}
```

## WebSocket Support (Coming Soon)

Real-time updates will be available via WebSocket for:
- Bot status updates
- Trade execution notifications
- Price alerts
- Account balance changes

Connect to: `wss://api.torgovo.com/ws/`

## Support

> **Note:** Official SDKs and dedicated support pages are planned but not yet available.

## Changelog

### v1.0.1 (2026-10-07 — Step 3 route verification)
- Removed nonexistent Swagger claim (`/api/docs/` not mounted).
- `auth/profile/` → `auth/user/` with real flat `UserSerializer` shape + writable fields.
- Signal-bot webhook URL → `webhooks/custombot/`; webhook payload corrected to
  required `bot_id`/`secret`/`action`/`timestamp`.
- Grid start/stop → `grid-bots/{id}/start|stop/` with flat success bodies;
  legacy `grid/{bot_id}/…` routes removed (broken, see BOTS_API.md §3).
- `quantum-ai-bots` → `quantum-investments` with real `fund`/`amount`/`status` payload.
- `bots/blockchain-addresses` & `bots/quantum-ai/…/deposit` → `investments/bots/…`.
- Indicator webhooks → `bots/indicators/ema|rsi/` + `X-Webhook-Token`.
- `users/my-orders` → `investments/users/my-orders`; `exchanges/` → `exchanges/list/`
  with real `{"success","data"}` shape; dropped non-writable `level_spacing_percent`
  from grid/martingale create bodies.

### v1.0.0
- Initial release with core trading features
- signal bots integration
- Grid and Martingale trading bots
- Quantum AI deposit system
- Multi-exchange support
- RESTful API with JWT authentication

---

**© 2026 Torgovo Crypto Trading Platform. All rights reserved.**
