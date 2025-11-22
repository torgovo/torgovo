"""
Celery configuration for Torgovo Crypto Trading Platform
"""
import os
from celery import Celery
from django.conf import settings

# Set default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')

app = Celery('torgovo')

# Configure Celery using Django settings
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in all Django apps
app.autodiscover_tasks()

# Configure task routes
app.conf.task_routes = {
    'apps.bots.tasks.*': {'queue': 'bots'},
    'apps.payments.tasks.*': {'queue': 'payments'},
    'apps.webhooks.tasks.*': {'queue': 'webhooks'},
    'apps.notifications.tasks.*': {'queue': 'notifications'},
}

# Configure task priorities
app.conf.task_inherit_parent_priority = True
app.conf.task_default_priority = 5

# Configure task soft time limits
app.conf.task_soft_time_limit = 300  # 5 minutes
app.conf.task_time_limit = 600       # 10 minutes

# Configure worker settings
app.conf.worker_prefetch_multiplier = 1
app.conf.task_acks_late = True

# Schedule periodic tasks
app.conf.beat_schedule = {
    'update-cryptocurrency-prices': {
        'task': 'apps.bots.tasks.update_cryptocurrency_prices',
        'schedule': 60.0,  # Every minute
    },
    'process-expired-webhooks': {
        'task': 'apps.webhooks.tasks.process_expired_webhooks',
        'schedule': 300.0,  # Every 5 minutes
    },
    'update-bot-performance-stats': {
        'task': 'apps.bots.tasks.update_bot_performance_stats',
        'schedule': 3600.0,  # Every hour
    },
    'check-pending-deposits': {
        'task': 'apps.payments.tasks.check_pending_deposits',
        'schedule': 600.0,  # Every 10 minutes
    },
    'send-daily-reports': {
        'task': 'apps.notifications.tasks.send_daily_reports',
        'schedule': 86400.0,  # Every day at midnight
        'options': {'queue': 'notifications'},
    },
}