Project Specification: Development of a Django-Based Automated Trading Bot Platform
Overview
Develop a comprehensive, scalable web platform using Django (version 5.x or later) as the primary framework, with asynchronous capabilities enabled via Django Channels and Celery (with Redis as the broker) for handling real-time tasks such as webhook processing, bot executions, and background jobs. The Django project shall be named "Torgovo". The platform will provide subscription-based services for users to create, manage, and subscribe to custom trading bots for cryptocurrency exchanges. It will integrate with multiple exchanges (including but not limited to Binance, Bybit, OKX, MEXC, and Coinbase) using the CCXT library (latest stable version) to standardize API interactions for spot and futures trading. The system must ensure high security, uniqueness of identifiers, and resource efficiency, with a focus on user-friendly interfaces and robust admin controls.

The database shall use PostgreSQL (via Django's ORM) for storing all data, including user profiles, bots, transactions, approvals, trade logs, and referral details. All components must enforce uniqueness (e.g., via UUIDv4 for bot IDs, user IDs, webhook URLs, and referral codes) to prevent conflicts. Prioritize system structure first: Define project structure with apps (e.g., users, bots, payments, investments, exchanges, referrals), models, views, urls, forms, and templates. Create separate Django apps or files for each exchange where possible (e.g., exchanges/binance.py, exchanges/bybit.py) to handle dynamic CCXT object creation and API key differences, while keeping core features uniform and configurable via a central ExchangeManager class that dynamically loads exchange-specific handlers based on user input.

For functionality: Complete detailed aspects such as JSON message creation, webhook handling (including detection of bot/user via secret_key and bot_id), Quantum AI percentage/proportional distribution logic, database interactions (e.g., querying/retrieving data from DB, creating/updating objects), object instantiation, form validation, and related logic. Where explanations are not detailed or defined, implement necessary foundational code (e.g., data retrieval from DB, model object creation, serialization) but do not leave sections totally empty; instead, provide structured code with comments for placeholders. Only the specific few lines solely related to trading execution (e.g., actual CCXT API calls for placing orders) shall be commented out or left as empty placeholders (e.g., # TODO: Implement CCXT trade execution here; pass), while completing the surrounding code (e.g., pre-execution validation, post-execution logging to TradeLog model). Create views for all bots (custom, grid, martingale, Quantum AI), with internal code partially implemented as per available details and placeholders for undefined parts. For each executed trade (across all bots), log details in the database (e.g., model TradeLog with fields: user_id (UUIDField), bot_id (UUIDField), exchange (CharField), symbol (CharField), amount (FloatField), buy_sell (CharField choices=["buy", "sell"]), timestamp (DateTimeField), outcome (TextField for success/failure details)).

Implement testing last, once the full system structure and functionality are ready, using Django's testing framework for comprehensive coverage.

Additionally, provide comprehensive API documentation for all endpoints, including URLs, request methods (e.g., GET, POST, PUT, DELETE), expected data formats (JSON structures with field names, data types, and examples), response formats (JSON structures with status codes, success/error messages, and data), authentication requirements (e.g., JWT or session-based), and any query parameters or headers. This documentation shall be detailed and structured (e.g., in a dedicated Markdown file or inline comments) such that it can be directly used by an AI to generate a compatible frontend in React + Vite, ensuring perfect integration with API calls, data handling, and error management.

User Registration and Onboarding
Users shall register via Gmail (using OAuth 2.0 integration) or phone number (with SMS OTP verification using a service like Twilio).
Upon successful registration, the system shall immediately generate and assign:
A unique webhook URL based on bot type (e.g., https://platform-domain.com/webhooks/custom_bots/ for custom, https://platform-domain.com/webhooks/quantum_bots/ for Quantum AI, etc.), though base URL structure remains consistent with differentiation via path if needed.
A JSON message template for signals, including fields: bot_id (UUID format, e.g., xxxxx-xxxx-xxxx), buy/sell (string: "buy" or "sell"), symbol (string, e.g., "BTCUSDT"), exchange (string, e.g., "binance"), amount/quantity (float), timestamp (ISO 8601 format), code (optional user identifier string), and secret_key (a unique, per-user or per-bot token string for authentication).
The secret_key must be validated on every incoming webhook request to prevent spamming or unauthorized access; invalid requests shall return a 403 Forbidden response with no further processing.
Additionally, generate a unique referral code for each user (e.g., alphanumeric string) stored in the database.
Webhook and Signal Handling
Webhooks shall receive POST requests with JSON payloads from TradingView at type-specific URLs (e.g., /webhooks/custom_bots/), validated against the user's secret_key.
Upon validation, parse the JSON to detect the bot_id and derive the associated user_id from the database.
Process the signal asynchronously (via Celery) to identify the bot type and user, then route to the appropriate execution handler (e.g., for custom bots: execute single trade; for others: queue in bot manager).
Support both spot and futures trading modes, with error handling for failed executions (e.g., retry up to 3 times, log errors, and notify the user via email if persistent failure occurs). Leave actual CCXT execution as placeholders, but complete surrounding logic like DB queries for user/bot details and TradeLog creation.
Bot Creation and Management
Users shall create and manage multiple bots via a dashboard interface, including:
Custom Bots: Event-driven via webhooks; receive signal, execute single trade, and terminate. No persistent management required unless extended in future. Create views (e.g., CustomBotCreateView, CustomBotDetailView) with form handling for parameters, DB object creation, and partial logic; internal execution code as placeholder for trade but complete DB interactions.
Grid Bots: Configurable with parameters including percentage difference between levels (float), trading pair (string), exchange (string), amount per level (float), starting amount (float), leverage (integer, if applicable for futures), and other strategy-specific settings. Bots shall run continuously when enabled, monitoring and executing multiple trades. Create views (e.g., GridBotCreateView) with DB object creation and enable/disable logic; placeholders for monitoring/execution but complete data retrieval.
Martingale Bots: Similar to grid bots, with parameters for progressive strategies (e.g., multiplier for loss recovery, max levels), running continuously for repeated trades. Create analogous views with partial implementation for DB handling and placeholders for undefined execution.
Quantum AI Bots: Handled via investment; create views for investment submission and balance viewing, with full implementation for proportional distribution (see below), including DB queries and object updates.
Bots shall be enabled/disabled by users at any time via the dashboard.
Implement a Bot Manager module (as a Django service or Celery-based scheduler) specifically for Quantum AI, grid, and martingale bots:
Dynamically create bots upon activation (e.g., user enables or admin approves), with full DB object creation.
Monitor and discard bots when disabled, expired, or inactive (e.g., after 24 hours of no activity) to optimize resources (e.g., release memory, stop API polling), completing DB updates but placeholders for resource release if undefined.
Custom bots shall remain ephemeral and not use the bot manager unless persistence is added later.
The platform shall handle multiple bots per user, of mixed types, across multiple exchanges simultaneously.
Exchange Integration
Users shall connect exchanges to their accounts or bots by securely storing API keys and secrets (encrypted in the database).
Display connected exchanges on the dashboard with masked keys (e.g., ****abcd) for security.
Use CCXT for all interactions, supporting spot/futures with unified methods; handle exchange-specific quirks dynamically via separate files/apps (e.g., class BinanceHandler(CCXTBase): def create_client(api_key, secret): ... with exchange-specific configs). Central ExchangeManager to instantiate handlers based on exchange name. Leave actual connection/execution code as placeholders, but complete object creation and DB retrieval logic.
Quantum AI Bots Investment Feature
Provide pre-built "Quantum AI" bots for investment, promising 2-15% monthly profit (with explicit disclaimers that all risk is borne by the user and it is presented as low-risk, but losses are possible and entirely user-responsible).
Investments shall be in USDT only, sent to platform-provided wallet addresses on blockchains such as ERC20 and Aptos.
Post-transaction, users shall upload a screenshot and details (e.g., transaction hash, amount), saved in the database along with the purpose ("Quantum AI Investment").
Admin shall review and approve via dashboard; upon approval, activate the investment without granting bot access or trading visibility.
Users shall view only their personal balance on the dashboard, updated based on admin's trade outcomes without revealing actual trades.
Profit/Loss Distribution (Fully Implement):
Pool all approved USDT investments into a total (e.g., 100,000 USDT), querying DB for summation.
For each admin-executed trade (e.g., +200 USDT profit), calculate a "shown" adjustment as up to 20% of the actual outcome (admin-configurable via dashboard, e.g., modifiable to 15% or other values).
Distribute proportionally: User's shown change = (user's investment / total pool) * shown adjustment.
Apply the same for losses.
Ensure total shown changes across all users do not exceed the configured cap (e.g., 20%).
Recalculate pool and shares via scheduled Celery tasks (e.g., fortnightly or on-demand), aligning with manual withdrawals processed only every two weeks post-investment.
Balances shall update asynchronously after trades, with email notifications for significant changes, fully implementing DB updates and notifications.
Subscription Plans and Payments
Plans:
Basic (Free): 1 bot (spot or futures) with 50 webhook alerts max; notify users near limits with upsell prompts.
Paid Tiers: Custom bots, martingale bots, grid bots, telegram trade signals (extra subscription for access to signals channel), telegram trade execution alerts (extra, via Telegram Bot API sending executions to user's channel), and investment section (tier) for investing and earning 2-15% monthly.
Admin shall modify plans (features, limits, pricing) via dashboard.
Payments:
Methods: PayPal, Stripe, Wise, and cryptocurrency (via shared wallets).
For crypto: Use same addresses as Quantum AI; require upload of proof, saved with purpose (e.g., "Bot Subscription", "Telegram Signal").
Admin approves all crypto payments; apply to user's account upon approval.
Track usage limits (e.g., alerts) per plan, enforcing restrictions asynchronously, with full DB tracking implementation.
Referral System
Each user receives a unique referral code upon registration.
If a new user signs up using an existing user's code (e.g., via a referral field in the signup form), credit a bonus to the referrer (e.g., free alerts, discount on subscription, or small USDT equivalent, configurable by admin).
Track referrals in the database (model Referral with fields: referrer_id, referred_id, code, bonus_amount, timestamp).
Display referral code and earnings on the user dashboard, with full view implementation for data retrieval.
User Dashboard
A secure, responsive interface (using Django templates or a frontend like React if extended) showing:
Created bots (details, status, enable/disable controls).
Subscription details (plan, limits, renewal).
Connected exchanges (name, masked keys/secrets).
Quantum AI balance (updates only, no trade details).
Investment/transaction history.
Referral code, referred users, and bonus earnings.
Admin Features
Full control: Restrict, disable, or manage user accounts.
Dashboard for approving payments/investments, modifying plans/distribution caps, viewing logs (including trade logs), and manual actions (e.g., withdrawals, bot overrides, referral bonuses).
Send system-wide or targeted emails (using Django's email backend, e.g., SMTP with SendGrid).
API Documentation
Document all endpoints in a structured format (e.g., OpenAPI-compatible YAML or Markdown file named api_docs.md in the project root), including:
Authentication: Use JWT (via django-rest-framework-simplejwt) for API access; require token in Authorization header (Bearer <token>) for protected endpoints.
Base URL: /api/v1/
Example Endpoints:
User Registration: POST /api/v1/users/register/ | Request JSON: {"email": string (or "phone": string), "password": string, "referral_code": string (optional)} | Response: 201 Created, JSON {"user_id": uuid, "webhook_url": string, "json_template": object (with fields as defined), "referral_code": string} | Errors: 400 Bad Request with {"error": string}.
Webhook for Custom Bots: POST /api/v1/webhooks/custom_bots/ | Request JSON: {bot_id: uuid, buy/sell: string, symbol: string, exchange: string, amount: float, timestamp: string, code: string (opt), secret_key: string} | Response: 200 OK, JSON {"status": "processed"} | Validates secret_key, retrieves user/bot from DB, logs to TradeLog.
Create Grid Bot: POST /api/v1/bots/grid/ | Request JSON: {"percentage_difference": float, "pair": string, "exchange": string, "amount_per_level": float, "starting_amount": float, "leverage": int} | Response: 201 Created, JSON {"bot_id": uuid, "status": "created"} | Creates DB object, integrates with BotManager.
Get User Dashboard Data: GET /api/v1/users/dashboard/ | Query Params: none | Response: 200 OK, JSON {"bots": array of objects ({id: uuid, type: string, status: bool}), "subscription": object ({plan: string, limits: object}), "exchanges": array ({name: string, masked_key: string}), "quantum_balance": float, "transactions": array, "referral": object ({code: string, earnings: float})}.
Quantum AI Investment Submit: POST /api/v1/investments/quantum/ | Request Multipart: {"amount": float, "tx_hash": string, "screenshot": file} | Response: 201 Created, JSON {"submission_id": uuid, "status": "pending"} | Saves to DB with purpose.
Admin Approve Payment: PUT /api/v1/admin/payments/<id>/approve/ | Request JSON: {"approved": bool} | Response: 200 OK, JSON {"status": "approved"} | Updates DB, triggers activations.
And similar for all other features (e.g., bot enable/disable: PATCH /api/v1/bots/<id>/, referral bonus claim: POST /api/v1/referrals/claim/).
Ensure all data types (e.g., string, float, uuid, bool, array, object), required/optional fields, examples, and status codes (200, 201, 400, 401, 403, 404, 500) are specified for seamless React + Vite frontend integration (e.g., using Axios for calls, Zod for schema validation).
Additional Requirements
Emails: Integrate for notifications (e.g., confirmations, alerts) using Django's mail framework.
Telegram Features: For relevant paid tiers: Send order executions to user's channel; manage signal channel access post-payment, with placeholders for Telegram API but complete DB/user checks.
Security: Encrypt sensitive data; rate-limit endpoints; use HTTPS; validate all inputs.
Performance: Asynchronous everywhere possible; optimize with caching (e.g., Redis).
Testing: Implement last, with 80%+ coverage, including all edge cases.
Deployment: Design for cloud (e.g., AWS/Heroku), with environment variables for secrets.
This specification defines the complete project scope, ensuring no ambiguities. Implement iteratively, starting with structure (apps, models, views), then detailed functionality (e.g., webhooks, Quantum AI logic, DB operations), leaving only specific CCXT/trade lines as commented placeholders.