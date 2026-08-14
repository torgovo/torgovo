# Setup Guide

## Prerequisites

- Python 3.11+
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
pip install -r requirements/dev.txt    # development extras
```

### 3. Configure environment

Copy the example env file:

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

### 5. Load seed data (optional)

```bash
python manage.py loaddata fixtures/initial_plans.json
```

### 6. Start services

```bash
# Terminal 1: Django dev server
python manage.py runserver

# Terminal 2: Celery worker
celery -A config worker -l info

# Terminal 3: Celery beat
celery -A config beat -l info

# Terminal 4: Redis (if not running as service)
redis-server
```

### 7. Verify

```bash
python manage.py check
curl http://localhost:8000/ht/    # health check
```

## Docker Development Setup

```bash
docker-compose -f deploy/docker-compose.yml up -d
docker-compose -f deploy/docker-compose.yml exec web python manage.py migrate
docker-compose -f deploy/docker-compose.yml exec web python manage.py createsuperuser
```

## Running Tests

```bash
# All tests
python manage.py test

# Specific app
python manage.py test apps.bots
python manage.py test apps.trading
python manage.py test apps.webhooks

# With coverage
coverage run --source='.' manage.py test
coverage report
```

## Project Structure

```
torgovo2/
+-- apps/
|   +-- bots/             Bot models, views, admin, indicator views
|   +-- trading/          Trading engine, strategies, exchange adapters
|   +-- exchanges/        Exchange/TradingPair/ExchangeCredentials models
|   +-- webhooks/         TradingView signal webhook receiver
|   +-- payments/         Payment processing, subscriptions
|   +-- subscriptions/    Telegram signal subscriptions
|   +-- authentication/   JWT, OAuth, OTP
|   +-- investments/      Quantum AI deposit/display
|   +-- referrals/        Referral system
|   +-- users/            User profiles, admin dashboards
+-- config/               Django settings, URLs, Celery, ASGI
+-- core/                 Base models, utils, middleware, pagination
+-- services/             BotExecutorService, QuantumAIFundService
+-- deploy/               Docker compose, scripts, monitoring
+-- docs/                 Documentation
+-- trading/              Legacy code (DO NOT MODIFY — reference only)
```

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
# Encrypt existing plaintext QuantumAIFund keys
python manage.py encrypt_quantum_fund_keys --dry-run
python manage.py encrypt_quantum_fund_keys
```
