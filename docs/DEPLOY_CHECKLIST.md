# Deployment Checklist

Pre-flight checklist for deploying Torgovo2 to production.

---

## 1. Server Prerequisites

- [ ] Linux server (Ubuntu 22.04+ recommended)
- [ ] Docker 24+ and Docker Compose v2 installed
- [ ] Domain DNS A record pointing to server IP
- [ ] Ports 80, 443, 5432, 6379 open (firewall/SG)
- [ ] Swap enabled (at least 2GB) — Celery workers can be memory-hungry

## 2. Clone & Configure

```bash
git clone <repo-url> torgovo2
cd torgovo2
```

## 3. Generate Production Secrets

```bash
# Generate secrets
SECRET_KEY=$(python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())")
FERNET_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
JWT_KEY=$(openssl rand -hex 32)

echo "DJANGO_SECRET_KEY=$SECRET_KEY"
echo "FERNET_KEY=$FERNET_KEY"
echo "JWT_SECRET_KEY=$JWT_KEY"
```

## 4. Create `.env`

Copy `.env.example` and fill in production values:

```bash
cp .env.example .env
```

**Required variables — all must be set before deploy:**

| Variable | How to get |
|----------|-----------|
| `DJANGO_SECRET_KEY` | Generated above |
| `FERNET_KEY` | Generated above |
| `JWT_SECRET_KEY` | Generated above |
| `DB_PASSWORD` | Generate a strong password |
| `ALLOWED_HOSTS` | Your domain (e.g. `api.yourdomain.com`) |
| `CSRF_TRUSTED_ORIGINS` | Your domain (e.g. `https://api.yourdomain.com`) |
| `CORS_ALLOWED_ORIGINS` | Frontend domain (e.g. `https://app.yourdomain.com`) |
| `GOOGLE_CLIENT_ID` | Google Cloud Console — OAuth 2.0 credentials |
| `GOOGLE_SECRET_KEY` | Google Cloud Console — same credentials |
| `TWILIO_ACCOUNT_SID` | Twilio console |
| `TWILIO_AUTH_TOKEN` | Twilio console |
| `TWILIO_PHONE_NUMBER` | Twilio purchased number |

**Optional but recommended:**

| Variable | Purpose |
|----------|---------|
| `SENTRY_DSN` | Error tracking (sentry.io) |
| `BINANCE_API_KEY` / `BINANCE_SECRET_KEY` | Exchange API (admin can add later) |
| `BYBIT_API_KEY` / `BYBIT_SECRET_KEY` | Exchange API (admin can add later) |
| `EMAIL_HOST` / `EMAIL_HOST_PASSWORD` | Transactional emails |

**Critical production overrides (already set in `config/settings/production.py`):**

```bash
DEBUG=False
DJANGO_SETTINGS_MODULE=config.settings.production
```

## 5. SSL Certificates

```bash
mkdir -p ssl

# Option A: Let's Encrypt (recommended)
sudo apt install certbot
sudo certbot certonly --standalone -d api.yourdomain.com
sudo cp /etc/letsencrypt/live/api.yourdomain.com/fullchain.pem ssl/torgovo.crt
sudo cp /etc/letsencrypt/live/api.yourdomain.com/privkey.pem ssl/torgovo.key

# Option B: Self-signed (testing only)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout ssl/torgovo.key -out ssl/torgovo.crt \
  -subj "/CN=api.yourdomain.com"
```

## 6. Build & Deploy

```bash
# Build images
docker compose -f docker-compose.prod.yml build

# Start all services (migrate + collectstatic + gunicorn run automatically)
docker compose -f docker-compose.prod.yml up -d

# Verify all containers are running
docker compose -f docker-compose.prod.yml ps
```

## 7. Post-Deploy

```bash
# Create admin user
docker compose -f docker-compose.prod.yml exec web python manage.py createsuperuser

# Verify health check
curl -k https://localhost/ht/

# Check logs for errors
docker compose -f docker-compose.prod.yml logs -f web
docker compose -f docker-compose.prod.yml logs -f celery-worker
```

## 8. Verify Services

| Check | Command | Expected |
|-------|---------|----------|
| Web | `curl -k https://localhost/` | 200 or 301 |
| Health | `curl -k https://localhost/ht/` | All checks green |
| Admin | `https://yourdomain.com/admin/` | Login page |
| Celery | `docker compose -f docker-compose.prod.yml logs celery-worker \| grep "ready"` | "celery@... ready" |
| Beat | `docker compose -f docker-compose.prod.yml logs celery-beat \| grep "beat:"` | Scheduling tasks |
| DB | `docker compose -f docker-compose.prod.yml exec db pg_isready` | "accepting connections" |
| Redis | `docker compose -f docker-compose.prod.yml exec redis redis-cli ping` | PONG |

## 9. Scheduled Tasks (Celery Beat)

These run automatically once Celery Beat starts:

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

## 10. Rollback

If something goes wrong:

```bash
# Stop all services
docker compose -f docker-compose.prod.yml down

# Restore database from backup
docker compose -f docker-compose.prod.yml exec -T db psql -U postgres torgovo < backup.sql

# Re-deploy previous version
git checkout <previous-commit>
docker compose -f docker-compose.prod.yml up -d --build
```

## 11. Ongoing Maintenance

```bash
# View logs
docker compose -f docker-compose.prod.yml logs -f web

# Restart a single service
docker compose -f docker-compose.prod.yml restart celery-worker

# Scale workers
docker compose -f docker-compose.prod.yml up -d --scale celery-worker=3

# Database backup (set up as cron job)
docker compose -f docker-compose.prod.yml exec -T db pg_dump -U postgres torgovo > backup_$(date +%Y%m%d).sql

# Update to latest code
git pull
docker compose -f docker-compose.prod.yml up -d --build
```
