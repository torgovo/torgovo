# Sequence Diagrams — Torgovo2 Key Interaction Flows

---

## 1. Grid/Martingale Bot — Start and Trade Lifecycle

```mermaid
sequenceDiagram
    participant Admin as Django Admin
    participant AdminCode as bots/admin.py
    participant Service as services/bot_executor.py
    participant Celery as Celery Worker
    participant Engine as apps/trading/engines/execution.py
    participant BotEngine as apps/trading/engines/bot_engine.py
    participant Strategy as strategies/quantum_ai.py
    participant Adapter as exchanges/base_adapter.py
    participant Exchange as CCXT / Exchange API
    participant DB as Database

    Admin->>AdminCode: Click "Start Bot"
    AdminCode->>Service: BotExecutorService.start_grid_bot(user, bot_id)
    Service->>DB: Check BotSubscription.is_active
    DB-->>Service: Active
    Service->>Celery: run_trading_bot.delay(bot_id, 'grid')

    Celery->>Engine: run_bot(bot_id, 'grid')

    Engine->>DB: Load GridBot (select_related user, subscription)
    DB-->>Engine: Bot model
    Engine->>DB: Check is_running flag
    DB-->>Engine: False
    Engine->>DB: Set is_running = True

    Engine->>DB: ExchangeCredentials.objects.get(user, exchange_name)
    DB-->>Engine: Credentials row
    Engine->>Engine: get_decrypted_credentials()
    Engine->>Engine: _mark_bot_starting(bot_id) — in-memory lock

    Engine->>BotEngine: BotEngine(config_dict)
    BotEngine->>BotEngine: BotExecutor.from_config(config) — creates adapter + strategy

    BotEngine->>Adapter: fetch_ticker(symbol)
    Adapter->>Exchange: CCXT fetch_ticker()
    Exchange-->>Adapter: Ticker data
    Adapter-->>BotEngine: Standardized ticker

    BotEngine->>Adapter: get_current_price(symbol)
    Adapter-->>BotEngine: 50000.0

    BotEngine->>BotEngine: update_conditions() — evaluates all 6 entry cases
    BotEngine->>Strategy: _sync_strategy() — syncs indicator values

    alt Buy Signal (e.g., EMA crossover + RSI < 30)
        BotEngine->>BotEngine: calculated_grid_orders(data)
        BotEngine->>Adapter: create_market_order_with_cost(symbol, 'buy', cost)
        Adapter->>Exchange: CCXT create_market_buy_order_with_cost()
        Exchange-->>Adapter: Order response
        Adapter-->>BotEngine: Order dict

        BotEngine->>Adapter: create_limit_order(symbol, 'sell', qty, favor_level_1)  — grid orders
        Adapter->>Exchange: CCXT create_limit_order()
        Exchange-->>Adapter: Limit order placed
        BotEngine->>Adapter: create_limit_order(symbol, 'sell', qty, favor_level_2)
        BotEngine->>Adapter: create_limit_order(symbol, 'buy', qty, against_level_1)

        BotEngine->>BotEngine: spawn monitor_grid_orders thread
        BotEngine->>BotEngine: spawn monitor_lossProfit thread

        BotEngine->>DB: save_order() — logs to Order model
    end

    BotEngine-->>Engine: {'success': True, 'signal': reason, 'side': 'Buy'}
    Engine-->>Celery: Result
    Celery-->>AdminCode: Async complete
```

---

## 2. Quantum AI Fund — Performance Smoothing

```mermaid
sequenceDiagram
    participant CeleryBeat as Celery Beat
    participant FundSvc as services/quantum_ai_fund.py
    participant Fund as bots/models/QuantumAIFund
    participant Reserve as bots/models/ReserveFund
    participant Investment as bots/models/QuantumAIInvestment
    participant Engine as BotEngine
    participant Exchange as CCXT Exchange

    Note over CeleryBeat,Exchange: Periodic Task (hourly)

    CeleryBeat->>FundSvc: update_fund_performance(fund_id)

    FundSvc->>Engine: Get current total_value from exchange
    Engine->>Exchange: fetch_balance / fetch_positions
    Exchange-->>Engine: Current portfolio value
    Engine-->>FundSvc: 125,000 USDT

    FundSvc->>Fund: Load fund (total_fund_value=100,000, total_deposits=80,000)
    Fund-->>FundSvc: Fund data

    FundSvc->>FundSvc: actual_return = (125,000 - 100,000) / 100,000 = 25%

    alt actual_return (25%) > monthly_max_return (15%)
        FundSvc->>FundSvc: smoothed_return = 15% (cap)
        FundSvc->>FundSvc: excess = 25% - 15% = 10%
        FundSvc->>Fund: monthly_max_return shown to users
        FundSvc->>FundSvc: calculate_excess_return() = 10%
        FundSvc->>Reserve: deposit_excess(10% of fund)
        Reserve->>Reserve: balance += excess_amount
    else actual_return (5%) < monthly_min_return (2%)
        FundSvc->>FundSvc: smoothed_return = 2% (floor)
        FundSvc->>FundSvc: shortfall = 2% - 5% = -3%
        FundSvc->>Reserve: is_below_target() — check if reserve can cover
        Reserve-->>FundSvc: True
        FundSvc->>Reserve: apply_cover(shortfall_amount)
        Reserve->>Reserve: balance -= cover_amount
    else min (2%) <= actual (8%) <= max (15%)
        FundSvc->>FundSvc: smoothed_return = actual_return = 8%
        FundSvc->>FundSvc: No reserve adjustment needed
    end

    FundSvc->>Fund: Update total_fund_value = 125,000
    FundSvc->>Fund: Update total_profit

    Note over FundSvc,Investment: Admin triggers distribution

    CeleryBeat->>FundSvc: calculate_profit_distribution(fund_id)

    FundSvc->>Investment: Get all active investments
    Investment-->>FundSvc: [user1: 10%, user2: 5%, ...]

    loop For each investment
        FundSvc->>FundSvc: user_share = weekly_profit * share_percentage * 0.2
        FundSvc->>FundSvc: admin_share = weekly_profit * share_percentage * 0.8
        FundSvc->>DB: Create QuantumWeeklyProfit record
        FundSvc->>Investment: user_accrued_profit += user_share
    end
```

---

## 3. TradingView Webhook → Signal Bot Execution

```mermaid
sequenceDiagram
    participant TV as TradingView Alert
    participant Nginx as Nginx
    participant Webhook as apps/webhooks/views.py
    participant Service as services/bot_executor.py
    participant Bot as bots/models/SignalBot
    participant Creds as exchanges/models/ExchangeCredentials
    participant Adapter as exchanges/base_adapter.py
    participant Exchange as CCXT Exchange
    participant OrderModel as bots/models/Order

    TV->>Nginx: POST /api/webhooks/custombot/
    Nginx->>Webhook: Forward request + JSON payload

    Webhook->>Webhook: Parse JSON: {bot_id, secret_key, symbol, side, qty, ...}
    Webhook->>Bot: Find SignalBot by webhook_url

    alt Invalid bot_id or secret_key
        Webhook-->>TV: 401 Unauthorized
    end

    Webhook->>Bot: Check signals_remaining > 0

    alt Rate limited
        Webhook-->>TV: 429 Too Many Requests
    end

    Webhook->>Service: BotExecutorService.execute_signal_bot_order(user, bot_id, payload)

    Service->>Creds: ExchangeCredentials.objects.get(user=user, exchange_name=..., is_active=True)
    Creds-->>Service: Credentials row
    Service->>Service: get_decrypted_credentials()

    Service->>Adapter: create_market_order(symbol, side, quantity, params)
    Adapter->>Exchange: CCXT create_market_order()
    Exchange-->>Adapter: Order confirmation {id, price, status, ...}
    Adapter-->>Service: Standardized order dict

    Service->>OrderModel: Create Order record
    Note over Service,OrderModel: Order fields: user, Pair, Side, Quantity, Price, Exchange, signal_bot FK

    Service->>Bot: Update total_trades++, successful_trades++, total_profit_loss
    Service->>Bot: Increment signals_used_this_month

    Service-->>Webhook: Execution result
    Webhook-->>TV: 200 OK + Order details JSON
```

---

## 4. Bot Stop + Resource Cleanup

```mermaid
sequenceDiagram
    participant Admin as Admin User
    participant AdminUI as Django Admin
    participant Service as services/bot_executor.py
    participant Celery as Celery Worker
    participant Engine as execution.py
    participant BotEngine as bot_engine.py
    participant Adapter as exchanges/adapter
    participant Exchange as CCXT Exchange
    participant DB as Database

    Admin->>AdminUI: Click "Stop Bot"
    AdminUI->>Service: BotExecutorService.stop_grid_bot(user, bot_id)

    Service->>Celery: stop_bot.delay(bot_id)

    Celery->>Engine: stop_bot(bot_id, bot_type)

    Engine->>Engine: _mark_bot_stopped(bot_id) — remove from in-memory set

    Engine->>Engine: Pop engine from _running_engines dict
    Engine->>BotEngine: engine.stop_bot()

    BotEngine->>BotEngine: Set is_running = False (signals threads)

    BotEngine->>BotEngine: monitor_grid_orders thread exits loop
    BotEngine->>BotEngine: monitor_lossProfit thread exits loop

    BotEngine->>BotEngine: Wait for thread joins (timeout)

    BotEngine->>Adapter: cancel_all_orders(symbol)
    Adapter->>Exchange: CCXT cancel_all_orders()
    Exchange-->>Adapter: Cancelled orders
    Adapter-->>BotEngine: List of cancelled orders

    BotEngine->>BotEngine: reset_trading_state()
    BotEngine->>BotEngine: Clear favor_lvl, against_lvl, signals_generated

    BotEngine-->>Engine: Stop complete

    Engine->>DB: Update is_running = False, stopped_at = now()
    alt quantum_ai type
        Engine->>DB: QuantumAIBot.objects.filter(id=bot_id).update(...)
    else grid type
        Engine->>DB: GridBot.objects.filter(id=bot_id).update(...)
    else martingale type
        Engine->>DB: MartingaleBot.objects.filter(id=bot_id).update(...)
    end

    Engine-->>Celery: {'success': True, 'bot_id': bot_id}
    Celery-->>AdminUI: Bot stopped
    AdminUI-->>Admin: Confirmation message
```

---

## 5. Subscription Purchase → Bot Activation

```mermaid
sequenceDiagram
    participant User as Platform User
    participant API as DRF API View
    participant Payment as payments/models
    participant Admin as Admin User
    participant Bot as bots/models

    User->>API: GET /api/payments/bot-subscription-plans/
    API-->>User: [plan1, plan2, plan3, ...]

    User->>API: POST /api/payments/bot-subscriptions/ {plan_id}
    API->>Payment: Create BotSubscription(user, plan, status='pending_payment')
    Payment-->>API: Subscription created
    API-->>User: {id, plan, status: 'pending_payment'}

    User->>API: POST /api/payments/bot-subscriptions/{id}/upload-payment/
    API->>Payment: Save payment_screenshot
    Payment-->>API: Screenshot saved
    API->>Payment: Update status = 'pending_approval'
    API-->>User: {status: 'pending_approval', message: 'Awaiting admin verification'}

    Admin->>API: GET /admin/payments/botsubscription/ — Review pending
    API-->>Admin: [pending_approval subscriptions]

    Admin->>API: POST /admin/payments/botsubscription/{id}/approve/
    API->>Payment: subscription.approve()
    Payment->>Payment: status = 'active', started_at = now(), expires_at = now + duration
    Payment-->>API: Approved

    API-->>Admin: Subscription activated
    API-->>User: (next request) status = 'active'

    User->>API: POST /api/bots/grid-bots/ {subscription_id, ...}
    API->>Bot: Create GridBot(subscription=active_sub, ...)
    Bot-->>API: GridBot created
    API-->>User: {id, name, status: 'stopped', ...}

    User->>API: POST /api/bots/grid-bots/{id}/start/
    API->>API: Check subscription still active
    alt Subscription expired
        API-->>User: 402 Payment Required
    else Active
        API->>Celery: dispatch run_bot(bot_id, 'grid')
        API-->>User: {status: 'starting'}
    end
```
