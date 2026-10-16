> **Note:** This is the original spec document from early development. Some details are outdated. See ARCHITECTURE.md and SETUP.md for current implementation details. **Product requirements (pricing, Quantum AI locks/payouts, referrals): FUNCTIONAL_REQUIREMENTS.md Part A wins** — the "every 2 weeks" Quantum cadence below is current-code description only, superseded by FR A5 (30–365d locks, profit-only post-lock withdrawals processed manually within 7 days).

# Torgovo - Crypto Trading Bot Platform

## Tech Stack
**Backend:** Django + Django REST Framework
**Frontend:** React + Vite
**Database:** PostgreSQL
**Architecture:** Async processing, production-ready with Docker

## Project Overview
A subscription-based platform where users create and manage cryptocurrency trading bots that execute trades on multiple exchanges (Binance, Bybit, OKX, MEXC, Coinbase) via CCXT library. The system handles webhooks from TradingView, manages investments, and provides referral rewards.

## User Registration & Setup
- Register via email + username + password (OAuth available but not primary flow)
- Phone (SMS OTP) is optional
- Auto-generate on signup:
  - Unique referral code
- Webhook URLs and secret keys are per-bot (created when user creates a SignalBot), not per-user

## Four Bot Types

### 1. Signal Bots (formerly Custom Bots)
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
- Recalculate pool automatically every 2 weeks (current code; target: FR A5 lock model)
- Manual withdrawals processed every 2 weeks only (current code; target: profit-only post-lock, manual within 7 days — FR A5)
- Admin can adjust shown percentage (5-20%) from dashboard

## Webhook Flow (Critical)

**Endpoint:** `POST /api/webhooks/custombot/` (single shared endpoint for all bot types)

**Process:**
1. Receive JSON from TradingView: `{bot_id, buy_sell, symbol, exchange, amount, timestamp, secret_key}`
2. Validate `secret_key` → return 403 if invalid
3. Find bot and user from database using `bot_id`
4. Process async:
   - Custom bots: execute trade immediately
   - Other bots: add to queue, bot manager handles execution
5. Log every trade to database: `BotOrder(user_id, bot_id, exchange, symbol, amount, buy_sell, timestamp, outcome)`
6. Retry 3 times on failure, email user if all fail

**Note:** CCXT is fully integrated via BotOrderService. All exchange interactions use real CCXT methods.

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
- Crypto deposits with admin approval

## Exchange Integration
- Users connect exchanges by entering API keys
- Store encrypted in database
- Display masked on dashboard (e.g., `****abcd`)
- Support spot and futures trading
- Exchange adapters live in `apps/trading/exchanges/` (already implemented: bybit, binance, mexc, alpaca, okx, coinbase)

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
- Configure Quantum AI profit parameters
- View all users, restrict/disable accounts
- View trade logs (filter by user, bot, exchange, date)
- Process manual withdrawals within 7 days of post-lock request (FR A5; current code: 2-week cadence)
- Send emails (system-wide or targeted)
- Adjust referral bonus amounts

## Key API Endpoints

**User:**
- `POST /api/auth/register/` - Register new user
- `POST /api/auth/login/` - Login, return JWT tokens

**Bots:**
- `POST /api/bots/signal-bots/` - Create custom bot
- `POST /api/bots/grid/` - Create grid bot with config
- `POST /api/bots/martingale/` - Create martingale bot with config
- `PATCH /api/bots/{id}/` - Enable/disable bot
- `GET /api/bots/{id}/` - Get bot details

**Webhooks:**
- `POST /api/webhooks/custombot/` - Receive TradingView signals

**Investments:**
- `POST /api/bots/quantum-investments/` - Submit investment (screenshot, tx_hash)
- `GET /api/investments/balance/` - Get current Quantum AI balance
- `GET /api/investments/history/` - Get investment history

**Admin:**
- `GET /api/admin/pending/` - Get pending approvals
- `PUT /api/admin/investments/{id}/approve/` - Approve/reject investment
- `PUT /api/admin/payments/{id}/approve/` - Approve/reject payment

**Referrals:**
- `GET /api/referrals/my-stats/` - Get referral stats and earnings

## Database Models (PostgreSQL)

**User:** id (UUID), email, username, phone, password, referral_code, subscription_plan

**Bot (4 separate models):** SignalBot, GridBot, MartingaleBot, QuantumAIBot — each has user_id, exchange, config (JSON), status

**BotOrder:** id (UUID), user_id, bot_id, exchange, symbol, amount, buy_sell, timestamp, outcome

**InvestorDeposit:** id (UUID), user_id, amount, tx_hash, screenshot, status (pending/approved), blockchain
**InvestorPortfolio:** tracks user investment balance in Quantum AI fund

**Referral:** id (UUID), referrer_id, referred_id, code, bonus_amount, timestamp

**SubscriptionPlan:** Free / Basic / Premium / Enterprise tiers with bot limits and features

## Implementation Requirements

1. **Async Processing:** All webhooks, emails, bot monitoring, and Quantum AI calculations run asynchronously
2. **Security:** Encrypt API keys, rate-limit endpoints, validate all inputs, HTTPS only
3. **Error Handling:** Retry mechanisms, comprehensive logging, user notifications on failures
4. **Resource Management:** check_stale_bots with configurable thresholds, optimize database queries
5. **Email Notifications:** Send on: registration, investment approval, trade failures, balance updates
6. **Telegram Integration:** For paid users, send trade executions to their Telegram channel (TelegramBotManager + Telegram signal system implemented)
7. **Testing:** Implement last with 80%+ coverage
8. **Production Ready:** Docker setup, environment variables, cloud deployment ready

## CCXT Integration Note
- Use CCXT library for all exchange interactions
- Support spot and futures trading
- **CCXT is fully integrated via BotOrderService** — all exchange interactions use real CCXT methods
- **Complete ALL other code:** validation, database operations, BotOrder entries, error handling, notifications

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
