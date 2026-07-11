# Torgovo Crypto Trading Platform - API Documentation

## Overview

Torgovo is a comprehensive Django REST API-based cryptocurrency trading platform that provides users with multiple automated trading strategies, signal bots (TradingView webhook receivers), and AI-powered trading bots. The platform supports integration with major cryptocurrency exchanges (Binance, Bybit, OKX, MEXC, Alpaca).

**Base URL**: `https://api.torgovo.com`
**API Version**: v1
**Content-Type**: `application/json`
**Authentication**: Bearer Token (JWT)

## Table of Contents

1. [Authentication](#authentication)
2. [User Management](#user-management)
3. [Trading Bots](#trading-bots)
   - [Signal Bots](#signal-bots)
   - [Grid Bots](#grid-bots)
   - [Martingale Bots](#martingale-bots)
4. [Quantum AI (Investment)](#quantum-ai-investment)
5. [Exchange Integration](#exchange-integration)
6. [Technical Indicators](#technical-indicators)
7. [Orders & Trade History](#orders--trade-history)
8. [Admin Endpoints](#admin-endpoints)
9. [Error Handling](#error-handling)

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
GET /api/auth/profile/
Authorization: Bearer {access_token}
```

**Response (200):**
```json
{
  "id": "uuid",
  "user_email": "trader@example.com",
  "user_full_name": "John Doe",
  "subscription_plan": "premium",
  "max_bots_allowed": 15,
  "timezone": "UTC",
  "demo_trading_enabled": true,
  "email_notifications": true,
  "is_subscription_active": true,
  "total_trades_executed": 1250,
  "total_volume_traded": "250000.00"
}
```

### Update Profile
```http
PUT /api/auth/profile/update/
Authorization: Bearer {access_token}
```

**Request Body:**
```json
{
  "timezone": "America/New_York",
  "demo_trading_enabled": false,
  "email_notifications": true,
  "sms_notifications": false,
  "trading_preferences": {
    "default_exchange": "binance",
    "risk_tolerance": "moderate"
  }
}
```

## Trading Bots

### Signal Bots

> **Model**: `SignalBot` (`apps/bots/models.py`)
> Signal bots receive a TradingView webhook signal, execute one trade, then stop. They do not run continuously. Each bot has a unique `webhook_url` and `secret_key` used by TradingView for authentication.

#### List Signal Bots
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
      "id": "signal_bot_uuid",
      "bot_name": "BTC Scalper",
      "webhook_url": "https://api.torgovo.com/api/webhooks/tradingview/signal_bot_uuid",
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

#### Create Signal Bot
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
  "id": "new_signal_bot_uuid",
  "webhook_url": "https://api.torgovo.com/api/webhooks/tradingview/new_signal_bot_uuid",
  "secret_key": "generated_secret_key",
  "message": "Signal bot created successfully"
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
  "level_spacing_percent": "1.5",
  "take_profit_percent": "6.0",
  "stop_loss_percent": "4.0"
}
```

#### Start Grid Bot
```http
POST /api/bots/grid/{bot_id}/start/
Authorization: Bearer {access_token}
```

**Response (200):**
```json
{
  "message": "Grid bot started successfully",
  "bot_id": "grid_bot_uuid",
  "status": "running"
}
```

#### Stop Grid Bot
```http
POST /api/bots/grid/{bot_id}/stop/
Authorization: Bearer {access_token}
```

**Response (200):**
```json
{
  "message": "Grid bot stopped successfully",
  "bot_id": "grid_bot_uuid",
  "status": "stopped",
  "final_profit_loss": "15.50"
}
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
  "level_spacing_percent": "2.0",
  "multiplier_factor": "2.0",
  "take_profit_percent": "10.0",
  "stop_loss_percent": "6.0"
}
```

#### Start/Stop Martingale Bot

Same pattern as Grid endpoints — replace `/grid/` with `/martingale/`:

```http
POST /api/bots/martingale/{bot_id}/start/
POST /api/bots/martingale/{bot_id}/stop/
```

## Quantum AI (Investment)

> **Note**: Quantum AI is an admin-managed investment fund. Users **cannot** create or control a QuantumAI bot. They deposit USDT, admin trades with pooled funds, and users see only their proportional balance changes.

### Get Blockchain Addresses for Deposits
```http
GET /api/investments/quantum/addresses/
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

### Submit Deposit
```http
POST /api/investments/quantum/deposit/
Authorization: Bearer {access_token}
Content-Type: multipart/form-data
```

**Form Data:**
- `amount`: "1000.00"
- `coin_type`: "USDT"
- `blockchain`: "BEP20"
- `from_address`: "0xuser...address"
- `transaction_hash`: "0x1234...abcd"
- `screenshot`: [file]

**Response (201):**
```json
{
  "id": "deposit_uuid",
  "status": "pending",
  "message": "Deposit submitted for admin approval"
}
```

### Get Quantum AI Balance
```http
GET /api/investments/quantum/balance/
Authorization: Bearer {access_token}
```

**Response (200):**
```json
{
  "current_balance": "1250.75",
  "total_invested": "1000.00",
  "total_profit": "250.75",
  "last_update": "2026-06-01T00:00:00Z"
}
```

## Exchange Integration

### List Supported Exchanges
```http
GET /api/exchanges/
Authorization: Bearer {access_token}
```

**Response (200):**
```json
{
  "exchanges": [
    {
      "name": "binance",
      "display_name": "Binance",
      "status": "active",
      "supported_features": ["spot", "futures", "margin"]
    },
    {
      "name": "bybit",
      "display_name": "Bybit",
      "status": "active",
      "supported_features": ["spot", "linear", "inverse"]
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
  "symbols": ["BTC/USDT", "ETH/USDT", "BNB/USDT", "ADA/USDT"]
}
```

## Technical Indicators (Webhooks)

### EMA Indicator
```http
POST /api/indicators/ema/
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
POST /api/indicators/rsi/
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

Signal bots receive trade signals from TradingView via a unique webhook URL. The signal is validated using `secret_key`, then the trade is executed asynchronously via a Celery task.

### Webhook URL Format
```
https://api.torgovo.com/api/webhooks/tradingview/{signal_bot_id}/
```

### Webhook Message Format
```json
{
  "secret": "generated_secret_key",
  "max_lag": "300",
  "timestamp": "1642248600",
  "trigger_price": "45000.50",
  "tv_exchange": "binance",
  "tv_instrument": "BTCUSDT",
  "action": "buy",
  "bot_uuid": "25bbfa8f-38fd-4afc-bf63-25dc209977e1",
  "strategy_info": {
    "market_position": "long",
    "market_position_size": "1.5"
  },
  "order": {
    "amount": "1.5",
    "currency_type": "base"
  }
}
```

**Validation:** `secret` must match the bot's `secret_key` — otherwise `403 INVALID_SECRET`.

## Orders & Trade History

### Get User Orders
```http
GET /api/users/my-orders/
Authorization: Bearer {access_token}
```

**Query Parameters:**
- `category`: Filter by bot type (`signal`, `grid`, `martingale`, `quantum`)
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
  "next": "https://api.torgovo.com/api/users/my-orders/?page=2",
  "previous": null,
  "results": [
    {
      "id": "order_uuid",
      "Time": "2024-01-15T14:30:00+05:00",
      "Pair": "BTC/USDT",
      "Side": "buy",
      "Category": "signal",
      "Order_type": "market",
      "Quantity": "0.00100000",
      "Price": 45250.75,
      "Exchange": "binance",
      "Take_Profit": 49775.82,
      "Stop_Loss": 42988.21,
      "Description": "TradingView signal bot",
      "profit_loss": "12.50"
    }
  ]
}
```

## Admin Endpoints

> All admin endpoints require superuser privileges.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/admin/pending/` | GET | List pending investments/payments |
| `/api/admin/investments/{id}/approve/` | PUT | Approve or reject investment |
| `/api/admin/payments/{id}/approve/` | PUT | Approve or reject payment |
| `/api/admin/quantum/config/` | PATCH | Update shown percentage (5–20%) |
| `/api/admin/emails/send/` | POST | Send system or targeted email |

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
| `INVALID_SECRET` | 403 | Webhook `secret_key` mismatch |
| `VALIDATION_ERROR` | 400 | Invalid input data |
| `RESOURCE_NOT_FOUND` | 404 | Requested resource doesn't exist |
| `EXCHANGE_API_ERROR` | 503 | Exchange API failure |
| `INSUFFICIENT_BALANCE` | 402 | Not enough funds for trade |
| `BOT_LIMIT_EXCEEDED` | 429 | User exceeded bot limit |
| `RATE_LIMIT_EXCEEDED` | 429 | Too many requests |
| `INTERNAL_SERVER_ERROR` | 500 | Unexpected server error |

## Rate Limiting

- **Free Users**: 100 requests per minute
- **Premium Users**: 1000 requests per minute
- **Enterprise Users**: 3000 requests per minute

Rate limit headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`

## Pagination

Parameters: `page`, `page_size` (default 20, max 100)

Response always includes `count`, `next`, `previous`, `results`.

## WebSocket Support (Coming Soon)

Real-time updates will be available via WebSocket at `wss://api.torgovo.com/ws/` for:
- Bot status updates
- Trade execution notifications
- Price alerts
- Account balance changes

## SDK & Libraries

- **Python**: `pip install torgovo-python`
- **JavaScript**: `npm install torgovo-js`
- **React**: `npm install torgovo-react`

## Support

- **Documentation**: https://docs.torgovo.com
- **API Status**: https://status.torgovo.com
- **Support Email**: support@torgovo.com
- **Telegram Community**: https://t.me/torgovo_community

## Changelog

### v1.1.0 (2026-05-19)
- Renamed `CustomBot` → `SignalBot` across models, serializers, views
- Signal bot endpoint: `/api/bots/signal-bots/`
- Quantum AI investment endpoints moved to `/api/investments/quantum/`
- Added `QuantumAIBot` model (admin-managed)
- Added `shown_percentage` (5–20%) to `QuantumAIFund`
- Architecture cleanup: removed `BotConfiguration`, `TradingBot`, `trading_manager`
- Bot engine ported from `oldbybit.py` — raw CCXT, grid monitor, SL/TP thread

### v1.0.0 (2024-01-15)
- Initial release

---

**© 2026 Torgovo Crypto Trading Platform. All rights reserved.**
