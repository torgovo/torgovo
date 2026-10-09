# Flow Charts — Torgovo2 Trading Lifecycle

---

## 1. Grid / Martingale Bot Lifecycle (Full Cycle)

```mermaid
flowchart TB
    START([Bot Start]) --> CHECK_SUB{Check<br/>Subscription?}
    CHECK_SUB -->|Active| LOAD_BOT[Load Bot from DB<br/>GridBot / MartingaleBot]
    CHECK_SUB -->|Inactive| REJ[Reject: Subscription Required]

    LOAD_BOT --> DB_CHECK{DB Flag<br/>is_running?}
    DB_CHECK -->|False| MARK_START[Mark is_running = True<br/>Save to DB]
    DB_CHECK -->|True| REJ2[Reject: Already Running]

    MARK_START --> LOAD_CREDS[Load ExchangeCredentials<br/>Decrypt API Keys]
    LOAD_CREDS --> CREATE_ENGINE[Create BotEngine<br/>with config dict]
    CREATE_ENGINE --> FETCH_PRICE[fetch_current_price]

    FETCH_PRICE --> EVAL_ENTRY{Evaluate<br/>Entry Conditions}
    EVAL_ENTRY -->|6 Buy Cases| BUY_SIGNAL{Buy Signal<br/>Generated?}
    EVAL_ENTRY -->|6 Sell Cases| SELL_SIGNAL{Sell Signal<br/>Generated?}

    BUY_SIGNAL -->|Yes| PLACE_BUY[Place Initial Market Buy<br/>with calculated_grid_orders]
    BUY_SIGNAL -->|No| WAIT[Wait for next cycle]
    SELL_SIGNAL -->|Yes| PLACE_SELL[Place Initial Market Sell<br/>with calculated_grid_orders]
    SELL_SIGNAL -->|No| WAIT

    PLACE_BUY --> GRID_ORDERS_B[Place Limit Sell Orders<br/>at favor levels<br/>Place Limit Buy Orders<br/>at against levels]
    PLACE_SELL --> GRID_ORDERS_S[Place Limit Buy Orders<br/>at favor levels<br/>Place Limit Sell Orders<br/>at against levels]

    GRID_ORDERS_B --> MONITOR_THREADS[Spawn Background Threads]
    GRID_ORDERS_S --> MONITOR_THREADS

    MONITOR_THREADS --> MONITOR_GRID{monitor_grid_orders<br/>Thread}
    MONITOR_THREADS --> MONITOR_SLTP{monitor_lossProfit<br/>Thread}

    MONITOR_GRID --> CHECK_FILL{Order Filled?}
    CHECK_FILL -->|Yes| COUNTER_ORDER[Place Counter-Order<br/>at opposite grid level]
    CHECK_FILL -->|No| CHECK_FILL
    COUNTER_ORDER --> CHECK_FILL

    MONITOR_SLTP --> CALC_PNL[Calculate PnL %]
    CALC_PNL --> TP_HIT{Take Profit<br/>Reached?}
    CALC_PNL --> SL_HIT{Stop Loss<br/>Reached?}

    TP_HIT -->|Yes| CLOSE_TP[Close Position<br/>Cancel All Limit Orders]
    SL_HIT -->|Yes| CLOSE_SL[Close Position<br/>Cancel All Limit Orders]
    TP_HIT -->|No| CALC_PNL
    SL_HIT -->|No| CALC_PNL

    CLOSE_TP --> RESET[Reset Trading State<br/>Clear grid levels]
    CLOSE_SL --> RESET

    RESET --> LOG_TRADE[Save Order to DB<br/>Update Bot Stats]
    LOG_TRADE --> EVAL_ENTRY

    WAIT --> EVAL_ENTRY

    %% Styles
    classDef decision fill:#fff9c4,stroke:#f9a825,stroke-width:2px
    classDef process fill:#e3f2fd,stroke:#1565c0,stroke-width:2px
    classDef terminal fill:#fce4ec,stroke:#c62828,stroke-width:2px
    classDef thread fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px

    class CHECK_SUB,DB_CHECK,EVAL_ENTRY,BUY_SIGNAL,SELL_SIGNAL,CHECK_FILL,TP_HIT,SL_HIT decision
    class START,REJ,REJ2 terminal
    class LOAD_BOT,MARK_START,LOAD_CREDS,CREATE_ENGINE,FETCH_PRICE,PLACE_BUY,PLACE_SELL,GRID_ORDERS_B,GRID_ORDERS_S process
    class MONITOR_GRID,MONITOR_SLTP thread
```

---

## 2. Quantum AI Fund Flow (Smoothing + Reserve)

```mermaid
flowchart TB
    START([Admin starts QuantumAIBot]) --> LOAD_QAI[Load QuantumAIBot<br/>+ QuantumAIFund]
    LOAD_QAI --> DECRYPT[Decrypt Fund<br/>Master API Keys]
    DECRYPT --> CREATE_ENGINE[Create BotEngine<br/>with Fund Credentials]
    CREATE_ENGINE --> TRADE_LOOP[Trading Loop<br/>BotEngine.startBot]

    subgraph TRADING[CORE TRADING]
        TRADE_LOOP --> EVAL_CONDITIONS[Evaluate 6 Buy Entry<br/>+ 4 Sell Exit Cases]
        EVAL_CONDITIONS --> PLACE_ORDERS[Execute Orders<br/>on Exchange]
        PLACE_ORDERS --> MONITOR[Monitor Positions<br/>SL/TP Threads]
        MONITOR --> UPDATE_PNL[Track Unrealized PnL]
        UPDATE_PNL --> EVAL_CONDITIONS
    end

    subgraph SMOOTHING[RETURN SMOOTHING]
        PERIODIC([Periodic: Celery Beat]) --> UPDATE_FUND[update_fund_performance]
        UPDATE_FUND --> CALC_ACTUAL{Calculate<br/>Actual Return}
        CALC_ACTUAL -->|actual < min_return| SHOW_MIN[Show Monthly Min<br/>Reserve covers gap]
        CALC_ACTUAL -->|min <= actual <= max| SHOW_ACTUAL[Show Actual Return]
        CALC_ACTUAL -->|actual > max| SHOW_MAX[Show Monthly Max<br/>Excess to Reserve]

        SHOW_MIN --> CHECK_RESERVE{Reserve can<br/>cover gap?}
        CHECK_RESERVE -->|Yes| DEDUCT[Withdraw from<br/>ReserveFund]
        CHECK_RESERVE -->|No| ADMIN_ALERT[Alert Admin:<br/>Reserve Low]

        SHOW_MAX --> EXCESS_CALC[Calculate excess]
        EXCESS_CALC --> DEPOSIT[Deposit excess to<br/>ReserveFund]
    end

    subgraph DISTRIBUTION[PROFIT DISTRIBUTION]
        CALC_PROFIT([Admin Action: Calculate Profit Distribution])
        CALC_PROFIT --> AGGREGATE[Aggregate InvestorPortfolio<br/>share_percentages]
        AGGREGATE --> ALLOCATE[Allocate weekly profit<br/>20% users / 80% admin]
        ALLOCATE --> CREATE_WEEKLY[Create QuantumWeeklyProfit<br/>records per user]
        CREATE_WEEKLY --> PAYOUT([Admin Action: Process Payouts])

        PAYOUT --> TRANSFER[Transfer USDT to<br/>User Wallets]
        TRANSFER --> UPDATE_INVESTMENT[Update<br/>InvestorPortfolio.accrued_profit]
        UPDATE_INVESTMENT --> MARK_DISTRIBUTED[Mark WeeklyProfit<br/>is_distributed = True]
    end

    TRADING -.-> PERIODIC
    SMOOTHING -.-> CALC_PROFIT

    style START fill:#fce4ec,stroke:#c62828
    style TRADING fill:#e3f2fd,stroke:#1565c0
    style SMOOTHING fill:#e8f5e9,stroke:#388e3c
    style DISTRIBUTION fill:#fff3e0,stroke:#f57c00
```

---

## 3. Signal Bot (TradingView Webhook) Flow

```mermaid
flowchart LR
    subgraph "External"
        TV[TradingView<br/>Strategy Alert]
    end

    subgraph "Webhook Reception"
        POST[POST /api/webhooks/custombot/]
        AUTH[Authenticate via<br/>bot_id + secret_key]
        PARSE[Parse Payload:<br/>side, qty, price, pair]
    end

    subgraph "Execution"
        FIND_BOT[Find SignalBot by webhook_url]
        CHECK_LIMIT{Signal limit<br/>remaining?}
        LOAD_CREDS[Load ExchangeCredentials<br/>Decrypt Keys]
        DECIDE_ENGINE{Use BotEngine<br/>or raw CCXT?}
    end

    subgraph "BotEngine Path"
        BE_PATH[Create BotEngine<br/>execute_once]
        BE_ORDER[Place Order via<br/>Adapter Layer]
    end

    subgraph "Raw CCXT Path (legacy)"
        RAW_PATH[Create CCXT Order<br/>Direct on Exchange]
    end

    subgraph "Post-Execution"
        LOG_ORDER[Log to Order Model<br/>FK = SignalBot]
        UPDATE_BOT[Update SignalBot:<br/>total_trades++, profit/loss]
        CHECK_SIGNAL{Check Signal Count}
        UPDATE_SIGNAL[Increment<br/>signals_used_this_month]
        RESPOND[Return JSON Response]
    end

    TV --> POST
    POST --> AUTH
    AUTH -->|Valid| PARSE
    AUTH -->|Invalid| REJECT[401 Unauthorized]
    PARSE --> FIND_BOT
    FIND_BOT --> CHECK_LIMIT
    CHECK_LIMIT -->|Yes| LOAD_CREDS
    CHECK_LIMIT -->|No / Rate Limited| RATE_LIMIT[429 Rate Limited]
    LOAD_CREDS --> DECIDE_ENGINE

    DECIDE_ENGINE -->|Grid/Martingale config| BE_PATH
    DECIDE_ENGINE -->|Simple signal| RAW_PATH

    BE_PATH --> BE_ORDER
    BE_ORDER --> LOG_ORDER
    RAW_PATH --> LOG_ORDER

    LOG_ORDER --> UPDATE_BOT
    UPDATE_BOT --> CHECK_SIGNAL
    CHECK_SIGNAL --> UPDATE_SIGNAL
    UPDATE_SIGNAL --> RESPOND

    classDef ext fill:#fff3e0,stroke:#f57c00,stroke-width:2px
    classDef webhook fill:#e3f2fd,stroke:#1565c0,stroke-width:2px
    classDef decision fill:#fff9c4,stroke:#f9a825,stroke-width:2px
    classDef execution fill:#fce4ec,stroke:#c62828,stroke-width:2px
    classDef post fill:#e8f5e9,stroke:#388e3c,stroke-width:2px

    class TV ext
    class POST,AUTH,PARSE,FIND_BOT webhook
    class CHECK_LIMIT,DECIDE_ENGINE,CHECK_SIGNAL decision
    class BE_PATH,RAW_PATH,BE_ORDER execution
    class LOG_ORDER,UPDATE_BOT,UPDATE_SIGNAL,RESPOND post
```

---

## 4. User Onboarding + Bot Creation Flow

```mermaid
flowchart TB
    USER([User]) --> REGISTER[Register<br/>POST /api/auth/register/]
    REGISTER --> VERIFY_EMAIL{Email<br/>Verified?}
    VERIFY_EMAIL -->|No| SEND_CODE[Send Verification Code]
    SEND_CODE --> VERIFY[Verify Email]
    VERIFY --> VERIFY_EMAIL
    VERIFY_EMAIL -->|Yes| LOGIN[Login<br/>JWT Token Issued]

    LOGIN --> BROWSE_PLANS{Choose<br/>Subscription Plan}
    BROWSE_PLANS --> PURCHASE[Purchase BotSubscriptionPlan]
    PURCHASE --> UPLOAD_PAYMENT[Upload Payment Proof<br/>Screenshot]
    UPLOAD_PAYMENT --> PENDING_APPROVAL{Admin<br/>Approves?}

    PENDING_APPROVAL -->|Yes| SUB_ACTIVE[BotSubscription = Active]
    PENDING_APPROVAL -->|No| SUB_REJECTED[BotSubscription = Rejected]

    SUB_ACTIVE --> CHOOSE_BOT_TYPE{Choose Bot Type}
    CHOOSE_BOT_TYPE -->|TradingView Alerts| CREATE_SIGNAL[Create SignalBot<br/>Set webhook_url + trading_pair]
    CHOOSE_BOT_TYPE -->|Grid Trading| CREATE_GRID[Create GridBot<br/>Set levels, qty, TP/SL]
    CHOOSE_BOT_TYPE -->|Martingale| CREATE_MARTINGALE[Create MartingaleBot<br/>Set multiplier, levels]
    CHOOSE_BOT_TYPE -->|Quantum AI| CREATE_QAI[InvestorDeposit<br/>Deposit to Fund Wallet]

    CREATE_SIGNAL --> CONFIGURE[Configure via API]
    CREATE_GRID --> CONFIGURE
    CREATE_MARTINGALE --> CONFIGURE

    CONFIGURE --> START_BOT{Start Bot?}
    START_BOT -->|Admin or API| TRADING_START[run_bot(bot_id, type)]
    TRADING_START --> ACTIVE_TRADING[Trading Active]

    ACTIVE_TRADING --> MONITOR_DASHBOARD[Monitor via Dashboard<br/>Order History, PnL]
    MONITOR_DASHBOARD --> STOP_BOT{Stop Bot?}
    STOP_BOT -->|Yes| BOT_STOP[stop_bot(bot_id)]
    STOP_BOT -->|No| ACTIVE_TRADING

    BOT_STOP --> ARCHIVE[Bot Stopped<br/>Can Restart Later]

    classDef user fill:#e1f5fe,stroke:#0288d1,stroke-width:2px
    classDef auth fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px
    classDef decision fill:#fff9c4,stroke:#f9a825,stroke-width:2px
    classDef bot fill:#e8f5e9,stroke:#388e3c,stroke-width:2px
    classDef trading fill:#fce4ec,stroke:#c62828,stroke-width:2px

    class USER user
    class REGISTER,SEND_CODE,VERIFY,LOGIN auth
    class VERIFY_EMAIL,BROWSE_PLANS,PENDING_APPROVAL,CHOOSE_BOT_TYPE,START_BOT,STOP_BOT decision
    class PURCHASE,UPLOAD_PAYMENT,SUB_ACTIVE,SUB_REJECTED,CONFIGURE bot
    class TRADING_START,ACTIVE_TRADING,MONITOR_DASHBOARD trading
```

---

## 5. Concurrent Bot Execution State Machine

```mermaid
stateDiagram-v2
    [*] --> IDLE: Bot Created

    IDLE --> STARTING: run_bot() called
    STARTING --> CHECK_DB_FLAG: Load Bot from DB

    CHECK_DB_FLAG --> DUPLICATE: is_running = True
    CHECK_DB_FLAG --> ACQUIRE_LOCK: is_running = False

    ACQUIRE_LOCK --> DUPLICATE: _mark_bot_starting() = False (already in _running_bots)
    ACQUIRE_LOCK --> LOADING: Lock acquired

    LOADING --> ACTIVE_TRADING: BotEngine.startBot() succeeds
    LOADING --> ERROR: startBot() throws exception

    ACTIVE_TRADING --> STOPPING: stop_bot() called
    ACTIVE_TRADING --> ERROR: Engine thread crashes
    ACTIVE_TRADING --> COMPLETED: TP/SL hit, grid complete

    STOPPING --> STOPPED: Engine stop_bot() called
    STOPPED --> RELEASING: _mark_bot_stopped() + DB is_running = False
    RELEASING --> IDLE: Ready to restart

    DUPLICATE --> [*]: Return error

    ERROR --> RELEASING: Clean up + mark stopped

    COMPLETED --> RELEASING

    note right of ACTIVE_TRADING
        - BotEngine evaluates entry conditions
        - Calculated grid orders placed
        - monitor_grid_orders thread running
        - monitor_lossProfit thread running
    end note

    note right of DUPLICATE
        Two-layer guard:
        1. DB: bot.is_running flag
        2. In-memory: _running_bots set
    end note
```
