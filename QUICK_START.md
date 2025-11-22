# Quick Start Guide - Torgovo Trading Platform

## 🚀 Quick Docker Setup

### 1. Prerequisites
Make sure you have Docker and Docker Compose installed:
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (includes Docker Compose)

### 2. Run the Platform

```bash
# Clone the repository
git clone <your-repository-url>
cd torgovo

# Start all services
docker-compose -f docker-compose.dev.yml up -d --build
```

### 3. Initialize the Platform

```bash
# Wait 30 seconds for services to start, then run:
docker-compose -f docker-compose.dev.yml exec web python manage.py migrate

# Create a superuser account
docker-compose -f docker-compose.dev.yml exec web python manage.py createsuperuser

# Optional: Create initial data (exchanges, subscription plans)
docker-compose -f docker-compose.dev.yml exec web python manage.py shell << 'EOF'
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
    {'name': 'Free', 'description': 'Basic trading features', 'price_per_month': 0, 'currency': 'USD'},
    {'name': 'Premium', 'description': 'Advanced trading features', 'price_per_month': 29.99, 'currency': 'USD'},
    {'name': 'Enterprise', 'description': 'Professional trading platform', 'price_per_month': 99.99, 'currency': 'USD'},
]

for plan_data in plans:
    SubscriptionPlan.objects.get_or_create(
        name=plan_data['name'],
        defaults=plan_data
    )

print("✅ Initial data created successfully!")
EOF
```

### 4. Access the Platform

- **API Base URL**: http://localhost:8000/api/
- **Admin Panel**: http://localhost:8000/admin/
- **Health Check**: http://localhost:8000/health/

### 5. Test the API

```bash
# Test health endpoint
curl http://localhost:8000/health/

# Test authentication
curl -X POST http://localhost:8000/api/auth/register/ \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"SecurePass123!","full_name":"Test User"}'
```

## 🛠 Common Commands

### Service Management
```bash
# View all services
docker-compose -f docker-compose.dev.yml ps

# View logs
docker-compose -f docker-compose.dev.yml logs -f web

# Stop all services
docker-compose -f docker-compose.dev.yml down

# Restart services
docker-compose -f docker-compose.dev.yml restart web
```

### Database Operations
```bash
# Run migrations
docker-compose -f docker-compose.dev.yml exec web python manage.py migrate

# Create superuser
docker-compose -f docker-compose.dev.yml exec web python manage.py createsuperuser

# Access Django shell
docker-compose -f docker-compose.dev.yml exec web python manage.py shell

# Access database directly
docker-compose -f docker-compose.dev.yml exec db psql -U postgres -d torgovo
```

### Development
```bash
# Rebuild after code changes
docker-compose -f docker-compose.dev.yml up -d --build

# Run Django tests
docker-compose -f docker-compose.dev.yml exec web python manage.py test

# Collect static files
docker-compose -f docker-compose.dev.yml exec web python manage.py collectstatic --noinput
```

## 🔧 Troubleshooting

### Port Already in Use
If port 8000 is already in use:
```bash
# Find what's using the port
netstat -tulpn | grep :8000

# Or use a different port
docker-compose -f docker-compose.dev.yml up -d --scale web=1 -p 8001:8000
```

### Build Failures
If the build fails:
```bash
# Clean up and rebuild
docker-compose -f docker-compose.dev.yml down
docker system prune -f
docker-compose -f docker-compose.dev.yml up -d --build
```

### Database Connection Issues
If you see database connection errors:
```bash
# Restart database service
docker-compose -f docker-compose.dev.yml restart db

# Check database logs
docker-compose -f docker-compose.dev.yml logs db
```

### Permission Issues
If you encounter permission errors:
```bash
# Fix permissions on Linux/Mac
sudo chown -R $USER:$USER .

# On Windows, run Docker Desktop as Administrator
```

## 📚 Next Steps

1. **Frontend Development**: Use the `FRONTEND_REQUIREMENTS.md` to build your React/Vue frontend
2. **API Testing**: Explore the API endpoints at http://localhost:8000/admin/
3. **Exchange Setup**: Configure your exchange API keys in the admin panel
4. **Bot Testing**: Create and test trading bots through the API or admin interface

## 📖 Documentation

- **API Documentation**: `API_DOCUMENTATION.md`
- **Frontend Requirements**: `FRONTEND_REQUIREMENTS.md`
- **Full Docker Guide**: `DOCKER_DEPLOYMENT.md`
- **Platform Overview**: `README.md`

## 🆘 Support

If you encounter issues:
1. Check the logs: `docker-compose -f docker-compose.dev.yml logs`
2. Verify all services are running: `docker-compose -f docker-compose.dev.yml ps`
3. Check this guide for common solutions
4. Review the full `DOCKER_DEPLOYMENT.md` for detailed troubleshooting

Happy Trading! 🚀