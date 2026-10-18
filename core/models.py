"""
Abstract base models for Torgovo Crypto Trading Platform
"""

import uuid
from functools import lru_cache

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


class SoftDeleteQuerySet(models.QuerySet):
    """QuerySet that soft-deletes instead of SQL DELETE."""

    def delete(self):
        """Soft-delete all records in this queryset."""
        return self.update(is_deleted=True, deleted_at=timezone.now())

    def hard_delete(self):
        """Actually delete records from the database."""
        return super().delete()

    def active(self):
        """Filter to non-deleted records."""
        return self.filter(is_deleted=False)

    def deleted(self):
        """Filter to soft-deleted records."""
        return self.filter(is_deleted=True)


class SoftDeleteManager(models.Manager):
    """Manager that defaults to active (non-deleted) records."""

    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).filter(is_deleted=False)

    def all_with_deleted(self):
        """Return all records including soft-deleted."""
        return SoftDeleteQuerySet(self.model, using=self._db)

    def deleted_only(self):
        """Return only soft-deleted records."""
        return SoftDeleteQuerySet(self.model, using=self._db).filter(is_deleted=True)


class SoftDeleteModel(TimeStampedModel):
    """
    Abstract model with soft delete functionality.

    FIN-2: Fixed to prevent two bugs:
    1. QuerySet.delete() now soft-deletes instead of SQL DELETE
    2. post_delete signal is NOT fired on soft delete (was misleading handlers
       into thinking the record was actually removed)
    """

    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = SoftDeleteManager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        """Soft delete — sets is_deleted and deleted_at, no signal fired."""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_deleted", "deleted_at"])

    def hard_delete(self, using=None, keep_parents=False):
        """Actually delete the record from the database."""
        super().delete(using=using, keep_parents=keep_parents)

    def restore(self):
        """Restore a soft-deleted model."""
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=["is_deleted", "deleted_at"])


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

    # G5 / FR A7 referral rewards config (admin-editable; NO hard-coded
    # business values in code — services/referral_rewards.get_referral_config()
    # merges these keys over the built-in defaults):
    #   {"commission_pct": 10, "referee_discount_pct": 15, "payout_minimum_usd": 50}
    referral_config = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Referral rewards settings: commission_pct, referee_discount_pct, "
            "payout_minimum_usd (empty dict = use defaults)"
        ),
    )

    class Meta:
        verbose_name = "Site Configuration"
        verbose_name_plural = "Site Configuration"
        db_table = "core_site_config"

    def __str__(self):
        return "Site Configuration"

    @classmethod
    @lru_cache(maxsize=1)
    def get(cls):
        """Get or create the singleton SiteConfig row.

        SCAL-1: Cached via lru_cache to avoid a DB hit on every call.
        Cache is cleared in save() when the admin updates plan_limits.
        """
        obj, _ = cls.objects.get_or_create(pk=1, defaults={"plan_limits": {}})
        return obj

    def save(self, *args, **kwargs):
        """Override save to invalidate the cached singleton."""
        super().save(*args, **kwargs)
        SiteConfig.get.cache_clear()

    def get_plan_limit(self, plan: str, default: int = 3) -> int:
        """Get bot limit for a plan, with built-in defaults as fallback.

        FR A2: a Model C SubscriptionPlan row (seeded, admin-editable) is
        authoritative for its slug — consulted BEFORE the legacy JSON so an
        admin edit on the row propagates to every profile recompute via
        User.save(). Deliberately not filtered on is_active: deactivation
        gates sales, it must not silently loosen limits for existing holders.
        """
        from apps.payments.models import SubscriptionPlan

        row = (
            SubscriptionPlan.objects.filter(slug=plan)
            .values_list("max_bots_allowed", flat=True)
            .first()
        )
        if row is not None:
            return row
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
