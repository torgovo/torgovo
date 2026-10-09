# Docker Deployment Guide — Torgovo Trading Platform

Step-by-step instructions for deploying the Torgovo crypto trading platform using Docker.

## Prerequisites

### System Requirements
- **OS**: Linux (Ubuntu 20.04+), macOS, or Windows 10+ with WSL2
- **Docker**: Version 24+
- **Docker Compose**: Version 2.0+
- **RAM**: Minimum 4GB, Recommended 8GB+
- **Storage**: Minimum 20GB free space

### Install Docker

#### Ubuntu/Debian
```bash
sudo apt-get update
sudo apt-get install ca-certificates curl gnupg lsb-release
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker $USER
# Logout and login again for group changes
```

#### macOS
```bash
brew install --cask docker
```

## Quick Start

### 1. Clone the Repository
```bash
git clone <repo-url> torgovo2
cd torgovo2
```

### 2. Environment Configuration
```bash
cp .env.example .env
```

**Required Environment Variables:**
```bash
# Generate secure secrets
DJANGO_SECRET_KEY=$(python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())")
FERNET_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
JWT_SECRET_KEY=$(openssl rand -hex 32)

# Database
DB_NAME=torgovo
DB_USER=postgres
DB_PASSWORD=<strong-random-password>
DB_HOST=db
DB_PORT=5432

# Redis
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

# Django
DEBUG=False
DJANGO_SETTINGS_MODULE=config.settings.production
ALLOWED_HOSTS=yourdomain.com,localhost

# Frontend
FRONTEND_URL=https://yourdomain.com
BASE_URL=https://api.yourdomain.com
```

### 3. SSL Certificates
```bash
mkdir -p ssl

# Let's Encrypt (production)
sudo apt install certbot
sudo certbot certonly --standalone -d api.yourdomain.com
sudo cp /etc/letsencrypt/live/api.yourdomain.com/fullchain.pem ssl/torgovo.crt
sudo cp /etc/letsencrypt/live/api.yourdomain.com/privkey.pem ssl/torgovo.key

# Or self-signed (testing)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout ssl/torgovo.key -out ssl/torgovo.crt \
  -subj "/CN=yourdomain.com"
```

### 4. Build and Start
```bash
docker compose -f docker-compose.prod.yml up -d --build
```

This automatically:
- Builds the Docker image
- Runs database migrations
- Collects static files
- Starts Gunicorn with Uvicorn workers

### 5. Create Admin User
```bash
docker compose -f docker-compose.prod.yml exec web python manage.py createsuperuser
```

### 6. Verify Deployment
```bash
# Check all containers are running
docker compose -f docker-compose.prod.yml ps

# Test API
curl -k https://localhost/

# Test health check
curl -k https://localhost/ht/
```

## Docker Compose Files

| File | Purpose | Usage |
|------|---------|-------|
| `docker-compose.yml` | Development | `docker compose up -d` |
| `docker-compose.prod.yml` | Production | `docker compose -f docker-compose.prod.yml up -d` |

### Production Services (`docker-compose.prod.yml`)

#### **web** — Django Application
- Runs `migrate` → `collectstatic` → `gunicorn` on startup
- 4 Uvicorn workers, max 1000 requests per worker
- Code baked into image (no volume mounts)

#### **db** — PostgreSQL 15
- Persistent volume: `postgres_data`
- Health check: `pg_isready`
- Exposed on port 5432

#### **redis** — Cache & Message Broker
- Persistent volume: `redis_data` with AOF append-only
- Health check: `redis-cli ping`

#### **celery-worker** — Background Tasks
- 4 concurrent workers
- `acks_late` for reliable processing
- Routes: trading tasks → `trading` queue, payment tasks → `payments` queue

#### **celery-beat** — Scheduled Tasks
- Uses `django_celery_beat.schedulers:DatabaseScheduler`
- Manages all periodic tasks (see schedule below)

#### **nginx** — Reverse Proxy
- TLS termination on ports 80/443
- Serves static files and media
- Proxies to web service on port 8000

## Scheduled Tasks

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

## Common Commands

### Service Management
```bash
# Start
docker compose -f docker-compose.prod.yml up -d

# Stop
docker compose -f docker-compose.prod.yml down

# Restart all
docker compose -f docker-compose.prod.yml restart

# Restart one service
docker compose -f docker-compose.prod.yml restart web

# View logs
docker compose -f docker-compose.prod.yml logs -f web
docker compose -f docker-compose.prod.yml logs -f celery-worker
```

### Database Operations
```bash
# Connect to database
docker compose -f docker-compose.prod.yml exec db psql -U postgres -d torgovo

# Create backup
docker compose -f docker-compose.prod.yml exec -T db pg_dump -U postgres torgovo > backup_$(date +%Y%m%d_%H%M%S).sql

# Restore backup
docker compose -f docker-compose.prod.yml exec -T db psql -U postgres torgovo < backup_file.sql

# Django shell
docker compose -f docker-compose.prod.yml exec web python manage.py shell
```

### Maintenance
```bash
# Run migrations after model changes
docker compose -f docker-compose.prod.yml exec web python manage.py migrate

# Collect static files
docker compose -f docker-compose.prod.yml exec web python manage.py collectstatic --noinput

# Check Django configuration
docker compose -f docker-compose.prod.yml exec web python manage.py check

# Scale workers
docker compose -f docker-compose.prod.yml up -d --scale celery-worker=3
```

## Backup & Recovery

### Automated Backups
```bash
# Create backup script
cat > backup.sh << 'EOF'
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups"
mkdir -p $BACKUP_DIR

# Database backup
docker compose -f docker-compose.prod.yml exec -T db pg_dump -U postgres torgovo > $BACKUP_DIR/db_$DATE.sql

# Media files backup
docker compose -f docker-compose.prod.yml exec -T web tar czf - /app/media > $BACKUP_DIR/media_$DATE.tar.gz

# Remove old backups (keep 7 days)
find $BACKUP_DIR -mtime +7 -delete

echo "Backup completed: $DATE"
EOF
chmod +x backup.sh

# Add to crontab (daily at 2 AM)
crontab -e
# 0 2 * * * /path/to/torgovo2/backup.sh
```

### Restore
```bash
# Restore database
docker compose -f docker-compose.prod.yml exec -T db psql -U postgres torgovo < /backups/db_20260918_020000.sql

# Restore media
docker compose -f docker-compose.prod.yml exec -T web tar xzf - -C / < /backups/media_20260918_020000.tar.gz

# Restart services
docker compose -f docker-compose.prod.yml restart
```

## Troubleshooting

### Service Won't Start
```bash
# Check Docker daemon
sudo systemctl status docker

# Check for port conflicts
sudo netstat -tulpn | grep -E ':80|:443|:5432|:6379'

# Check service logs
docker compose -f docker-compose.prod.yml logs web
```

### Database Connection Issues
```bash
# Check database is healthy
docker compose -f docker-compose.prod.yml ps db

# Test connection
docker compose -f docker-compose.prod.yml exec web python manage.py dbshell
```

### Migration Issues
```bash
# Check migration status
docker compose -f docker-compose.prod.yml exec web python manage.py showmigrations

# Apply pending migrations
docker compose -f docker-compose.prod.yml exec web python manage.py migrate
```

### Memory Issues
```bash
# Check resource usage
docker stats

# Restart a memory-hungry service
docker compose -f docker-compose.prod.yml restart celery-worker
```

## Production Security Checklist

- [ ] `DEBUG=False`
- [ ] Fresh `DJANGO_SECRET_KEY` (50+ chars)
- [ ] Fresh `FERNET_KEY`
- [ ] Fresh `JWT_SECRET_KEY`
- [ ] `ALLOWED_HOSTS` set to actual domain
- [ ] `CORS_ALLOWED_ORIGINS` set to frontend domain
- [ ] TLS certificates installed in `ssl/`
- [ ] Database password is strong
- [ ] Redis has no external access (internal only)
- [ ] Exchange API keys are production keys
- [ ] Sentry DSN configured
- [ ] Backup cron job running
