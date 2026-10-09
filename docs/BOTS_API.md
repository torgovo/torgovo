# Bots API — `/api/bots/` (apps/bots)

> **Code-verified reference.** Sources: `apps/bots/urls.py`, `apps/bots/views.py`,
> `apps/bots/serializers.py`, `apps/bots/models.py`, `apps/bots/indicators_views.py`,
> `core/exceptions.py`, `core/pagination.py`, `core/models.py`,
> `config/settings/base.py`. Verified against installed DRF/django-filter behavior
> on 2026-10-02, and re-verified 2026-10-03 with a DB-free serializer field dump
> (all 9 bot serializers: `read_only` / `write_only` / `required` / choices) plus
> executed viewset + exception-handler probes (§2B, §3, §5 start/stop). This file
> supersedes the "Bot Management" section of `docs/archive/API.md` (archived
> 2026-10-07) for the `/api/bots/` prefix.

---

## 1. Global rules (apply to every DRF endpoint in this app)

| Aspect | Behavior | Source |
|---|---|---|
| Mount | `path("api/bots/", include("apps.bots.urls"))` (namespace `bots`) | `config/urls.py:37` |
| Auth | `JWTAuthentication` (Bearer `access` token) then `SessionAuthentication` | `settings/base.py:191-194` |
| Permission (default) | `IsAuthenticated` — all routers views except `quantum-funds` | `base.py:195` + per-viewset |
| Permission (override) | `quantum-funds` → `IsAdminUser` (requires `is_staff`) | `views.py:305` |
| Row scoping | Every viewset: `is_staff` → all rows, otherwise `user=request.user` | `get_queryset()` in each viewset |
| Throttling | `AnonRateThrottle` 100/h, `UserRateThrottle` 1000/h, `ScopedRateThrottle` (never fires here — no bots view sets `throttle_scope`). 429 → error envelope `code=RATE_LIMIT_EXCEEDED` | `base.py:205-214` |
| Pagination | `StandardResultsSetPagination`: 20/page (`?page=`, `?page_size=` up to 100). Envelope: `{"count", "next", "previous", "results"}`. Applies to the **8 list endpoints only** — not to actions (`start/stop/toggle_active/balance/recent`) or detail reads | `core/pagination.py:9-26` |
| Ordering | `?ordering=<field>` works on list endpoints (allowed fields = serializer fields, `-` prefix for descending) | `base.py:196-199`, DRF `OrderingFilter` default |
| Search/filter | **Not available**: no bots viewset declares `search_fields` / `filterset_class` / `filterset_fields`, so `?search=` and django-filter params are ignored | `views.py` (verified by grep) |
| DELETE | Soft-delete: `SoftDeleteModel.delete()` sets `is_deleted`/`deleted_at`; default manager `SoftDeleteManager` filters `is_deleted=False`, so the row disappears from subsequent list/retrieve (404). Restore only via `hard_delete`/`restore` at DB level | `core/models.py:46-93` |
| Unknown body keys | Silently ignored by DRF (e.g. sending `level_spacing_percent` to `POST grid-bots/` has no effect — it is not in `GridBotCreateSerializer`) | DRF default |

---

## 2. Error contract

There are **three distinct response shapes**. Only shape A goes through the custom
exception handler; B and C are returned directly by view code.

### A) Exception envelope — `core.exceptions.custom_exception_handler`

Produced for every exception DRF (or the handler) converts to a response:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Validation failed. Please check your input.",
    "details": {"trading_pair": ["This field is required."]},
    "field_errors": {"trading_pair": ["This field is required."]}
  },
  "timestamp": "2026-10-02T12:00:00.123456+00:00"
}
```

- `field_errors` present **only** when `exc.detail` is a dict (field-keyed).
- `details` is the raw DRF `detail` (dict/list/string) or `null`.
- With `DEBUG=True` a `debug` object (method, path, view class, exception type,
  traceback) is appended. Never present in production.
- `message` resolution (`get_error_message`):
  1. `detail` is a string → that string;
  2. dict containing `non_field_errors` → its first entry (e.g. the
     "You already have a Grid Bot for this subscription…" text);
  3. list → first entry;
  4. other dict → generic `"Validation failed. Please check your input."`
     (per-field text lives in `field_errors`);
  5. `Http404` → `"The requested resource was not found."`;
  6. fallback: `DEBUG` → `str(exc)`, else generic
     `"An internal server error occurred. Please try again later."`.
     Note: builtin `PermissionError` and the whole `TradingBotException` family
     have no `.detail`, so they always land here — their own text
     (`"No active Grid Bot subscription"`, `"Minimum deposit is …"`) is only
     returned when `DEBUG=True`.

**Code / status map** (`get_error_code` + `get_status_code`, keyed by exception
class name; custom exceptions prefer their own `error_code`/`status_code`
attributes):

| Exception | code | HTTP |
|---|---|---|
| `NotAuthenticated` | `AUTHENTICATION_REQUIRED` | 401 |
| `AuthenticationFailed` | `AUTHENTICATION_FAILED` | 401 |
| `PermissionDenied` (DRF) | `PERMISSION_DENIED` | 403 |
| `PermissionError` (builtin — subscription gate) | `PERMISSION_DENIED` | 403 |
| `ValidationError` (DRF), `ParseError` | `VALIDATION_ERROR`, `PARSE_ERROR` | 400 |
| `NotFound`, `Http404` | `RESOURCE_NOT_FOUND` | 404 |
| `MethodNotAllowed` | `METHOD_NOT_ALLOWED` | 405 |
| `Throttled` | `RATE_LIMIT_EXCEEDED` | 429 |
| anything else / unhandled | `INTERNAL_SERVER_ERROR` | 500 |
| `TradingBotException` family | `TRADING_BOT_ERROR`, `EXCHANGE_API_ERROR` (503), `INSUFFICIENT_BALANCE` (402), `INVALID_ORDER` (400), `BOT_LIMIT_EXCEEDED` (429), `DEPOSIT_ERROR` (400), `WEBHOOK_ERROR` (400) | per class |

**Production caveat — subscription gate.** `perform_create` raises builtin
`PermissionError("No active Grid Bot subscription")` etc. The handler maps it to
403 + `code=PERMISSION_DENIED`, but the message passes through the fallback
(PermissionError has no `.detail`): with `DEBUG=False` the client sees the
generic *"An internal server error occurred. Please try again later."* — the
subscription text is only visible with `DEBUG=True` (and in logs).
`details` is `null` for this case.

### B) Flat `{"error": "..."}` — returned directly by views (bypasses the handler)

| Endpoint | Status | Body |
|---|---|---|
| `toggle_active`, `start`, `stop` — caller is not owner and not staff | 403 | `{"error": "Permission denied"}` |
| `start` — bot has no active subscription | 400 | `{"error": "No active subscription"}` |
| `start` / `stop` — executor raised | 500 | `{"error": "Failed to start bot"}` / `{"error": "Failed to stop bot"}` |

Success counterparts are also flat: `{"success": true, "message": "..."}`.

### C) Webhook shape — indicator endpoints (plain Django views)

`{"status": "success" | "error", "message": "..."}` (+ indicator values on
success). See §12. Unhandled exceptions inside these views are caught and
returned as 500 `{"status":"error","message":"Internal server error"}`.

---

## 3. Route index

`DefaultRouter` (also serves `GET /api/bots/` API root). `{pk}` is the row UUID.

| Method | Path | Notes |
|---|---|---|
| GET/POST | `/api/bots/signal-bots/` | list / create |
| GET/PUT/PATCH/DELETE | `/api/bots/signal-bots/{pk}/` | CRUD (DELETE = soft) |
| POST | `/api/bots/signal-bots/{pk}/toggle_active/` | `@action(detail=True)` |
| GET/POST | `/api/bots/grid-bots/` | list / create |
| GET/PUT/PATCH/DELETE | `/api/bots/grid-bots/{pk}/` | CRUD |
| POST | `/api/bots/grid-bots/{pk}/start/` | executor start |
| POST | `/api/bots/grid-bots/{pk}/stop/` | executor stop |
| GET/POST | `/api/bots/martingale-bots/` | list / create |
| GET/PUT/PATCH/DELETE | `/api/bots/martingale-bots/{pk}/` | CRUD |
| POST | `/api/bots/martingale-bots/{pk}/start/` | executor start |
| POST | `/api/bots/martingale-bots/{pk}/stop/` | executor stop |
| GET | `/api/bots/quantum-funds/`, `/api/bots/quantum-funds/{pk}/` | **read-only, staff only** |
| GET/POST | `/api/bots/quantum-investments/` | list / create |
| GET/PUT/PATCH/DELETE | `/api/bots/quantum-investments/{pk}/` | CRUD |
| GET | `/api/bots/quantum-investments/balance/` | totals (unpaginated) |
| GET/POST | `/api/bots/pair-configs/` | list / create |
| GET/PUT/PATCH/DELETE | `/api/bots/pair-configs/{pk}/` | CRUD |
| GET | `/api/bots/orders/`, `/api/bots/orders/{pk}/` | read-only history |
| GET | `/api/bots/orders/recent/` | latest 50 (unpaginated) |
| GET/POST | `/api/bots/indicators/` | Indicator rows CRUD |
| GET/PUT/PATCH/DELETE | `/api/bots/indicators/{pk}/` | |
| POST | `/api/bots/indicators/ema/` | TradingView webhook (§12) |
| POST | `/api/bots/indicators/rsi/` | TradingView webhook (§12) |
| POST | `/api/bots/indicators/bb/` | TradingView webhook (§12) |

**Legacy alias routes (declared but broken — do not use):**
`POST /api/bots/grid/{bot_id}/start|stop/` and
`POST /api/bots/martingale/{bot_id}/start|stop/` (`urls.py:34-53`) pass the URL
kwarg `bot_id` into a handler whose signature is `start(self, request, pk=None)`.
DRF binds URL kwargs positionally at dispatch time, so the call fails **before
`get_object` ever runs**: `TypeError: GridBotViewSet.start() got an unexpected
keyword argument 'bot_id'`. DRF logs `ERROR API Exception: TypeError`,
`custom_exception_handler` returns `None` (TypeError is not mapped), and
`handle_exception` re-raises → Django serves a **non-JSON HTTP 500** (debug
traceback page when `DEBUG=True`, plain 500 in production) — i.e. outside the
three shapes in §2. No tests and no in-repo consumers use them. Use the router
routes above.

---

## 4. `signal-bots` — SignalBotViewSet

- Permissions: `IsAuthenticated`; queryset scoped to owner (staff: all).
- **Create (`POST`)** uses `SignalBotCreateSerializer`:

```json
{
  "bot_name": "My EMA Bot",
  "exchange_name": "bybit",
  "market_type": "spot",
  "trading_pair": "BTC/USDT",
  "default_amount": "10",
  "take_profit_percent": "1.5",
  "stop_loss_percent": "1"
}
```

  - `exchange_name` must be one of the model choices (lowercase): `binance`,
    `bybit`, `okx`, `mexc`, `alpaca`, `coinbase`. Uppercase input fails the
    ChoiceField validation before the custom `validate_exchange_name` runs.
  - `market_type`: `spot` (default) | `futures`.
  - `trading_pair` must contain `/`; `validate_trading_pair` upper-cases it.
  - `webhook_url`, `bot_id` are read-only; `user` is hidden (write-only, so it
    never appears in responses).
  - **Gate:** active `BotSubscription` with `plan__bot_type="custom"` → else
    `PermissionError` → 403 `PERMISSION_DENIED` (message only visible when
    `DEBUG=True`, see §2).
  - Side effects: `SignalBot.save()` auto-generates
    `bot_id` (`xxxxx-xxxxx-xxxxx`), `webhook_url = {SITE_URL}/api/webhooks/custombot/`,
    `secret_key`, `webhook_message` template; `generate_webhook_credentials()`
    then no-ops (only fills empty values).
  - **201 body = create serializer output**, exactly:
    `bot_name, exchange_name, market_type, trading_pair, default_amount,
    take_profit_percent, stop_loss_percent, webhook_url, bot_id`.
    Note the asymmetries: `is_active` and `secret_key` are **not** returned on
    create (they appear on subsequent reads), and `bot_id` is **only** returned
    on create (reads use `id`).
- **Read (list/retrieve)** uses `SignalBotSerializer` — includes `secret_key`,
  `is_active`, `signals_used_this_month`, `signal_limit`, `last_triggered`,
  `total_trades`, `successful_trades`, `total_profit_loss`, `success_rate`
  (computed), `last_error`, `subscription` (id), timestamps — but **not**
  `bot_id` or `webhook_message`.
- Update (PUT/PATCH) via `SignalBotSerializer`: writable = `bot_name`,
  `exchange_name`, `market_type`, `trading_pair`, `default_amount`,
  `take_profit_percent`, `stop_loss_percent`, `is_active`, and — because they
  are **not** in `read_only_fields` — also `signals_used_this_month` and
  `signal_limit` (a client can PATCH its own usage counter / quota; treat as a
  known gap). Read-only: `id, webhook_url, secret_key, last_triggered,
  total_trades, successful_trades, total_profit_loss, created_at, updated_at,
  success_rate, last_error, subscription`. No subscription gate on update.
- `POST {pk}/toggle_active/` → flips `is_active`; owner or staff; success:
  `{"success": true, "is_active": bool, "message": "Bot <name> is now active|inactive"}`;
  non-owner non-staff → flat 403 `{"error": "Permission denied"}`.
- There are **no** `start` / `stop` / `get-signals` / `orders` sub-routes
  (the old `API.md` listed them — removed).

## 5. `grid-bots` — GridBotViewSet

- Permissions/scoping: `IsAuthenticated`, owner-scoped.
- **Create** uses `GridBotCreateSerializer`, writable fields:
  `bot_name, exchange_name, trading_pair, initial_amount, base_amount,
  favor_levels, against_levels, favor_level_qty, against_level_qty,
  favor_level_difference, against_level_difference, amount_type,
  take_profit_percent, stop_loss_percent`.
  - `favor_levels` / `against_levels`: enforced 1–50 (model
    `MinValueValidator(1)` / `MaxValueValidator(50)` are carried into the
    serializer fields).
  - `level_spacing_percent` is **not** writable here (model default `1.0`);
    it *is* writable via PUT/PATCH on `GridBotSerializer`.
  - `exchange_name` choices: `binance, bybit, okx, mexc, alpaca, coinbase`.
  - **Gate 1:** active subscription `plan__bot_type="grid"` → else 403
    (generic message in production).
  - **Gate 2:** one bot per subscription — model `unique_together =
    ["subscription"]` + explicit pre-check → DRF `ValidationError`
    (400, `VALIDATION_ERROR`) with message *"You already have a Grid Bot for
    this subscription. You can update the existing bot's settings instead."*
    (surfaces in `message` via `non_field_errors`).
  - **201 body does NOT contain `id`** (create serializer omits it; `user` is
    hidden). Re-list the collection to obtain the id.
- **Read/update** via `GridBotSerializer`: adds `level_spacing_percent`,
  `is_running`, `started_at`, `stopped_at`, `current_profit_loss`,
  `total_invested`, `total_trades_executed` (computed/read-only),
  `subscription` (read-only), timestamps. No subscription gate on update.
- **`POST {pk}/start/`** (owner/staff): flat 403 if not owner; flat 400
  `{"error": "No active subscription"}` if `subscription` missing/inactive;
  then `services.bot_executor.BotExecutorService.start_grid_bot(user, id)` →
  `{"success": true, "message": "Grid bot started"}`; any executor exception →
  flat 500 `{"error": "Failed to start bot"}`.
- **`POST {pk}/stop/`**: same ownership check, **no** subscription check →
  `BotExecutorService.stop_grid_bot` → `{"success": true, "message": "Grid bot stopped"}`;
  exception → flat 500 `{"error": "Failed to stop bot"}`.

## 6. `martingale-bots` — MartingaleBotViewSet

Identical pattern to §5 with these differences:

- Create adds writable `multiplier_factor`; read adds read-only
  `current_level`, `max_level_reached`, `last_execution_price`.
- Subscription must be `plan__bot_type="martingale"`; duplicate message
  *"You already have a Martingale Bot for this subscription…"*.
- Start/stop call `BotExecutorService.start_martingale_bot` /
  `stop_martingale_bot`; success messages say "Martingale bot started/stopped".

## 7. `quantum-funds` — QuantumAIFundViewSet (admin)

- `ReadOnlyModelViewSet` + `permission_classes = [IsAdminUser]` →
  list + retrieve only; unauthenticated → 401, authenticated non-staff → 403
  (`"You do not have permission to perform this action."`).
- Serializer fields: `id, name, trading_strategy, risk_parameters,
  total_fund_value, total_profit (read-only), total_deposits, last_trade_at,
  is_active, admin_notes, created_at, updated_at`.
- `master_api_key` / `master_secret_key` are **not** exposed.

## 8. `quantum-investments` — InvestorPortfolioViewSet

- **Create gate:** active subscription `plan__bot_type="quantum_ai"` → else 403
  (generic message in production).
- Writable: `fund`, `amount`, `status`
  (`pending` (default) | `active` | `withdrawn` | `cancelled`).
  Read-only: `id, deposited_at` (model `auto_now_add=True` → DRF marks it
  read-only, so a submitted timestamp is silently dropped), `user` (hidden),
  `share_percentage, accrued_profit, total_payouts, user_share_amount,
  subscription`.
- DB uniqueness: `unique_together = ["user", "fund"]` → serializer auto-adds
  `UniqueTogetherValidator` → duplicate deposit for the same fund →
  400 `VALIDATION_ERROR` with field errors.
- `user_share_amount` **always returns `"0"`** — `get_user_share_amount()`
  hardcodes `Decimal("0")` (serializer.py:327-328). Known placeholder.
- **`GET balance/`** (unpaginated): sums over the caller's
  `status="active"` investments:
  `{"total_invested": "…", "total_profit": "…", "current_balance": "…"}` —
  all values are decimal strings.

## 9. `pair-configs` — PairConfigViewSet

- Single serializer for create/read/update. Writable: `pair_symbol`, `bot_type`,
  `quantity`, level fields, `Order_Type`, `Amount_Type`, `SLTP_Type`,
  `Stop_Loss`, `Take_Profit`, RSI/BB/EMA entry+exit fields, `SL_Exit`.
  Read-only: `id`, `slug` (nullable and never populated by the API),
  `subscription`.
- `bot_type`: `grid` (default) | `martingale` | `custom`.
- Other enumerated values (all optional, model choices): `Order_Type`
  `market`|`limit`; `Amount_Type` `coin`|`dollar`; `SLTP_Type`
  `percentage`|`dollars`; `*_Entry` fields `buy`|`sell`|`both`|null;
  `*_Exit` fields `tp`|`sl`|`both`|null (null is the nullable default).
- **Create gate:** active subscription whose `plan__bot_type` equals the posted
  `bot_type` (defaults to `"grid"` when omitted) → else 403
  `No active subscription for <bot_type> bot` (generic in production).
- Uniqueness: `unique_together = ["user", "pair_symbol", "bot_type"]` →
  `UniqueTogetherValidator` → duplicate → 400 field errors.

## 10. `orders` — OrderViewSet (read-only)

- List/detail only, owner-scoped. `GET recent/` → latest **50** rows
  (`select_related` on all four bot FKs), **not paginated**.
- Serializer exposes exactly: `id, Time, user_info, Pair, PairConfig,
  Indicators, Side, Category, Order_type, Quantity, Price, Exchange,
  Take_Profit, Stop_Loss, Description, Details, signal_bot, grid_bot,
  martingale_bot, quantum_ai_investment` plus computed `*_info` objects
  (`{id, bot_name}` per bot; `quantum_ai_info` = `{id, amount}`;
  `user_info` = `{id, email}`). `user` is a `HiddenField` (write-only) and the
  viewset is read-only, so `user` never appears in any response.

## 11. `indicators` — IndicatorViewSet (CRUD)

- Standard authenticated CRUD over `Indicator` rows; `user` forced to the
  caller on create. Response fields: `id, Pair, EMA, RSI, Prev_RSI, Color,
  Prev_Color, BB, TSI, ADX` (`user` is a `HiddenField` → write-only, never
  serialized; requests are scoped by owner in `get_queryset()`).
- Rows are also written internally by the webhooks (§12).

## 12. TradingView indicator webhooks — `/api/bots/indicators/{ema,rsi,bb}/`

Plain async Django views (`csrf_exempt`), **not DRF**: no JWT/session auth, no
DRF throttling, no error envelope — responses use shape C (§2).

- **Auth:** `X-Webhook-Token` header **or** `webhook_token` form field →
  looked up as `User.webhook_token`. Missing/unknown → 401
  `{"status": "error", "message": "Unauthorized"}`.
- **Body:** JSON (a leading/trailing `"` strip is applied, so a TradingView
  double-quoted string body works).
- Common required fields: `pair` (e.g. `BTC/USDT`); `exchange` optional,
  defaults to `bybit`. A `PairConfig` for (user, pair) must exist → else 404
  `Pair config for <pair> not found`. Active `ExchangeCredentials` for
  (user, exchange) must exist → else 404 `No exchange credentials found`.
- Per-endpoint payloads / success bodies:

| Endpoint | Required | Optional | 200 body (on success) |
|---|---|---|---|
| `POST indicators/ema/` | `EMA200` (numeric) | `pair`, `exchange` | `{"status":"success","message":"EMA processed for <pair>","EMA":<val>,"current_side":…,"reason":…}` |
| `POST indicators/rsi/` | `RSI` (numeric) | `PrevRSI` (default = RSI), `color` (default `white`), `prev_color` (default `white`) | same shape with `"RSI": <val>` |
| `POST indicators/bb/` | `BB` | — | same shape with `"BB": <value>` |

- Missing indicator key → 400 (`"EMA200 value is required"` / `"RSI value is
  required"` / `"BB value is required"`); missing `pair` → 400; invalid JSON →
  400 `"Invalid JSON format"`; any other exception → 500
  `"Internal server error"`.
- Side effects (all three): resolve/create a cached `BotEngine` (in-memory
  registry keyed `{user_id}_{pair}_{exchange}`, 1 h TTL), update the indicator
  value on the engine, persist an `Indicator` row, then run
  `engine.startBot()` — **this can place real trades**.

---

## 13. Known gaps / discrepancies

1. **Legacy start/stop aliases are broken** (`/grid/{bot_id}/…`,
   `/martingale/{bot_id}/…` → non-JSON 500 from a dispatch-time `TypeError`, see
   §3). Fix candidates: rename the URL kwarg to `pk` or drop the aliases.
2. **Old `docs/API.md` was wrong for bots** — `signal-bots/{id}/start|stop|
   get-signals|orders`, `grid-bots/{id}/grid-status/`, `quantum-ai-bots/*` do
   not exist, and the old error format (`detail`/`code`) does not match
   `core/exceptions.py`. The Bot Management section and the error-format
   section in `API.md` were corrected to point here (2026-10-02).
3. **`QuantumDepositSerializer` / `QuantumDepositWalletSerializer`** defined in
   `apps/bots/serializers.py` are not referenced by any bots view. Deposits are
   served by `apps/payments` (`quantum-deposits` router +
   `QuantumDepositViewSet` with its own serializers).
4. **`user_share_amount` is a placeholder** always returning `"0"` (§8).
5. **Create responses omit ids** for `grid-bots` and `martingale-bots`
   (§5/§6) — clients must re-fetch the list.
6. **Production hides subscription-gate messages** (§2A) — 403 body message is
   generic while `code=PERMISSION_DENIED` still identifies the class of error.
7. **`POST indicators/`** allows clients to insert arbitrary Indicator rows for
   themselves (only `user` is forced); there is no gate tying it to an
   active subscription.
8. **`signals_used_this_month` / `signal_limit` are PATCH-able** (§4) —
   missing from `read_only_fields`, so a client can reset its own quota
   counter. Fix candidate: add both to `SignalBotSerializer.read_only_fields`.
9. **`deposited_at` cannot be set on create** (§8) — `auto_now_add` makes it
   read-only, so back-dating a deposit timestamp via the API is impossible.
