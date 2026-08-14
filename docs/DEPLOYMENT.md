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

File: `deploy/docker-compose.yml`

```bash
# Build and start all services
docker-compose -f deploy/docker-compose.yml up -d --build

# Apply migrations
docker-compose -f deploy/docker-compose.yml exec web python manage.py migrate

# Create admin user
docker-compose -f deploy/docker-compose.yml exec web python manage.py createsuperuser

# Collect static files
docker-compose -f deploy/docker-compose.yml exec web python manage.py collectstatic --noinput
```

### Services

| Service | Image | Ports | Notes |
|---------|-------|-------|-------|
| web | Dockerfile.web | :8000 | Gunicorn + Uvicorn (ASGI) |
| celery-worker | Dockerfile.web | — | 4 concurrency, acks_late |
| celery-beat | Dockerfile.web | — | DatabaseScheduler |
| redis | redis:7-alpine | :6379 | |
| postgres | postgres:15-alpine | :5432 | |
| nginx | nginx:alpine | :80 :443 | Reverse proxy, TLS |

## Environment Variables (Production)

```bash
# Required
DATABASE_URL=postgres://user:password@db:5432/torgovo
REDIS_URL=redis://redis:6379/0
SECRET_KEY=<random-64-char>
FERNET_KEY=<base64-32-byte>
SENTRY_DSN=https://key@app.sentry.io/project

# Django
DEBUG=False
ALLOWED_HOSTS=api.torgovo.com,localhost
CORS_ALLOWED_ORIGINS=https://app.torgovo.com

# Email
EMAIL_HOST=smtp.sendgrid.net
EMAIL_PORT=587
EMAIL_HOST_USER=apikey
EMAIL_HOST_PASSWORD=<sendgrid-api-key>
DEFAULT_FROM_EMAIL=noreply@torgovo.com

# Exchange API Keys (admin only)
QUANTUM_AI_MASTER_KEY=
QUANTUM_AI_MASTER_SECRET=
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

## Production Checklist

- [ ] `DEBUG=False` in production
- [ ] Generate fresh `SECRET_KEY` and `FERNET_KEY`
- [ ] Configure `ALLOWED_HOSTS` and `CORS_ALLOWED_ORIGINS`
- [ ] Set up TLS certificates (Let's Encrypt / certbot)
- [ ] Configure PostgreSQL with proper `pool_size` and `connect_timeout`
- [ ] Set up Redis persistence and maxmemory policy
- [ ] Configure Sentry DSN for error tracking
- [ ] Set up Grafana + Prometheus monitoring stack (`deploy/monitoring/`)
- [ ] Run `python manage.py check --deploy`
- [ ] Verify health check endpoint returns all services green
- [ ] Set up database backups (pg_dump cron)
- [ ] Configure log rotation for Docker containers
- [ ] Set up SSL/TLS for Redis and PostgreSQL connections
- [ ] Enable fail2ban or equivalent for brute-force protection
- [ ] Verify rate limiting and throttling configuration
- [ ] Test Celery task execution and retry behavior

## Docker Command Reference

```bash
# View logs
docker-compose logs -f web
docker-compose logs -f celery-worker

# Execute inside container
docker-compose exec web python manage.py shell
docker-compose exec web python manage.py dbshell

# Restart a service
docker-compose restart celery-worker

# Scale workers
docker-compose up -d --scale celery-worker=3

# Backup database
docker-compose exec postgres pg_dump -U postgres torgovo > backup.sql
```
