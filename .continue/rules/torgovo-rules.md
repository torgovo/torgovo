# =============================================================================
# Continue (VSCodium) Config — Torgovo Stack
# File: ~/.continue/config.yaml
#
# Stack: Django 5.x · DRF · Celery+Redis · WebSockets · PostgreSQL · React+Vite
# Source distilled from: alirezarezvani/claude-skills (engineering subset)
#
# How to use:
#   1. Copy this file to ~/.continue/config.yaml
#   2. Set ANTHROPIC_API_KEY in your environment
#   3. Reload VSCodium / Continue extension
# =============================================================================

name: Torgovo Dev
version: 1.0.0

# ── Models ────────────────────────────────────────────────────────────────────
models:
  - name: Claude Sonnet (Primary)
    provider: anthropic
    model: claude-sonnet-4-5
    apiKey: $ANTHROPIC_API_KEY

  - name: Claude Haiku (Fast)
    provider: anthropic
    model: claude-haiku-4-5-20251001
    apiKey: $ANTHROPIC_API_KEY

# ── Tab Autocomplete ──────────────────────────────────────────────────────────
tabAutocomplete:
  model: claude-haiku-4-5-20251001
  provider: anthropic
  apiKey: $ANTHROPIC_API_KEY

# ── Rules (distilled from claude-skills engineering subset) ──────────────────
# These replace the need to clone/install claude-skills just for Continue.
# Each block maps to a skill category from alirezarezvani/claude-skills.
rules:
  # ── senior-architect ──────────────────────────────────────────────────────
  - name: Architecture Principles
    rule: |
      Adapter pattern for exchange integrations (get_adapter() factory).
      Strategy pattern for trading logic (get_strategy() factory).
      BotEngine accepts plain dict config — never Django model instances.
      UUID primary keys everywhere via SoftDeleteModel / TimeStampedModel.
      Keep apps/trading/strategies/ and apps/trading/exchanges/ pure Python (no Django imports).
      Service layer (services/) orchestrates between Django and engine.

  # ── senior-backend (Django/DRF) ───────────────────────────────────────────
  - name: Django & DRF Standards
    rule: |
      Use DRF serializers for ALL validation — never validate in views.
      ViewSets use action decorators (@action) for non-CRUD endpoints.
      Permissions: IsAuthenticated on all endpoints; custom permissions for admin-only.
      Pagination: always return {count, next, previous, results} for list endpoints.
      Filters: use django-filter for query params; never raw request.GET parsing.
      Error responses: always {error: {code, message, details}} format.
      Models: use core.TimeStampedModel or core.SoftDeleteModel as base.
      API keys: always encrypt with Fernet (core/utils.py) before storing.
      Never put bot views in apps/payments/ — they belong in apps/bots/.
      Never create new Django models for engine runtime state — use plain dicts.

  # ── Celery + Redis ────────────────────────────────────────────────────────
  - name: Celery & Async Standards
    rule: |
      All bot start/stop goes through Celery tasks in apps/trading/tasks.py.
      Task naming: verb_noun pattern (run_trading_bot, stop_bot, check_all_active_bots).
      Always set task_acks_late=True on tasks that execute trades.
      Use Celery Beat for scheduled tasks (bot monitoring, quantum AI distribution).
      Retry pattern: max_retries=3, exponential backoff, notify user on all-fail.
      Never do synchronous CCXT calls in request/response cycle — always Celery.
      Webhook receipt: acknowledge immediately (202), process async in task.

  # ── WebSockets ────────────────────────────────────────────────────────────
  - name: WebSocket Standards
    rule: |
      Use Django Channels for WebSocket support (planned, not yet implemented).
      Channel groups per user: user_{user_id} for personal notifications.
      Message schema: {type, payload, timestamp} — always include type for routing.
      Authentication: JWT token in query string for WS handshake.
      Reconnect logic belongs in frontend, not backend.

  # ── database-designer (PostgreSQL) ────────────────────────────────────────
  - name: Database Standards
    rule: |
      All models use UUID PKs. Never use integer PKs for domain models.
      Add db_index=True on FK fields used in filters (user, bot, exchange).
      Use select_related() for FK traversal, prefetch_related() for M2M.
      Migrations: one migration per logical change. Never edit existing migrations.
      Soft delete: use SoftDeleteModel.delete() — never hard-delete domain data.
      Index strategy: composite indexes on (user, created_at) for history queries.
      Never use ORM in engine/strategy/adapter layers — pass plain dicts.

  # ── api-design-reviewer (REST) ────────────────────────────────────────────
  - name: REST API Design
    rule: |
      URL structure: /api/{app}/{resource}/{id}/{action}/
      HTTP verbs: GET=read, POST=create/action, PUT=full update, PATCH=partial, DELETE=soft-delete.
      Start/stop bots: POST /api/bots/{type}/{id}/start/ and /stop/ (not PUT).
      Webhook endpoints: POST /api/webhooks/{type}/{id}/ — no auth required, use secret_key.
      Versioning: /api/v1/ prefix for all endpoints.
      Never expose internal IDs — use UUIDs in all URLs.
      Consistent field naming: snake_case everywhere.

  # ── senior-frontend (React+Vite) ─────────────────────────────────────────
  - name: React + Vite Standards
    rule: |
      TypeScript strict mode. No any types — use proper interfaces.
      State: Zustand for global state, useState for local component state.
      API calls: Axios with interceptors for JWT refresh. All calls in services/ layer.
      Forms: React Hook Form with Zod schema validation.
      Error handling: error boundaries + toast notifications (no raw alerts).
      Auth: store access token in memory, refresh token in httpOnly cookie.
      Components: functional only. No class components.
      Naming: PascalCase components, camelCase hooks (useAuth, useBots), kebab-case files.
      Charts: Recharts for portfolio/profit displays.
      Real-time: WebSocket hook in hooks/useWebSocket.ts with auto-reconnect.

  # ── senior-devops (Docker/Redis) ─────────────────────────────────────────
  - name: DevOps & Docker Standards
    rule: |
      Multi-stage Dockerfile: builder stage + slim runtime stage.
      Never put secrets in Dockerfile or docker-compose — use .env files.
      Health checks on all services: /health/ endpoint returning 200.
      Redis connection: use REDIS_URL env var, never hardcode host/port.
      Static files: collectstatic in entrypoint, not at build time.
      Celery worker and beat as separate containers/processes.
      Production: gunicorn with --workers=4, --timeout=120.

  # ── observability-designer (Logging) ─────────────────────────────────────
  - name: Logging Standards
    rule: |
      Use Python logging module — never print() in production code.
      Log levels:
        DEBUG — detailed execution flow, variable values (dev only)
        INFO  — business events: bot started, trade executed, deposit approved
        WARNING — recoverable issues: retry attempt, rate limit hit
        ERROR — failures requiring attention: trade failed, exchange error
        CRITICAL — system failures: DB unreachable, Celery down
      Always include context in log message: user_id, bot_id, exchange, pair.
      Use structured logging format: %(asctime)s %(levelname)s %(name)s: %(message)s
      Never log raw API keys, passwords, or secret_key values.
      Webhook receipt: always log INFO with webhook_id and action.

  # ── tdd-guide ─────────────────────────────────────────────────────────────
  - name: Testing Standards
    rule: |
      Target: 80%+ coverage (apps/ only, not trading/ legacy code).
      Use pytest + pytest-django. Never use unittest directly.
      Fixtures: factory_boy for model factories. No manual .create() in tests.
      Mock CCXT calls: never hit real exchanges in tests.
      API tests: use APIClient from DRF. Test auth, validation, and response schema.
      Celery tasks: test with task.apply() in CELERY_TASK_ALWAYS_EAGER=True mode.
      WebSocket: use pytest-asyncio + channels.testing.WebsocketCommunicator.
      Test file naming: test_{module}.py mirroring source structure.

  # ── code-reviewer ─────────────────────────────────────────────────────────
  - name: Code Review Checklist
    rule: |
      Before suggesting code, check:
      1. Does it import Django models in engine/strategy/adapter? → Reject.
      2. Does it use integer PKs? → Use UUID.
      3. Does it store API keys in plaintext? → Use Fernet encryption.
      4. Does it call CCXT synchronously in a view? → Move to Celery task.
      5. Does it put bot logic in apps/payments/? → Move to apps/bots/.
      6. Does it reference deleted models (BotConfiguration, TradingBot, CustomBot)? → Use current models.
      7. Does it use print() for logging? → Use logger.info/error.
      8. Does it hardcode exchange URLs or credentials? → Use env vars.

  # ── Torgovo Project-Specific Rules ────────────────────────────────────────
  - name: Torgovo Architecture Rules
    rule: |
      Bot model locations:
        SignalBot, GridBot, MartingaleBot, QuantumAIBot → apps/bots/models.py
        ExchangeCredentials (canonical) → apps/exchanges/models.py
        Exchange, TradingPair, StrategyConfig → apps/trading/models.py

      Removed/renamed (never reference these):
        CustomBot → now SignalBot
        BotConfiguration → removed
        TradingBot → removed
        trading_manager → removed (use BotEngine)
        BotBridge → never existed

      Bot execution flow:
        View → BotExecutorService (services/bot_executor.py)
             → Celery task (apps/trading/tasks.py)
             → BotExecutor.from_config(dict) (apps/trading/engines/execution.py)
             → BotEngine.startBot() (apps/trading/engines/bot_engine.py)

      Do NOT implement actual CCXT trade execution.
      Leave as: # TODO: Implement CCXT trade execution

      QuantumAI: users see ONLY balance + changes. Never expose trade details.
      All bot views: apps/bots/views.py. Payment views: apps/payments/views.py.

# ── Custom Commands (slash commands in Continue) ──────────────────────────────
customCommands:
  - name: review
    description: "Review this code against Torgovo standards"
    prompt: |
      Review the selected code against these Torgovo project standards:
      1. No Django imports in engine/strategy/adapter layers
      2. UUID PKs, SoftDeleteModel base, Fernet-encrypted API keys
      3. Bot views in apps/bots/, payment views in apps/payments/
      4. No references to deleted models (BotConfiguration, TradingBot, CustomBot)
      5. Celery for all async work, never sync CCXT in request cycle
      6. Proper logging levels (DEBUG/INFO/WARNING/ERROR)
      7. DRF serializers for validation, not in views
      Flag any violations with the file + line and suggest the fix.

  - name: docstring
    description: "Add docstring to function"
    prompt: |
      Add a concise docstring to the selected function.
      Format: one-line summary, then Args/Returns only if non-obvious.
      Keep it short — the code should be readable without lengthy docs.
      Match the style: """Brief summary. Args: x: description. Returns: type."""

  - name: migrate
    description: "Generate Django migration notes"
    prompt: |
      For the selected model change, describe:
      1. What migration to generate (field added/removed/altered)
      2. Whether it requires a data migration
      3. Rollback risk (can this be rolled back without data loss?)
      4. Suggested migration name following pattern: NNNN_verb_field_model

  - name: celery-task
    description: "Convert to Celery task"
    prompt: |
      Convert the selected synchronous code to a proper Celery task.
      Apply: task_acks_late=True, max_retries=3, exponential backoff,
      bind=True for self access, proper logging, return value structure.
      Show both the task definition and how to call it from a view.

# ── Context Providers ─────────────────────────────────────────────────────────
context:
  - provider: file
  - provider: code
  - provider: diff
  - provider: terminal
  - provider: open
    params:
      onlyPinned: false

# ── Embeddings (for @codebase search) ────────────────────────────────────────
embeddingsProvider:
  provider: anthropic
  model: voyage-code-3
  apiKey: $ANTHROPIC_API_KEY