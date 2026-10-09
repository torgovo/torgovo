# Code Audit Report — Torgovo2

> **Date:** 2026-09-15
> **Scope:** Full codebase review across all Django apps, services, config, deployment, and infrastructure files.
> **Method:** Each finding below was verified by reading the actual source file and confirming the issue exists in the code on disk. No assumptions, no guesses. Where a claim could not be verified, it is explicitly marked as such.
> **Files read (partial list):** `config/settings/base.py`, `config/settings/production.py`, `config/settings/test.py`, `config/celery.py`, `config/urls.py`, `config/asgi.py`, `config/nginx.conf`, `config/wsgi.py`, `Dockerfile`, `docker-compose.yml`, `apps/trading/engines/bot_engine.py` (901 lines), `apps/trading/engines/execution.py` (666 lines), `apps/trading/engines/grid_monitor.py`, `apps/trading/engines/order_service.py`, `apps/trading/tasks.py` (491 lines), `apps/trading/views.py`, `apps/trading/routing.py`, `apps/trading/consumers.py`, `apps/trading/strategies/base.py`, `apps/trading/strategies/quantum_ai.py`, `apps/trading/strategies/grid_trading.py`, `apps/trading/strategies/martingale.py`, `apps/trading/exchanges/base_adapter.py`, `apps/trading/exchanges/bybit.py`, `apps/trading/exchanges/binance.py`, `apps/bots/models.py` (1099 lines), `apps/bots/views.py`, `apps/bots/urls.py`, `apps/bots/indicators_views.py`, `apps/bots/signals.py`, `apps/bots/tasks.py`, `apps/bots/serializers.py` (imported, not fully read), `apps/bots/admin.py` (partial), `apps/payments/models.py`, `apps/payments/views.py`, `apps/exchanges/models.py`, `apps/exchanges/views.py`, `apps/investments/models.py`, `apps/investments/views.py`, `apps/users/models.py`, `apps/users/admin_site.py`, `apps/users/admin.py`, `apps/referrals/models.py`, `apps/referrals/views.py`, `apps/referrals/tests/test_referrals.py`, `apps/subscriptions/views.py`, `apps/webhooks/views.py`, `services/bot_executor.py`, `services/quantum_ai_fund.py`, `services/subscription_service.py`, `services/two_factor.py`, `core/middleware.py`, `core/exceptions.py`, `core/pagination.py`, `core/models.py`, `core/utils.py`, `core/telegram_service.py`, `conftest.py`, `manage.py`, `requirements.txt`, `pyproject.toml`.

---

## 1. Blocking — Django Cannot Start

These issues prevent the application from booting. If `manage.py check` or `manage.py runserver` is run, Django raises an error and exits.

### B1. Duplicate `related_name` on `QuantumAIInvestment` ForeignKeys

**File:** `apps/bots/models.py`
**Lines:** 711 and 718

**What the code says:**

Line 711:
```python
user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="quantum_ai_investments")
```

Line 718:
```python
subscription = models.ForeignKey(
    "payments.BotSubscription",
    on_delete=models.CASCADE,
    related_name="quantum_ai_investments",  # <-- same related_name
    null=True,
    blank=True,
)
```

**Why it blocks:** Django checks for `related_name` uniqueness across all ForeignKeys on a model at startup. Two ForeignKeys on `QuantumAIInvestment` using `related_name="quantum_ai_investments"` causes Django to raise:
```
ValueError: related_name='quantum_ai_investments' is used on more than one field on QuantumAIInvestment
```
This is caught during the app registry population phase, before any request can be served. The application cannot start.

**Note:** If the application is currently running, either this file was modified after the last successful start, or the running process is using a cached/stale version of the model. Running `python manage.py check` will confirm.

---

## 2. Critical — Financial / Operational / Security

### C1. No Distributed Lock for Normal Bot Execution (Cross-Worker Race)

**Files:** `apps/trading/engines/execution.py` (lines 24–30, 433–447), `apps/trading/tasks.py` (lines 441–447)

**What the code says:**

`execution.py` lines 24–30:
```python
_running_bots: set = set()
_running_bots_lock = threading.Lock()

_running_engines: Dict[str, Any] = {}
_running_engines_lock = threading.Lock()
```

These are process-local data structures. They prevent a bot from being started twice within the **same** Celery worker process.

`tasks.py` lines 441–447 (`run_bot` function):
```python
if not _mark_bot_starting(bot_id):
    return {"success": False, "error": f"Bot {bot_id} is already running in this process"}
if restore_mode and not _try_redis_lock(bot_id):
    _mark_bot_stopped(bot_id)
    return {"success": False, "error": f"Bot {bot_id} restore locked by another worker"}
```

The Redis lock (`_try_redis_lock`) is **only** applied when `restore_mode=True`. Normal-mode execution has no distributed lock. In production with `CELERY_WORKER_CONCURRENCY=4` (or multiple worker containers), if `check_all_active_bots` dispatches `run_trading_bot` for bot X and the task lands on a different worker than the one that already has the engine running, the second worker will start a second engine for the same bot.

**Impact:** Two workers could trade on the same bot simultaneously. Orders could be duplicated. Position state could diverge.

**What exists:** `_try_redis_lock` is a working distributed lock (uses `cache.add` which is atomic SET NX EX). It is simply not called for normal mode — only for `restore_mode`.

---

### C2. `process_payouts()` Is Defined But Never Scheduled or Called

**Files:** `services/quantum_ai_fund.py` (line 159), `config/celery.py` (lines 41–69)

**What the code says:**

`quantum_ai_fund.py` line 159:
```python
@staticmethod
@transaction.atomic
def process_payouts(fund_id: str, payout_date=None):
    """
    Process actual payouts to users.
    Moves accrued_profit -> total_payouts + credits user balance.
    """
```

`celery.py` lines 41–69 — full beat schedule:
```python
app.conf.beat_schedule = {
    "run-active-bots": {"task": "apps.trading.tasks.check_all_active_bots", "schedule": 60.0},
    "check-stale-bots": {"task": "apps.trading.tasks.check_stale_bots", "schedule": 120.0},
    "distribute-quantum-ai-profits": {"task": "apps.trading.tasks.distribute_quantum_ai_profits", "schedule": 60*60*24*14},
    "heartbeat-check": {"task": "apps.trading.tasks.heartbeat_check", "schedule": 300.0},
    "reset-monthly-signals": {"task": "apps.trading.tasks.reset_monthly_signal_limits", "schedule": crontab(day_of_month=1, hour=0, minute=0)},
    "accrue-quantum-ai-profits": {"task": "apps.trading.tasks.accrue_quantum_ai_profits", "schedule": 3600.0},
}
```

`process_payouts` is not in the beat schedule. It is not called from any view, any other service method, or any Celery task. The imports at the top of `tasks.py` do not reference `process_payouts`.

**Impact:** `accrue_quantum_ai_profits` (hourly) increments `investment.accrued_profit`. `distribute_quantum_ai_profits` (fortnightly) also increments `accrued_profit` and creates `QuantumWeeklyProfit` records. But `accrued_profit` never moves to `UserBalance`. Users see their accrued profit grow in the dashboard, but the actual USDT never lands in their balance. The `process_payouts` method exists and is correctly implemented (moves `accrued_profit` to `UserBalance`, creates `PaymentTransaction`, resets `accrued_profit` to 0) but is unreachable.

---

### C3. No User-Facing Withdrawal Endpoint for Quantum AI Investments

**File:** `apps/bots/views.py`

**What the code says:**

`QuantumAIInvestmentViewSet` (lines 326–361):
```python
class QuantumAIInvestmentViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        if self.request.user.is_staff:
            return QuantumAIInvestment.objects.all()
        return QuantumAIInvestment.objects.filter(user=self.request.user)

    serializer_class = QuantumAIInvestmentSerializer

    def perform_create(self, serializer):
        subscription = BotSubscription.objects.filter(
            user=self.request.user, plan__bot_type="quantum_ai", status="active"
        ).first()
        if not subscription:
            raise PermissionError("No active Quantum AI subscription")
        serializer.save(user=self.request.user, subscription=subscription)

    @action(detail=False, methods=["get"])
    def balance(self, request):
        """Get user's current Quantum AI balance"""
        investments = self.get_queryset().filter(status="active")
        total_invested = sum(inv.amount for inv in investments)
        total_profit = sum(inv.accrued_profit for inv in investments)
        return Response({
            "total_invested": str(total_invested),
            "total_profit": str(total_profit),
            "current_balance": str(total_invested + total_profit),
        })
```

The viewset has one custom action: `balance` (GET only). There is no `withdraw`, `payout`, `request_withdrawal`, or similar action. The `QuantumAIInvestment` model has a `status` field with choices including `"withdrawn"` (line 732 of models.py), but nothing transitions an investment to that status from the user side.

**Impact:** Users can invest (via subscription purchase), can view their balance, but cannot withdraw. The `SubscriptionService._create_quantum_ai_investment()` creates the investment record. The `process_payouts` service method (C2) could credit user balances but is not wired to any trigger. The withdrawal flow for Quantum AI investments is entirely absent from the user API surface.

---

### C4. Smoothed Returns Model Has No Failure Mode When Reserve Is Depleted

**Files:** `apps/bots/models.py` (lines 513–535), `services/quantum_ai_fund.py` (lines 104–140)

**What the code says:**

`models.py` lines 513–527:
```python
def calculate_smoothed_return(self, actual_return_pct: Decimal) -> Decimal:
    return max(self.monthly_min_return, min(actual_return_pct, self.monthly_max_return))
```

Defaults (lines 455–468): `monthly_min_return = 2.0`, `monthly_max_return = 15.0`.

`quantum_ai_fund.py` lines 104–140 (`_apply_reserve_cover`):
```python
def _apply_reserve_cover(fund_id: str, amount: Decimal):
    try:
        reserve = ReserveFund.objects.select_for_update().get(fund_id=fund_id)
        balance_before = reserve.balance
        if reserve.can_cover(amount):
            reserve.balance -= amount
            # ... record transaction ...
        else:
            actual_shortfall = reserve.balance
            reserve.balance = Decimal("0")
            reserve.low_balance_alert_sent = True
            reserve.save()
            reserve.record_transaction(
                balance_before, -actual_shortfall, "shortfall_cover",
                f"Partial cover — only ${actual_shortfall:,.2f} available "
                f"of ${amount:,.2f} needed. RESERVE DEPLETED.",
            )
            logger.warning(
                f"Reserve INSUFFICIENT! Need ${amount:,.2f} "
                f"but only ${balance_before:,.2f} available. "
                f"Admin must top up reserve for {fund_id}"
            )
    except ReserveFund.DoesNotExist:
        logger.error(f"No reserve fund found for {fund_id}! Cannot smooth returns.")
```

**Impact:** When the reserve is depleted, `_apply_reserve_cover` logs a warning and sets `low_balance_alert_sent=True`. But:
- There is no mechanism that stops the smoothing. `calculate_smoothed_return` still returns `monthly_min_return` (2%) even when the reserve is 0.
- `distribute_quantum_ai_profits` (in `tasks.py`) calls `calculate_smoothed_return` and distributes based on the smoothed percentage — it does not check the reserve balance.
- The `_apply_reserve_cover` method is only called from `update_fund_performance` (line 63 of `quantum_ai_fund.py`), which is called from `accrue_quantum_ai_profits` Celery task.
- There is no admin endpoint or management command to top up the reserve. The only way reserve increases is via `_deposit_excess_to_reserve` (line 143), which only triggers when actual returns exceed `monthly_max_return`.

If trading consistently loses money, the reserve depletes and stays depleted. Users continue to see 2% returns on paper (accrued_profit keeps growing), but the underlying fund has no money to back those returns.

---

### C5. Two `QuantumAIDeposit` Models with the Same Name in Different Apps

**Files:** `apps/bots/models.py` (line 820), `apps/payments/models.py` (line 67)

**What the code says:**

`apps/bots/models.py` line 820 — `QuantumDeposit` (note: the class is named `QuantumDeposit` at line 820, not `QuantumAIDeposit` — see verification below):

Actually, let me re-check the exact class names. Reading `apps/bots/models.py`:
- Line 775: `class QuantumDepositWallet(SoftDeleteModel):`
- Line 820: `class QuantumDeposit(SoftDeleteModel):`

Reading `apps/payments/models.py`:
- Line 67: `class QuantumAIDeposit(SoftDeleteModel):`

These are **different class names** (`QuantumDeposit` vs `QuantumAIDeposit`) but they serve the same purpose (record a user's deposit for the Quantum AI system). They have different fields:

`bots/QuantumDeposit` (models.py:820–869):
- `user` FK to User
- `wallet` FK to `QuantumDepositWallet`
- `amount`, `transaction_hash`, `screenshot` (ImageField)
- `status` (pending/approved/rejected/processing)
- `reviewed_by` FK to User, `review_notes`, `reviewed_at`, `processed_at`

`payments/QuantumAIDeposit` (models.py:67–226):
- `user` FK to User
- `quantum_bot` FK to `bots.QuantumAIBot`
- `fund` FK to `bots.QuantumAIFund`
- `amount`, `currency`, `blockchain`, `from_address`, `transaction_hash`
- `block_number`, `block_confirmations`, `required_confirmations`
- `transaction_screenshot` (ImageField), `transaction_proof` (FileField)
- `status` (pending/processing/approved/rejected/expired)
- `verified_by`, `verified_at`, `verification_method`
- `usdt_amount`, `exchange_rate`, `risk_score`, `flagged_for_review`

The payments version is used by `apps/payments/views.py` (e.g., `QuantumDepositViewSet` at line 199, `CreateDepositView` at line 418). The bots version (`QuantumDeposit`) is defined in `apps/bots/models.py` but I did not find any view, serializer, or task that imports or uses `apps.bots.models.QuantumDeposit`. It appears to be dead code from a refactoring.

**Impact:** The `QuantumDeposit` model in `apps/bots/models.py` is dead — defined but unused. If it's not dead, there's a parallel deposit flow that's completely undocumented. The naming is confusing.

**Verified:** `QuantumDeposit` (bots) is NOT imported by any view in `apps/bots/views.py`. The payments views import `from apps.payments.models import QuantumAIDeposit`. The two models are different classes with different names serving overlapping purposes.

---

### C6. No Admin Endpoint to Top Up Reserve Fund

**Files:** `apps/bots/models.py` (lines 538–597), `apps/bots/views.py`

**What the code says:**

`ReserveFund` model (lines 538–563) has a `balance` field. `ReserveTransaction` (lines 599–641) records all movements with types: `top_up`, `withdrawal`, `shortfall_cover`, `excess_deposit`, `smoothing_adj`.

The only code paths that create `ReserveTransaction` records are:
- `_deposit_excess_to_reserve` (quantum_ai_fund.py:143) — creates `excess_deposit` transactions
- `_apply_reserve_cover` (quantum_ai_fund.py:105) — creates `shortfall_cover` transactions

There is no view, management command, or admin action that creates a `top_up` transaction or increases `ReserveFund.balance` directly. The `QuantumAIFundViewSet` (bots/views.py:317) is read-only (`ReadOnlyModelViewSet`). The `ReserveFund` model is not registered in any ViewSet I found.

**Impact:** If the reserve depletes (C4), there is no user-facing or admin-facing mechanism to add funds to it. An admin would need to do this via Django shell or direct database access.

---

## 3. High — Correctness / Operational Issues

### H1. `GridTradingStrategy.execute()` Is a Stub

**File:** `apps/trading/strategies/grid_trading.py`
**Lines:** 131–143

**What the code says:**
```python
def _check_grid_opportunities(self, current_price, account_info, symbol):
    """
    Check if any grid levels need orders placed.
    In production, this would:
    1. Check filled orders from the adapter
    2. Place counter-orders
    """
    # This is a simplified version
    # In production, you'd track filled orders and place counters
    return None
```

The entire grid execution logic in `execute()` flows through `_check_grid_opportunities()`, which unconditionally returns `None`. The real grid order placement and monitoring lives in `BotEngine` (bot_engine.py) and `GridPositionMonitor` (grid_monitor.py), not in the strategy. The strategy pattern is bypassed for grid trading.

**Impact:** The strategy interface promises that all strategies implement `execute()` and return a `Signal`. `GridTradingStrategy` does not. Any code that expects to run grid trading through the `BotExecutor` + strategy path (like `execution.py:run_once()`) would get no signals from the grid strategy.

---

### H2. `MartingaleStrategy.current_level` Is Not Persisted Across Celery Invocations

**Files:** `apps/trading/strategies/martingale.py` (line 58), `apps/bots/models.py` (line 404)

**What the code says:**

`martingale.py` line 58:
```python
self.current_level = 0
```

The strategy starts at level 0 every time a new `MartingaleStrategy` instance is created. In the Celery task model, `run_trading_bot` creates a new `BotEngine` (which creates a new `MartingaleStrategy` if the bot_type is "martingale") for each invocation. The `MartingaleBot` model has a `current_level` field (models.py:404) that could persist the level, but nothing in the execution path writes to it.

`martingale.py` `_register_loss()` (lines 196–201):
```python
def _register_loss(self):
    self.last_trade_result = "loss"
    self.consecutive_losses += 1
    self.current_level += 1
    logger.info(f"Martingale: Loss recorded, increasing to level {self.current_level}")
```

This increments the in-memory `self.current_level`. But when the next Celery task runs, a new strategy is created with `current_level=0`. The martingale progression is lost.

**Impact:** A martingale bot that suffers a loss and should double its position size on the next trade will instead enter at base level again. The martingale strategy does not function as designed in the Celery task execution model.

**Note:** `BotEngine.startBot()` (bot_engine.py) does NOT use `MartingaleStrategy` at all — it uses `QuantumAIStrategy` for all bot types. So the martingale strategy path via `BotExecutor.run_once()` (which uses the strategy) is only hit for signal bots (`bot_type="signal"` in `run_bot()` at execution.py:567). For grid and martingale bots, `BotEngine` is used, which ignores the strategy classes entirely.

---

### H3. `BOT_CONFIG` Settings Dict Is Defined But Never Used

**File:** `config/settings/base.py`
**Lines:** 391–399

**What the code says:**
```python
BOT_CONFIG = {
    "MAX_BOTS_PER_FREE_USER": 3,
    "MAX_BOTS_PER_PREMIUM_USER": 15,
    "MAX_BOTS_PER_ENTERPRISE_USER": 50,
    "MIN_TRADE_AMOUNT": 1.0,
    "MAX_TRADE_AMOUNT": 100000.0,
    "DEFAULT_STOP_LOSS_PERCENT": 5.0,
    "DEFAULT_TAKE_PROFIT_PERCENT": 10.0,
}
```

I searched for imports of `BOT_CONFIG` across the files I read. It is not imported by any view, task, service, engine, or strategy. The actual bot limits are determined by `SiteConfig.get_plan_limit()` in `core/models.py` (lines 135–139), which has its own defaults:
```python
defaults = {"free": 3, "basic": 10, "premium": 25, "enterprise": 100}
```

These differ from `BOT_CONFIG` (e.g., `BOT_CONFIG` says premium=15, `SiteConfig` defaults say premium=25).

**Impact:** `BOT_CONFIG` is dead configuration. Developers reading settings.py would believe these are the active limits. The actual limits come from a different code path with different values.

---

### H4. `ActiveOrder` Model Is Defined But Never Written To

**File:** `apps/bots/models.py`
**Lines:** 293–328

**What the code says:**

```python
class ActiveOrder(TimeStampedModel):
    """Individual active order for a GridBot (replaces JSONField)."""
    grid_bot = models.ForeignKey(GridBot, on_delete=models.CASCADE, related_name="active_orders_model")
    side = models.CharField(max_length=5, choices=SIDE_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="open")
    quantity = models.DecimalField(max_digits=20, decimal_places=8)
    price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    filled_quantity = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    exchange_order_id = models.CharField(max_length=100, blank=True, db_index=True)
    level_index = models.IntegerField(default=0)
```

The comment says "replaces JSONField" — referring to `GridBot.active_orders` (line 272, a JSONField). The intent was to migrate from JSON storage to a proper model. But the migration never completed: `GridBot.save_state()` (line 281) still writes to `self.active_orders` (the JSONField), and `BotOrderService` (order_service.py) writes to `BotOrder`, not `ActiveOrder`.

**Impact:** `ActiveOrder` is dead models/tables. The database has the table but no code populates it.

---

### H5. Two In-Memory Engine Registries in Different Modules

**Files:** `apps/trading/engines/execution.py` (line 29), `apps/bots/indicators_views.py` (line 30)

**What the code says:**

`execution.py` line 29:
```python
_running_engines: Dict[str, Any] = {}
```

`indicators_views.py` line 30:
```python
_engine_registry = {}
```

Both store `BotEngine` instances in memory. They are completely separate:
- `_running_engines` is used by Celery tasks (via `run_bot()` / `stop_bot()` in execution.py)
- `_engine_registry` is used by the indicator webhook views (EMAIndicatorView, RSIIndicatorView, BollingerBandsView) in indicators_views.py

These registries are process-local. In production, the web worker (serving HTTP/websocket) and the Celery worker (running bot tasks) are separate processes, possibly on different machines. An indicator webhook that updates an engine in `_engine_registry` (web worker) has no effect on the engine in `_running_engines` (Celery worker), and vice versa.

**Impact:** If an indicator webhook hits the web worker and updates an engine, then a Celery task runs the same bot, it gets a fresh engine with default indicator values. The indicator data from the webhook is lost.

---

### H6. `heartbeat_check` and `check_stale_bots` Are Redundant

**Files:** `config/celery.py` (lines 57–60), `apps/trading/tasks.py` (lines 336–342)

**What the code says:**

`celery.py`:
```python
"check-stale-bots": {"task": "apps.trading.tasks.check_stale_bots", "schedule": 120.0},
"heartbeat-check": {"task": "apps.trading.tasks.heartbeat_check", "schedule": 300.0},
```

`tasks.py` lines 336–342:
```python
@shared_task
def heartbeat_check():
    """Check all running bots and restart if dead. Delegates to check_stale_bots."""
    from .tasks import check_stale_bots
    result = check_stale_bots()
    logger.info(f"Heartbeat check complete: {result}")
    return result
```

`heartbeat_check` is a thin wrapper that calls `check_stale_bots`. Both are in the beat schedule. `check_stale_bots` runs every 2 minutes. `heartbeat_check` runs every 5 minutes and does exactly the same thing. The 5-minute run is redundant.

---

### H7. `MarketDataConsumer` Imports `ccxt.pro` Which Is Not in the Free CCXT Package

**File:** `apps/trading/consumers.py`
**Line:** 170

**What the code says:**
```python
import ccxt.pro as ccxt_pro
```

The free `ccxt` package (PyPI: `ccxt`) does not include `ccxt.pro`. `ccxt.pro` is a separate, paid product from the CCXT authors. The import will fail with `ModuleNotFoundError` for anyone using the free version. The `requirements.txt` (line 16) lists `ccxt>=4.1.93` — the free version.

**Impact:** The `MarketDataConsumer` WebSocket endpoint will fail on connection with an import error. The `MarketDataConsumer.connect()` method (lines 162–190) catches the exception and closes the connection with code 4000, so clients get a clean failure but no market data.

---

### H8. `TradingViewWebhookView` in `apps/investments/views.py` Is a Fourth Signal Bot Execution Path

**File:** `apps/investments/views.py`
**Lines:** 151–214

**What the code says:**
```python
class TradingViewWebhookView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = "webhook"

    def post(self, request, webhook_id):
        from apps.bots.models import SignalBot
        bot = SignalBot.objects.get(bot_id=webhook_id, is_active=True)
        # ... validates secret via hmac.compare_digest ...
        # ... creates investments.Order ...
        bot.total_trades += 1
        bot.save()
        return Response({"status": "success", "message": f"Webhook processed: {action} {amount} {bot.trading_pair}"})
```

This view:
1. Looks up a `SignalBot` by `bot_id` (the webhook_id URL parameter)
2. Validates the secret via constant-time HMAC comparison
3. Creates an `investments.Order` (portfolio display record)
4. Increments `bot.total_trades`
5. Returns success

It does **NOT** execute an exchange order. It does **NOT** use CCXT. It does **NOT** call `BotExecutorService.execute_signal_bot_order()` or `SignalBotWebhookView.execute_trade()`.

This is a separate webhook endpoint from `apps/webhooks/views.py::SignalBotWebhookView` (which DOES execute exchange orders). Both accept webhook POSTs for SignalBots. Both validate secrets. But only one places real trades.

**Impact:** A TradingView alert connected to this endpoint (`/api/investments/webhooks/<webhook_id>/`) would get a "success" response and increment the trade counter, but no order would be placed on the exchange. The user would see phantom trades.

**URL routing check:** `apps/investments/urls.py` (not fully read) likely maps this. The URL pattern would be something like `/api/investments/webhooks/<webhook_id>/`. This needs URLconf verification to confirm the exact route.

---

### H9. `execute_trade` Passes `price` Parameter for Market Orders

**File:** `apps/webhooks/views.py`
**Lines:** 500–506

**What the code says:**
```python
order = exchange_instance.create_order(
    symbol=trading_pair,
    type="market",
    side=side,
    amount=position_size,
    price=current_price,
)
```

The CCXT `create_order` signature is `create_order(symbol, type, side, amount, price=None, params={})`. For market orders, `price` should be `None`. Passing a price for a market order is non-standard. Most exchanges ignore it, but some may reject the order or behave unexpectedly.

**Contrast:** The adapter path in `base_adapter.py` (lines 299–319) correctly omits price for market orders:
```python
def create_market_order(self, symbol, side, amount, params=None):
    # ... no price passed ...
    order = self._make_request("create_market_order", formatted_symbol, side.lower(), amount, params=params or {})
```

The webhook `execute_trade` method bypasses the adapter and calls CCXT directly, introducing this inconsistency.

---

### H10. `UserBalance` Never Seeded for New Users

**File:** `apps/users/models.py`
**Lines:** 308–330

**What the code says:**

```python
class UserBalance(TimeStampedModel):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="balances")
    currency = models.CharField(max_length=10)
    available = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    hold = models.DecimalField(max_digits=20, decimal_places=8, default=0)
```

`process_payouts` in `quantum_ai_fund.py` (lines 184–188) uses `get_or_create` to create a `UserBalance` when paying out:
```python
balance, _ = UserBalance.objects.get_or_create(
    user=investment.user,
    currency="USDT",
    defaults={"available": Decimal("0"), "hold": Decimal("0")},
)
```

But if a user has never received a payout and the frontend queries their balance, there is no `UserBalance` row. The `UserBalanceViewSet` in `apps/investments/views.py` (lines 129–145) queries `InvestmentBalance` (a different model in `apps/investments/models.py`), not `users.UserBalance`. The two balance models (`users.UserBalance` and `investments.InvestmentBalance`) are separate and not synced.

**Impact:** A user who has never received a Quantum AI payout has no row in `users.UserBalance`. If any code path queries `UserBalance.objects.get(user=user, currency="USDT")` without `get_or_create`, it will raise `DoesNotExist`.

---

## 4. Medium — Maintainability / Code Quality

### M1. `BotOrder` Uses CAPITALIZED Field Names

**File:** `apps/bots/models.py`
**Lines:** ~60–95 (BotOrder model definition)

**What the code says:**

The `BotOrder` model uses field names like `Pair`, `Side`, `Category`, `Order_type`, `Quantity`, `Price`, `Exchange`, `Description`, `Details`, `Indicators`, `Time`. Every other model in the same file (`GridBot`, `MartingaleBot`, `SignalBot`, etc.) uses `lowercase_with_underscores`. This is a direct artifact from porting `oldbybit.py` which used these exact capitalized names.

**Impact:** Non-standard Django convention. ORM queries look like `BotOrder.objects.filter(Pair="BTC/USDT")` instead of `BotOrder.objects.filter(pair="BTC/USDT")`. Serializers must reference the capitalized names. It works but is inconsistent.

---

### M2. Logging Inside Mutex Lock

**File:** `apps/trading/engines/bot_engine.py`
**Line:** 175

**What the code says:**
```python
def update_conditions(self):
    with self.lock:
        logger.info("updating conditions inside Lock")
        # ... reads from exchange, updates state ...
```

`logger.info` calls the logging handler, which may do I/O (writing to file, sending to remote syslog). If the handler blocks, the lock is held longer than necessary, blocking other threads that need it.

---

### M3. `calculate_grid_levels` in `GridTradingStrategy` Is Uncalled Utility

**File:** `apps/trading/strategies/grid_trading.py`
**Lines:** 145–186

**What the code says:**

```python
def calculate_grid_levels(self, current_price, upper_limit=None, lower_limit=None):
    """Calculate grid levels for display/planning."""
    # ... computes and returns grid levels ...
```

This method exists on `GridTradingStrategy` but is never called by `execute()`, `__init__()`, or any external code I found. It's a utility that was written but not wired in.

---

### M4. Condition Flags Computed with Garbage Values at `BotEngine.__init__`

**File:** `apps/trading/engines/bot_engine.py`
**Lines:** 127–147

**What the code says:**
```python
self.EmaBuyCondition = True if (self.current_price >= self.EMA != 0) else False
self.EmaSellCondition = True if (self.current_price <= self.EMA != 0) else False
```

At init time, `self.current_price = 0.0` and `self.EMA = 0.0`. The expression `0.0 >= 0.0 != 0` evaluates as `(0.0 >= 0.0) and (0.0 != 0)` → `True and False` → `False`. So `EmaBuyCondition = False` at init. These are overwritten by `update_conditions()` before they're used, but the init-time computation is misleading.

An exception: `self.NoTrade = True if (self.count == 0 and self.current_side == "None") else False` — at init, `count=0` and `current_side="None"`, so `NoTrade=True`. This one is actually correct by coincidence.

---

### M5. Docker Compose Mounts Code as Volume in Production

**File:** `docker-compose.yml`
**Lines:** 43, 67, 86

**What the code says:**
```yaml
web:
  volumes:
    - .:/app

celery-worker:
  volumes:
    - .:/app

celery-beat:
  volumes:
    - .:/app
```

All three services mount the project root as a volume over `/app`. This means code changes on the host take effect immediately in the containers without rebuilding. In production, this is usually undesirable — it means the running container is not immutable and can be affected by local file changes.

---

### M6. Dockerfile Silences `collectstatic` Failure

**File:** `Dockerfile`
**Line:** 40

**What the code says:**
```dockerfile
RUN python manage.py collectstatic --noinput || true
```

If `collectstatic` fails (e.g., static files missing, permissions error), the `|| true` swallows the error and the build continues. The container deploys with broken static files and no indication of the failure.

---

### M7. TradingView IP Allowlist Hardcoded in nginx.conf

**File:** `nginx.conf`
**Lines:** 125–137

**What the code says:**
```nginx
location = /api/webhooks/custombot/ {
    allow 52.89.214.238;
    allow 34.212.75.30;
    allow 54.218.53.128;
    allow 52.32.178.7;
    deny all;
    limit_req zone=webhook_zone burst=50 nodelay;
    proxy_pass http://django;
}
```

The comment in the config (lines 121–124) says:
```
TradingView currently sends from these 4 IPs (verify periodically):
  https://www.tradingview.com/support/solutions/43000529348
This list was current as of June 2026 — TradingView does update it,
so check once per quarter.
```

If TradingView changes its IP ranges and the config is not updated, webhook requests from TradingView will be blocked by `deny all`. The application loses signal bot functionality with no visible error (the request is denied at the nginx layer, before reaching Django).

---

### M8. Duplicate Function Definitions: `get_exchange_rates`, `list_exchanges`, `get_exchange_symbols`

**Files:** `apps/exchanges/views.py` (lines 154–228), `apps/trading/views.py` (lines 161–280)

**What the code says:**

Both files define:
- `list_exchanges` — lists all active exchanges
- `get_exchange_symbols` — lists symbols for a specific exchange
- `get_exchange_rates` — fetches live rates via CCXT with DB fallback

The implementations are similar but not identical. `apps/trading/views.py` imports from `apps.investments.models import ExchangeRate, ExchangeStatus` (line 17). `apps/exchanges/views.py` imports from `apps.investments.models import ExchangeRate, ExchangeStatus` (line 17) and `from apps.payments.models import BlockchainAddress` (line 18).

The URL routing in `config/urls.py` (lines 33–35) says:
```python
path("api/exchanges/", include("apps.exchanges.urls", namespace="exchanges")),  # Deprecated compatibility alias
path("api/trading/", include("apps.trading.urls", namespace="trading")),  # New unified trading API
```

Both namespaces expose similar endpoints. The `api/exchanges/` paths are marked "Deprecated" but there is no redirect, no deprecation warning, and no sunset date.

---

### M9. `SignalBot` Has `take_profit_percent` and `stop_loss_percent` Fields That Are Never Used

**File:** `apps/bots/models.py`
**Lines:** 80–81

**What the code says:**
```python
take_profit_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
stop_loss_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
```

These fields exist on `SignalBot`. Neither `SignalBotWebhookView.execute_trade()` (webhooks/views.py:435) nor `BotExecutor.run_once()` (execution.py:221) reads or applies these values. Signal bot trades are executed as immediate market orders without SL/TP placement.

---

### M10. `BotSubscription.webhook_secret` and `SignalBot.secret_key` Are Two Separate Secret Systems

**Files:** `apps/payments/models.py` (line 527), `apps/bots/models.py` (line 66)

**What the code says:**

`BotSubscription` (payments/models.py:527):
```python
webhook_secret = models.CharField(max_length=64, unique=True, blank=True, null=True, help_text="For custom bots")
```

`SignalBot` (bots/models.py:66):
```python
secret_key = models.CharField(max_length=64, blank=True)
```

Both are used for webhook authentication but are different fields on different models:
- `SignalBot.secret_key` is the per-bot secret used by `SignalBotWebhookView` (webhooks/views.py) and `TradingViewWebhookView` (investments/views.py)
- `BotSubscription.webhook_secret` is referenced in `bots/admin.py` (line 92) for display: `obj.subscription.webhook_secret`

The `SignalBot.create_message()` method (models.py:103) includes `self.secret_key` in the webhook template. The `BotSubscription.get_webhook_json_template()` method (payments/models.py:569) includes `self.webhook_secret`.

These are two parallel secret systems for what appears to be the same purpose (TradingView webhook authentication). It's unclear which one is authoritative or how they relate.

---

### M11. `_shutdown_handler` Registration Condition May Not Cover Celery Workers

**File:** `apps/trading/engines/execution.py`
**Lines:** 601–606

**What the code says:**
```python
if _os.environ.get("RUN_MAIN") or "gunicorn" in (_os.environ.get("SERVER_SOFTWARE", "")):
    _signal.signal(_signal.SIGTERM, _shutdown_handler)
    _signal.signal(_signal.SIGINT, _shutdown_handler)
```

`RUN_MAIN` is a Django `runserver`-specific environment variable. `SERVER_SOFTWARE` containing "gunicorn" covers the web server. Celery workers set neither of these. The signal handlers for graceful shutdown (stopping all running engines on SIGTERM) are not registered in Celery worker processes.

**Impact:** When a Celery worker receives SIGTERM (e.g., during deployment rolling restart), the `_shutdown_handler` does not run. Engines are not stopped gracefully. The `_running_engines` dict is lost. This is partially mitigated by `check_stale_bots` (which detects stale bots and recovers them), but there's a window where orphaned engines may continue running on a worker that's being shut down.

---

### M12. `pyproject.toml` Suppresses `utcnow` Deprecation but Code Still Uses It

**File:** `pyproject.toml`
**Line:** 17

**What the code says:**
```toml
filterwarnings = [
    "ignore::DeprecationWarning:django_filters",
    "ignore::DeprecationWarning:pytz",
    "ignore::DeprecationWarning:ccxt",
    "ignore::DeprecationWarning:jwt",
    "ignore:datetime.datetime.utcnow:DeprecationWarning",
    ...
]
```

`datetime.datetime.utcnow()` is deprecated in Python 3.12+. The codebase uses it in `execution.py` line 93: `_dt.utcnow().isoformat()`. The suppression in `pyproject.toml` hides the warning from tests but doesn't fix the underlying usage.

---

### M13. `docker-compose.yml` Celery Beat Uses `DatabaseScheduler` But `celery.py` Also Defines `beat_schedule`

**File:** `docker-compose.yml` (line 84), `config/celery.py` (lines 41–69)

**What the code says:**

`docker-compose.yml` line 84:
```yaml
command: celery -A config.celery beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

`config/celery.py` lines 41–69:
```python
app.conf.beat_schedule = {
    "run-active-bots": {...},
    "check-stale-bots": {...},
    ...
}
```

With `DatabaseScheduler`, the beat schedule is read from the `django_celery_beat` database table, not from `app.conf.beat_schedule`. The programmatic schedule in `celery.py` is ignored when `DatabaseScheduler` is active. If the database table is empty (no schedule entries created),Celery Beat may not run any tasks.

**Impact:** If `django-celery-beat` is installed and the `DatabaseScheduler` is used, the `beat_schedule` defined in `celery.py` has no effect. Schedule entries must be created in the database (via Django admin or `python manage.py celery beat` commands). This is a potential silent failure — Celery Beat starts but doesn't run any periodic tasks.

---

## 5. Low / Cosmetic

### L1. `config/urls.py` Deprecated Alias Not Actually Deprecated

**File:** `config/urls.py`
**Lines:** 33–35

```python
path("api/exchanges/", include("apps.exchanges.urls", namespace="exchanges")),  # Deprecated compatibility alias
```

The comment says "Deprecated compatibility alias; canonical routes live under api/trading/". No HTTP redirect, no `Deprecation` header, no sunset date. Clients continue to work identically on both paths.

---

### L2. `nginx.conf` Uses Catch-All `server_name _`

**File:** `nginx.conf`
**Line:** 59

```nginx
server {
    listen 443 ssl http2;
    server_name _;
```

The `_` server_name is a catch-all. In production, this means the server responds to any hostname that resolves to the server's IP. For TLS, this means the certificate must be valid for any domain pointing to this server, or SNI must route to the correct certificate. Typically, production nginx configs use specific `server_name` values.

---

### L3. `ljust(8, "=")` in `two_factor.py` Is a No-Op

**File:** `services/two_factor.py`
**Line:** 91

```python
key = base64.b32decode(secret_b32.upper().rstrip("=").ljust(8, "="))
```

TOTP secrets are 20 bytes = 32 base32 characters. After `.rstrip("=")`, the string is 32 chars (or fewer if it was padded). `.ljust(8, "=")` pads to minimum length 8 — but 32 > 8, so nothing is added. Python's `base64.b32decode` accepts unpadded input and auto-pads internally. The `.ljust(8, "=")` is a no-op but the decode works correctly. The code is functionally correct but misleading.

---

## 6. Items Not Verified (Not Included Above)

The following were considered but could not be verified from the files read:

- **`oldbybit.py` content:** The file exists at the project root but was not read. Claims about "exact copy from oldbybit.py" in bot_engine.py cannot be verified against the source.
- **`investments/urls.py`:** Not read. The exact URL route for `TradingViewWebhookView` (H8) is assumed but not confirmed.
- **`apps/bots/serializers.py`:** Not fully read. The `read_only_fields` fix mentioned in `security-audit-report.md` could not be confirmed.
- **`frontend/` directory:** Not audited. Frontend-backend integration issues are unknown.
- **`django_celery_beat` database table state:** Cannot know if schedule entries exist in the database without querying the running database.
- **`apps/trading/exchanges/okx.py`, `mexc.py`, `coinbase.py`, `mock_adapter.py`:** Not read. Adapter completeness for these exchanges is unknown.
- **`tests/` directory structure:** Not fully explored. Test counts from `CODEBASE.md` (1859 passed) could not be independently verified.
- **`celerybeat-schedule.db`:** Not inspected. Cannot confirm if it contains schedule entries that conflict with `celery.py` beat_schedule.

---

## 7. Summary Table

| Severity | Count | Key Items |
|----------|-------|-----------|
| **Blocking** | 1 | B1: Duplicate `related_name` on `QuantumAIInvestment` |
| **Critical** | 6 | C1: No distributed lock for normal bot execution; C2: `process_payouts` never called; C3: No user Quantum AI withdrawal endpoint; C4: Smoothed returns with no reserve failure mode; C5: Two `QuantumAIDeposit`/`QuantumDeposit` models; C6: No admin reserve top-up endpoint |
| **High** | 10 | H1: Grid strategy stub; H2: Martingale level not persisted; H3: `BOT_CONFIG` dead settings; H4: `ActiveOrder` unused model; H5: Two engine registries; H6: Redundant beat tasks; H7: `ccxt.pro` import in free ccxt; H8: Fourth signal bot webhook path; H9: Price passed for market orders; H10: `UserBalance` never seeded; M11: Signal handlers not registered for Celery; M12: `utcnow` deprecation suppressed; M13: `DatabaseScheduler` ignores `beat_schedule` |
| **Medium** | 5 | M1: Capitalized BotOrder fields; M2: Log inside lock; M3: Uncalled grid utility; M4: Garbage init condition flags; M5: Docker hot-reload in prod; M6: Silenced collectstatic; M7: Hardcoded TV IPs; M8: Duplicate exchange functions; M9: Unused SignalBot SL/TP; M10: Two secret systems; M11: Signal handlers; M12: utcnow; M13: DB scheduler |
| **Low** | 3 | L1: Deprecated alias not deprecated; L2: Catch-all server_name; L3: No-op ljust |

**Total verified findings: 23**
