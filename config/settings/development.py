"""
Development settings for Torgovo Crypto Trading Platform
"""
from .base import *
from decouple import config
import logging
from logging import StreamHandler
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime
import pytz

# ==================== DEBUG TOOLS ====================
# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('DJANGO_SECRET_KEY', default='django-insecure-DEV-ONLY-do-not-use-in-production-' + 'x'*32)


DEBUG = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '0.0.0.0']


# AUTH_USER_MODEL = 'bot.User'


# Only add debug apps if they are installed
# We convert tuples/lists from base.py to list and append debug tools safely
INSTALLED_APPS = list(INSTALLED_APPS)
for app in ['debug_toolbar', 'django_extensions', 'silk']:
    if app not in INSTALLED_APPS:
        INSTALLED_APPS.append(app)

MIDDLEWARE = list(MIDDLEWARE)
# Add debug toolbar and silk middleware safely
if 'silk' in INSTALLED_APPS and 'silk.middleware.SilkyMiddleware' not in MIDDLEWARE:
    MIDDLEWARE.append('silk.middleware.SilkyMiddleware')
if 'debug_toolbar' in INSTALLED_APPS and 'debug_toolbar.middleware.DebugToolbarMiddleware' not in MIDDLEWARE:
    MIDDLEWARE.append('debug_toolbar.middleware.DebugToolbarMiddleware')



# Debug Toolbar settings
INTERNAL_IPS = ['127.0.0.1', 'localhost', '0.0.0.0']
DEBUG_TOOLBAR_CONFIG = {
    'SHOW_TOOLBAR_CALLBACK': lambda request: DEBUG,
    'INTERCEPT_REDIRECTS': False,
}

# Silk settings (API Profiling)
SILKY_PYTHON_PROFILER = True
SILKY_PYTHON_PROFILER_BINARY = True
SILKY_META = True
SILKY_MAX_RECORDED_REQUESTS = 1000
SILKY_MAX_RECORDED_REQUESTS_CHECK_PERCENT = 10

# Sentry SDK (Error Tracking) - Only init if DSN provided
SENTRY_DSN = config('SENTRY_DSN', default='')
if SENTRY_DSN and SENTRY_DSN.strip() and SENTRY_DSN.startswith('http'):
    import sentry_sdk
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        traces_sample_rate=1.0,
        profiles_sample_rate=1.0,
        environment="development",
        send_default_pii=True,
    )

# django-extensions settings
SHELL_PLUS_PRINT_SQL = True
GRAPH_MODELS = {
    'all_applications': True,
    'output': 'models.png',
}

# ==================== DATABASE ====================

# DATABASES['default'].update({
#     'NAME': config('DB_NAME', default='torgovo_dev'),
# })

# Custom formatter that generates fresh timestamp for each log entry
class TimezoneFormatter(logging.Formatter):
    """Custom formatter that uses timezone-aware datetime with microseconds"""

    def __init__(self, fmt=None, datefmt=None, tz_name='Asia/Karachi'):
        super().__init__(fmt, datefmt)
        self.tz = pytz.timezone(tz_name)

    def formatTime(self, record, datefmt=None):
        # Generate fresh timestamp with timezone and microseconds
        dt = datetime.now(self.tz)
        if datefmt:
            return dt.strftime(datefmt)
        else:
            return dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]  # Include milliseconds


LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {
            '()': 'config.settings.development.TimezoneFormatter',
            'format': '%(asctime)s - %(levelname)s - %(message)s',
        },
        'verbose': {
            '()': 'config.settings.development.TimezoneFormatter',
            'format': '%(asctime)s - %(levelname)s - %(name)s - %(process)d - %(thread)d - %(message)s',
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'Views': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'views.log',
            'maxBytes': 10485760,
            'backupCount': 5,
            'formatter': 'simple',
        },
        'BinanceBot': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'BinanceBot.log',
            'maxBytes': 10485760,
            'backupCount': 5,
            'formatter': 'simple',
        },
        'BybitBot': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'BybitBot.log',
            'maxBytes': 10485760,
            'backupCount': 5,
            'formatter': 'simple',
        },
        'KrakenSpotBot': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'KrakenSpotBot.log',
            'maxBytes': 10485760,
            'backupCount': 5,
            'formatter': 'simple',
        },
        'MexcBot': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'MexcBot.log',
            'maxBytes': 10485760,
            'backupCount': 5,
            'formatter': 'simple',
        },
        'BotManager': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'BotManager.log',
            'maxBytes': 10485760,
            'backupCount': 5,
            'formatter': 'simple',
        },
        'BybitArbitrageBot': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'BybotArbitrageBot.log',
            'maxBytes': 10485760,
            'backupCount': 5,
            'formatter': 'simple',
        },
        'error_file': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'error_file.log',
            'maxBytes': 10485760,
            'backupCount': 5,
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'Torgovo.Views': {
            'handlers': ['console', 'Views', 'error_file'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'Torgovo.BinanceBot': {
            'handlers': ['console', 'BinanceBot', 'error_file'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'Torgovo.BybitBot': {
            'handlers': ['console', 'BybitBot', 'error_file'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'Torgovo.KrakenSpotBot': {
            'handlers': ['console', 'KrakenSpotBot', 'error_file'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'Torgovo.MexcBot': {
            'handlers': ['console', 'MexcBot', 'error_file'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'Torgovo.BotManager': {
            'handlers': ['console', 'BotManager', 'error_file'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'Torgovo.BybitArbitrageBot': {
            'handlers': ['console', 'BybitArbitrageBot', 'error_file'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
}

# WSGI_APPLICATION is inherited from base.py, but we set it explicitly here just in case.
WSGI_APPLICATION = 'config.wsgi.application'


CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
]

# ==================== EMAIL ====================

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# ==================== LOGGING ====================

# # Console handler shows INFO and above (reduce noise)
# LOGGING['handlers']['console']['level'] = 'INFO'
# # Django internals at INFO to hide SQL queries, template loading, etc.
# LOGGING['loggers']['django']['level'] = 'INFO'
# # Your app loggers can stay at DEBUG for meaningful output
# LOGGING['loggers']['apps']['level'] = 'DEBUG'
# LOGGING['loggers']['trading']['level'] = 'DEBUG'


LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True
# ==================== CELERY ====================

CELERY_TASK_EAGER_PROPAGATES = True
CELERY_TASK_ALWAYS_EAGER = True

# ==================== SECURITY (Relaxed for dev) ====================

SECURE_SSL_REDIRECT = False
SECURE_BROWSER_XSS_FILTER = False
SECURE_CONTENT_TYPE_NOSNIFF = False
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False


# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]
