# C4 Architecture — Torgovo2 Trading Bot Platform

> C4 Model: Context → Container → Component. Level 4 (Code) is covered by the existing class/sequence diagrams.

---

## Level 1: System Context

```mermaid
C4Context
    title System Context — Torgovo2 Crypto Trading Bot Platform

    Person(trader, "Trader / End User", "Retail crypto trader who wants automated trading bots")
    Person(admin, "Platform Admin", "Reviews subscriptions, manages funds, starts/stops bots")
    System_Boundary(torgovo2, "Torgovo2 Platform") {
        System(torgovo2_sys, "Torgovo2 Trading Bot Platform", "Automated crypto trading with grid, martingale, signal, and Quantum AI strategies")
    }
    System_Ext(exchanges, "Crypto Exchanges", "Bybit, Binance, OKX, MEXC, Coinbase")
    System_Ext(tradingview, "TradingView", "Sends webhook alerts for SignalBot")
    System_Ext(telegram, "Telegram Bot API", "Sends notifications, manages signal subscriptions")
    System_Ext(stripe, "Stripe / Crypto", "Payment processing")
    System_Ext(email, "SMTP / Email", "Email notifications and verification")

    Rel(trader, torgovo2_sys, "Trades via REST API", "HTTPS")
    Rel(trader, torgovo2_sys, "Views admin via browser", "HTTPS")
    Rel(admin, torgovo2_sys, "Manages platform via Admin", "HTTPS")
    Rel(torgovo2_sys, exchanges, "Places orders, fetches data", "CCXT / REST")
    Rel(tradingview, torgovo2_sys, "Webhook alerts", "POST /api/webhooks/")
    Rel(torgovo2_sys, telegram, "Notifications, subscriptions", "Bot API")
    Rel(torgovo2_sys, email, "Verification, alerts", "SMTP")
    Rel(trader, stripe, "Buy subscription", "Stripe Checkout")
    Rel(torgovo2_sys, stripe, "Verify payments", "Stripe API")

    UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```

---

## Level 2: Container Diagram

```mermaid
C4Container
    title Container Diagram — Torgovo2 Platform

    Person(trader, "Trader", "API consumer, frontend user")
    Person(admin, "Admin", "Django admin, platform manager")

    System_Boundary(torgovo2, "Torgovo2 Platform") {
        Container(web, "Daphne ASGI Server", "Python 3.14, Django 5.2", "Serves Django Admin, DRF API, WebSocket, and static files")
        Container(celery_worker, "Celery Worker", "Python, Celery", "Executes trading bots asynchronously")
        Container(celery_beat, "Celery Beat", "Python, Celery", "Scheduled tasks: fund performance updates")
        ContainerDb(db, "PostgreSQL", "PostgreSQL 16", "Primary data store — all models, orders, users")
        ContainerDb(redis, "Redis", "Redis 7", "Cache, Celery broker, Channels layer")
        Container(frontend, "React SPA", "React, Vite", "Single-page application for traders")
    }

    System_Ext(exchange_api, "Exchange APIs", "Bybit, Binance, OKX, MEXC, Coinbase")
    System_Ext(tv, "TradingView", "Webhook source")
    System_Ext(tg, "Telegram", "Bot API")
    System_Ext(stripe, "Stripe", "Payment gateway")

    Rel(trader, frontend, "Uses", "HTTPS")
    Rel(trader, web, "Calls API", "HTTPS /api/*")
    Rel(admin, web, "Manages platform", "HTTPS /admin/")
    Rel(frontend, web, "API calls", "HTTPS /api/")
    Rel(web, db, "Reads/Writes", "SQL")
    Rel(web, redis, "Caches, sessions", "Redis protocol")
    Rel(celery_worker, redis, "Polls tasks", "Redis protocol")
    Rel(celery_worker, db, "Reads/Writes", "SQL")
    Rel(celery_beat, redis, "Schedules tasks", "Redis protocol")
    Rel(celery_worker, exchange_api, "Trades via CCXT", "REST/WebSocket")
    Rel(web, stripe, "Verifies payments", "Stripe API")
    Rel(web, tg, "Sends messages", "Telegram Bot API")

    UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="2")
```

---

## Level 3: Component — Django Web Container

```mermaid
C4Component
    title Component Diagram — Django Web Container

    Container_Boundary(django, "Daphne ASGI Server") {
        Component(admin_site, "Django Admin", "django.contrib.admin", "Admin interface for all models with custom actions")
        Component(drf_api, "DRF API", "djangorestframework", "REST API endpoints for all 10 apps")
        Component(websocket, "WebSocket Consumer", "Django Channels", "Real-time trading updates")
        Component(auth, "Auth Layer", "JWT + SimpleJWT", "Token-based authentication and permission checks")

        Component(views_bots, "Bot API Views", "apps/bots/views.py", "CRUD for bots, indicators, pair configs, orders")
        Component(views_auth, "Auth Views", "apps/authentication/views.py", "Registration, login, verification, 2FA")
        Component(views_payments, "Payment Views", "apps/payments/views.py", "Subscription purchase, deposit upload")
        Component(views_sub, "Subscription Views", "apps/subscriptions/views.py", "Telegram signal subscriptions")
        Component(views_trading, "Trading Views", "apps/trading/views.py", "Trading data, strategy configs")
        Component(views_webhook, "Webhook View", "apps/webhooks/views.py", "TradingView alert receiver")

        Component(services, "Services", "services/*.py", "Business logic: BotExecutorService, QuantumAIFundService")
        Component(engine, "Trading Engine", "engines/*.py", "BotEngine, BotExecutor, run_bot/stop_bot")

        Component(models_bots, "Bot Models", "apps/bots/models.py", "12 models: Signal, Grid, Martingale, Quantum AI, Order, Indicator")
        Component(models_payments, "Payment Models", "apps/payments/models.py", "5 models: Subscriptions, plans, withdrawals")
        Component(models_all, "All Other Models", "apps/*/models.py", "Users, exchanges, webhooks, referrals, subscriptions")
    }

    Rel(auth, views_bots, "Authenticates")
    Rel(auth, views_payments, "Authenticates")
    Rel(auth, views_sub, "Authenticates")
    Rel(admin_site, models_bots, "CRUD")
    Rel(admin_site, models_payments, "CRUD")
    Rel(drf_api, views_bots, "Routes")
    Rel(drf_api, views_auth, "Routes")
    Rel(drf_api, views_payments, "Routes")
    Rel(views_webhook, services, "Delegates execution")
    Rel(services, engine, "run_bot / stop_bot")
    Rel(engine, models_bots, "Reads/Writes orders, bot state")
```

---

## Deployment Diagram (C4 Level 3)

```mermaid
C4Deployment
    title Deployment Diagram — Production

    Deployment_Node(cloud, "Cloud Server (VPS)", "Linux, Ubuntu 24.04") {
        Deployment_Node(docker, "Docker Compose", "") {
            Deployment_Node(nginx, "Nginx Container", "nginx:alpine") {
                Container(nginx_cont, "Nginx", "Reverse proxy, SSL, static/media serving")
            }
            Deployment_Node(web_container, "Web Container", "python:3.14-slim") {
                Container(daphne, "Daphne Server", "ASGI, 4 workers")
            }
            Deployment_Node(worker_container, "Worker Container", "python:3.14-slim") {
                Container(celery, "Celery Worker", "4-8 concurrent workers")
                Container(beat, "Celery Beat", "1 scheduler process")
            }
            Deployment_Node(redis_container, "Redis Container", "redis:7-alpine") {
                ContainerDb(redis_db, "Redis", "Port 6379")
            }
            Deployment_Node(db_container, "DB Container", "postgres:16-alpine") {
                ContainerDb(postgres, "PostgreSQL", "Port 5432, persistent volume")
            }
        }
    }

    Rel(nginx_cont, daphne, "Proxies /api/, /admin/", "HTTP")
    Rel(nginx_cont, daphne, "Serves /static/, /media/", "Direct")
    Rel(celery, redis_db, "Task queue", "Redis protocol")
    Rel(beat, redis_db, "Schedule", "Redis protocol")
    Rel(daphne, redis_db, "Cache + sessions", "Redis protocol")
    Rel(celery, postgres, "Reads/Writes", "SQL")
    Rel(daphne, postgres, "Reads/Writes", "SQL")

    UpdateLayoutConfig($c4ShapeInRow="2", $c4BoundaryInRow="1")
```
