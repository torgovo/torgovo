"""
Production settings for Torgovo Crypto Trading Platform
"""

from decouple import config

from .base import *  # noqa: F403

# Security settings for production
DEBUG = False
SECRET_KEY = config("DJANGO_SECRET_KEY")

ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS", default="", cast=lambda v: [s.strip() for s in v.split(",")]
)

# HTTPS and Security
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
# Required when sitting behind nginx terminating TLS — Django then knows
# the original request was HTTPS.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

# CSRF trusted origins must be set when running behind a proxy; populated
# from env so it lines up with the public domain.
CSRF_TRUSTED_ORIGINS = config(
    "CSRF_TRUSTED_ORIGINS",
    default="",
    cast=lambda v: [s.strip() for s in v.split(",") if s.strip()],
)

# CORS configuration
CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS", default="", cast=lambda v: [s.strip() for s in v.split(",")]
)
CORS_ALLOW_CREDENTIALS = True

# Frontend URL for verification/password-reset links
FRONTEND_URL = config("FRONTEND_URL", default="http://localhost:3000")

# Email configuration for production
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = config("EMAIL_HOST", default="smtp.gmail.com")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="noreply@torgovo.com")

# Logging for production — extend base config
LOGGING["handlers"]["error_file"] = {  # noqa: F405
    "level": "ERROR",
    "class": "logging.handlers.RotatingFileHandler",
    "filename": BASE_DIR / "logs" / "django_errors.log",  # noqa: F405
    "maxBytes": 1024 * 1024 * 15,
    "backupCount": 10,
    "formatter": "verbose",
    "filters": ["cred_redact"],
}
LOGGING["handlers"]["trading_file"] = {  # noqa: F405
    "level": "INFO",
    "class": "logging.handlers.RotatingFileHandler",
    "filename": BASE_DIR / "logs" / "trading.log",  # noqa: F405
    "maxBytes": 1024 * 1024 * 15,
    "backupCount": 20,
    "formatter": "verbose",
    "filters": ["cred_redact"],
}
LOGGING["root"]["handlers"] = ["file"]  # noqa: F405
LOGGING["loggers"]["django"]["handlers"] = ["file", "error_file"]  # noqa: F405
LOGGING["loggers"]["apps"]["handlers"] = ["file", "error_file"]  # noqa: F405
LOGGING["loggers"]["trading"]["handlers"] = ["trading_file", "error_file"]  # noqa: F405

# Structured JSON logging for production (item #2)
LOGGING["handlers"]["json_file"] = {  # noqa: F405
    "level": "INFO",
    "class": "logging.handlers.RotatingFileHandler",
    "filename": BASE_DIR / "logs" / "django-json.log",  # noqa: F405
    "maxBytes": 1024 * 1024 * 15,
    "backupCount": 10,
    "formatter": "json",
    "filters": ["cred_redact", "request_id"],
}
# Route apps + trading logs to JSON file as well
LOGGING["loggers"]["apps"]["handlers"].append("json_file")  # noqa: F405
LOGGING["loggers"]["trading"]["handlers"].append("json_file")  # noqa: F405

# Cache for production
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": config("REDIS_URL", default="redis://127.0.0.1:6379/1"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "SOCKET_CONNECT_TIMEOUT": 5,
            "SOCKET_TIMEOUT": 5,
            "RETRY_ON_TIMEOUT": True,
            "MAX_CONNECTIONS": 1000,
            "CONNECTION_POOL_KWARGS": {
                "max_connections": 500,
                "retry_on_timeout": True,
            },
        },
    }
}

# Database connection pool for production
DATABASES["default"].update(  # noqa: F405
    {
        "CONN_MAX_AGE": 60,
    }
)
DATABASES["default"]["OPTIONS"] = {  # noqa: F405
    "connect_timeout": 60,
}
# Celery for production
CELERY_BROKER_URL = config("CELERY_BROKER_URL", default="redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = config("CELERY_RESULT_BACKEND", default="redis://127.0.0.1:6379/0")
CELERY_WORKER_CONCURRENCY = config("CELERY_WORKER_CONCURRENCY", default=4, cast=int)
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_ACKS_LATE = True

# Static files for production
STATIC_ROOT = BASE_DIR / "staticfiles"  # noqa: F405
MEDIA_ROOT = BASE_DIR / "media"  # noqa: F405

# Monitoring and Error Tracking
SENTRY_DSN = config("SENTRY_DSN", default="")

if SENTRY_DSN and SENTRY_DSN.strip() and SENTRY_DSN.startswith("http"):
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            DjangoIntegration(
                transaction_style="url",
                middleware_spans=True,
                signals_spans=True,
            ),
            CeleryIntegration(
                monitor_beat_tasks=True,
                propagate_traces=True,
            ),
        ],
        traces_sample_rate=0.1,
        send_default_pii=False,
        environment="production",
    )

# Database backup configuration (item #6)
# Uses django-dbbackup for automated backups to local/S3 storage.
# Run: python manage.py dbbackup           # backup to BACKUP_STORAGE_DIR
# Run: python manage.py dbrestore          # restore from latest backup
# Schedule via Celery beat or cron for automated daily backups.
DBBACKUP_STORAGE = config("DBBACKUP_STORAGE", default="django.core.files.storage.FileSystemStorage")
DBBACKUP_STORAGE_OPTIONS = {
    "location": config("BACKUP_STORAGE_DIR", default=str(BASE_DIR / "backups")),  # noqa: F405
}
DBBACKUP_TEMPLATE_NAME = "torgovo_{datetime}.{extension}"
DBBACKUP_FILENAME_TEMPLATE = "torgovo_{datetime}.{extension}"
# Backup retention: keep last 30 daily backups
DBBACKUP_CLEANUP_KEEP = 30
