# Setup Guide

## Prerequisites

- Python 3.12+
- PostgreSQL 15+
- Redis 7+
- Docker + docker-compose (optional, for containerized setup)

## Local Development Setup

### 1. Clone and create environment

```bash
git clone <repo-url> torgovo2
cd torgovo2
python -m venv venv
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements/base.txt
pip install -r requirements/development.txt    # development extras (pytest, flake8, etc.)
```

### 3. Configure environment

```bash
cp .env.example .env
```

Key settings in `.env`:
```
DEBUG=True
DATABASE_URL=postgres://user:password@localhost:5432/torgovo
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=your-secret-key-here
FERNET_KEY=your-fernet-key-here
SENTRY_DSN=your-sentry-dsn
```

### 4. Setup database

```bash
createdb torgovo
python manage.py migrate
python manage.py createsuperuser
```

### 5. Start services

```bash
# Terminal 1: Django dev server
python manage.py runserver

# Terminal 2: Celery worker
celery -A config.celery worker -l info

# Terminal 3: Celery beat
celery -A config.celery beat -l info

# Terminal 4: Redis (if not running as service)
redis-server
```

### 6. Verify

```bash
python manage.py check
curl http://localhost:8000/ht/    # health check
```

## Docker Development Setup

```bash
docker compose up -d
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

## Running Tests

```bash
# All tests (use project venv, NOT system python)
.venv/bin/python -m pytest -q

# Specific app
.venv/bin/python -m pytest tests/bots/
.venv/bin/python -m pytest tests/trading/
.venv/bin/python -m pytest tests/payments/

# With coverage
.venv/bin/python -m pytest --cov=. -q
```

> **Note:** The project uses `.venv/bin/python` (not system python) because system python lacks `pytest-asyncio`.

## Project Structure

```
torgovo2/
+-- apps/
|   +-- authentication/   JWT, OAuth, OTP, email verification
|   +-- bots/             Bot models (Signal, Grid, Martingale, QuantumAI), views, admin
|   +-- exchanges/        Exchange, TradingPair, ExchangeCredentials models
|   +-- investments/      InvestorPortfolio, InvestorDeposit, fund display
|   +-- payments/         Payment processing, subscriptions, InvestorDeposit
|   +-- referrals/        Referral system
|   +-- subscriptions/    Telegram signal subscriptions
|   +-- trading/          Trading engine, strategies, exchange adapters, Celery tasks
|   +-- users/            User profiles, admin dashboards
|   +-- webhooks/         TradingView signal webhook receiver
+-- config/               Django settings (base/dev/prod/test), URLs, Celery, ASGI
+-- core/                 Base models (SoftDeleteModel, SiteConfig, AuditLog), utils, middleware
+-- docs/                 Documentation
+-- nginx.conf            Nginx reverse proxy configuration
+-- docker-compose.yml    Development compose (volume mounts, runserver)
+-- docker-compose.prod.yml  Production compose (gunicorn, no mounts)
+-- Dockerfile            Python 3.12 slim image
```

## Key Models

| Model | Location | Purpose |
|-------|----------|---------|
| `InvestorPortfolio` | `apps.bots` | User investment in Quantum AI fund |
| `InvestorDeposit` | `apps.payments` | Individual deposit records |
| `QuantumAIFund` | `apps.bots` | Fund configuration + profit distribution |
| `QuantumAIBot` | `apps.bots` | Automated fund trading bot |
| `SignalBot` | `apps.bots` | TradingView webhook signal bots |
| `GridBot` | `apps.bots` | Grid trading bots |
| `MartingaleBot` | `apps.bots` | Martingale strategy bots |
| `BotOrder` | `apps.bots` | All trading orders |
| `ExchangeCredentials` | `apps.exchanges` | Fernet-encrypted API keys |
| `SiteConfig` | `core` | Site-wide settings (cached with `lru_cache`) |
| `AuditLog` | `core` | Audit trail (auto-cleaned after 90 days) |

## Common Tasks

### Create a new migration
```bash
python manage.py makemigrations <app_name>
```

### Collect static files
```bash
python manage.py collectstatic
```

### Management commands
```bash
# Encrypt existing plaintext Quantum AI fund keys
python manage.py encrypt_quantum_fund_keys --dry-run
python manage.py encrypt_quantum_fund_keys
```

### Pre-deploy checks
```bash
python manage.py check
python manage.py check --deploy
python manage.py makemigrations --check
```
