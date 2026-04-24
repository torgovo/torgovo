# Torgovo - Crypto Trading Bot Platform

## Tech Stack
**Backend:** Django + Django REST Framework  
**Frontend:** React + Vite  
**Database:** PostgreSQL  
**Architecture:** Async processing, production-ready with Docker

## Project Overview
A subscription-based platform where users create and manage cryptocurrency trading bots that execute trades on multiple exchanges (Binance, Bybit, OKX, MEXC, Coinbase) via CCXT library. The system handles webhooks from TradingView, manages investments, and provides referral rewards.

## User Registration & Setup
- Register via Gmail OAuth or phone (SMS OTP)
- Auto-generate on signup:
  - Unique webhook URL for receiving trade signals
  - JSON message template with fields: `bot_id, buy_sell, symbol, exchange, amount, timestamp, secret_key`
  - `secret_key` for webhook authentication (403 if invalid)
  - Unique referral code

## Four Bot Types

### 1. Custom Bots
- Webhook-driven: Receive signal from TradingView → execute single trade → done
- No continuous monitoring
- User creates bot, gets webhook URL, connects to TradingView

### 2. Grid Bots
- **Config:** percentage_difference, trading_pair, exchange, amount_per_level, starting_amount, leverage
- Runs continuously when enabled
- Places multiple buy/sell orders at different price levels
- Auto-manages positions based on grid strategy
- User can enable/disable anytime

### 3. Martingale Bots
- **Config:** multiplier, max_levels, trading_pair, exchange, starting_amount, leverage
- Runs continuously when enabled
- Progressive strategy: doubles position on losses to recover
- User can enable/disable anytime

### 4. Quantum AI Bots (Investment Model)
- Users invest USDT only (send to platform wallet on ERC20/Aptos)
- Upload transaction screenshot + hash
- Admin approves investment
- **Users see ONLY their balance updates, NO trade details or bot access**

## Quantum AI Profit Distribution (Critical - Implement Fully)

**How it works:**
1. Pool all approved USDT investments (e.g., total = 100,000 USDT)
2. Admin executes real trades (e.g., +200 USDT profit)
3. Calculate "shown adjustment" = up to 20% of actual profit/loss (admin configurable: 5-20%)
4. Distribute proportionally to each user:
   ```
   user_shown_change = (user_investment / total_pool) × shown_adjustment
   ```
5. Update each user's balance in database
6. Send email notification

**Example:**
- Total pool: 100,000 USDT
- User A invested: 10,000 USDT (10%)
- Admin makes +200 USDT profit
- Shown adjustment (20%): 40 USDT
- User A gets: 10% × 40 = +4 USDT added to balance

**Rules:**
- Apply same logic for losses
- Recalculate pool automatically every 2 weeks
- Manual withdrawals processed every 2 weeks only
- Admin can adjust shown percentage (5-20%) from dashboard

## Webhook Flow (Critical)

**Endpoint:** `POST /webhooks/custom_bots/` (or `/quantum_bots/`, `/grid_bots/` etc.)

**Process:**
1. Receive JSON from TradingView: `{bot_id, buy_sell, symbol, exchange, amount, timestamp, secret_key}`
2. Validate `secret_key` → return 403 if invalid
3. Find bot and user from database using `bot_id`
4. Process async:
   - Custom bots: execute trade immediately
   - Other bots: add to queue, bot manager handles execution
5. Log every trade to database: `TradeLog(user_id, bot_id, exchange, symbol, amount, buy_sell, timestamp, outcome)`
6. Retry 3 times on failure, email user if all fail

**Note:** Leave actual CCXT trade execution as `# TODO: Implement CCXT` but complete all surrounding code (validation, database queries, logging, error handling)

## Subscription Plans

**Free Tier:**
- 1 bot (spot or futures)
- 50 webhook alerts max
- Show upgrade prompts near limit

**Paid Tiers:**
- Multiple custom/grid/martingale bots
- Unlimited webhooks
- Telegram trade signals (separate subscription)
- Telegram execution alerts (sends trades to user's Telegram channel)
- Quantum AI investment access

**Payment Methods:**
- PayPal, Stripe, Wise (auto-approved)
- Crypto (upload proof, admin approves)

## Exchange Integration
- Users connect exchanges by entering API keys
- Store encrypted in database
- Display masked on dashboard (e.g., `****abcd`)
- Support spot and futures trading
- Create separate handler files per exchange: `exchanges/binance.py`, `exchanges/bybit.py` etc.
- Central manager dynamically loads correct handler

## Referral System
- Each user gets unique code on signup
- New user enters referral code → referrer gets bonus (configurable: free alerts, discount, or USDT)
- Track in database: referrer, referred user, bonus amount
- Display on dashboard: code, total referrals, earnings

## Bot Manager (Background Service)
- Monitors grid, martingale, and Quantum AI bots continuously
- Auto-creates bot instance when user enables
- Discards bot after 24 hours of inactivity or when user disables
- Custom bots don't use manager (they're one-shot via webhooks)

## User Dashboard (Frontend)
Show:
- All bots (type, status, exchange, enable/disable toggle)
- Current subscription (plan, limits, usage like "30/50 alerts used")
- Connected exchanges (name, masked keys, add/remove buttons)
- Quantum AI balance (if invested) - no trade history visible
- Transaction history (investments, payments with status)
- Referral code, number of referrals, total bonus earned

## Admin Dashboard (Frontend)
Features:
- Approve pending investments/payments (one-click approve/reject)
- Modify subscription plans (features, pricing, limits)
- Configure Quantum AI shown percentage (5-20%)
- View all users, restrict/disable accounts
- View trade logs (filter by user, bot, exchange, date)
- Process manual withdrawals every 2 weeks
- Send emails (system-wide or targeted)
- Adjust referral bonus amounts

## Key API Endpoints

**User:**
- `POST /api/users/register/` - Register new user
- `POST /api/users/login/` - Login, return JWT tokens
- `GET /api/users/dashboard/` - Get all dashboard data

**Bots:**
- `POST /api/bots/custom/` - Create custom bot
- `POST /api/bots/grid/` - Create grid bot with config
- `POST /api/bots/martingale/` - Create martingale bot with config
- `PATCH /api/bots/{id}/` - Enable/disable bot
- `GET /api/bots/{id}/` - Get bot details

**Webhooks:**
- `POST /api/webhooks/custom_bots/` - Receive TradingView signals

**Investments:**
- `POST /api/investments/quantum/` - Submit investment (screenshot, tx_hash)
- `GET /api/investments/balance/` - Get current Quantum AI balance
- `GET /api/investments/history/` - Get investment history

**Admin:**
- `GET /api/admin/pending/` - Get pending approvals
- `PUT /api/admin/investments/{id}/approve/` - Approve/reject
- `PUT /api/admin/payments/{id}/approve/` - Approve/reject
- `PATCH /api/admin/quantum/config/` - Update shown percentage
- `POST /api/admin/emails/send/` - Send emails

**Referrals:**
- `GET /api/referrals/stats/` - Get referral stats and earnings

## Database Models (PostgreSQL)

**User:** id (UUID), email/phone, password, webhook_url, secret_key, referral_code, subscription_plan

**Bot:** id (UUID), user_id, type (custom/grid/martingale/quantum), exchange, config (JSON), status (active/inactive)

**TradeLog:** id (UUID), user_id, bot_id, exchange, symbol, amount, buy_sell, timestamp, outcome

**Investment:** id (UUID), user_id, amount, tx_hash, screenshot, status (pending/approved), blockchain

**Referral:** id (UUID), referrer_id, referred_id, code, bonus_amount, timestamp

**Subscription:** user_id, plan, limits (JSON: bot_count, webhook_alerts), usage (JSON), renewal_date

## Implementation Requirements

1. **Async Processing:** All webhooks, emails, bot monitoring, and Quantum AI calculations run asynchronously
2. **Security:** Encrypt API keys, rate-limit endpoints, validate all inputs, HTTPS only
3. **Error Handling:** Retry mechanisms, comprehensive logging, user notifications on failures
4. **Resource Management:** Auto-discard inactive bots after 24h, optimize database queries
5. **Email Notifications:** Send on: registration, investment approval, trade failures, balance updates
6. **Telegram Integration:** For paid users, send trade executions to their Telegram channel (placeholder for Telegram API calls, complete user permission checks)
7. **Testing:** Implement last with 80%+ coverage
8. **Production Ready:** Docker setup, environment variables, cloud deployment ready

## CCXT Integration Note
- Use CCXT library for all exchange interactions
- Support spot and futures trading
- **Leave actual trade execution calls as `# TODO: Implement CCXT trade execution`**
- **Complete ALL other code:** validation, database operations, TradeLog entries, error handling, notifications

## Frontend Requirements
- React + Vite setup
- All API integrations pre-configured with Axios
- JWT authentication implemented
- Responsive design for dashboard
- Real-time bot status updates
- Form validations matching backend
- Error handling with notifications
- Document all API integrations and component structure

## Documentation
Create comprehensive API documentation including:
- All endpoints with methods, URLs, request/response formats
- Authentication requirements
- Error codes and messages
- Example requests/responses
- Frontend integration guide