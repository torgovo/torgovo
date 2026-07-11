# State Machines — Torgovo2 Platform

---

## 1. BotSubscription Lifecycle (6 states)

```mermaid
stateDiagram-v2
    [*] --> pending_payment: User purchases plan

    pending_payment --> pending_approval: User uploads payment proof
    pending_payment --> cancelled: User cancels before payment

    pending_approval --> active: Admin approves
    pending_approval --> rejected: Admin rejects (invalid proof)
    pending_approval --> cancelled: User cancels during review

    active --> expired: expires_at reached
    active --> cancelled: Admin cancels (violation)
    active --> active: User renews → extends expires_at

    expired --> active: User renews (payment)
    expired --> [*]: Not renewed within grace period

    cancelled --> [*]: Terminal state
    rejected --> [*]: Terminal state

    note right of pending_approval
        Admin receives notification
        Reviews payment screenshot
        Approves or rejects
    end note

    note right of active
        Bot creation allowed
        Engine checks is_expired
        before starting bots
    end note
```

### Transition Table

| From | To | Trigger | Guard | Actor |
|---|---|---|---|---|
| `[*]` | `pending_payment` | POST /api/payments/bot-subscriptions/ | None | User |
| `pending_payment` | `pending_approval` | Upload payment screenshot | File attached | User |
| `pending_payment` | `cancelled` | Cancel order | Within 24h | User |
| `pending_approval` | `active` | Admin approve | Screenshot valid, payment verified | Admin |
| `pending_approval` | `rejected` | Admin reject | Invalid/duplicate screenshot | Admin |
| `pending_approval` | `cancelled` | Cancel request | Before admin action | User |
| `active` | `expired` | Celery beat or access check | `now() > expires_at` | System |
| `active` | `cancelled` | Admin force-cancel | TOS violation | Admin |
| `active` | `active` | User renews | New payment successful | User + System |
| `expired` | `active` | User re-subscribes | New payment | User |

---

## 2. BotEngine Trading State Machine

```mermaid
stateDiagram-v2
    [*] --> IDLE: Bot created in DB

    IDLE --> STARTING: run_bot(bot_id, type)

    STARTING --> ACQUIRING_LOCK: DB is_running = True
    ACQUIRING_LOCK --> EVALUATING: _mark_bot_starting() → True
    ACQUIRING_LOCK --> DUPLICATE: Bot already in _running_bots set

    EVALUATING --> BUY_SIGNAL: Entry condition matched (Buy)
    EVALUATING --> SELL_SIGNAL: Entry condition matched (Sell)
    EVALUATING --> WAITING: No conditions met → retry

    BUY_SIGNAL --> INITIAL_ORDER_BUY: Place market buy
    SELL_SIGNAL --> INITIAL_ORDER_SELL: Place market sell

    INITIAL_ORDER_BUY --> GRID_PLACED: Grid limit orders placed
    INITIAL_ORDER_SELL --> GRID_PLACED: Grid limit orders placed

    GRID_PLACED --> MONITORING_GRID: Thread: monitor_grid_orders
    GRID_PLACED --> MONITORING_SLTP: Thread: monitor_lossProfit

    MONITORING_GRID --> ORDER_FILLED: Grid order filled
    ORDER_FILLED --> PLACE_COUNTER: Place opposite grid order
    PLACE_COUNTER --> MONITORING_GRID

    MONITORING_SLTP --> TP_HIT: Take-profit percent reached
    MONITORING_SLTP --> SL_HIT: Stop-loss percent reached

    TP_HIT --> CLOSING: Close position + cancel all orders
    SL_HIT --> CLOSING: Close position + cancel all orders
    ORDER_FILLED --> CLOSING: All grid levels exhausted

    CLOSING --> IDLE: reset_trading_state()
    CLOSING --> DUPLICATE: External stop_bot() called

    WAITING --> EVALUATING: Next evaluation cycle (polling)

    DUPLICATE --> [*]: Error returned to caller

    state MONITORING_GRID {
        [*] --> CHECK_ORDER_STATUS: Poll exchange
        CHECK_ORDER_STATUS --> ORDER_FILLED: Status = 'closed'
        CHECK_ORDER_STATUS --> CHECK_ORDER_STATUS: Not filled yet
    }

    state MONITORING_SLTP {
        [*] --> FETCH_POSITION: Poll position
        FETCH_POSITION --> CALC_PNL: Calculate PnL%
        CALC_PNL --> TP_HIT: PnL% >= Take_Profit%
        CALC_PNL --> SL_HIT: PnL% <= Stop_Loss%
        CALC_PNL --> FETCH_POSITION: Within bounds
    }
```

---

## 3. Quantum AI Investment Status

```mermaid
stateDiagram-v2
    [*] --> pending: User deposits to fund wallet
    pending --> active: Deposit confirmed (blockchain)
    pending --> cancelled: User cancels deposit

    active --> active: Profit accrues weekly
    active --> withdrawn: User requests withdrawal
    active --> cancelled: Admin force-removes (violation)

    withdrawn --> [*]: Payout processed
    cancelled --> [*]: Funds returned

    note right of active
        - Shares calculate_payout() weekly
        - 20% user / 80% admin split
        - Accrued profit tracked
    end note
```

---

## 4. QuantumDeposit Status

```mermaid
stateDiagram-v2
    [*] --> pending: Transaction submitted
    pending --> confirmed: Blockchain confirmations met
    pending --> failed: Transaction failed/reversed
    confirmed --> [*]: Investment credited
    failed --> [*]: Investment not credited
```

---

## 5. WithdrawalRequest Status

```mermaid
stateDiagram-v2
    [*] --> pending: User submits request
    pending --> approved: Admin approves + 2FA
    pending --> rejected: Admin rejects
    approved --> processing: System sends transaction
    processing --> completed: Blockchain confirmed
    processing --> failed: Network error/insufficient funds
    completed --> [*]
    failed --> [*]: Funds returned to balance
    rejected --> [*]: Funds not deducted
```

---

## 6. TelegramSubscription Status

```mermaid
stateDiagram-v2
    [*] --> pending_approval: User signs up, uploads payment
    pending_approval --> active: Admin approves
    pending_approval --> rejected: Admin rejects

    active --> active: Subscription renewed
    active --> expired: end_date reached
    active --> cancelled: Admin removes user
    active --> cancelled: User leaves channel

    expired --> active: User re-subscribes
    expired --> [*]: Not renewed
    cancelled --> [*]
    rejected --> [*]
```

---

## Composite: Full Platform State Space

```mermaid
stateDiagram-v2
    state "Platform" as PLATFORM {
        [*] --> IDLE

        IDLE --> USER_ONBOARDING: User registers

        state USER_ONBOARDING {
            [*] --> EMAIL_VERIFICATION
            EMAIL_VERIFICATION --> PHONE_VERIFICATION
            PHONE_VERIFICATION --> ONBOARDED
        }

        ONBOARDED --> SUBSCRIPTION_FLOW: User purchases plan

        state SUBSCRIPTION_FLOW {
            [*] --> PENDING_PAYMENT
            PENDING_PAYMENT --> PENDING_APPROVAL
            PENDING_APPROVAL --> ACTIVE_SUB
        }

        ACTIVE_SUB --> BOT_CREATION: User creates bot

        state BOT_CREATION {
            [*] --> CONFIGURE
            CONFIGURE --> DEPLOY
            DEPLOY --> TRADING
        }

        TRADING --> PROFIT_DISTRIBUTION: Quantum AI cycle
        TRADING --> COMPLETED: Grid cycle ends
        PROFIT_DISTRIBUTION --> TRADING
        COMPLETED --> IDLE
    }
```
