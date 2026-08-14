# Docker Deployment Guide - Torgovo Trading Platform

This guide provides step-by-step instructions for deploying the Torgovo crypto trading platform using Docker and Docker Compose.

## 📋 Prerequisites

### System Requirements
- **Operating System**: Linux (Ubuntu 20.04+), macOS, or Windows 10+ with WSL2
- **Docker**: Version 20.10+
- **Docker Compose**: Version 2.0+
- **RAM**: Minimum 4GB, Recommended 8GB+
- **Storage**: Minimum 20GB free space
- **Network**: Stable internet connection for exchange APIs

### Install Docker

#### Ubuntu/Debian
```bash
# Update package index
sudo apt-get update

# Install packages to allow apt to use a repository over HTTPS
sudo apt-get install ca-certificates curl gnupg lsb-release

# Add Docker's official GPG key
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# Set up the repository
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker Engine
sudo apt-get update
sudo apt-get install docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Start and enable Docker
sudo systemctl start docker
sudo systemctl enable docker

# Add your user to docker group (run this and logout/login)
sudo usermod -aG docker $USER
```

#### macOS
```bash
# Download and install Docker Desktop
# Visit: https://docs.docker.com/desktop/mac/install/

# Or using Homebrew
brew install --cask docker
```

#### Windows
```bash
# Download and install Docker Desktop
# Visit: https://docs.docker.com/desktop/windows/install/

# Ensure WSL2 is enabled
wsl --install
```

## 🚀 Quick Start

### 1. Clone the Repository
```bash
git clone <your-repository-url>
cd torgovo
```

### 2. Environment Configuration
```bash
# Copy environment template
cp .env.example .env

# Edit environment file
nano .env  # or use your preferred editor
```

**Required Environment Variables:**
```bash
# Generate secure secrets
DJANGO_SECRET_KEY=$(python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')
JWT_SECRET_KEY=$(openssl rand -hex 32)
FERNET_KEY=$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')

# Database
DB_NAME=torgovo
DB_USER=postgres
DB_PASSWORD=your-secure-database-password
DB_HOST=db
DB_PORT=5432

# Redis
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

# Frontend URLs
FRONTEND_URL=http://localhost:3000
BASE_URL=http://localhost:8000

# For development
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
```

### 3. Build and Start Services
```bash
# Build all services and start in detached mode
docker-compose up -d --build

# View logs (optional)
docker-compose logs -f
```

### 4. Initialize Database
```bash
# Wait for services to be ready (30-60 seconds)
sleep 60

# Run database migrations
docker-compose exec web python manage.py migrate

# Create superuser account
docker-compose exec web python manage.py createsuperuser

# Collect static files
docker-compose exec web python manage.py collectstatic --noinput

# Create initial data (exchanges, subscription plans)
docker-compose exec web python manage.py shell << EOF
from apps.bots.models import Exchange
from apps.subscriptions.models import SubscriptionPlan

# Create exchanges
exchanges = [
    {'name': 'binance', 'display_name': 'Binance', 'api_base_url': 'https://api.binance.com'},
    {'name': 'bybit', 'display_name': 'Bybit', 'api_base_url': 'https://api.bybit.com'},
    {'name': 'okx', 'display_name': 'OKX', 'api_base_url': 'https://www.okx.com'},
    {'name': 'mexc', 'display_name': 'MEXC', 'api_base_url': 'https://api.mexc.com'},
    {'name': 'alpaca', 'display_name': 'Alpaca', 'api_base_url': 'https://api.alpaca.com'},
]

for exchange_data in exchanges:
    Exchange.objects.get_or_create(
        name=exchange_data['name'],
        defaults=exchange_data
    )

# Create subscription plans
plans = [
    {
        'name': 'Free',
        'description': 'Basic trading features',
        'price_per_month': 0,
        'currency': 'USD',
        'max_bots': 3,
        'trial_days': 0
    },
    {
        'name': 'Premium',
        'description': 'Advanced trading features',
        'price_per_month': 29.99,
        'currency': 'USD',
        'max_bots': 15,
        'trial_days': 14
    },
    {
        'name': 'Enterprise',
        'description': 'Professional trading platform',
        'price_per_month': 99.99,
        'currency': 'USD',
        'max_bots': 50,
        'trial_days': 30
    }
]

for plan_data in plans:
    SubscriptionPlan.objects.get_or_create(
        name=plan_data['name'],
        defaults=plan_data
    )

print("Initial data created successfully!")
EOF
```

### 5. Verify Deployment
```bash
# Check service status
docker-compose ps

# Test health endpoint
curl http://localhost:8000/health/

# Test API endpoint
curl http://localhost:8000/api/auth/register/
```

### 6. Access Services

- **API**: http://localhost:8000
- **Admin Panel**: http://localhost:8000/admin/
- **API Documentation**: http://localhost:8000/api/docs/
- **Database**: localhost:5432
- **Redis**: localhost:6379

## 🐳 Docker Compose Services

### Service Breakdown

#### **web** (Django Application)
- **Port**: 8000
- **Purpose**: Main Django application with REST API
- **Environment**: All environment variables from .env
- **Health Check**: HTTP health endpoint every 30 seconds

```yaml
web:
  build: .
  ports:
    - "8000:8000"
  depends_on:
    - db
    - redis
  environment:
    - DJANGO_SECRET_KEY=${DJANGO_SECRET_KEY}
    - DEBUG=${DEBUG}
    - DB_HOST=db
    - REDIS_URL=redis://redis:6379/0
```

#### **db** (PostgreSQL Database)
- **Port**: 5432
- **Purpose**: Primary database storage
- **Volume**: Persistent data storage
- **Health Check**: Database connectivity check

```yaml
db:
  image: postgres:15
  environment:
    POSTGRES_DB: ${DB_NAME}
    POSTGRES_USER: ${DB_USER}
    POSTGRES_PASSWORD: ${DB_PASSWORD}
  volumes:
    - postgres_data:/var/lib/postgresql/data
```

#### **redis** (Cache & Message Broker)
- **Port**: 6379
- **Purpose**: Caching and Celery message broker
- **Volume**: Persistent data storage
- **Health Check**: Redis ping check

```yaml
redis:
  image: redis:7-alpine
  command: redis-server --appendonly yes
  volumes:
    - redis_data:/data
```

#### **celery-worker** (Background Tasks)
- **Purpose**: Execute asynchronous tasks
- **Concurrency**: 4 worker processes
- **Dependencies**: Database and Redis

```yaml
celery-worker:
  build: .
  command: celery -A config worker --loglevel=info --concurrency=4
  depends_on:
    - db
    - redis
```

#### **celery-beat** (Scheduled Tasks)
- **Purpose**: Execute periodic tasks
- **Dependencies**: Database and Redis

```yaml
celery-beat:
  build: .
  command: celery -A config beat --loglevel=info
  depends_on:
    - db
    - redis
```

#### **nginx** (Reverse Proxy - Optional)
- **Ports**: 80, 443
- **Purpose**: Load balancing and SSL termination
- **Dependencies**: Web service

```yaml
nginx:
  image: nginx:alpine
  ports:
    - "80:80"
    - "443:443"
  volumes:
    - ./nginx.conf:/etc/nginx/nginx.conf
  depends_on:
    - web
```

## 🔧 Common Docker Commands

### Service Management
```bash
# Start all services
docker-compose up -d

# Stop all services
docker-compose down

# Restart all services
docker-compose restart

# Restart specific service
docker-compose restart web

# View service logs
docker-compose logs web

# View logs in real-time
docker-compose logs -f web

# View all service logs
docker-compose logs
```

### Database Operations
```bash
# Connect to database
docker-compose exec db psql -U postgres -d torgovo

# Create database backup
docker-compose exec db pg_dump -U postgres torgovo > backup_$(date +%Y%m%d_%H%M%S).sql

# Restore database backup
docker-compose exec -T db psql -U postgres torgovo < backup_file.sql

# Access Django shell
docker-compose exec web python manage.py shell
```

### Maintenance
```bash
# Update Django models
docker-compose exec web python manage.py migrate

# Create superuser
docker-compose exec web python manage.py createsuperuser

# Collect static files
docker-compose exec web python manage.py collectstatic --noinput

# Run Django tests
docker-compose exec web python manage.py test

# Check Django configuration
docker-compose exec web python manage.py check
```

### Monitoring
```bash
# Check resource usage
docker stats

# Check service status
docker-compose ps

# Inspect service
docker-compose inspect web

# Execute command in container
docker-compose exec web ls -la
```

## 🚀 Production Deployment

### 1. Production Environment Setup
```bash
# Create production environment file
cp .env.example .env.production

# Edit production settings
nano .env.production
```

**Production Environment Variables:**
```bash
# Security
DEBUG=False
DJANGO_SECRET_KEY=your-super-secure-secret-key
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com

# SSL/HTTPS
SECURE_SSL_REDIRECT=True
SECURE_HSTS_SECONDS=31536000
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True

# Database (use strong passwords)
DB_PASSWORD=your-production-database-password

# Frontend URLs
FRONTEND_URL=https://yourdomain.com
BASE_URL=https://api.yourdomain.com

# CORS
CORS_ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
```

### 2. SSL Certificate Setup
```bash
# Create SSL directory
mkdir -p ssl

# Generate self-signed certificate (for testing)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout ssl/torgovo.key \
  -out ssl/torgovo.crt \
  -subj "/C=US/ST=State/L=City/O=Organization/CN=yourdomain.com"

# For production, use Let's Encrypt
sudo apt-get install certbot
sudo certbot certonly --standalone -d yourdomain.com -d api.yourdomain.com
sudo cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem ssl/torgovo.crt
sudo cp /etc/letsencrypt/live/yourdomain.com/privkey.pem ssl/torgovo.key
```

### 3. Production Docker Compose
```bash
# Create production compose file
cp docker-compose.yml docker-compose.prod.yml

# Edit production settings
nano docker-compose.prod.yml
```

**Production modifications:**
```yaml
# Remove port mapping for internal services
# Keep only necessary external ports
ports:
  - "80:80"
  - "443:443"

# Add health checks
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/health/"]
  interval: 30s
  timeout: 10s
  retries: 3

# Add resource limits
deploy:
  resources:
    limits:
      memory: 1G
    reservations:
      memory: 512M
```

### 4. Deploy Production
```bash
# Use production environment file
docker-compose --env-file .env.production -f docker-compose.prod.yml up -d --build

# Run production migrations
docker-compose --env-file .env.production -f docker-compose.prod.yml exec web python manage.py migrate

# Collect static files
docker-compose --env-file .env.production -f docker-compose.prod.yml exec web python manage.py collectstatic --noinput
```

## 🔍 Troubleshooting

### Common Issues

#### **Service Won't Start**
```bash
# Check Docker daemon
sudo systemctl status docker

# Check Docker Compose version
docker-compose --version

# Check for port conflicts
sudo netstat -tulpn | grep :8000

# Check service logs
docker-compose logs web
```

#### **Database Connection Issues**
```bash
# Check database service
docker-compose ps db

# Check database logs
docker-compose logs db

# Test database connection
docker-compose exec web python manage.py dbshell
```

#### **Migration Issues**
```bash
# Check current migrations
docker-compose exec web python manage.py showmigrations

# Reset migrations (last resort)
docker-compose exec web python manage.py migrate app_name zero
docker-compose exec web python manage.py migrate app_name
```

#### **Permission Issues**
```bash
# Fix file permissions
sudo chown -R $USER:$USER .

# Check Docker group membership
groups $USER

# Add to docker group if needed
sudo usermod -aG docker $USER
```

#### **Memory Issues**
```bash
# Check memory usage
docker stats

# Increase Docker memory limits
# In Docker Desktop: Settings > Resources > Memory
```

### Performance Optimization

#### **Database Performance**
```bash
# Enable connection pooling in settings.py
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'OPTIONS': {
            'MAX_CONNS': 20,
            'MIN_CONNS': 5,
        }
    }
}
```

#### **Redis Performance**
```bash
# Enable Redis persistence
redis-cli CONFIG SET save "900 1 300 10 60 10000"
```

#### **Application Performance**
```bash
# Scale worker processes
docker-compose up -d --scale celery-worker=4

# Enable Gunicorn tuning
# In Dockerfile or command:
gunicorn config.wsgi:application --workers 4 --worker-class gevent
```

## 📊 Monitoring and Logging

### Application Logs
```bash
# View application logs
docker-compose logs -f web

# View structured logs with filtering
docker-compose logs web | grep ERROR
```

### Database Monitoring
```bash
# Connect to PostgreSQL monitoring
docker-compose exec db psql -U postgres -d torgovo -c "SELECT * FROM pg_stat_activity;"

# Monitor slow queries
docker-compose exec db psql -U postgres -d torgovo -c "SELECT query, mean_time, calls FROM pg_stat_statements ORDER BY mean_time DESC LIMIT 10;"
```

### Health Checks
```bash
# Check all service health
docker-compose exec web curl -f http://localhost:8000/health/

# Monitor service availability
watch -n 5 'curl -s http://localhost:8000/health/ | jq .'
```

## 🔄 Backup and Recovery

### Automated Backups
```bash
# Create backup script
cat > backup.sh << 'EOF'
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups"

# Create backup directory
mkdir -p $BACKUP_DIR

# Database backup
docker-compose exec -T db pg_dump -U postgres torgovo > $BACKUP_DIR/db_backup_$DATE.sql

# Media files backup
docker cp $(docker-compose ps -q web):/app/media $BACKUP_DIR/media_$DATE

# Remove old backups (keep last 7 days)
find $BACKUP_DIR -name "*.sql" -mtime +7 -delete
find $BACKUP_DIR -name "media_*" -mtime +7 -delete

echo "Backup completed: $DATE"
EOF

chmod +x backup.sh

# Add to crontab for daily backups
crontab -e
# Add line: 0 2 * * * /path/to/torgovo/backup.sh
```

### Disaster Recovery
```bash
# Restore database from backup
docker-compose exec -T db psql -U postgres torgovo < backup_20240101_020000.sql

# Restore media files
docker cp media_20240101_020000/. $(docker-compose ps -q web):/app/media/

# Restart services
docker-compose restart
```

## 🛠️ Development Workflow

### Development Environment
```bash
# Start development environment
docker-compose -f docker-compose.dev.yml up -d

# Enable hot reload (development only)
docker-compose exec web python manage.py runserver 0.0.0.0:8000

# Debug with Django Debug Toolbar
pip install django-debug-toolbar
# Add 'debug_toolbar' to INSTALLED_APPS in development settings
```

### Code Updates
```bash
# Rebuild after code changes
docker-compose up -d --build

# Update specific service
docker-compose up -d --build web

# Pull latest changes and rebuild
git pull
docker-compose down
docker-compose up -d --build
```

This comprehensive Docker deployment guide covers everything from initial setup to production deployment, monitoring, and maintenance of the Torgovo trading platform.
