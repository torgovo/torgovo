# Torgovo Crypto Trading Platform - API Documentation

## Overview

Torgovo is a comprehensive Django REST API-based cryptocurrency trading platform that provides users with multiple automated trading strategies, signal bots, and AI-powered trading bots. The platform supports integration with major cryptocurrency exchanges (Binance, Bybit, OKX, MEXC, Alpaca).

**Base URL**: `https://api.torgovo.com`
**API Version**: v1
**Content-Type**: `application/json`
**Authentication**: Bearer Token (JWT)

## Table of Contents

1. [Authentication](#authentication)
2. [User Management](#user-management)
3. [Trading Bots](#trading-bots)
4. [signal bots](#webhook-alerts)
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
      "webhook_url": "https://api.torgovo.com/api/webhooks/tradingview/webhook_uuid",
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
  "webhook_url": "https://api.torgovo.com/api/webhooks/tradingview/new_webhook_uuid",
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

### Quantum AI Bots

#### Create Quantum AI Bot
```http
POST /api/bots/quantum-ai-bots/
Authorization: Bearer {access_token}
```

**Request Body:**
```json
{
  "bot_name": "AI Portfolio Manager",
  "auto_compound": true,
  "compound_frequency": "weekly",
  "risk_level": "moderate"
}
```

#### Get Blockchain Addresses for Deposits
```http
GET /api/bots/blockchain-addresses/
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
POST /api/bots/quantum-ai/{bot_id}/deposit/
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

### Webhook URL Format
```
https://api.torgovo.com/api/webhooks/tradingview/{webhook_id}/
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

## Orders & Trade History

### Get User Orders
```http
GET /api/users/my-orders/
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
  "next": "https://api.torgovo.com/api/users/my-orders/?page=2",
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

- **Free Users**: 100 requests per minute
- **Premium Users**: 1000 requests per minute
- **Enterprise Users**: 3000 requests per minute

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

## SDK & Libraries

Official SDKs are available for:
- **Python**: `pip install torgovo-python`
- **JavaScript**: `npm install torgovo-js`
- **React**: `npm install torgovo-react`

## Support

- **Documentation**: https://docs.torgovo.com
- **API Status**: https://status.torgovo.com
- **Support Email**: support@torgovo.com
- **Telegram Community**: https://t.me/torgovo_community

## Changelog

### v1.0.0 (2024-01-15)
- Initial release with core trading features
- signal bots integration
- Grid and Martingale trading bots
- Quantum AI deposit system
- Multi-exchange support
- RESTful API with JWT authentication

---

**© 2024 Torgovo Crypto Trading Platform. All rights reserved.**
