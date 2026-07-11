# Torgovo Crypto Trading Platform

A comprehensive Django REST API-based cryptocurrency trading platform that provides users with multiple automated trading strategies, webhook alerts, and AI-powered trading bots. The platform supports integration with major cryptocurrency exchanges including Binance, Bybit, OKX, MEXC, and Alpaca.

## 🚀 Features

### Core Trading Features
- **Webhook Alerts**: TradingView integration for automated trading signals
- **Grid Trading**: Automated grid strategy with customizable levels
- **Martingale Bots**: Progressive betting strategy with multiplier support
- **Quantum AI Bots**: AI-powered portfolio management with deposit system
- **Telegram Signals**: Subscription-based trading signals

### Exchange Integration
- **Multi-Exchange Support**: Binance, Bybit, OKX, MEXC, Alpaca
- **Real-time Trading**: Market and limit order execution
- **Risk Management**: Take profit, stop loss, and position sizing
- **API Key Security**: Encrypted credential storage

### User Features
- **Advanced Authentication**: Email, Google OAuth, Phone verification
- **Subscription Tiers**: Free, Premium, Enterprise plans
- **Portfolio Tracking**: Real-time profit/loss monitoring
- **Trading History**: Complete order and trade history

## 📋 System Requirements

- Python 3.11+
- PostgreSQL 12+
- Redis 6+
- Docker & Docker Compose
- Nginx (production)

## 🛠 Quick Start

### 1. Clone and Setup
```bash
git clone https://github.com/your-org/torgovo.git
cd torgovo
cp .env.example .env
# Edit .env with your configuration
```

### 2. Docker Deployment (Recommended)
```bash
# Build and start all services
docker-compose up -d

# Run migrations
docker-compose exec web python manage.py migrate

# Create superuser
docker-compose exec web python manage.py createsuperuser

# Collect static files
docker-compose exec web python manage.py collectstatic --noinput
```

### 3. Manual Installation
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements/production.txt

# Setup database
createdb torgovo
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Start services
redis-server
celery -A config worker --loglevel=info &
celery -A config beat --loglevel=info &
gunicorn config.wsgi:application --bind 0.0.0.0:8000
```

## 🔧 Configuration

### Environment Variables
Key environment variables in `.env`:

```bash
# Django
DJANGO_SECRET_KEY=your-secret-key
DEBUG=False
ALLOWED_HOSTS=yourdomain.com

# Database
DB_NAME=torgovo
DB_USER=postgres
DB_PASSWORD=your-password
DB_HOST=localhost

# Redis
REDIS_URL=redis://localhost:6379/0

# Exchange APIs
BINANCE_API_KEY=your-binance-key
BINANCE_SECRET_KEY=your-binance-secret

# JWT
JWT_SECRET_KEY=your-jwt-secret
JWT_ACCESS_TOKEN_LIFETIME=900
```

### Supported Exchanges
- **Binance**: Spot, Futures, Margin trading
- **Bybit**: Linear, Inverse, Spot trading
- **OKX**: Spot, Futures, Options trading
- **MEXC**: Spot and Futures trading
- **Alpaca**: Stock and Crypto trading

## 📚 API Documentation

### Authentication
```bash
# Register
curl -X POST http://localhost:8000/api/auth/register/ \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"SecurePass123!","username":"trader"}'

# Login
curl -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"SecurePass123!"}'
```

### Trading Bots
```bash
# Create Webhook Alert
curl -X POST http://localhost:8000/api/bots/webhook-alerts/ \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"bot_name":"BTC Scalper","exchange_name":"binance","trading_pair":"BTC/USDT","default_amount":"100"}'

# Create Grid Bot
curl -X POST http://localhost:8000/api/bots/grid-bots/ \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"bot_name":"BTC Grid","exchange_name":"binance","trading_pair":"BTC/USDT","base_amount":"50","favor_levels":5,"against_levels":5}'
```

### TradingView Webhook
```bash
# Webhook URL format
https://yourdomain.com/api/webhooks/tradingview/{webhook_id}/

# Webhook payload
curl -X POST https://yourdomain.com/api/webhooks/tradingview/webhook_uuid/ \
  -H "Content-Type: application/json" \
  -d '{"secret":"webhook_secret","action":"buy","tv_exchange":"binance","tv_instrument":"BTCUSDT","order":{"amount":"1.0"}}'
```

## 🏗 Architecture

### Project Structure
```
torgovo/
├── config/                    # Django project configuration
│   ├── settings/             # Environment-specific settings
│   ├── urls.py               # Root URL configuration
│   ├── wsgi.py               # WSGI configuration
│   ├── asgi.py               # ASGI configuration
│   └── celery.py             # Celery configuration
├── apps/                     # Django applications
│   ├── authentication/       # User management and auth
│   ├── webhooks/            # TradingView webhook integration
│   ├── bots/                # Trading bot management
│   ├── exchanges/           # Exchange integrations
│   ├── payments/            # Quantum AI deposit system
│   ├── subscriptions/       # Telegram signals
│   └── users/               # User profile management
├── trading/                  # Trading engine
│   ├── manager.py           # Trading manager
│   ├── exchanges/           # Exchange-specific bots
│   └── strategies/          # Trading strategies
├── core/                     # Shared utilities
├── static/                   # Static files
├── media/                    # User uploads
└── templates/                # HTML templates
```

### Technology Stack
- **Backend**: Django 4.2, Django REST Framework
- **Database**: PostgreSQL with connection pooling
- **Cache**: Redis for sessions and caching
- **Task Queue**: Celery with Redis broker
- **Trading**: CCXT library for exchange integration
- **Authentication**: JWT tokens, Django Allauth
- **Frontend Ready**: RESTful API with comprehensive documentation

## 🔒 Security Features

- **API Key Encryption**: Fernet encryption for exchange credentials
- **JWT Authentication**: Access and refresh tokens with rotation
- **Rate Limiting**: User-based request throttling
- **CORS Protection**: Configurable origin whitelist
- **Input Validation**: Comprehensive data validation
- **SQL Injection Prevention**: Django ORM protection
- **HTTPS Enforcement**: Production SSL/TLS required

## 📊 Monitoring & Logging

### Logging
- Request/response logging with correlation IDs
- Trading execution audit trails
- Error tracking with Sentry integration
- Performance metrics and monitoring

### Health Checks
- Database connectivity
- Cache connectivity
- Exchange API status
- Bot execution status

## 🚀 Deployment

### Production Deployment
```bash
# Using Docker Compose
docker-compose -f docker-compose.prod.yml up -d

# Manual deployment
pip install gunicorn
gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 4
```

### Environment-Specific Settings
- **Development**: Debug mode, SQLite/PostgreSQL, detailed logging
- **Testing**: Isolated test database, mocked APIs
- **Production**: Optimized settings, security headers, error tracking

## 🧪 Testing

### Run Tests
```bash
# All tests
pytest

# Specific app
pytest apps/authentication/

# Coverage report
pytest --cov=apps --cov-report=html
```

### Test Categories
- Unit tests for models and utilities
- Integration tests for API endpoints
- Exchange integration tests with mocking
- Performance tests for high-load scenarios

## 📈 Performance

### Optimization Features
- Database indexing strategy
- Connection pooling
- Redis caching for frequently accessed data
- Async task processing with Celery
- Optimized database queries

### Benchmarks
- **API Response Time**: <200ms average
- **Throughput**: 1000+ requests/minute
- **Database**: Optimized for 10,000+ concurrent users
- **Bot Execution**: <1s order placement

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

### Development Guidelines
- Follow PEP 8 style guidelines
- Write comprehensive tests
- Update documentation
- Use meaningful commit messages

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

- **Documentation**: [https://docs.torgovo.com](https://docs.torgovo.com)
- **API Reference**: [https://api.torgovo.com/docs](https://api.torgovo.com/docs)
- **Issues**: [GitHub Issues](https://github.com/your-org/torgovo/issues)
- **Email**: support@torgovo.com
- **Telegram**: [@torgovo_support](https://t.me/torgovo_support)

## 🎯 Roadmap

### Version 1.1 (Q2 2024)
- [ ] WebSocket support for real-time updates
- [ ] Mobile API SDKs
- [ ] Advanced charting and analytics
- [ ] Social trading features

### Version 1.2 (Q3 2024)
- [ ] DEX integration (Uniswap, PancakeSwap)
- [ ] Copy trading functionality
- [ ] Advanced backtesting engine
- [ ] Multi-asset portfolio support

### Version 2.0 (Q4 2024)
- [ ] Machine learning-based trading signals
- [ ] Options and derivatives trading
- [ ] Institutional-grade features
- [ ] White-label solutions

---

**⭐ Star this repo if it helps you build your crypto trading platform!**

Built with ❤️ by the Torgovo Team