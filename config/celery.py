"""
Celery configuration for Torgovo Crypto Trading Platform
"""

import os

from celery import Celery
from celery.schedules import crontab

# Set default Django settings module
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

app = Celery("torgovo")

# Configure Celery using Django settings
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks in all Django apps
app.autodiscover_tasks()

# Configure task routes
app.conf.task_routes = {
    "apps.trading.tasks.*": {"queue": "trading"},
    "apps.payments.tasks.*": {"queue": "payments"},
}

# Configure task priorities
app.conf.task_inherit_parent_priority = True
app.conf.task_default_priority = 5

# Configure task soft time limits
app.conf.task_soft_time_limit = 300  # 5 minutes
app.conf.task_time_limit = 600  # 10 minutes

# Configure worker settings
app.conf.worker_prefetch_multiplier = 1
app.conf.task_acks_late = True

# Schedule periodic tasks
# NOTE: Only reference tasks that actually exist in apps/trading/tasks.py
app.conf.beat_schedule = {
    # Run all active grid/martingale bots every 60 seconds
    "run-active-bots": {
        "task": "apps.trading.tasks.check_all_active_bots",
        "schedule": 60.0,
    },
    # Check for stale bots (missed heartbeats) every 30 seconds — Phase 5
    # (CHG-5-3): matches the 30s cutoff and 10s heartbeat cadence.
    "check-stale-bots": {
        "task": "apps.trading.tasks.check_stale_bots",
        "schedule": 30.0,
    },
    # Distribute Quantum AI profits every 2 weeks (fortnightly)
    "distribute-quantum-ai-profits": {
        "task": "apps.trading.tasks.distribute_quantum_ai_profits",
        "schedule": 60 * 60 * 24 * 14,  # 14 days in seconds
    },
    "heartbeat-check": {
        "task": "apps.trading.tasks.heartbeat_check",
        "schedule": 60.0,  # Phase 5 (CHG-5-3): every 60 seconds
    },
    "reset-monthly-signals": {
        "task": "apps.trading.tasks.reset_monthly_signal_limits",
        "schedule": crontab(day_of_month=1, hour=0, minute=0),
    },
    "accrue-quantum-ai-profits": {
        "task": "apps.trading.tasks.accrue_quantum_ai_profits",
        "schedule": 3600.0,  # 1 hour
    },
    # FIN-1: Process investor payouts daily at 00:05 UTC (after profit
    # distribution at 00:00 UTC). Moves accrued_profit → user balance.
    "process-fund-payouts": {
        "task": "apps.investments.tasks.process_fund_payouts",
        "schedule": crontab(hour=0, minute=5),
    },
    # SCAL-2: Clean up old AuditLog rows on the 1st of each month at 02:00 UTC.
    # Default retention: 90 days. Pass {"days": N} to override.
    "cleanup-old-audit-logs": {
        "task": "core.tasks.cleanup_old_audit_logs",
        "schedule": crontab(day_of_month=1, hour=2, minute=0),
    },
}
