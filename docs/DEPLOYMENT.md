# Deployment Guide

## Production Architecture

```
                         Internet
                            |
                       +----+----+
                       |  nginx  |  TLS, rate limiting, static/media
                       |  :443   |
                       +----+----+
                            |
                  +---------+----------+
                  |  Gunicorn + Uvicorn |
                  |  4 workers, ASGI    |
                  |  max 1000 req/worker|
                  +---------+----------+
                            |
              +-------------+-------------+
              |             |             |
        +-----+-----+ +----+----+ +------+------+
        |  Celery   | |  Redis   | | PostgreSQL  |
        |  Worker   | |  :6379   | |  :5432      |
        +-----------+ +---------+ +-------------+
```

## Docker Deployment

### Production docker-compose

File: `docker-compose.prod.yml` (in project root)

```bash
# Build and start all services
docker compose -f docker-compose.prod.yml up -d --build

# Apply migrations
docker compose -f docker-compose.prod.yml exec web python manage.py migrate

# Create admin user
docker compose -f docker-compose.prod.yml exec web python manage.py createsuperuser

# Collect static files
docker compose -f docker-compose.prod.yml exec web python manage.py collectstatic --noinput
```

> **Note:** The web service command in `docker-compose.prod.yml` already runs `migrate` and `collectstatic` at startup. You only need to run these manually for initial setup or after model changes.

### Services

| Service | Image | Ports | Notes |
|---------|-------|-------|-------|
| web | Dockerfile | :8000 (internal) | Gunicorn + Uvicorn (ASGI) |
| celery-worker | Dockerfile | — | 4 concurrency, acks_late |
| celery-beat | Dockerfile | — | DatabaseScheduler |
| redis | redis:7-alpine | :6379 | |
| postgres | postgres:15 | :5432 | |
| nginx | nginx:1.25-alpine | :80 :443 | Reverse proxy, TLS |

### Environment Variables

The web service reads from `.env` at project root. Override per-environment via `environment:` in compose.

**Required:**
```bash
DATABASE_URL=postgres://user:password@db:5432/torgovo
REDIS_URL=redis://redis:6379/0
DJANGO_SECRET_KEY=<random-64-char>
FERNET_KEY=<base64-32-byte>
SENTRY_DSN=https://key@app.sentry.io/project
```

**Django:**
```bash
DEBUG=False
DJANGO_SETTINGS_MODULE=config.settings.production
ALLOWED_HOSTS=api.torgovo.com,localhost
CORS_ALLOWED_ORIGINS=https://app.torgovo.com
```

**Exchange API Keys (admin can add later via /admin/):**
```bash
BINANCE_API_KEY=
BINANCE_SECRET_KEY=
BYBIT_API_KEY=
BYBIT_SECRET_KEY=
```

## Health Checks

```bash
# Standard health check
GET /ht/    -> django-health-check (DB, Redis, Celery)

# Metrics
GET /metrics -> Prometheus metrics

# Sentry
SENTRY_DSN  -> Error tracking + performance
```

## Scheduled Tasks (Celery Beat)

Configured in `config/celery.py`:

| Task | Schedule | Purpose |
|------|----------|---------|
| `run-active-bots` | Every 60s | Execute active grid/martingale bots |
| `check-stale-bots` | Every 2min | Detect missed heartbeats |
| `heartbeat-check` | Every 5min | Bot health monitoring |
| `accrue-quantum-ai-profits` | Every hour | Accrue fund profits |
| `reset-monthly-signals` | 1st of month 00:00 | Reset signal usage counters |
| `distribute-quantum-ai-profits` | Every 14 days | Distribute fund profits |
| `process-fund-payouts` | Daily 00:05 | Move accrued profit to user balance |
| `cleanup-old-audit-logs` | 1st of month 02:00 | Remove audit logs older than 90 days |

## Production Checklist

- [ ] `DEBUG=False` in production
- [ ] Generate fresh `DJANGO_SECRET_KEY`, `FERNET_KEY`, `JWT_SECRET_KEY`
- [ ] Configure `ALLOWED_HOSTS` and `CORS_ALLOWED_ORIGINS`
- [ ] Set up TLS certificates (Let's Encrypt / certbot)
- [ ] Configure PostgreSQL with proper `pool_size` and `connect_timeout`
- [ ] Set up Redis persistence and maxmemory policy
- [ ] Configure Sentry DSN for error tracking
- [ ] Run `python manage.py check --deploy`
- [ ] Verify health check endpoint returns all services green
- [ ] Set up database backups (pg_dump cron)
- [ ] Configure log rotation for Docker containers
- [ ] Verify rate limiting and throttling configuration
- [ ] Test Celery task execution and retry behavior

## Docker Command Reference

```bash
# View logs
docker compose -f docker-compose.prod.yml logs -f web
docker compose -f docker-compose.prod.yml logs -f celery-worker

# Execute inside container
docker compose -f docker-compose.prod.yml exec web python manage.py shell
docker compose -f docker-compose.prod.yml exec web python manage.py dbshell

# Restart a service
docker compose -f docker-compose.prod.yml restart celery-worker

# Scale workers
docker compose -f docker-compose.prod.yml up -d --scale celery-worker=3

# Backup database
docker compose -f docker-compose.prod.yml exec -T db pg_dump -U postgres torgovo > backup.sql
```
