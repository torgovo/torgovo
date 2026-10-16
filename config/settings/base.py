"""
Base settings for Torgovo Crypto Trading Platform
"""

import os
from pathlib import Path

from decouple import config

SENTRY_DSN = os.environ.get("SENTRY_DSN", "")

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Ensure the log directory exists (gitignored) so RotatingFileHandler
# handlers below and in development.py don't fail on a fresh checkout.
(BASE_DIR / "logs").mkdir(parents=True, exist_ok=True)

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config("DJANGO_SECRET_KEY")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config("DEBUG", default=False, cast=bool)

ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS", default="", cast=lambda v: [s.strip() for s in v.split(",")]
)
FRONTEND_URL = config("FRONTEND_URL", default="http://localhost:3000")
# Public site origin — used to build user-facing links (e.g. referral links).
# Production: https://torgovo.com (frontend also reachable via torgovo.vercel.app).
SITE_URL = config("SITE_URL", default="https://torgovo.com")

# Compliance / Consent versions (COMPLIANCE Phase-1)
# Bump when the legal documents change; consents recorded against an older
# version are considered stale and must be re-accepted in-app.
PRIVACY_POLICY_VERSION = "2026-08-1"
TERMS_VERSION = "2026-08-1"

# Application definition
DJANGO_APPS = [
    "django_prometheus",
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
]

THIRD_PARTY_APPS = [
    "health_check",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "corsheaders",
    "channels",
    "drf_yasg",
    # 'allauth',  # Temporarily disabled
    # 'allauth.account',
    # 'allauth.socialaccount',
    # 'allauth.socialaccount.providers.google',
]

LOCAL_APPS = [
    "apps.authentication",
    "apps.webhooks",
    "apps.bots",
    "apps.trading",  # New unified trading app
    "apps.exchanges",  # Will be removed after migration
    "apps.payments",
    "apps.subscriptions",
    "apps.users",
    "apps.investments",
    "apps.referrals",
    "apps.analytics",
    "core",
]
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS
MIDDLEWARE = [
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.RequestLoggingMiddleware",
    "core.middleware.RequestBodyLimitMiddleware",
    "core.middleware.SecurityHeadersMiddleware",
    "core.middleware.CorrelationIDMiddleware",
    "core.middleware.AuthRateLimitMiddleware",
    "core.middleware.RateLimitMiddleware",
    "django_prometheus.middleware.PrometheusAfterMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [config("REDIS_URL", default="redis://127.0.0.1:6379/0")],
        },
    },
}

# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("DB_NAME", default="torgovo"),
        "USER": config("DB_USER", default="postgres"),
        "PASSWORD": config("DB_PASSWORD"),
        "HOST": config("DB_HOST", default="localhost"),
        "PORT": config("DB_PORT", default="5432"),
        "OPTIONS": {
            "connect_timeout": 60,
        },
    }
}

# Cache configuration
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": config("REDIS_URL", default="redis://127.0.0.1:6379/1"),
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Custom User Model
AUTH_USER_MODEL = "users.CustomUser"

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [
    BASE_DIR / "static",
]

# Media files
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Django REST Framework
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "core.pagination.StandardResultsSetPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "rest_framework.schemas.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "core.exceptions.custom_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
        "user": "1000/hour",
        # Scoped: protect sensitive endpoints from credential-stuffing /
        # webhook flooding.
        "login": "20/hour",
        "register": "20/hour",
        "password_reset": "10/hour",
        "webhook": "120/min",
        "withdrawal": "5/hour",
        "phone_verification": "5/hour",
        "two_factor": "5/hour",
    },
}

# JWT Configuration
from datetime import timedelta  # noqa: E402  (config block import)

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=config("JWT_ACCESS_TOKEN_LIFETIME", default=15, cast=int)
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=config("JWT_REFRESH_TOKEN_LIFETIME", default=7, cast=int)
    ),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    # SECURITY (HIGH-4): JWT signing key MUST be separate from DJANGO_SECRET_KEY.
    # Sharing keys means rotating one invalidates the other. No fallback.
    "SIGNING_KEY": config("JWT_SECRET_KEY"),
    "VERIFYING_KEY": None,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
    "USER_ID_FIELD": "id",
}

ACCOUNT_USERNAME_REQUIRED = False
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_USER_MODEL_EMAIL_FIELD = "email"

# Google OAuth Configuration
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "SCOPE": [
            "profile",
            "email",
        ],
        "AUTH_PARAMS": {
            "access_type": "online",
        },
        "APP": {
            "client_id": config("GOOGLE_CLIENT_ID", default=""),
            "secret": config("GOOGLE_SECRET_KEY", default=""),
        },
    }
}

# CORS Configuration
CORS_ALLOW_ALL_ORIGINS = config("CORS_ALLOW_ALL_ORIGINS", default=False, cast=bool)
# SECURITY (LOW-5): filter empty strings caused by trailing commas in .env
CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    default="",
    cast=lambda v: [s.strip() for s in v.split(",") if s.strip()],
)

# Security Settings
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_HSTS_SECONDS = config("SECURE_HSTS_SECONDS", default=31536000, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=False, cast=bool)

# Logging Configuration
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "cred_redact": {
            "()": "core.logging_filters.CredentialRedactionFilter",
        },
        "request_id": {
            "()": "core.request_id_filter.RequestIDFilter",
        },
    },
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
        "json": {
            "()": "core.json_formatter.JSONFormatter",
        },
    },
    "handlers": {
        "file": {
            "level": "INFO",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": BASE_DIR / "logs" / "django.log",
            "maxBytes": 1024 * 1024 * 15,  # 15MB
            "backupCount": 10,
            "formatter": "verbose",
            "filters": ["cred_redact", "request_id"],
        },
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "simple",
            "filters": ["cred_redact", "request_id"],
        },
        "json_file": {
            "level": "INFO",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": BASE_DIR / "logs" / "django-json.log",
            "maxBytes": 1024 * 1024 * 15,  # 15MB
            "backupCount": 10,
            "formatter": "json",
            "filters": ["cred_redact", "request_id"],
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["file", "console"],
            "level": "INFO",
            "propagate": False,
        },
        "apps": {
            "handlers": ["file", "console"],
            "level": "INFO",
            "propagate": False,
        },
        "trading": {
            "handlers": ["file", "console"],
            # SECURITY (MED-3): DEBUG in base settings risks logging CCXT raw
            # HTTP bodies (partial API keys, account balances). Override to
            # DEBUG only in development.py.
            "level": "INFO",
            "propagate": False,
        },
    },
}

# Celery Configuration
# Defaults match .env.example (redis://127.0.0.1:6379/0)
CELERY_BROKER_URL = config("CELERY_BROKER_URL", default="redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = config("CELERY_RESULT_BACKEND", default="redis://127.0.0.1:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE

# Encryption key for API keys
# Check os.environ first so tests can inject a valid key without .env interference.
# decouple gives .env priority over os.environ (ConfigEnv.get() uses `data or environ`),
# which would otherwise make test key injection impossible.  Production via Docker
# has no .env file (ConfigShell → os.environ only), so both paths resolve identically.
# Other settings keep plain config() because they don't need test-time injection.
FERNET_KEY = os.environ.get("FERNET_KEY") or config("FERNET_KEY")

from cryptography.fernet import Fernet  # noqa: E402  (requires FERNET_KEY resolved above)

try:
    Fernet(FERNET_KEY.encode())
except Exception:
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured(
        "FERNET_KEY is invalid. Generate a valid key with:\n"
        '  python -c "from cryptography.fernet import Fernet; '
        'print(Fernet.generate_key().decode())"'
    )

# File Upload Configuration
FILE_UPLOAD_MAX_MEMORY_SIZE = 5242880  # 5MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 5242880  # 5MB

# Exchange API Configuration
EXCHANGE_CONFIG = {
    "RATE_LIMIT_DEFAULT": 1200,  # requests per minute
    "RATE_LIMIT_PREMIUM": 6000,  # requests per minute for premium users
    "DEFAULT_TIMEOUT": 30,  # seconds
    "MAX_RETRIES": 3,
    "RETRY_DELAY": 1,  # seconds
}

# Bot limits are managed via SiteConfig in DB (core/models.py:135)
# The old BOT_CONFIG dict was removed — SiteConfig.get_plan_limit() is the
# single source of truth, runtime-configurable without redeploy.

# Payment Quote Configuration (G2 / FR A3 — manual multi-coin payments)
# Quote TTL: exchange-style price lock. Default 15s per product decision
# (10-15s typical, hard max 60s — service clamps any config value to 1..60).
# FR A3 quote refresh cadence (default 5 minutes — FE auto-updates the
# combined amount while the payment window is open). Clamped to 60..3600 in
# apps/payments/services/quote.py.
PAYMENT_QUOTE_TTL_SECONDS = config("PAYMENT_QUOTE_TTL_SECONDS", default=300, cast=int)
# CCXT exchange used for the public USD ticker when locking a quote price.
PAYMENT_QUOTE_EXCHANGE = config("PAYMENT_QUOTE_EXCHANGE", default="bybit")
# Coins assumed pegged 1:1 to USD when no live ticker pair is available.
# Non-stable coins with no ticker MUST fail the quote (never silently peg).
PAYMENT_STABLE_COINS = ["USDT", "USDC"]

# Subscription expiry lifecycle (G4 / FR A6) — admin-driven, no hard-codes.
# Grace days: after expires_at the user keeps FULL access for this long,
# then hard-stop (no new bot entries). Open positions are never touched.
SUBSCRIPTION_GRACE_PERIOD_DAYS = config("SUBSCRIPTION_GRACE_PERIOD_DAYS", default=2, cast=int)
# Reminder offsets, in days BEFORE expires_at. Comma-separated env string
# parsed to a list of ints, e.g. "7,5,3,1". Each offset emails once per
# paid term (idempotency ledger on BotSubscription.expiry_reminders_sent).
SUBSCRIPTION_REMINDER_OFFSET_DAYS = [
    int(d.strip())
    for d in config("SUBSCRIPTION_REMINDER_OFFSET_DAYS", default="7,5,3,1").split(",")
    if d.strip().isdigit()
]

# Resend API key — FALLBACK delivery path behind core.email.send_email()
# (FR Part B Q22: own SMTP primary, Resend/SendGrid fallback). Empty =
# fallback disabled, SMTP only.
RESEND_API_KEY = config("RESEND_API_KEY", default="")

# Quantum AI Configuration
QUANTUM_AI_CONFIG = {
    "SUPPORTED_COINS": ["USDT", "USDC", "BTC", "ETH", "BNB"],
    "SUPPORTED_BLOCKCHAINS": {
        "USDT": ["BEP20", "ERC20", "TRC20", "SOL", "APTOS", "POLYGON"],
        "USDC": ["BEP20", "ERC20", "TRC20", "SOL", "APTOS", "POLYGON"],
        "BTC": ["Bitcoin"],
        "ETH": ["ERC20"],
        "BNB": ["BEP20", "ERC20"],
    },
    "MIN_DEPOSIT_AMOUNT": 100.0,  # USDT
    "MAX_DEPOSIT_AMOUNT": 1000000.0,  # USDT
}
