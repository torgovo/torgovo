# Data Flow Diagram — Money & Order Flow

> Trace every path: how data, money, and orders move through the system. Critical for audit, compliance, and debugging.

---

## Legend

```
[External Entity]   (Process)           {Data Store}           ───►  Data Flow
   User            Execute Trade        PostgreSQL DB
```

---

## Level 0: Context DFD

```mermaid
flowchart LR
    subgraph External
        TRADER([Trader])
        ADMIN([Admin])
        EXCHANGE([Crypto Exchange])
        TV([TradingView])
    end

    subgraph System
        P0("Torgovo2 Platform")
    end

    TRADER -- "API calls, Payments" --> P0
    P0 -- "Order confirmations, Dashboard" --> TRADER
    ADMIN -- "Approvals, Bot actions" --> P0
    P0 -- "Status, Reports" --> ADMIN
    TV -- "Webhook alerts" --> P0
    P0 -- "Market orders" --> EXCHANGE
    EXCHANGE -- "Fills, Balances, Prices" --> P0
```

---

## Level 1: Main Data Flows

```mermaid
flowchart TB
    subgraph External
        USER([User / Trader])
        ADMIN([Platform Admin])
        EX([Exchange API])
        TV([TradingView])
    end

    subgraph Processes
        REG("1. Register / Auth")
        SUB("2. Subscribe / Pay")
        CREATE("3. Create Bot")
        EXEC("4. Execute Trading")
        MONITOR("5. Monitor Positions")
        PNL("6. Track PnL")
        SMOOTH("7. Smooth Returns")
        DIST("8. Distribute Profit")
        WITHDRAW("9. Withdraw Funds")
        AUDIT("10. Audit Log")
    end

    subgraph Stores
        USERS[(Users DB)]
        SUBS[(Subscriptions DB)]
        BOTS[(Bots DB)]
        ORDERS[(Orders DB)]
        EXCH_DATA[(Exchange Data)]
        FUND[(Fund DB)]
        RESERVE[(Reserve DB)]
        PROFIT[(Weekly Profit DB)]
        AUDIT_LOG[(Audit Log DB)]
    end

    %% Flow 1: Auth
    USER -->|email, password| REG
    REG -->|user record| USERS
    REG -->|JWT token| USER

    %% Flow 2: Subscription
    USER -->|plan_id, payment proof| SUB
    SUB -->|subscription row| SUBS
    ADMIN -->|approve/reject| SUB
    SUB -->|status notification| USER

    %% Flow 3: Bot Creation
    USER -->|config: levels, pairs, qty| CREATE
    CREATE -->|bot model row| BOTS
    CREATE -->|bot_id, status| USER

    %% Flow 4: Trading Execution
    TV -->|webhook payload| EXEC
    ADMIN -->|start/stop| EXEC
    EXEC -->|read config| BOTS
    EXEC -->|read credentials| EXCH_DATA
    EXEC -->|market order via CCXT| EX
    EX -->|order fill| EXEC
    EXEC -->|order row| ORDERS
    EXEC -->|update bot state| BOTS

    %% Flow 5: Monitor
    EXEC -->|poll position, price| EX
    EX -->|position data| MONITOR
    MONITOR -->|grid counter-orders| EX
    MONITOR -->|SL/TP check| EXEC

    %% Flow 6: PnL
    MONITOR -->|unrealized PnL| PNL
    EXEC -->|closed trade PnL| PNL
    PNL -->|update bot PnL| BOTS

    %% Flow 7: Smoothing
    PNL -->|actual return| SMOOTH
    SMOOTH -->|smoothed return| FUND
    SMOOTH -->|excess deposited| RESERVE
    SMOOTH -->|gap covered from| RESERVE

    %% Flow 8: Distribution
    ADMIN -->|trigger| DIST
    DIST -->|read share %| BOTS
    DIST -->|read fund| FUND
    DIST -->|weekly profit row| PROFIT
    DIST -->|accrued profit| BOTS
    DIST -->|payout| USER

    %% Flow 9: Withdrawal
    USER -->|withdrawal request| WITHDRAW
    ADMIN -->|approve| WITHDRAW
    WITHDRAW -->|send crypto| EX
    WITHDRAW -->|record| ORDERS

    %% Flow 10: Audit
    REG -->|action| AUDIT
    SUB -->|action| AUDIT
    ADMIN -->|action| AUDIT
    EXEC -->|action| AUDIT
    AUDIT -->|audit row| AUDIT_LOG

    %% Styles
    classDef ext fill:#e1f5fe,stroke:#0288d1
    classDef process fill:#fce4ec,stroke:#c62828,stroke-width:2px
    classDef store fill:#e8f5e9,stroke:#388e3c,stroke-width:2px

    class USER,ADMIN,EX,TV ext
    class REG,SUB,CREATE,EXEC,MONITOR,PNL,SMOOTH,DIST,WITHDRAW,AUDIT process
    class USERS,SUBS,BOTS,ORDERS,EXCH_DATA,FUND,RESERVE,PROFIT,AUDIT_LOG store
```

---

## Level 2: Trading Execution Data Flow (Detailed)

```mermaid
flowchart TB
    subgraph "External"
        EX([Bybit / Binance / OKX])
    end

    subgraph "Entry"
        CMD["run_bot(bot_id, type)"]
        CONFIG["{bot_id, bot_name, symbol,
               exchange_name, api_key,
               secret_key, credentials,
               parameters: {...}}"]
    end

    subgraph "Engine"
        BE["BotEngine.__init__(config)"]
        FE["fetch_current_price()"]
        UC["update_conditions()
            → 6 entry flags
            → 4 exit flags"]
        GRID["calculated_grid_orders(data)
            → initial_order
            → grid_orders"]
        MON["monitor_grid_orders()
            ↔ exchanged order fills"]
        SLTP["monitor_lossProfit()
            → SL/TP check"]
        SAVE["save_order()
            → Order model"]
    end

    subgraph "Adapter"
        TICK["fetch_ticker(symbol)
            → {last, bid, ask, ...}"]
        MKT["create_market_order_with_cost(symbol, side, cost)
            → {id, price, status, ...}"]
        LIMIT["create_limit_order(symbol, side, qty, price)
            → {id, status, ...}"]
        CANCEL["cancel_all_orders(symbol)
            → [cancelled orders]"]
        POS["fetch_position(symbol)
            → {size, entryPrice, unrealisedPnl}"]
        BAL["fetch_balance()
            → {total, free, used}"]
    end

    subgraph "Storage"
        ORDERS[(bots_order)]
        BOT[(bots_grid_bot / bots_martingale_bot)]
        INDICATOR[(bots_indicator)]
    end

    %% Flow
    CMD --> CONFIG
    CONFIG --> BE
    BE --> FE
    FE --> TICK --> EX
    TICK --> UC
    UC -->|"Flag matched → prepare_order_data()"| GRID
    GRID --> MKT --> EX
    GRID --> LIMIT --> EX
    GRID --> MON --> EX
    GRID --> SLTP

    MON -->|"Order filled"| GRID
    SLTP --> POS --> EX
    SLTP -->|"TP/SL hit"| CANCEL --> EX

    GRID --> SAVE --> ORDERS
    SAVE --> BOT
    UC --> INDICATOR

    MON -.->|updates| BOT
    SLTP -.->|reset| BOT

    %% Data flows labeled
    TICK --- data1["{last: 50000, bid: 49990, ask: 50010}"]
    MKT --- data2["{id: 'abc123', price: 50005, status: 'closed'}"]
    POS --- data3["{size: 0.1, entryPrice: 50000, unrealisedPnl: 50}"]
```

---

## Level 2: Quantum AI Fund — Money Flow

```mermaid
flowchart TB
    subgraph "Inflows"
        DEPOSIT["User deposits USDT
                 to fund wallet"]
        TRADE_PROFIT["BotEngine generates
                      trading profit"]
    end

    subgraph "Fund"
        FUND_DB[(QuantumAIFund)]
        INV[(QuantumAIInvestment)]
    end

    subgraph "Smoothing Engine"
        CALC["calculate_smoothed_return()
              → min/max capped"]
        EXCESS["calculate_excess_return()
               → reserve deposit"]
        SHORTFALL["shortfall
                   → reserve withdraw"]
    end

    subgraph "Reserve"
        RESERVE_DB[(ReserveFund)]
    end

    subgraph "Outflows"
        USER_PROFIT["User profit share
                     → accrued_profit"]
        ADMIN_PROFIT["Admin fee (80%)"]
        PAYOUT["Process Payout
                → USDT to user"]
    end

    %% Primary Flow
    DEPOSIT --> FUND_DB
    FUND_DB --> INV
    TRADE_PROFIT --> CALC

    CALC -->|"actual > max"| EXCESS
    CALC -->|"actual < min"| SHORTFALL
    CALC -->|"min ≤ actual ≤ max"| USER_PROFIT

    EXCESS -->|deposit| RESERVE_DB
    SHORTFALL -->|withdraw| RESERVE_DB
    RESERVE_DB -->|cover gap| USER_PROFIT

    CALC --> ADMIN_PROFIT
    USER_PROFIT --> PAYOUT
    ADMIN_PROFIT --> FUND_DB

    PAYOUT -->|USDT sent| USER

    note right of EXCESS
        Excess = max(0, actual - max)
        Goes to reserve buffer
    end note

    note right of SHORTFALL
        Shortfall = max(0, min - actual)
        Reserve must can_cover()
        before withdrawal
    end note
```

---

## Data Dictionary — Key Flows

| Data Flow | Source | Target | Content | Frequency | Volume |
|---|---|---|---|---|---|
| `run_bot command` | Celery task | execution.run_bot() | `{bot_id, bot_type}` | On admin start | <1/sec |
| `config dict` | run_bot() | BotEngine.__init__() | `{symbol, api_key, parameters, ...}` | Per bot start | ~2KB |
| `market order` | BotEngine | Adapter → CCXT | `{symbol, side, amount, params}` | Per trade cycle | ~500B |
| `ticker data` | CCXT → Adapter | BotEngine | `{last, bid, ask, volume}` | Every evaluation cycle | ~200B |
| `order fill` | Exchange → CCXT | BotEngine.save_order() | `{id, price, qty, status, fee}` | Per trade | ~1KB |
| `fund update` | BotEngine | QuantumAIFundService | `{fund_id, new_total_value}` | Periodic (hourly) | ~500B |
| `smoothed return` | QuantumAIFundService | Django Admin display | `{monthly_return, floor, cap}` | Hourly | ~200B |
| `payout` | Admin action → Service | User wallet | `{user_id, amount, currency}` | Weekly | ~1KB |
| `subscription` | User → API → DB | BotSubscription | `{user_id, plan_id, status}` | One-time per purchase | ~500B |
| `webhook payload` | TradingView | apps/webhooks/views.py | `{bot_id, secret, side, qty, ...}` | On alert trigger | ~1KB |
| `audit log` | All processes | core_audit_log | `{action, resource, user, timestamp}` | On state change | ~500B |
