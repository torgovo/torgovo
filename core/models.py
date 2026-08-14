"""
Abstract base models for Torgovo Crypto Trading Platform
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    """
    Abstract base model with created_at and updated_at fields.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SoftDeleteModel(TimeStampedModel):
    """
    Abstract model with soft delete functionality.
    """

    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        """Soft delete the model and fire post_delete signal."""
        from django.db.models.signals import post_delete

        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save()
        # Fire post_delete signal for cleanup handlers
        post_delete.send(sender=self.__class__, instance=self)

    def hard_delete(self, using=None, keep_parents=False):
        """Actually delete the model from database."""
        super().delete(using=using, keep_parents=keep_parents)

    def restore(self):
        """Restore a soft-deleted model."""
        self.is_deleted = False
        self.deleted_at = None
        self.save()


class UserActivityLog(SoftDeleteModel):
    """
    Model to track user activities for audit purposes.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="activity_logs"
    )
    action = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    endpoint = models.CharField(max_length=255, blank=True)
    method = models.CharField(max_length=10, blank=True)
    status_code = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = "core_user_activity_log"
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["action", "created_at"]),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.action} at {self.created_at}"


class SystemConfiguration(TimeStampedModel):
    """
    Model for storing system-wide configuration.
    """

    key = models.CharField(max_length=100, unique=True)
    value = models.TextField()
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "core_system_configuration"

    def __str__(self):
        return f"{self.key} = {self.value}"


class SiteConfig(models.Model):
    """
    Singleton for admin-editable site-wide configuration.

    Usage:
        config = SiteConfig.get()
        limits = config.plan_limits

    Admin can edit plan_limits as JSON:
        {"free": 3, "basic": 10, "premium": 25, "enterprise": 100}
    """

    plan_limits = models.JSONField(
        default=dict,
        help_text=(
            "Bot limits per subscription plan, e.g. "
            "{'free': 3, 'basic': 10, 'premium': 25, 'enterprise': 100}"
        ),
    )

    class Meta:
        verbose_name = "Site Configuration"
        verbose_name_plural = "Site Configuration"
        db_table = "core_site_config"

    def __str__(self):
        return "Site Configuration"

    @classmethod
    def get(cls):
        """Get or create the singleton SiteConfig row."""
        obj, _ = cls.objects.get_or_create(pk=1, defaults={"plan_limits": {}})
        return obj

    def get_plan_limit(self, plan: str, default: int = 3) -> int:
        """Get bot limit for a plan, with built-in defaults as fallback."""
        defaults = {"free": 3, "basic": 10, "premium": 25, "enterprise": 100}
        plan_limits = {**defaults, **self.plan_limits}
        return plan_limits.get(plan, default)


class AuditLog(TimeStampedModel):
    """
    Model for tracking important system changes.
    """

    ACTION_CHOICES = [
        ("create", "Created"),
        ("update", "Updated"),
        ("delete", "Deleted"),
        ("login", "Login"),
        ("logout", "Logout"),
        ("password_change", "Password Changed"),
        ("api_key_change", "API Key Changed"),
        ("bot_start", "Bot Started"),
        ("bot_stop", "Bot Stopped"),
        ("deposit", "Deposit"),
        ("withdrawal", "Withdrawal"),
        ("trade", "Trade Executed"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    resource_type = models.CharField(max_length=50)
    resource_id = models.CharField(max_length=50, blank=True)
    old_values = models.JSONField(null=True, blank=True)
    new_values = models.JSONField(null=True, blank=True)
    description = models.TextField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    class Meta:
        db_table = "core_audit_log"
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["action", "created_at"]),
            models.Index(fields=["resource_type", "resource_id"]),
        ]

    def __str__(self):
        return f"{self.action} on {self.resource_type} at {self.created_at}"
