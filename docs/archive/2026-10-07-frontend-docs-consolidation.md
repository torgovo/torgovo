# Frontend docs consolidation — 2026-10-07 (Step 2 of frontend-docs plan)

## What / why
`docs/frontend-connectivity.md` and `docs/FRONTEND.md` overlapped with `docs/FRONTEND_PROMPT.md` and disagreed with the codebase (wrong auth token keys, wrong pagination type, non-existent endpoints). All three were competing "source of truth" docs for the frontend AI. Consolidation: absorb unique verified content into `docs/FRONTEND_PROMPT.md` (now §13 WebSocket + §14 implementation guide + corrected §1/§2/§6.3/§8/§11/§12), then archive the two originals **verbatim** (zero information loss).

## Corrections applied to FRONTEND_PROMPT.md (verified against source 2026-10-07)
- Auth tokens: response is `tokens.access_token`/`tokens.refresh_token` (was wrongly `access`/`refresh`); refresh body key is `refresh_token`; refresh response is flat `{access_token, refresh_token, message}`.
- Register returns **201** (connectivity said 200); `LOCKED_OUT` 429 = 5 fails / 15 min.
- Pagination = `StandardResultsSetPagination` PageNumberPagination (20/page, max 100) — was "LimitOffset".
- Withdrawal TOTP key = `two_factor_code` (was "`code`").
- WebSocket: `ws/bot/<id>/` exists but has **no `bot_update` producer** (nothing `group_send`s it; `bot-management` messages unconsumed) → poll; `ws/market/<ex>/<sym>/` is live; **no `ws/wallet/`**.
- Profile = `GET/PUT/PATCH /api/auth/user/` (no `/api/auth/profile/`).
- Order filters = `pair, exchange, start_date, end_date, status, side, order_type` (no `category`/`bot` params).
- Auth error responses bypass §11 envelope (`{"error": {...}}`, no `timestamp`).
- Stale §6.8 ref → §11; checklist renumbered §13 → §15.

## Do-not-use paths (verified non-existent; originals kept in archive)
`auth/profile/` · `bots/orders/recent/` · `investments/balances/summary/` · `payments/transactions/recent/` · `payments/transactions/by_type/` · `trading/credentials/active/` · `GET webhooks/custombot/indicators/ema|rsi/` (real: `POST /api/bots/indicators/…`) · `payments/withdrawals/<pk>/cancel/` (no route in `apps/payments/urls.py`).

## Archive-only lines (NOT absorbed — with justification)
- FRONTEND.md: "Scaffold exists in `frontend/` … App.jsx/AuthContext.jsx …" → superseded (scaffold stub deleted; FRONTEND_PROMPT header forbids resurrecting it).
- FRONTEND.md: "WebSocket planned but not implemented — fallback to polling" → superseded by §13 (partial WS now exists).
- FRONTEND.md: "All API responses follow consistent format (see `docs/API.md`)" → pointer only; `docs/API.md` handled in Step 3.
- connectivity: "max 3 pending withdrawals" → **unverified** (no such limit found in `apps/payments/`); keep out of canonical until proven.
- connectivity: `withdrawals/<pk>/cancel/` → disproven (above).
- connectivity: stack-table rationale cells "Already set up in `frontend/`" → scaffold removed.

## How tested
1. Content-level line gap check (normalized, ≥40-char lines) of both sources vs canonical → every flagged line is either (a) same content in different table formatting, (b) listed above as justified archive-only, or (c) absorbed (§13/§14, auth shapes, do-not-use list, §14.8).
2. Targeted greps against `apps/authentication/views.py|urls.py|serializers.py`, `apps/investments/views.py` (OrderFilter, pagination), `apps/payments/urls.py`, `apps/payments/serializers.py:149`, `apps/bots/serializers.py`, `apps/webhooks/views.py`, `apps/trading/` — all canonical claims re-checked.
3. Internal cross-reference scan of FRONTEND_PROMPT.md: headings §1–§15 sequential, no dangling §refs.
4. Post-move: sources live verbatim at `docs/archive/frontend-connectivity.md` + `docs/archive/FRONTEND.md`; `docs/README.md` link updated.

---

# Step 3 — API docs route verification & API.md archive (2026-10-07)

## What / why
`docs/API_DOCUMENTATION.md` (canonical full-API reference) contained 13 verified-wrong routes and stale response shapes; `docs/API.md` was stale across auth/users/referrals/trading. Consolidation: correct every wrong route in API_DOCUMENTATION.md against `urls.py` sources (zero information loss — archived originals untouched), then archive API.md.

## Corrections applied to API_DOCUMENTATION.md (all verified against source 2026-10-07)
- Removed nonexistent Swagger claim (`/api/docs/` — no mount in `config/urls.py`).
- `GET/PUT/PATCH /api/auth/profile(/update)/` → `GET/PUT/PATCH /api/auth/user/` with real flat `UserSerializer` shape; writable = `email, username, first_name, last_name, phone_number, timezone` (`authentication/serializers.py` read_only_fields).
- Signal-bot `webhook_url` → `https://…/api/webhooks/custombot/` (global URL; `SignalBot.save()`), both example occurrences + TradingView section.
- TradingView webhook payload → required `bot_id, secret|X-Signature, side/action/direction, timestamp` (was `bot_uuid` etc. — would 400).
- `POST /api/bots/grid/{bot_id}/start|stop/` → `/api/bots/grid-bots/{id}/start|stop/` + flat `{"success", "message"}` bodies (legacy `grid/{bot_id}/…` = broken TypeError 500, BOTS_API §3).
- `POST /api/bots/quantum-ai-bots/` → `/api/bots/quantum-investments/` with real `fund, amount, status` payload (BOTS_API §8; was a nonexistent bot-creation API).
- `GET /api/bots/blockchain-addresses/` → `/api/investments/bots/blockchain-addresses/`; `POST /api/bots/quantum-ai/{id}/deposit/` → `/api/investments/bots/…/deposit/` + real rules (amount/coin_type/blockchain required, tx-hash **or** screenshot, duplicate → 409).
- Indicator webhooks `/api/indicators/ema|rsi/` → `/api/bots/indicators/ema|rsi/` + `X-Webhook-Token` header (BOTS_API §3).
- `GET /api/users/my-orders/` → `/api/investments/users/my-orders/` (incl. pagination `next` example).
- `GET /api/exchanges/` (router API-root) → `GET /api/exchanges/list/` + real `{"success", "data":[…]}` shape (was `{"exchanges": […]}`).
- Removed non-writable `level_spacing_percent` from grid + martingale create bodies (not in create serializer; BOTS_API §5/§6).
- TOC anchor `#webhook-alerts` → `#signal-bots`; added `v1.0.1` changelog entry.
- Superseded-note at §Bots updated: drops stale `API.md` pointer, records 2026-10-07 route corrections.

## Archive move
- `git mv docs/API.md docs/archive/API.md` (verbatim, zero information loss).
- `docs/README.md` row → `API_DOCUMENTATION.md` (+ archive pointer); `docs/BOTS_API.md` header → `docs/archive/API.md`. No other `](API.md)` links existed.

## How tested
1. Python route checker: parses every `/api/…` path from API_DOCUMENTATION.md, strips `{placeholders}`, resolves mount prefix → `apps/<app>/urls.py` `path()`/`register()` prefixes. Post-fix result: only 3 flags, each manually confirmed a checker artifact (route exists): `exchanges/{exchange_name}/symbols/` (Django `<str:…>` kwarg vs doc placeholder), `investments/bots/quantum-ai/{bot_id}/deposit/` (`<uuid:bot_id>`), `webhooks/custombot/` (nested mount in `config/urls.py:53`, app urls root is `""`).
2. Payload spot-checks vs code: profile writable fields, deposit form fields (`InvestorDepositView.post`), grid/martingale create writable lists, quantum-investments `fund/amount/status`, list_exchanges response shape — all match.
3. Link scan: no remaining `](API.md)` references outside archive; README/BOTS_API pointers updated.
