"""Tests for core infrastructure tasks."""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from core.models import AuditLog
from core.tasks import cleanup_old_audit_logs

User = get_user_model()

pytestmark = pytest.mark.django_db


class TestCleanupOldAuditLogs:
    """SCAL-2: Tests for the AuditLog cleanup task."""

    def _create_old_log(self, user, days_old=100):
        """Create an AuditLog with a backdated created_at."""
        log = AuditLog.objects.create(
            user=user,
            action="login",
            resource_type="auth",
            description="Old login",
        )
        # auto_now_add ignores the kwarg — update directly
        AuditLog.objects.filter(pk=log.pk).update(
            created_at=timezone.now() - timedelta(days=days_old)
        )
        return log

    def test_deletes_old_logs(self):
        user = User.objects.create_user(
            username="old_log_user", email="old@test.com", password="pass"
        )
        old_log = self._create_old_log(user, days_old=100)
        recent_log = AuditLog.objects.create(
            user=user,
            action="login",
            resource_type="auth",
            description="Recent login",
        )

        result = cleanup_old_audit_logs(days=90)

        assert result["deleted_count"] == 1
        assert not AuditLog.objects.filter(pk=old_log.pk).exists()
        assert AuditLog.objects.filter(pk=recent_log.pk).exists()

    def test_preserves_logs_within_retention(self):
        user = User.objects.create_user(
            username="recent_log_user", email="recent@test.com", password="pass"
        )
        log = AuditLog.objects.create(
            user=user,
            action="trade",
            resource_type="order",
            description="Recent trade",
        )

        result = cleanup_old_audit_logs(days=90)

        assert result["deleted_count"] == 0
        assert AuditLog.objects.filter(pk=log.pk).exists()

    def test_custom_days_parameter(self):
        user = User.objects.create_user(
            username="custom_days_user", email="custom@test.com", password="pass"
        )
        log_30d = self._create_old_log(user, days_old=30)

        result = cleanup_old_audit_logs(days=20)

        assert result["deleted_count"] == 1
        assert not AuditLog.objects.filter(pk=log_30d.pk).exists()
