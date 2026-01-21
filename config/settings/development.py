"""
Development settings for Torgovo Crypto Trading Platform
"""
from .base import *

DEBUG = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '0.0.0.0']

# ==================== DEBUG TOOLS ====================

# Only add debug apps if they are installed
try:
    import debug_toolbar
    INSTALLED_APPS += ['debug_toolbar']
    # Debug Toolbar Middleware (must be at the top)
    MIDDLEWARE.insert(0, 'debug_toolbar.middleware.DebugToolbarMiddleware')
except ImportError:
    pass

try:
    import django_extensions
    INSTALLED_APPS += ['django_extensions']
except ImportError:
    pass

try:
    import silk
    INSTALLED_APPS += ['silk']
    # Silk Middleware (for API profiling)
    MIDDLEWARE += ['silk.middleware.SilkyMiddleware']
except ImportError:
    pass

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
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'postgres',
        'USER': 'postgres',
        'PASSWORD': '808507',
        'HOST': 'localhost',  # Or 127.0.0.1
        'PORT': '5432',       # Change if using different port
    }
}
# ==================== CORS ====================

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

# Console handler shows INFO and above (reduce noise)
LOGGING['handlers']['console']['level'] = 'INFO'
# Django internals at INFO to hide SQL queries, template loading, etc.
LOGGING['loggers']['django']['level'] = 'INFO'
# Your app loggers can stay at DEBUG for meaningful output
LOGGING['loggers']['apps']['level'] = 'DEBUG'
LOGGING['loggers']['trading']['level'] = 'DEBUG'

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