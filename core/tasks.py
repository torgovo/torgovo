"""
Celery tasks for core infrastructure operations.
"""

import logging

from celery import shared_task

logger = logging.getLogger("core.tasks")


@shared_task
def cleanup_old_audit_logs(days=90):
    """
    SCAL-2: Delete AuditLog rows older than N days.

    Runs monthly via Celery beat. Prevents unbounded table growth.
    The 90-day default balances compliance needs vs disk usage.
    """
    from datetime import timedelta

    from django.utils import timezone

    from core.models import AuditLog

    cutoff = timezone.now() - timedelta(days=days)
    deleted_count, _ = AuditLog.objects.filter(created_at__lt=cutoff).delete()
    logger.info(f"AuditLog cleanup: deleted {deleted_count} rows older than {days} days")
    return {"deleted_count": deleted_count, "cutoff_days": days}
